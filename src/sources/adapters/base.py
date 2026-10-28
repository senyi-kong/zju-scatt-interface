"""Common source records, coordinate selection and particle-adapter protocol."""

from __future__ import annotations

import math
import re
from bisect import bisect_left
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import zju_scatt_interface.optics.loading as _domain_optics_loading
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    normalize_parameter_name,
)
from zju_scatt_interface.optics.interpolation import (
    InterpolatedOpticalProduct,
    OpticalNode,
    OpticalSourceRequest,
    interpolate_nodes,
)
from zju_scatt_interface.optics.refractive_index import (
    RefractiveIndexTable,
    wavelength_to_um,
)
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
    DatabaseBoundaryError,
)


def _fill_phase_nan_gaps(optics: Any) -> int:
    """Interpolate source-normalized phase bases across interior angle gaps.

    Some L1 ice files store several native angular grids on one union coordinate;
    unused positions are NaN padding.  Endpoints must remain finite, so this helper
    never extrapolates beyond the resolved angular support.
    """
    phase = optics.phase_matrix
    angles = optics.scattering_angles
    if phase is None or angles is None:
        return 0
    filled = 0
    positions = {
        "p12": (0, 1),
        "p22": (1, 1),
        "p33": (2, 2),
        "p44": (3, 3),
        "p43": (3, 2),
    }

    def fill(values: list[float]) -> tuple[list[float], int]:
        finite_indices = [index for index, value in enumerate(values) if math.isfinite(value)]
        if len(finite_indices) == len(values):
            return values, 0
        if (
            len(finite_indices) < 2
            or finite_indices[0] != 0
            or finite_indices[-1] != len(values) - 1
        ):
            return values, 0
        result = list(values)
        count = 0
        finite_angles = [float(angles[index]) for index in finite_indices]
        for index, value in enumerate(values):
            if math.isfinite(value):
                continue
            position = bisect_left(finite_angles, float(angles[index]))
            lower = finite_indices[position - 1]
            upper = finite_indices[position]
            fraction = (float(angles[index]) - float(angles[lower])) / (
                float(angles[upper]) - float(angles[lower])
            )
            result[index] = values[lower] + fraction * (values[upper] - values[lower])
            count += 1
        return result, count

    for size_matrix in phase:
        original_p11 = [float(matrix[0][0]) for matrix in size_matrix]
        p11, count = fill(original_p11)
        filled += count
        ratios: dict[str, list[float]] = {}
        for name, (row, column) in positions.items():
            values = []
            for matrix, denominator in zip(size_matrix, original_p11):
                numerator = float(matrix[row][column])
                values.append(
                    numerator / denominator
                    if math.isfinite(numerator) and math.isfinite(denominator) and denominator > 0.0
                    else float("nan")
                )
            ratios[name], count = fill(values)
            filled += count
        for index, matrix in enumerate(size_matrix):
            if not math.isfinite(p11[index]) or any(
                not math.isfinite(values[index]) for values in ratios.values()
            ):
                continue
            value = p11[index]
            p12 = ratios["p12"][index] * value
            p43 = ratios["p43"][index] * value
            matrix[:] = [
                [value, p12, 0.0, 0.0],
                [p12, ratios["p22"][index] * value, 0.0, 0.0],
                [0.0, 0.0, ratios["p33"][index] * value, -p43],
                [0.0, 0.0, p43, ratios["p44"][index] * value],
            ]
    return filled


@dataclass(frozen=True)
class AdapterSourceNode:
    path: Path
    coordinates: Mapping[str, float | str]
    coordinate_indices: Mapping[str, int] = field(default_factory=dict)
    wavelength_um: float | None = None

    def to_request(self, *, include_phase_matrix: bool, size_dataset: str) -> OpticalSourceRequest:
        from zju_scatt_interface.optics.interpolation import OpticalSourceRequest

        return OpticalSourceRequest(
            path=self.path,
            coordinates=self.coordinates,
            coordinate_indices=self.coordinate_indices,
            wavelength_um=self.wavelength_um,
            include_phase_matrix=include_phase_matrix,
            size_dataset=size_dataset,
        )


