"""optics / loading domain implementation."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional, Sequence, Union

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.errors import ScattError
from zju_scatt_interface.optics.models import SingleParticleOptics

SINGLE_OPTICS_SIZE_ALIASES = (
    "xsize_veq",
    "xsize_maxd",
    "size",
    "diameter",
    "radius",
    "reff",
    "effective_radius",
)


SINGLE_OPTICS_EXTINCTION_ALIASES = (
    "cext",
    "c_ext",
    "extinction_cross_section",
)


SINGLE_OPTICS_SCATTERING_ALIASES = (
    "csca",
    "c_sca",
    "scattering_cross_section",
)


SINGLE_OPTICS_ABSORPTION_ALIASES = (
    "cabs",
    "c_abs",
    "absorption_cross_section",
)


SINGLE_OPTICS_PROJECTED_AREA_ALIASES = (
    "proj_area",
    "projected_area",
    "projected_cross_section",
)


SINGLE_OPTICS_QEXT_ALIASES = ("qext", "q_ext", "extinction_efficiency")


SINGLE_OPTICS_QSCA_ALIASES = ("qsca", "q_sca", "scattering_efficiency")


SINGLE_OPTICS_QABS_ALIASES = ("qabs", "q_abs", "absorption_efficiency")


SINGLE_OPTICS_SSA_ALIASES = ("ssa", "single_scattering_albedo")


SINGLE_OPTICS_G_ALIASES = ("g", "asymmetry_factor", "asymmetry_parameter")


SINGLE_OPTICS_WAVELENGTH_ALIASES = ("wavelength", "wavelength_um", "wl")


SINGLE_OPTICS_ANGLE_ALIASES = ("sca_angle", "scattering_angle", "angle")


SINGLE_OPTICS_PHASE_ALIASES = {
    "p11": ("p11", "P11"),
    "p12": ("p12", "P12"),
    "p22": ("p22", "P22"),
    "p33": ("p33", "P33"),
    "p43": ("p43", "P43"),
    "p44": ("p44", "P44"),
}


def _normalize_dataset_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().casefold()).strip("_")


def _windows_long_path(path: Path) -> str:
    resolved = str(path.expanduser().resolve())
    if os.name == "nt" and len(resolved) >= 248 and not resolved.startswith("\\\\?\\"):
        if resolved.startswith("\\\\"):
            return "\\\\?\\UNC\\" + resolved[2:]
        return "\\\\?\\" + resolved
    return resolved


def _require_h5py() -> Any:
    try:
        import h5py
    except ImportError as exc:
        raise ScattError(
            "Reading ZJU-SCATT NetCDF files requires h5py. Install it with "
            "`python -m pip install h5py` or `python -m pip install zju-scatt[database-test]`."
        ) from exc
    return h5py


def _h5_dataset_names(handle: Any) -> dict[str, str]:
    names: dict[str, str] = {}

    def visit(name: str, obj: Any) -> None:
        if hasattr(obj, "shape"):
            names[_normalize_dataset_name(PurePosixPath(name).name)] = name

    handle.visititems(visit)
    return names


def _h5_read_dataset(
    handle: Any,
    names: Mapping[str, str],
    aliases: Sequence[str],
) -> Optional[Any]:
    for alias in aliases:
        normalized = _normalize_dataset_name(alias)
        if normalized in names:
            return handle[names[normalized]][()]
    return None


def _h5_find_dataset(
    handle: Any,
    names: Mapping[str, str],
    aliases: Sequence[str],
) -> Optional[Any]:
    for alias in aliases:
        normalized = _normalize_dataset_name(alias)
        if normalized in names:
            return handle[names[normalized]]
    return None


def _h5_dimension_names(dataset: Any) -> list[str]:
    dimensions: list[str] = []
    for axis, dimension in enumerate(dataset.dims):
        label = str(dimension.label or "").strip()
        keys = list(dimension.keys())
        name = label or (PurePosixPath(keys[0]).name if len(keys) == 1 else "")
        dimensions.append(name or f"axis_{axis}")
    return dimensions


def _coordinate_index(
    dimension: str,
    length: int,
    coordinate_indices: Mapping[str, int],
    label: str,
) -> int:
    normalized = _normalize_dataset_name(dimension)
    normalized_indices = {
        _normalize_dataset_name(name): int(index) for name, index in coordinate_indices.items()
    }
    if normalized in normalized_indices:
        index = normalized_indices[normalized]
    elif length == 1:
        index = 0
    else:
        raise ScattError(
            f"{label} has unresolved dimension {dimension!r} with {length} values. "
            f"Supply coordinate_indices={{'{dimension}': INDEX}}."
        )
    if index < 0 or index >= length:
        raise ScattError(f"Index {index} is outside dimension {dimension!r} with length {length}")
    return index


def _h5_selected_value(
    dataset: Any,
    *,
    retain_dimensions: Sequence[str],
    coordinate_indices: Mapping[str, int],
    label: str,
) -> Any:
    retained = {_normalize_dataset_name(name) for name in retain_dimensions}
    dimensions = _h5_dimension_names(dataset)
    selection: list[Any] = []
    for axis, dimension in enumerate(dimensions):
        if _normalize_dataset_name(dimension) in retained:
            selection.append(slice(None))
        else:
            selection.append(
                _coordinate_index(
                    dimension,
                    int(dataset.shape[axis]),
                    coordinate_indices,
                    label,
                )
            )
    return dataset[tuple(selection)] if selection else dataset[()]


def _size_dimension(dataset: Any) -> str:
    dimensions = _h5_dimension_names(dataset)
    candidates = [
        name
        for name in dimensions
        if _normalize_dataset_name(name)
        in {"xsize_maxd", "xsize_veq", "size", "radius", "diameter"}
    ]
    if candidates:
        return candidates[-1]
    if dataset.ndim == 1:
        dataset_name = _normalize_dataset_name(PurePosixPath(dataset.name).name)
        if dataset_name in {
            "xsize_maxd",
            "xsize_veq",
            "size",
            "radius",
            "diameter",
        }:
            return dataset_name
        return dimensions[0]
    raise ScattError(
        "Cannot identify the size dimension for dataset "
        f"{dataset.name!r}; dimensions are {dimensions}"
    )


def _dataset_to_float_list(value: Any, label: str, *, allow_nan: bool = False) -> list[float]:
    if value is None:
        raise ScattError(f"{label} dataset is missing")
    if hasattr(value, "reshape"):
        value = value.reshape(-1).tolist()
    elif not isinstance(value, (list, tuple)):
        value = [value]
    result: list[float] = []
    for item in value:
        number = float(item)
        if math.isnan(number) and allow_nan:
            result.append(number)
        elif math.isfinite(number):
            result.append(number)
        else:
            raise ScattError(f"{label} must be finite; got {item!r}")
    if not result:
        raise ScattError(f"{label} dataset is empty")
    return result


def _dataset_to_float_matrix(
    value: Any, label: str, *, allow_nan: bool = False
) -> list[list[float]]:
    if value is None:
        raise ScattError(f"{label} dataset is missing")
    if not hasattr(value, "shape") or len(value.shape) != 2:
        raise ScattError(f"{label} must be a 2-D size by angle dataset")
    return [_dataset_to_float_list(row, label, allow_nan=allow_nan) for row in value.tolist()]


def _h5_phase_matrix(
    handle: Any,
    names: Mapping[str, str],
    size_count: int,
    *,
    size_dimension: str,
    coordinate_indices: Mapping[str, int],
    allow_nan: bool = False,
) -> Optional[list[list[list[list[float]]]]]:
    phase_arrays: dict[str, list[list[float]]] = {}
    scaled_by_p11: set[str] = set()
    for name, aliases in SINGLE_OPTICS_PHASE_ALIASES.items():
        dataset = _h5_find_dataset(handle, names, aliases)
        if dataset is not None:
            dimensions = _h5_dimension_names(dataset)
            angle_dimensions = [
                dimension
                for dimension in dimensions
                if _normalize_dataset_name(dimension) in {"sca_angle", "scattering_angle", "angle"}
            ]
            if not angle_dimensions:
                raise ScattError(f"{name} has no recognizable scattering-angle dimension")
            value = _h5_selected_value(
                dataset,
                retain_dimensions=(size_dimension, angle_dimensions[-1]),
                coordinate_indices=coordinate_indices,
                label=name,
            )
            phase_arrays[name] = _dataset_to_float_matrix(value, name, allow_nan=allow_nan)
            description = dataset.attrs.get("description", "")
            if isinstance(description, bytes):
                description = description.decode("utf-8", errors="replace")
            normalized_description = str(description).strip().casefold()
            if name != "p11" and "scaled by p11" in normalized_description:
                scaled_by_p11.add(name)
    if "p11" not in phase_arrays:
        return None
    angle_count = len(phase_arrays["p11"][0])

    def value_or_zero(name: str, size_index: int, angle_index: int) -> float:
        values = phase_arrays.get(name)
        if values is None:
            return 0.0
        value = values[size_index][angle_index]
        if name in scaled_by_p11:
            value *= phase_arrays["p11"][size_index][angle_index]
        return value

    phase_by_size: list[list[list[list[float]]]] = []
    for size_index in range(size_count):
        angles: list[list[list[float]]] = []
        for angle_index in range(angle_count):
            p11 = value_or_zero("p11", size_index, angle_index)
            p12 = value_or_zero("p12", size_index, angle_index)
            p22 = value_or_zero("p22", size_index, angle_index)
            p33 = value_or_zero("p33", size_index, angle_index)
            p43 = value_or_zero("p43", size_index, angle_index)
            p44 = value_or_zero("p44", size_index, angle_index)
            angles.append(
                [
                    [p11, p12, 0.0, 0.0],
                    [p12, p22, 0.0, 0.0],
                    [0.0, 0.0, p33, -p43],
                    [0.0, 0.0, p43, p44],
                ]
            )
        phase_by_size.append(angles)
    return phase_by_size


@_registration_required
def load_single(
    path: Union[str, Path],
    *,
    include_phase_matrix: bool = False,
    size_dataset: Optional[str] = None,
    coordinate_indices: Optional[Mapping[str, int]] = None,
    cext_mode: str = "auto",
    wavelength_um: Optional[float] = None,
    allow_nan_asymmetry: bool = False,
) -> SingleParticleOptics:
    """Load one coordinate slice from a ZJU-SCATT L1 NetCDF file.

    L1 ``cext`` values are normally ``k^2 Cext``. In ``auto`` mode they are
    converted to physical ``m^2`` whenever the selected size coordinate is a
    dimensionless ``xsize_*`` parameter. Multidimensional environmental or
    shape coordinates must be selected explicitly with ``coordinate_indices``;
    only singleton dimensions default to index zero.
    """
    from zju_scatt_interface.access.metadata import extract_scatt_metadata
    from zju_scatt_interface.bulk.lowlevel import _finite_float
    from zju_scatt_interface.optics.models import SingleParticleOptics

    source = Path(path)
    indices = dict(coordinate_indices or {})
    mode = cext_mode.strip().casefold()
    if mode not in {"auto", "scaled_k2", "physical_um2", "physical_m2"}:
        raise ScattError("cext_mode must be 'auto', 'scaled_k2', 'physical_um2', or 'physical_m2'")
    metadata = extract_scatt_metadata(source.name)
    h5py = _require_h5py()
    with h5py.File(_windows_long_path(source), "r") as handle:
        names = _h5_dataset_names(handle)
        known_dimensions: set[str] = set()
        for dataset_path in names.values():
            dataset = handle[dataset_path]
            known_dimensions.update(
                _normalize_dataset_name(name)
                for name in _h5_dimension_names(dataset)
                if not name.startswith("axis_")
            )
        unknown_indices = sorted(
            name for name in indices if _normalize_dataset_name(name) not in known_dimensions
        )
        if unknown_indices:
            raise ScattError(
                "Unknown coordinate_indices dimensions: "
                + ", ".join(unknown_indices)
                + ". Available dimensions: "
                + ", ".join(sorted(known_dimensions))
            )
        size_aliases = (size_dataset,) if size_dataset else SINGLE_OPTICS_SIZE_ALIASES
        size_source = _h5_find_dataset(handle, names, size_aliases)
        if size_source is None:
            raise ScattError("No recognized size dataset found; tried " + ", ".join(size_aliases))
        size_dimension = _size_dimension(size_source)
        size_value = (
            size_source[()]
            if size_source.ndim == 1
            else _h5_selected_value(
                size_source,
                retain_dimensions=(size_dimension,),
                coordinate_indices=indices,
                label="size",
            )
        )
        raw_sizes = _dataset_to_float_list(size_value, "size")
        size_label = size_dataset
        if size_label is None:
            for alias in SINGLE_OPTICS_SIZE_ALIASES:
                if _normalize_dataset_name(alias) in names:
                    size_label = alias
                    break

        # Some sea-salt high-RH rows contain an all-one placeholder instead
        # of their size coordinate. The same native file explicitly defines
        # ve = r_veq / r_major, so its coordinate is recoverable without
        # altering optical values or guessing particle geometry.
        if (
            size_label == "xsize_veq"
            and "coated_super_spheroid_seasalt" in source.name
            and len(raw_sizes) > 1
            and all(value == 1.0 for value in raw_sizes)
        ):
            factor_source = _h5_find_dataset(handle, names, ("ve",))
            major_source = _h5_find_dataset(handle, names, ("xsize_maxd",))
            if factor_source is not None and major_source is not None:
                factors = _dataset_to_float_list(
                    _h5_selected_value(
                        factor_source, retain_dimensions=(), coordinate_indices=indices, label="ve"
                    ),
                    "ve",
                )
                major = _dataset_to_float_list(major_source[()], "xsize_maxd")
                recovered = [value * factors[0] for value in major] if len(factors) == 1 else []
                if (
                    len(recovered) == len(raw_sizes)
                    and all(math.isfinite(v) and v > 0 for v in recovered)
                    and all(b > a for a, b in zip(recovered, recovered[1:]))
                ):
                    raw_sizes = recovered
                    metadata["size_coordinate_reconstruction"] = (
                        "All-one sea-salt xsize_veq placeholder replaced in memory by native xsize_maxd * ve"
                    )

        wavelength_source = _h5_find_dataset(handle, names, SINGLE_OPTICS_WAVELENGTH_ALIASES)
        if wavelength_source is not None:
            wavelength_value = _h5_selected_value(
                wavelength_source,
                retain_dimensions=(),
                coordinate_indices=indices,
                label="wavelength",
            )
            wavelengths = _dataset_to_float_list(wavelength_value, "wavelength")
            if wavelengths:
                metadata["wavelength_um"] = wavelengths[0]
        source_wavelength_um = metadata.get("wavelength_um")
        if wavelength_um is not None:
            requested_wavelength_um = _finite_float(wavelength_um, "wavelength_um")
            if requested_wavelength_um <= 0:
                raise ScattError("wavelength_um must be positive")
            if source_wavelength_um is not None and not math.isclose(
                requested_wavelength_um,
                float(source_wavelength_um),
                rel_tol=1.0e-8,
                abs_tol=1.0e-12,
            ):
                raise ScattError(
                    f"Requested wavelength {requested_wavelength_um:g} um does not "
                    f"match source wavelength {float(source_wavelength_um):g} um"
                )
            metadata["wavelength_um"] = requested_wavelength_um
        wavelength_um = metadata.get("wavelength_um")

        normalized_size_label = _normalize_dataset_name(size_label or "")
        size_is_parameter = normalized_size_label in {"xsize_veq", "xsize_maxd"}
        if size_is_parameter:
            if wavelength_um is None:
                raise ScattError(
                    f"{size_label} is dimensionless and requires wavelength metadata "
                    "to obtain a physical radius"
                )
            size_factor_um = float(wavelength_um) / (2.0 * math.pi)
            sizes = [value * size_factor_um for value in raw_sizes]
            size_unit = "um"
            size_definition = (
                "volume_equivalent_sphere_radius"
                if normalized_size_label == "xsize_veq"
                else "maximum_dimension_radius"
            )
        else:
            sizes = raw_sizes
            size_factor_um = 1.0
            size_unit = "unknown"
            size_definition = "unspecified"

        def selected_list(
            aliases: Sequence[str], label: str, *, allow_nan: bool = False
        ) -> Optional[list[float]]:
            dataset = _h5_find_dataset(handle, names, aliases)
            if dataset is None:
                return None
            value = _h5_selected_value(
                dataset,
                retain_dimensions=(size_dimension,),
                coordinate_indices=indices,
                label=label,
            )
            return _dataset_to_float_list(value, label, allow_nan=allow_nan)

        cext_values = selected_list(SINGLE_OPTICS_EXTINCTION_ALIASES, "cext")
        csca_values = selected_list(SINGLE_OPTICS_SCATTERING_ALIASES, "csca")
        cabs_values = selected_list(SINGLE_OPTICS_ABSORPTION_ALIASES, "cabs")
        projected_area_values = selected_list(
            SINGLE_OPTICS_PROJECTED_AREA_ALIASES, "projected_area"
        )
        extinction_efficiency = selected_list(SINGLE_OPTICS_QEXT_ALIASES, "qext")
        scattering_efficiency = selected_list(SINGLE_OPTICS_QSCA_ALIASES, "qsca")
        absorption_efficiency = selected_list(SINGLE_OPTICS_QABS_ALIASES, "qabs")
        ssa_values = selected_list(SINGLE_OPTICS_SSA_ALIASES, "ssa")
        asymmetry_factor = selected_list(
            SINGLE_OPTICS_G_ALIASES,
            "g",
            allow_nan=allow_nan_asymmetry,
        )

        resolved_cext_mode = mode
        if resolved_cext_mode == "auto":
            resolved_cext_mode = "scaled_k2" if size_is_parameter else "physical_m2"
        if resolved_cext_mode == "scaled_k2":
            if wavelength_um is None:
                raise ScattError("scaled_k2 cext requires wavelength metadata")
            cross_section_factor = (float(wavelength_um) / (2.0 * math.pi)) ** 2 * 1.0e-12
        elif resolved_cext_mode == "physical_um2":
            cross_section_factor = 1.0e-12
        else:
            cross_section_factor = 1.0

        def physical_cross_sections(
            values: Optional[Sequence[float]],
        ) -> Optional[list[float]]:
            if values is None:
                return None
            return [float(value) * cross_section_factor for value in values]

        extinction_cross_section = physical_cross_sections(cext_values)
        scattering_cross_section = physical_cross_sections(csca_values)
        absorption_cross_section = physical_cross_sections(cabs_values)
        projected_area = physical_cross_sections(projected_area_values)

        if extinction_cross_section is None and extinction_efficiency and projected_area:
            extinction_cross_section = [
                efficiency * area for efficiency, area in zip(extinction_efficiency, projected_area)
            ]
        if scattering_cross_section is None and scattering_efficiency and projected_area:
            scattering_cross_section = [
                efficiency * area for efficiency, area in zip(scattering_efficiency, projected_area)
            ]

        angle_source = _h5_find_dataset(handle, names, SINGLE_OPTICS_ANGLE_ALIASES)
        scattering_angles = (
            _dataset_to_float_list(angle_source[()], "sca_angle")
            if angle_source is not None
            else None
        )

        if scattering_cross_section is None and extinction_cross_section and ssa_values:
            scattering_cross_section = [
                extinction * single_scattering_albedo
                for extinction, single_scattering_albedo in zip(
                    extinction_cross_section,
                    ssa_values,
                )
            ]
        if (
            absorption_cross_section is None
            and extinction_cross_section
            and scattering_cross_section
        ):
            absorption_cross_section = [
                extinction - scattering
                for extinction, scattering in zip(
                    extinction_cross_section,
                    scattering_cross_section,
                )
            ]
        derived_ssa = ssa_values
        if extinction_cross_section is not None and scattering_cross_section is not None:
            derived_ssa = [
                scattering / extinction if extinction > 0.0 else 0.0
                for extinction, scattering in zip(
                    extinction_cross_section, scattering_cross_section
                )
            ]
        if scattering_efficiency is None and extinction_efficiency and ssa_values:
            scattering_efficiency = [
                extinction * single_scattering_albedo
                for extinction, single_scattering_albedo in zip(
                    extinction_efficiency,
                    ssa_values,
                )
            ]
        if absorption_efficiency is None and extinction_efficiency and scattering_efficiency:
            absorption_efficiency = [
                extinction - scattering
                for extinction, scattering in zip(
                    extinction_efficiency,
                    scattering_efficiency,
                )
            ]
        phase_matrix = (
            _h5_phase_matrix(
                handle,
                names,
                len(sizes),
                size_dimension=size_dimension,
                coordinate_indices=indices,
                allow_nan=allow_nan_asymmetry,
            )
            if include_phase_matrix
            else None
        )

    metadata.update(
        {
            "source_file": str(source),
            "size_dataset": size_label,
            "size_dimension": size_dimension,
            "size_definition": size_definition,
            "size_unit": size_unit,
            "size_parameter_to_um_factor": size_factor_um,
            "cext_source_scaling": resolved_cext_mode,
            "cross_section_to_m2_factor": cross_section_factor,
            "cross_section_unit": "m2",
            "coordinate_indices": indices,
            "wavelength_source": (
                "user" if wavelength_um is not None and source_wavelength_um is None else "source"
            ),
        }
    )
    if scattering_angles is not None:
        metadata["scattering_angles"] = scattering_angles

    return SingleParticleOptics(
        sizes=sizes,
        extinction_cross_section=extinction_cross_section,
        scattering_cross_section=scattering_cross_section,
        absorption_cross_section=absorption_cross_section,
        extinction_efficiency=extinction_efficiency,
        scattering_efficiency=scattering_efficiency,
        absorption_efficiency=absorption_efficiency,
        asymmetry_factor=asymmetry_factor,
        phase_matrix=phase_matrix,
        scattering_angles=scattering_angles,
        size_unit=size_unit,
        cross_section_unit="m2",
        metadata=metadata,
        projected_area=projected_area,
        single_scattering_albedo=derived_ssa,
    )
