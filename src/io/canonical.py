"""io / canonical domain implementation."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from zju_scatt_interface._version import __version__
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.bulk.grid import BulkGrid, MultiBulkGrid
from zju_scatt_interface.bulk.models import BulkDataset, PopulationResult
from zju_scatt_interface.optics.models import BulkOptics

SCHEMA_NAME = "zju_scatt_bulk_optical_scheme"
SCHEMA_VERSION = "1.0"
MULTIDIMENSIONAL_SCHEMA_NAME = "zju_scatt_multidimensional_bulk_optics"
MULTIDIMENSIONAL_SCHEMA_VERSION = "1.0"
PHASE_ELEMENTS = {
    "p11": (0, 0),
    "p12": (0, 1),
    "p22": (1, 1),
    "p33": (2, 2),
    "p43": (3, 2),
    "p44": (3, 3),
}


@dataclass(frozen=True)
class OutputOptions:
    """Storage controls shared by the NetCDF4 and HDF5 writers."""

    compression: bool = True
    compression_level: int = 4
    shuffle: bool = True
    chunk_wavelength: Optional[int] = None
    atomic: bool = True

    def __post_init__(self) -> None:
        if not 0 <= int(self.compression_level) <= 9:
            raise ValueError("compression_level must be between 0 and 9")
        if self.chunk_wavelength is not None and int(self.chunk_wavelength) <= 0:
            raise ValueError("chunk_wavelength must be positive when provided")


@dataclass(frozen=True)
class OutputValidationReport:
    """Result of validating a written Phase-8 product."""

    path: Path
    format: str
    passed: bool
    components: tuple[str, ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def require_valid(self) -> "OutputValidationReport":
        if not self.passed:
            raise ValueError("invalid bulk optical output: " + "; ".join(self.errors))
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "format": self.format,
            "passed": self.passed,
            "components": list(self.components),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return repr(value)


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _normalize_format(path: Path, format_name: Optional[str]) -> str:
    value = (format_name or path.suffix.lstrip(".")).casefold()
    aliases = {
        "nc": "netcdf4",
        "netcdf": "netcdf4",
        "netcdf4": "netcdf4",
        "h5": "hdf5",
        "hdf": "hdf5",
        "hdf5": "hdf5",
    }
    if value not in aliases:
        raise ValueError("format must be 'netcdf4' or 'hdf5'")
    return aliases[value]


def _safe_group_name(name: str) -> str:
    value = str(name).strip()
    if not value:
        raise ValueError("component names cannot be empty")
    if "/" in value or value in {".", ".."}:
        raise ValueError(f"component name {value!r} cannot contain '/'")
    return value


def _dataset(
    data: object,
    dimensions: Sequence[str],
    units: str = "1",
    description: str = "",
) -> dict[str, object]:
    return {
        "data": data,
        "dimensions": list(dimensions),
        "units": units,
        "description": description,
    }


def _value(result: BulkOptics, name: str) -> float:
    value = getattr(result, name)
    return float("nan") if value is None else float(value)


def _phase_rows(result: BulkOptics, name: str) -> list[float]:
    matrix = result.phase_matrix
    if matrix is None:
        return []
    row, column = PHASE_ELEMENTS[name]
    return [float(item[row][column]) for item in matrix]


def _first_psd(results: Sequence[object]) -> Mapping[str, object]:
    for result in results:
        members = getattr(result, "members", ())
        for member in members:
            value = getattr(member.bulk, "metadata", {}).get("psd")
            if isinstance(value, Mapping):
                return value
    return {}


def _numeric_parameter_names(results: Sequence[object]) -> list[str]:
    names: set[str] = set()
    for result in results:
        for member in getattr(result, "members", ()):
            for name, value in member.parameters.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    names.add(str(name))
    return sorted(names)


def _parameter_dataset_name(name: str) -> str:
    from zju_scatt_interface.config.particles import normalize_parameter_name

    canonical = normalize_parameter_name(name)
    aliases = {
        "temperature": "temperature",
        "relative_humidity": "relative_humidity",
        "roundness": "ssph_n",
        "aspect_ratio": "ssph_asp",
        "refractive_index_real": "mr",
        "refractive_index_imaginary": "mi",
    }
    if canonical in aliases:
        return aliases[canonical]
    return re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_").casefold()


def _parameter_unit(name: str) -> str:
    return "K" if name in {"temperature_k", "temperature"} else "1"


def _optical_datasets(
    wavelengths: Sequence[float],
    results: Sequence[BulkOptics],
) -> dict[str, dict[str, object]]:
    datasets = {
        "wavelength": _dataset(list(wavelengths), ["wavelength"], "um", "Vacuum wavelength"),
        "beta_ext": _dataset(
            [_value(item, "extinction_coefficient") for item in results],
            ["wavelength"],
            "m^-1",
            "Bulk extinction coefficient",
        ),
        "beta_sca": _dataset(
            [_value(item, "scattering_coefficient") for item in results],
            ["wavelength"],
            "m^-1",
            "Bulk scattering coefficient",
        ),
        "beta_abs": _dataset(
            [_value(item, "absorption_coefficient") for item in results],
            ["wavelength"],
            "m^-1",
            "Bulk absorption coefficient",
        ),
        "ssa": _dataset(
            [_value(item, "single_scattering_albedo") for item in results],
            ["wavelength"],
            "1",
            "Single-scattering albedo",
        ),
        "g": _dataset(
            [_value(item, "asymmetry_factor") for item in results],
            ["wavelength"],
            "1",
            "Asymmetry factor",
        ),
        "number_concentration": _dataset(
            [float(item.number_concentration) for item in results],
            ["wavelength"],
            "cm-3",
            "Integrated particle number concentration",
        ),
    }
    phase_presence = [item.phase_matrix is not None for item in results]
    if any(phase_presence) and not all(phase_presence):
        raise ValueError("phase matrices must be present at every wavelength or omitted")
    if all(phase_presence):
        angles = [
            list(map(float, item.metadata.get("scattering_angles_degrees", []))) for item in results
        ]
        if not angles[0]:
            raise ValueError("phase matrices require scattering_angles_degrees metadata")
        if any(row != angles[0] for row in angles[1:]):
            raise ValueError("all wavelengths must use the same scattering-angle grid")
        if any(len(item.phase_matrix) != len(angles[0]) for item in results):
            raise ValueError("phase-matrix length does not match scattering-angle length")
        datasets["sca_angle"] = _dataset(angles[0], ["sca_angle"], "degree", "Scattering angle")
        for name in PHASE_ELEMENTS:
            datasets[name] = _dataset(
                [_phase_rows(item, name) for item in results],
                ["wavelength", "sca_angle"],
                "1",
                f"Bulk phase matrix element {name}",
            )
    return datasets


def _component_schema(
    name: str,
    wavelengths: Sequence[float],
    calculations: Sequence[object],
) -> dict[str, object]:
    if len(calculations) != len(wavelengths):
        raise ValueError(
            f"component {name!r} has {len(calculations)} results for {len(wavelengths)} wavelengths"
        )
    bulks = [result.bulk for result in calculations]
    datasets = _optical_datasets(wavelengths, bulks)
    psd = _first_psd(calculations)
    if psd:
        datasets["psd_size"] = _dataset(
            [float(value) for value in psd.get("size", [])],
            ["psd_size"],
            "um",
            "User-supplied particle radius",
        )
        datasets["psd_dndr"] = _dataset(
            [float(value) for value in psd.get("dndr", [])],
            ["psd_size"],
            "cm-3",
            "Number concentration in each represented size bin",
        )
    maximum_members = max(
        (len(getattr(result, "members", ())) for result in calculations), default=0
    )
    if maximum_members:
        datasets["ensemble_member"] = _dataset(
            list(range(maximum_members)),
            ["ensemble_member"],
            "1",
            "Zero-based shape ensemble index; identifies the corresponding shape parameters and shape_weight",
        )
        weights = []
        for result in calculations:
            members = getattr(result, "members", ())
            weights.append(
                [float(member.weight) for member in members]
                + [float("nan")] * (maximum_members - len(members))
            )
        datasets["shape_weight"] = _dataset(
            weights,
            ["wavelength", "ensemble_member"],
            "1",
            "Normalized shape/parameter ensemble weight",
        )
        for parameter in _numeric_parameter_names(calculations):
            rows = []
            for result in calculations:
                members = getattr(result, "members", ())
                rows.append(
                    [float(member.parameters.get(parameter, float("nan"))) for member in members]
                    + [float("nan")] * (maximum_members - len(members))
                )
            dataset_name = _parameter_dataset_name(parameter)
            if dataset_name in datasets:
                dataset_name = "source_" + dataset_name
            datasets[dataset_name] = _dataset(
                rows,
                ["wavelength", "ensemble_member"],
                _parameter_unit(parameter),
                f"Source/ensemble coordinate {parameter}",
            )
    particle_type = str(calculations[0].particle_type)
    metadata = bulks[0].metadata
    return {
        "attributes": {
            "component_name": name,
            "particle_type": particle_type,
            "size_definition": str(
                psd.get(
                    "size_definition",
                    metadata.get("size_definition", "volume_equivalent_sphere_radius"),
                )
            ),
            "psd_integration_mode": str(psd.get("integration_mode", "discrete_bin")),
            "psd_source": str(psd.get("source", "unknown")),
            "psd_metadata": _json(psd.get("metadata", {})),
            "coefficient_unit": "m^-1",
            "phase_matrix_convention": "random_orientation_six_independent_elements",
        },
        "datasets": datasets,
    }


@_registration_required
def build_bulk_output_schema(
    result: BulkDataset,
    *,
    scheme: object = None,
    database_version: str = "ZJU-SCATT-V1.0",
    source_manifest: object = None,
    title: Optional[str] = None,
) -> dict[str, object]:
    """Convert a Phase-7 result into the format-neutral Phase-8 schema."""

    if not isinstance(result, BulkDataset):
        raise TypeError("result must be a BulkDataset")
    if not result.wavelengths_um:
        raise ValueError("at least one wavelength is required")
    if not result.components:
        raise ValueError("at least one particle component is required")
    components: dict[str, object] = {}
    for name, calculations in result.components.items():
        group_name = _safe_group_name(name)
        if group_name in components:
            raise ValueError(f"duplicate output component name {group_name!r}")
        components[group_name] = _component_schema(group_name, result.wavelengths_um, calculations)
    if result.mixture is not None:
        if len(result.mixture) != len(result.wavelengths_um):
            raise ValueError("mixture result count must match wavelength count")
        components["mixture"] = {
            "attributes": {
                "component_name": "mixture",
                "particle_type": "external_mixture",
                "coefficient_unit": "m^-1",
                "phase_matrix_convention": "random_orientation_six_independent_elements",
            },
            "datasets": _optical_datasets(result.wavelengths_um, result.mixture),
        }
    created = datetime.now(timezone.utc).isoformat()
    normalized_scheme = (
        scheme.to_dict() if scheme is not None and hasattr(scheme, "to_dict") else scheme
    )
    dependency_plan = (
        result.dependency_plan.to_dict()
        if result.dependency_plan is not None and hasattr(result.dependency_plan, "to_dict")
        else result.dependency_plan
    )
    return {
        "attributes": {
            "title": title or result.name,
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "Conventions": "CF-1.10",
            "source": "ZJU-SCATT Interface",
            "interface_version": __version__,
            "database_version": database_version,
            "created_utc": created,
            "history": f"{created}: generated by zju-scatt-interface {__version__}",
            "normalized_scheme": _json(normalized_scheme),
            "source_manifest": _json(source_manifest),
            "dependency_plan": _json(dependency_plan),
        },
        "datasets": {},
        "components": components,
    }


def _reshape_grid(values: Sequence[object], shape: Sequence[int]) -> object:
    if not shape:
        if len(values) != 1:
            raise ValueError("scalar grid requires exactly one value")
        return values[0]
    expected = math.prod(shape)
    if len(values) != expected:
        raise ValueError(f"grid shape {tuple(shape)} requires {expected} values, got {len(values)}")
    if len(shape) == 1:
        return list(values)
    block = math.prod(shape[1:])
    return [
        _reshape_grid(values[index * block : (index + 1) * block], shape[1:])
        for index in range(shape[0])
    ]


def _grid_component_schema(result: BulkGrid) -> dict[str, object]:
    calculations = result.calculations
    dimensions = [_parameter_dataset_name(dimension.name) for dimension in result.dimensions]
    shape = result.shape
    bulks = [calculation.bulk for calculation in calculations]
    datasets: dict[str, dict[str, object]] = {}
    for dimension in result.dimensions:
        datasets[_parameter_dataset_name(dimension.name)] = _dataset(
            list(dimension.coordinates),
            [_parameter_dataset_name(dimension.name)],
            dimension.unit,
            dimension.description or f"Bulk grid coordinate {dimension.name}",
        )

    def grid_values(name: str) -> object:
        return _reshape_grid([_value(bulk, name) for bulk in bulks], shape)

    for name, attribute, unit, description in (
        ("beta_ext", "extinction_coefficient", "m^-1", "Bulk extinction coefficient"),
        ("beta_sca", "scattering_coefficient", "m^-1", "Bulk scattering coefficient"),
        ("beta_abs", "absorption_coefficient", "m^-1", "Bulk absorption coefficient"),
        ("ssa", "single_scattering_albedo", "1", "Single-scattering albedo"),
        ("g", "asymmetry_factor", "1", "Asymmetry factor"),
    ):
        datasets[name] = _dataset(grid_values(attribute), dimensions, unit, description)
    datasets["number_concentration"] = _dataset(
        _reshape_grid([float(bulk.number_concentration) for bulk in bulks], shape),
        dimensions,
        "cm-3",
        "Integrated particle number concentration",
    )
    psd = _first_psd(calculations)
    if psd:
        datasets["psd_size"] = _dataset(
            [float(value) for value in psd.get("size", [])],
            ["psd_size"],
            "um",
            "User-supplied particle radius",
        )
        datasets["psd_dndr"] = _dataset(
            [float(value) for value in psd.get("dndr", [])],
            ["psd_size"],
            "cm-3",
            "Number concentration in each represented size bin",
        )
    phase_presence = [bulk.phase_matrix is not None for bulk in bulks]
    if any(phase_presence) and not all(phase_presence):
        raise ValueError("phase matrices must be present at every grid point or omitted")
    if all(phase_presence):
        angles = [
            list(map(float, bulk.metadata.get("scattering_angles_degrees", []))) for bulk in bulks
        ]
        if not angles[0] or any(value != angles[0] for value in angles[1:]):
            raise ValueError("all grid points must use one scattering-angle grid")
        datasets["sca_angle"] = _dataset(angles[0], ["sca_angle"], "degree", "Scattering angle")
        for name in PHASE_ELEMENTS:
            datasets[name] = _dataset(
                _reshape_grid([_phase_rows(bulk, name) for bulk in bulks], shape),
                [*dimensions, "sca_angle"],
                "1",
                f"Bulk phase matrix element {name}",
            )
    wavelength_dimension = next(
        _parameter_dataset_name(dimension.name)
        for dimension in result.dimensions
        if dimension.parameter in {"wavelength", "wavelength_um"}
    )
    return {
        "attributes": {
            "component_name": result.name,
            "particle_type": result.particle_type,
            "dimension_names": _json(dimensions),
            "dimension_shape": _json(list(shape)),
            "wavelength_dimension": wavelength_dimension,
            "size_definition": str(
                psd.get(
                    "size_definition",
                    bulks[0].metadata.get("size_definition", "volume_equivalent_sphere_radius"),
                )
            ),
            "coefficient_unit": "m^-1",
            "phase_matrix_convention": "random_orientation_six_independent_elements",
        },
        "datasets": datasets,
    }


@_registration_required
def build_multidimensional_bulk_output_schema(
    result: Union[BulkGrid, MultiBulkGrid],
    *,
    scheme: object = None,
    database_version: str = "ZJU-SCATT-V1.0",
    source_manifest: object = None,
    title: Optional[str] = None,
) -> dict[str, object]:
    """Build a format-neutral schema retaining each declared bulk dimension."""

    if isinstance(result, BulkGrid):
        name = result.name
        components = {result.name: result}
    elif isinstance(result, MultiBulkGrid):
        name = result.name
        components = dict(result.components)
    else:
        raise TypeError("result must be BulkGrid or MultiBulkGrid")
    created = datetime.now(timezone.utc).isoformat()
    normalized_scheme = (
        scheme.to_dict() if scheme is not None and hasattr(scheme, "to_dict") else scheme
    )
    return {
        "attributes": {
            "title": title or name,
            "schema_name": MULTIDIMENSIONAL_SCHEMA_NAME,
            "schema_version": MULTIDIMENSIONAL_SCHEMA_VERSION,
            "Conventions": "CF-1.10",
            "source": "ZJU-SCATT Interface",
            "interface_version": __version__,
            "database_version": database_version,
            "created_utc": created,
            "history": f"{created}: generated by zju-scatt-interface {__version__}",
            "normalized_scheme": _json(normalized_scheme),
            "source_manifest": _json(source_manifest),
        },
        "datasets": {},
        "components": {
            _safe_group_name(component_name): _grid_component_schema(component)
            for component_name, component in components.items()
        },
    }


def _optics_dataset(
    wavelengths_um: Sequence[float],
    component_results: Mapping[str, Sequence[BulkOptics]],
    title: str,
) -> BulkDataset:
    from zju_scatt_interface.bulk.models import PopulationResult
    from zju_scatt_interface.bulk.quality import BulkQualityReport

    wavelengths = tuple(float(value) for value in wavelengths_um)
    components = {}
    for name, bulks in component_results.items():
        calculations = []
        for wavelength, bulk in zip(wavelengths, bulks):
            qa = BulkQualityReport(True, {}, {})
            calculations.append(
                PopulationResult(
                    particle_type=str(bulk.metadata.get("particle_type", name)),
                    wavelength_um=wavelength,
                    bulk=bulk,
                    qa=qa,
                    members=(),
                    ensemble={},
                )
            )
        components[name] = tuple(calculations)
    return BulkDataset(title, wavelengths, components)


def _dimensions(datasets: Mapping[str, Mapping[str, object]]) -> dict[str, int]:
    dimensions: dict[str, int] = {}
    for variable in datasets.values():
        data = variable["data"]
        shape = getattr(data, "shape", None)
        if shape is None:
            shape = _shape(data)
        for name, length in zip(variable["dimensions"], shape):
            previous = dimensions.setdefault(str(name), int(length))
            if previous != int(length):
                raise ValueError(f"inconsistent dimension {name!r}: {previous} versus {length}")
    return dimensions


def _shape(value: object) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)):
        return ()
    try:
        length = len(value)  # type: ignore[arg-type]
    except TypeError:
        return ()
    if length == 0:
        return (0,)
    return (length,) + _shape(value[0])  # type: ignore[index]


def _first_data_value(value: object) -> object:
    while isinstance(value, (list, tuple)) and value:
        value = value[0]
    return value


def _chunks(
    dimensions: Sequence[str],
    shape: Sequence[int],
    options: OutputOptions,
) -> Optional[tuple[int, ...]]:
    if options.chunk_wavelength is None or not dimensions:
        return None
    return tuple(
        min(int(length), int(options.chunk_wavelength)) if name == "wavelength" else int(length)
        for name, length in zip(dimensions, shape)
    )


def _netcdf_write_schema(path: Path, schema: Mapping[str, object], options: OutputOptions) -> None:
    try:
        from netCDF4 import Dataset
    except ImportError as exc:
        raise RuntimeError(
            "NetCDF output requires netCDF4; install zju-scatt-interface[netcdf]"
        ) from exc

    def write_container(container, content):
        datasets = content["datasets"]
        for name, length in _dimensions(datasets).items():
            container.createDimension(name, length)
        for key, value in content.get("attributes", {}).items():
            container.setncattr(key, value)
        for name, spec in datasets.items():
            data = spec["data"]
            dimensions = tuple(spec["dimensions"])
            is_string = isinstance(_first_data_value(data), str)
            kwargs = {}
            if options.compression and not is_string:
                kwargs = {
                    "zlib": True,
                    "complevel": options.compression_level,
                    "shuffle": options.shuffle,
                }
            chunks = _chunks(dimensions, _shape(data), options)
            if chunks is not None and not is_string:
                kwargs["chunksizes"] = chunks
            variable = container.createVariable(
                name,
                str
                if is_string
                else (
                    "i4"
                    if name == "ensemble_member"
                    else "i1"
                    if name.endswith("_passed")
                    else "f8"
                ),
                dimensions,
                fill_value=None
                if is_string
                else (
                    False
                    if name == "ensemble_member"
                    else None
                    if name.endswith("_passed")
                    else float("nan")
                ),
                **kwargs,
            )
            variable.setncattr("units", spec["units"])
            if spec["description"]:
                variable.setncattr("description", spec["description"])
            if is_string:
                import numpy as np

                variable[:] = np.asarray(data, dtype=object)
            else:
                variable[:] = data

    with Dataset(path, "w", format="NETCDF4") as handle:
        write_container(handle, schema)
        for name, component in schema["components"].items():
            write_container(handle.createGroup(name), component)


def _hdf5_write_schema(path: Path, schema: Mapping[str, object], options: OutputOptions) -> None:
    try:
        import h5py
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "HDF5 output requires h5py; install zju-scatt-interface[netcdf]"
        ) from exc

    def write_container(container, content):
        for key, value in content.get("attributes", {}).items():
            container.attrs[key] = value
        for name, spec in content["datasets"].items():
            data = spec["data"]
            is_string = isinstance(_first_data_value(data), str)
            array = (
                np.asarray(data, dtype=h5py.string_dtype("utf-8"))
                if is_string
                else np.asarray(
                    data,
                    dtype="i4"
                    if name == "ensemble_member"
                    else "i1"
                    if name.endswith("_passed")
                    else "f8",
                )
            )
            kwargs = {}
            if options.compression and array.size and not is_string:
                kwargs = {
                    "compression": "gzip",
                    "compression_opts": options.compression_level,
                    "shuffle": options.shuffle,
                }
            chunks = _chunks(spec["dimensions"], array.shape, options)
            if chunks is not None and array.size and not is_string:
                kwargs["chunks"] = chunks
            dataset = container.create_dataset(name, data=array, **kwargs)
            dataset.attrs["units"] = spec["units"]
            dataset.attrs["dimensions"] = _json(spec["dimensions"])
            if spec["description"]:
                dataset.attrs["description"] = spec["description"]

    with h5py.File(path, "w") as handle:
        write_container(handle, schema)
        for name, component in schema["components"].items():
            write_container(handle.create_group(name), component)


def _atomic_target(path: Path, options: OutputOptions) -> Path:
    if not options.atomic:
        return path
    return path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")


@_registration_required
def _write_dataset(
    path: Union[str, Path],
    result: BulkDataset,
    *,
    format: Optional[str] = None,
    scheme: object = None,
    database_version: str = "ZJU-SCATT-V1.0",
    source_manifest: object = None,
    title: Optional[str] = None,
    options: Optional[OutputOptions] = None,
) -> Path:
    """Atomically write one Phase-7 scheme result as NetCDF4 or HDF5."""

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    format_name = _normalize_format(target, format)
    controls = options or OutputOptions()
    schema = build_bulk_output_schema(
        result,
        scheme=scheme,
        database_version=database_version,
        source_manifest=source_manifest,
        title=title,
    )
    working = _atomic_target(target, controls)
    try:
        if format_name == "netcdf4":
            _netcdf_write_schema(working, schema, controls)
        else:
            _hdf5_write_schema(working, schema, controls)
        validate_file(working, format=format_name).require_valid()
        if working != target:
            os.replace(working, target)
    except BaseException:
        if working != target and working.is_file():
            working.unlink()
        raise
    return target


@_registration_required
def _write_grid(
    path: Union[str, Path],
    result: Union[BulkGrid, MultiBulkGrid],
    *,
    format: Optional[str] = None,
    scheme: object = None,
    database_version: str = "ZJU-SCATT-V1.0",
    source_manifest: object = None,
    title: Optional[str] = None,
    options: Optional[OutputOptions] = None,
) -> Path:
    """Write retained multidimensional particle grids as NetCDF4 or HDF5."""

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    format_name = _normalize_format(target, format)
    controls = options or OutputOptions()
    schema = build_multidimensional_bulk_output_schema(
        result,
        scheme=scheme,
        database_version=database_version,
        source_manifest=source_manifest,
        title=title,
    )
    working = _atomic_target(target, controls)
    try:
        if format_name == "netcdf4":
            _netcdf_write_schema(working, schema, controls)
        else:
            _hdf5_write_schema(working, schema, controls)
        validate_file(working, format=format_name).require_valid()
        if working != target:
            os.replace(working, target)
    except BaseException:
        if working != target and working.is_file():
            working.unlink()
        raise
    return target


def _single_component_result(
    calculations: Union[PopulationResult, Sequence[PopulationResult]],
    *,
    component_name: Optional[str] = None,
    title: Optional[str] = None,
) -> BulkDataset:
    values = (calculations,) if isinstance(calculations, PopulationResult) else tuple(calculations)
    if not values:
        raise ValueError("at least one bulk calculation result is required")
    if not all(isinstance(value, PopulationResult) for value in values):
        raise TypeError("calculations must contain PopulationResult objects")
    particle_types = {value.particle_type for value in values}
    if len(particle_types) != 1:
        raise ValueError("a single-component output cannot contain different particle types")
    wavelengths = tuple(float(value.wavelength_um) for value in values)
    if len(wavelengths) != len(set(wavelengths)):
        raise ValueError("bulk calculation wavelengths must be unique")
    name = component_name or values[0].particle_type
    return BulkDataset(
        name=title or f"{name} bulk optical properties",
        wavelengths_um=wavelengths,
        components={name: values},
    )


@_registration_required
def _write_population(
    path: Union[str, Path],
    calculations: Union[PopulationResult, Sequence[PopulationResult]],
    *,
    component_name: Optional[str] = None,
    format: Optional[str] = None,
    title: Optional[str] = None,
    database_version: str = "ZJU-SCATT-V1.0",
    source_manifest: object = None,
    options: Optional[OutputOptions] = None,
) -> Path:
    """Write one particle population independently as NetCDF4 or HDF5."""

    result = _single_component_result(
        calculations,
        component_name=component_name,
        title=title,
    )
    return _write_dataset(
        path,
        result,
        format=format,
        database_version=database_version,
        source_manifest=source_manifest,
        title=title,
        options=options,
    )


@_registration_required
def _write_optics(
    path: Union[str, Path],
    wavelengths_um: Sequence[float],
    bulk_results: Sequence[BulkOptics],
    *,
    component_name: str = "user_derived",
    format: Optional[str] = None,
    title: str = "ZJU-SCATT user-derived bulk optical properties",
    database_version: str = "ZJU-SCATT-V1.0",
    source_manifest: object = None,
    options: Optional[OutputOptions] = None,
) -> Path:
    """Write custom ``BulkOptics`` values as NetCDF4 or HDF5."""

    wavelengths = tuple(float(value) for value in wavelengths_um)
    bulks = tuple(bulk_results)
    if not wavelengths or len(wavelengths) != len(bulks):
        raise ValueError("wavelengths_um and bulk_results must have the same non-zero length")
    if not all(isinstance(value, BulkOptics) for value in bulks):
        raise TypeError("bulk_results must contain BulkOptics objects")
    result = _optics_dataset(wavelengths, {component_name: bulks}, title)
    return _write_dataset(
        path,
        result,
        format=format,
        database_version=database_version,
        source_manifest=source_manifest,
        title=title,
        options=options,
    )


def _plain(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "filled"):
        value = value.filled(float("nan"))
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@_registration_required
def read(path: Union[str, Path], *, format: Optional[str] = None) -> dict[str, object]:
    """Read either output format into one normalized inspection structure."""

    source = Path(path).expanduser().resolve()
    format_name = _normalize_format(source, format)
    if format_name == "netcdf4":
        try:
            from netCDF4 import Dataset
        except ImportError as exc:
            raise RuntimeError("reading NetCDF4 requires netCDF4") from exc

        def read_container(container):
            return {
                "attributes": {
                    name: _plain(container.getncattr(name)) for name in container.ncattrs()
                },
                "datasets": {
                    name: {
                        "data": _plain(variable[:]),
                        "dimensions": list(variable.dimensions),
                        "units": str(getattr(variable, "units", "1")),
                        "description": str(getattr(variable, "description", "")),
                    }
                    for name, variable in container.variables.items()
                },
            }

        with Dataset(source) as handle:
            content = read_container(handle)
            content["components"] = {
                name: read_container(group) for name, group in handle.groups.items()
            }
    else:
        try:
            import h5py
        except ImportError as exc:
            raise RuntimeError("reading HDF5 requires h5py") from exc

        def read_container(container):
            datasets = {}
            for name, dataset in container.items():
                if not isinstance(dataset, h5py.Dataset):
                    continue
                dimensions = json.loads(str(_plain(dataset.attrs.get("dimensions", "[]"))))
                datasets[name] = {
                    "data": _plain(dataset[()]),
                    "dimensions": dimensions,
                    "units": str(_plain(dataset.attrs.get("units", "1"))),
                    "description": str(_plain(dataset.attrs.get("description", ""))),
                }
            return {
                "attributes": {name: _plain(value) for name, value in container.attrs.items()},
                "datasets": datasets,
            }

        with h5py.File(source) as handle:
            content = read_container(handle)
            content["components"] = {
                name: read_container(group)
                for name, group in handle.items()
                if isinstance(group, h5py.Group)
            }
    content["format"] = format_name
    content["path"] = str(source)
    return content


def _all_finite_or_nan(values: object) -> bool:
    if isinstance(values, list):
        return all(_all_finite_or_nan(value) for value in values)
    if isinstance(values, (int, float)):
        return not math.isinf(float(values))
    return True


def _flatten_values(values: object) -> list[object]:
    if isinstance(values, list):
        return [item for value in values for item in _flatten_values(value)]
    return [values]


def _validate_multidimensional_content(
    source: Path,
    format_name: str,
    content: Mapping[str, object],
) -> OutputValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    attrs = content["attributes"]
    if attrs.get("schema_version") != MULTIDIMENSIONAL_SCHEMA_VERSION:
        errors.append("unsupported multidimensional schema_version")
    components = tuple(content["components"])
    if not components:
        errors.append("no multidimensional component groups are present")
    required = {
        "beta_ext": "m^-1",
        "beta_sca": "m^-1",
        "beta_abs": "m^-1",
        "ssa": "1",
        "g": "1",
        "number_concentration": "cm-3",
    }
    for name, component in content["components"].items():
        component_attrs = component["attributes"]
        try:
            dimensions = json.loads(component_attrs.get("dimension_names", "[]"))
            shape = tuple(
                int(value) for value in json.loads(component_attrs.get("dimension_shape", "[]"))
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            errors.append(f"{name}: invalid dimension metadata")
            continue
        if not dimensions or len(dimensions) != len(shape):
            errors.append(f"{name}: dimension names and shape are inconsistent")
            continue
        datasets = component["datasets"]
        for dimension, length in zip(dimensions, shape):
            coordinate = datasets.get(dimension)
            if coordinate is None:
                errors.append(f"{name}: coordinate {dimension!r} is missing")
            elif coordinate["dimensions"] != [dimension] or len(coordinate["data"]) != length:
                errors.append(f"{name}: coordinate {dimension!r} shape is invalid")
        wavelength_dimension = component_attrs.get("wavelength_dimension")
        if wavelength_dimension not in dimensions:
            errors.append(f"{name}: wavelength dimension is invalid")
        elif datasets[wavelength_dimension]["units"] != "um":
            errors.append(f"{name}: wavelength coordinate unit must be um")
        for variable, unit in required.items():
            dataset = datasets.get(variable)
            if dataset is None:
                errors.append(f"{name}: missing required variable {variable}")
                continue
            if dataset["units"] != unit:
                errors.append(f"{name}: {variable} unit must be {unit}")
            if dataset["dimensions"] != dimensions or _shape(dataset["data"]) != shape:
                errors.append(f"{name}: {variable} grid shape is invalid")
            if not _all_finite_or_nan(dataset["data"]):
                errors.append(f"{name}: {variable} contains infinity")
        if all(variable in datasets for variable in ("beta_ext", "beta_sca", "beta_abs")):
            extinction = _flatten_values(datasets["beta_ext"]["data"])
            scattering = _flatten_values(datasets["beta_sca"]["data"])
            absorption = _flatten_values(datasets["beta_abs"]["data"])
            for index, (ext, sca, absorb) in enumerate(zip(extinction, scattering, absorption)):
                if any(math.isnan(float(value)) for value in (ext, sca, absorb)):
                    continue
                tolerance = max(1.0e-12, abs(float(ext)) * 1.0e-7)
                if abs(float(ext) - float(sca) - float(absorb)) > tolerance:
                    errors.append(f"{name}: extinction closure fails at flat grid index {index}")
        phase = [key in datasets for key in PHASE_ELEMENTS]
        if any(phase) and not all(phase):
            errors.append(f"{name}: phase-matrix variables are incomplete")
        if all(phase):
            if "sca_angle" not in datasets:
                errors.append(f"{name}: phase matrix lacks sca_angle")
            else:
                angle_count = len(datasets["sca_angle"]["data"])
                expected_shape = (*shape, angle_count)
                for variable in PHASE_ELEMENTS:
                    if _shape(datasets[variable]["data"]) != expected_shape:
                        errors.append(f"{name}: {variable} shape is invalid")
        if ("psd_size" in datasets) != ("psd_dndr" in datasets):
            errors.append(f"{name}: PSD size and dN/dr must occur together")
        if "psd_size" not in datasets:
            warnings.append(f"{name}: source PSD arrays are unavailable")
    return OutputValidationReport(
        source,
        format_name,
        not errors,
        components,
        tuple(errors),
        tuple(warnings),
    )


@_registration_required
def validate_file(
    path: Union[str, Path], *, format: Optional[str] = None
) -> OutputValidationReport:
    """Validate schema identity, shapes, units, flags, and optical closure."""

    source = Path(path).expanduser().resolve()
    format_name = _normalize_format(source, format)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        content = read(source, format=format_name)
    except Exception as exc:
        return OutputValidationReport(source, format_name, False, (), (f"cannot read file: {exc}",))
    attrs = content["attributes"]
    if attrs.get("schema_name") == MULTIDIMENSIONAL_SCHEMA_NAME:
        return _validate_multidimensional_content(source, format_name, content)
    if attrs.get("schema_name") != SCHEMA_NAME:
        errors.append("missing or invalid schema_name")
    if attrs.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    root_wavelength = content["datasets"].get("wavelength")
    if root_wavelength is not None:
        if root_wavelength["units"] != "um":
            errors.append("root wavelength unit must be um")
    reference_wavelengths = root_wavelength["data"] if root_wavelength is not None else None
    components = tuple(content["components"])
    if not components:
        errors.append("no component groups are present")
    required = {
        "wavelength": "um",
        "beta_ext": "m^-1",
        "beta_sca": "m^-1",
        "beta_abs": "m^-1",
        "ssa": "1",
        "g": "1",
        "number_concentration": "cm-3",
    }
    for name, component in content["components"].items():
        datasets = component["datasets"]
        local_wavelengths = datasets.get("wavelength", {}).get("data", [])
        if reference_wavelengths is None:
            reference_wavelengths = local_wavelengths
        elif local_wavelengths != reference_wavelengths:
            errors.append(f"{name}: component wavelength coordinates are inconsistent")
        wavelength_count = len(local_wavelengths)
        if not component["attributes"].get("particle_type"):
            errors.append(f"{name}: particle_type attribute is missing")
        for variable, unit in required.items():
            if variable not in datasets:
                errors.append(f"{name}: required variable {variable} is missing")
                continue
            if datasets[variable]["units"] != unit:
                errors.append(f"{name}: {variable} unit must be {unit}")
            if len(datasets[variable]["data"]) != wavelength_count:
                errors.append(f"{name}: {variable} wavelength length is invalid")
            if not _all_finite_or_nan(datasets[variable]["data"]):
                errors.append(f"{name}: {variable} contains infinity")
        if all(key in datasets for key in ("beta_ext", "beta_sca", "beta_abs")):
            for index, values in enumerate(
                zip(
                    datasets["beta_ext"]["data"],
                    datasets["beta_sca"]["data"],
                    datasets["beta_abs"]["data"],
                )
            ):
                ext, sca, absorb = map(float, values)
                if all(math.isfinite(value) for value in (ext, sca, absorb)):
                    tolerance = max(1.0e-12, abs(ext) * 1.0e-7)
                    if abs(ext - sca - absorb) > tolerance:
                        errors.append(
                            f"{name}: extinction closure fails at wavelength index {index}"
                        )
        phase = [key in datasets for key in PHASE_ELEMENTS]
        if any(phase) and not all(phase):
            errors.append(f"{name}: phase-matrix variables are incomplete")
        if all(phase):
            if "sca_angle" not in datasets:
                errors.append(f"{name}: phase matrix lacks sca_angle")
            else:
                angle_count = len(datasets["sca_angle"]["data"])
                for variable in PHASE_ELEMENTS:
                    rows = datasets[variable]["data"]
                    if len(rows) != wavelength_count or any(
                        len(row) != angle_count for row in rows
                    ):
                        errors.append(f"{name}: {variable} shape is invalid")
        if ("psd_size" in datasets) != ("psd_dndr" in datasets):
            errors.append(f"{name}: PSD size and dN/dr must occur together")
        if name != "mixture" and "psd_size" not in datasets:
            warnings.append(f"{name}: source PSD arrays are unavailable")
    return OutputValidationReport(
        source,
        format_name,
        not errors,
        components,
        tuple(errors),
        tuple(warnings),
    )