@dataclass
class AdapterProvenance:
    adapter: str
    particle_type: str
    public_wavelength_um: float
    target_native_coordinates: dict[str, float | str]
    size_definition: str
    source_candidate_count: int
    selected_node_count: int
    refractive_index_input_mode: str = "database"
    refractive_index_sources: dict[str, str] = field(default_factory=dict)
    coordinate_conversions: list[str] = field(default_factory=list)
    defaults_applied: list[str] = field(default_factory=list)
    database_type: str | None = None
    ri_scheme: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdapterResolution:
    particle_type: str
    target_coordinates: dict[str, float | str]
    sources: tuple[OpticalSourceRequest, ...]
    provenance: AdapterProvenance

    def interpolate(
        self,
        *,
        target_size_um: Sequence[float] | None = None,
        source_size_grids_um: Mapping[str | Path, Sequence[float]] | None = None,
        drop_invalid_size_points: bool = False,
        target_angles_degrees: Sequence[float] | None = None,
        phase_normalization: str = "preserve",
    ) -> InterpolatedOpticalProduct:
        nodes = [
            OpticalNode(
                coordinates=source.coordinates,
                optics=_domain_optics_loading.load_single(
                    source.path,
                    include_phase_matrix=source.include_phase_matrix,
                    size_dataset=source.size_dataset,
                    coordinate_indices=dict(source.coordinate_indices),
                    wavelength_um=source.wavelength_um,
                    allow_nan_asymmetry=drop_invalid_size_points,
                ),
                source=str(Path(source.path)),
            )
            for source in self.sources
        ]
        dropped_by_source: dict[str, int] = {}
        phase_filled_by_source: dict[str, int] = {}
        valid_indices_by_source: dict[str, list[int]] = {}
        size_fields = (
            "extinction_cross_section",
            "scattering_cross_section",
            "absorption_cross_section",
            "extinction_efficiency",
            "scattering_efficiency",
            "absorption_efficiency",
            "asymmetry_factor",
            "projected_area",
            "single_scattering_albedo",
        )
        if drop_invalid_size_points:
            for node in nodes:
                source = str(Path(node.source).expanduser().resolve())
                filled = _fill_phase_nan_gaps(node.optics)
                if filled:
                    phase_filled_by_source[source] = filled

                def phase_is_finite(index: int) -> bool:
                    if node.optics.phase_matrix is None:
                        return True
                    return all(
                        math.isfinite(float(value))
                        for angle_matrix in node.optics.phase_matrix[index]
                        for row in angle_matrix
                        for value in row
                    )

                valid = [
                    index
                    for index in range(len(node.optics.sizes))
                    if all(
                        values is None or math.isfinite(float(values[index]))
                        for values in (
                            getattr(node.optics, field_name) for field_name in size_fields
                        )
                    )
                    and phase_is_finite(index)
                ]
                if not valid:
                    raise AdapterError(f"No finite optical size points remain in {node.source}")
                valid_indices_by_source[source] = valid
                dropped = len(node.optics.sizes) - len(valid)
                if dropped:
                    dropped_by_source[source] = dropped
                    node.optics.sizes = [node.optics.sizes[index] for index in valid]
                    for field_name in size_fields:
                        values = getattr(node.optics, field_name)
                        if values is not None:
                            setattr(
                                node.optics,
                                field_name,
                                [values[index] for index in valid],
                            )
                    if node.optics.phase_matrix is not None:
                        node.optics.phase_matrix = [
                            node.optics.phase_matrix[index] for index in valid
                        ]
        if source_size_grids_um is not None:
            grids = {
                str(Path(path).expanduser().resolve()): [float(value) for value in values]
                for path, values in source_size_grids_um.items()
            }
            for node in nodes:
                source = str(Path(node.source).expanduser().resolve())
                if source not in grids:
                    raise AdapterError(f"source_size_grids_um has no entry for {node.source}")
                grid = grids[source]
                if source in valid_indices_by_source:
                    grid = [grid[index] for index in valid_indices_by_source[source]]
                if len(node.optics.sizes) != len(grid):
                    raise AdapterError(
                        "Each source_size_grids_um entry must match its source array"
                    )
                node.optics.sizes = list(grid)
        product = interpolate_nodes(
            self.particle_type,
            nodes,
            self.target_coordinates,
            target_size_um=target_size_um,
            target_angles_degrees=target_angles_degrees,
            phase_normalization=phase_normalization,
        )
        product.provenance.adapter = self.provenance.to_dict()
        if dropped_by_source:
            product.provenance.warnings.append(
                "Dropped non-finite optical size points: "
                + ", ".join(
                    f"{Path(source).name}={count}"
                    for source, count in sorted(dropped_by_source.items())
                )
            )
        if phase_filled_by_source:
            product.provenance.warnings.append(
                "Interpolated interior phase-angle NaN padding without extrapolation: "
                + ", ".join(
                    f"{Path(source).name}={count}"
                    for source, count in sorted(phase_filled_by_source.items())
                )
            )
        product.optics.metadata["adapter_provenance"] = self.provenance.to_dict()
        product.optics.metadata["interpolation_provenance"] = product.provenance.to_dict()
        return product


@dataclass(frozen=True)
class _FileRecord:
    path: Path
    coordinates: Mapping[str, float | str]
    indices: Mapping[str, int] = field(default_factory=dict)


def _finite(value: object, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AdapterError(f"{name} must be numeric.") from exc
    if not math.isfinite(result):
        raise AdapterError(f"{name} must be finite.")
    return result


def _normalized_parameters(parameters: Mapping[str, object] | None) -> dict[str, object]:
    result: dict[str, object] = {}
    for raw_name, value in (parameters or {}).items():
        name = normalize_parameter_name(raw_name)
        if name in result:
            raise AdapterError(f"{name!r} was supplied more than once through aliases.")
        result[name] = value
    return result


def _expand_netcdf_paths(paths: str | Path | Sequence[str | Path]) -> tuple[Path, ...]:
    from zju_scatt_interface.sources.validation import _netcdf_path

    supplied = [paths] if isinstance(paths, (str, Path)) else list(paths)
    result: list[Path] = []
    for item in supplied:
        path = Path(item).expanduser()
        if Path(_netcdf_path(path)).is_file():
            if path.suffix.casefold() in {".nc", ".nc4", ".h5", ".hdf5"}:
                result.append(path.resolve())
        elif path.is_dir():
            result.extend(
                candidate.resolve()
                for candidate in path.rglob("*")
                if candidate.suffix.casefold() in {".nc", ".nc4", ".h5", ".hdf5"}
                and Path(_netcdf_path(candidate)).is_file()
            )
        else:
            raise AdapterError(f"Source path does not exist: {path}")
    unique = tuple(dict.fromkeys(result))
    if not unique:
        raise AdapterError("No NetCDF/HDF5 L1 source files were found.")
    return unique


def _match_number(text: str, pattern: str, name: str) -> float:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        raise AdapterError(f"Cannot resolve {name} from source filename {text!r}.")
    return _finite(match.group(1), name)


def _retain_rectangular_brackets(
    records: Sequence[_FileRecord],
    target: Mapping[str, float | str],
    axes: Sequence[str],
) -> list[_FileRecord]:
    from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryError

    selected = list(records)
    for axis in axes:
        wanted = target[axis]
        if isinstance(wanted, str):
            selected = [record for record in selected if record.coordinates.get(axis) == wanted]
            if not selected:
                raise AdapterError(f"No source node matches {axis}={wanted!r}.")
            continue
        values = sorted(
            {float(record.coordinates[axis]) for record in selected if axis in record.coordinates}
        )
        if not values:
            raise AdapterError(f"Source metadata does not contain coordinate {axis!r}.")
        numeric = float(wanted)
        lower = [value for value in values if value <= numeric or math.isclose(value, numeric)]
        upper = [value for value in values if value >= numeric or math.isclose(value, numeric)]
        if not lower or not upper:
            raise DatabaseBoundaryError(
                f"No extrapolation is allowed: {axis}={numeric:g} is outside "
                f"available source coordinates [{values[0]:g}, {values[-1]:g}]."
            )
        bracket = (max(lower), min(upper))
        selected = [
            record
            for record in selected
            if axis in record.coordinates
            and (
                math.isclose(float(record.coordinates[axis]), bracket[0])
                or math.isclose(float(record.coordinates[axis]), bracket[1])
            )
        ]
    if not selected:
        raise AdapterError("No source nodes remain after coordinate bracketing.")
    return selected


def _retain_brackets(
    records: Sequence[_FileRecord],
    target: Mapping[str, float | str],
    axes: Sequence[str],
) -> list[_FileRecord]:
    """Keep rectangular brackets, preserving support on correlated sparse grids.

    Sequential axis filtering can discard one RI side while filtering another
    coordinate. Rechecking the retained support catches that false boundary;
    the fallback uses the same bounded sparse selector as source planning.
    """
    try:
        selected = _retain_rectangular_brackets(records, target, axes)
        _retain_rectangular_brackets(selected, target, axes)
        return selected
    except DatabaseBoundaryError as boundary:
        from zju_scatt_interface.optics.interpolation import _select_neighbors

        candidates = list(records)
        numeric_axes = []
        for axis in axes:
            if isinstance(target[axis], str):
                candidates = [
                    record for record in candidates if record.coordinates.get(axis) == target[axis]
                ]
            else:
                numeric_axes.append(axis)
        if not candidates or not numeric_axes:
            raise boundary
        nodes = [
            OpticalNode({axis: record.coordinates[axis] for axis in numeric_axes}, None, str(i))
            for i, record in enumerate(candidates)
        ]
        try:
            _, chosen, _, _, _ = _select_neighbors(
                tuple(numeric_axes), target, nodes, sparse_power=2.0
            )
        except ValueError:
            raise boundary
        # Keep both coordinate sides for later interpolation/preflight stages,
        # including sparse support points which may carry zero final weight.
        for axis in numeric_axes:
            for lower in (True, False):

                def side(node):
                    return (
                        node.coordinates[axis] <= target[axis]
                        if lower
                        else node.coordinates[axis] >= target[axis]
                    )

                if not any(side(node) for node in chosen):
                    available = [node for node in nodes if side(node)]
                    if not available:
                        raise boundary
                    chosen.append(
                        min(available, key=lambda node: abs(node.coordinates[axis] - target[axis]))
                    )
        indices = {int(node.source) for node in chosen}
        return [record for i, record in enumerate(candidates) if i in indices]


def _read_coordinate(path: Path, variable_name: str) -> list[float]:
    try:
        from netCDF4 import Dataset
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Particle adapters require netCDF4; install zju-scatt-interface[netcdf]."
        ) from exc
    from zju_scatt_interface.sources.validation import _netcdf_path

    with Dataset(_netcdf_path(path)) as dataset:
        if variable_name not in dataset.variables:
            raise AdapterError(f"{path} does not contain coordinate {variable_name!r}.")
        values = dataset.variables[variable_name][:]
        if hasattr(values, "compressed"):
            values = values.compressed()
        return [float(value) for value in values.reshape(-1)]


def _size_dataset(profile_name: str, size_definition: str | None) -> tuple[str, str]:
    profile = get_particle_profile(profile_name)
    definition = size_definition or profile.default_size_definition
    if definition not in profile.supported_size_definitions:
        raise AdapterError(
            f"{profile.particle_type} does not support size_definition={definition!r}; "
            f"choose from {', '.join(profile.supported_size_definitions)}."
        )
    dataset = "xsize_veq" if definition == "volume_equivalent_sphere_radius" else "xsize_maxd"
    return definition, dataset


class ParticleAdapter:
    """Base class for one scientifically explicit particle-family adapter."""

    particle_type: str
    axes: tuple[str, ...]
    internal_axis: str | None = None

    def _target(
        self,
        wavelength_um: float,
        parameters: Mapping[str, object],
        tables: Mapping[str, str | Path | RefractiveIndexTable] | None,
    ) -> tuple[dict[str, float | str], str, dict[str, str], list[str]]:
        raise NotImplementedError

    def _file_coordinates(self, path: Path) -> dict[str, float | str]:
        raise NotImplementedError

    def _expand_internal(
        self, records: Sequence[_FileRecord]
    ) -> tuple[list[_FileRecord], list[str]]:
        return list(records), []

    def resolve(
        self,
        source_paths: str | Path | Sequence[str | Path],
        *,
        wavelength: object,
        wavelength_unit: str = "um",
        parameters: Mapping[str, object] | None = None,
        refractive_index_tables: (Mapping[str, str | Path | RefractiveIndexTable] | None) = None,
        size_definition: str | None = None,
        include_phase_matrix: bool = False,
    ) -> AdapterResolution:
        wavelength_um = wavelength_to_um(wavelength, wavelength_unit)
        normalized = _normalized_parameters(parameters)
        target, ri_mode, ri_sources, defaults = self._target(
            wavelength_um, normalized, refractive_index_tables
        )
        paths = _expand_netcdf_paths(source_paths)
        records: list[_FileRecord] = []
        rejected = 0
        for path in paths:
            normalized_path = str(path).casefold().replace("-", "_")
            if self.particle_type not in normalized_path:
                rejected += 1
                continue
            try:
                coordinates = self._file_coordinates(path)
            except AdapterError:
                rejected += 1
                continue
            records.append(_FileRecord(path, coordinates))
        if not records:
            raise AdapterError(
                f"No supplied source file matches {self.particle_type}; "
                f"{rejected} files lacked required particle-specific metadata."
            )
        pre_axes = tuple(
            axis for axis in self.axes if all(axis in record.coordinates for record in records)
        )
        selected = _retain_brackets(records, target, pre_axes)
        expanded, conversions = self._expand_internal(selected)
        selected = _retain_brackets(expanded, target, self.axes)
        definition, size_dataset = _size_dataset(self.particle_type, size_definition)
        requests = tuple(
            AdapterSourceNode(
                path=record.path,
                coordinates=record.coordinates,
                coordinate_indices=record.indices,
                wavelength_um=(
                    wavelength_um
                    if self.particle_type
                    in {
                        "super_spheroid",
                        "encapsulated_fractal_aggregates_black_carbon",
                    }
                    and "_wl_nan_" in record.path.name.casefold()
                    else None
                ),
            ).to_request(
                include_phase_matrix=include_phase_matrix,
                size_dataset=size_dataset,
            )
            for record in selected
        )
        provenance = AdapterProvenance(
            adapter=type(self).__name__,
            particle_type=self.particle_type,
            public_wavelength_um=wavelength_um,
            target_native_coordinates=dict(target),
            size_definition=definition,
            source_candidate_count=len(records),
            selected_node_count=len(requests),
            refractive_index_input_mode=ri_mode,
            refractive_index_sources=ri_sources,
            coordinate_conversions=conversions,
            defaults_applied=defaults,
        )
        return AdapterResolution(self.particle_type, target, requests, provenance)
