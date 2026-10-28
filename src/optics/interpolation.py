"""optics / interpolation domain implementation."""

from __future__ import annotations

import json
import math
import re
from bisect import bisect_left
from dataclasses import asdict, dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from zju_scatt_interface.access.metadata import extract_scatt_metadata
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import get_particle_profile
from zju_scatt_interface.optics.loading import load_single
from zju_scatt_interface.optics.models import SingleParticleOptics
from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryError
from zju_scatt_interface.sources.coordinates import object_series_key

_ALIASES = {
    "wavelength_um": "wavelength",
    "mr": "refractive_index_real",
    "mi": "refractive_index_imaginary",
    "n": "roundness",
    "smoothness": "roundness",
    "alpha": "aspect_ratio",
    "asp": "aspect_ratio",
}

_PHASE_RATIO_POSITIONS = {
    "p12_over_p11": (0, 1),
    "p22_over_p11": (1, 1),
    "p33_over_p11": (2, 2),
    "p44_over_p11": (3, 3),
    "p43_over_p11": (3, 2),
}


class InterpolationError(ValueError):
    """Raised when a requested product cannot be interpolated safely."""


class InterpolationBoundaryError(InterpolationError, DatabaseBoundaryError):
    """A requested interpolation coordinate exceeds source coverage."""


@dataclass(frozen=True)
class OpticalNode:
    """One source product at a known set of canonical scientific coordinates."""

    coordinates: Mapping[str, float | str]
    optics: SingleParticleOptics
    source: str = ""


@dataclass(frozen=True)
class OpticalSourceRequest:
    """Description of an L1 source file that can be loaded as an optical node."""

    path: str | Path
    coordinates: Mapping[str, float | str]
    coordinate_indices: Mapping[str, int] = field(default_factory=dict)
    wavelength_um: float | None = None
    include_phase_matrix: bool = False
    size_dataset: str | None = None


@dataclass(frozen=True)
class InterpolationNeighbor:
    source: str
    coordinates: Mapping[str, float | str]
    weight: float
    normalized_distance: float


@dataclass
class InterpolationProvenance:
    method: str
    particle_type: str
    target_coordinates: dict[str, float | str]
    axis_transforms: dict[str, str]
    optical_transforms: dict[str, str]
    neighbors: list[InterpolationNeighbor]
    size_grid_um: list[float]
    angle_grid_degrees: list[float]
    no_extrapolation: bool = True
    phase_normalization: str = "preserve"
    constraint_corrections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    adapter: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterpolatedOpticalProduct:
    particle_type: str
    coordinates: dict[str, float | str]
    optics: SingleParticleOptics
    provenance: InterpolationProvenance


@dataclass(frozen=True)
class InterpolatedFileResult:
    """One local target-wavelength product created from downloaded sources."""

    path: Path
    particle_type: str
    target_wavelength_um: float | None
    fixed_coordinates: Mapping[str, float | str]
    source_paths: tuple[Path, ...]
    status: str
    provenance: Mapping[str, Any] = field(default_factory=dict)


def _canonical_coordinates(values: Mapping[str, float | str]) -> dict[str, float | str]:
    result: dict[str, float | str] = {}
    for key, value in values.items():
        name = _ALIASES.get(str(key).strip().lower(), str(key).strip().lower())
        result[name] = value
    return result


def _is_imaginary_axis(name: str) -> bool:
    return name.endswith("_imaginary") or name in {"mi", "k"}


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-12)


def _profile_axes(particle_type: str) -> tuple[str, ...]:
    from zju_scatt_interface.extensions.particles import get_particle_definition

    return get_particle_definition(particle_type).axes


def _validate_target(
    particle_type: str,
    target: Mapping[str, float | str],
    nodes: Sequence[OpticalNode],
) -> tuple[str, tuple[str, ...], dict[str, float | str], list[OpticalNode]]:
    profile = get_particle_profile(particle_type)
    canonical = profile.particle_type
    expected = _profile_axes(canonical)
    values = _canonical_coordinates(target)
    from zju_scatt_interface.extensions.particles import get_particle_definition

    policy = get_particle_definition(canonical).interpolation_policy
    enforce_profile_bounds = True
    if policy is not None:
        expected, enforce_profile_bounds = policy(values, nodes)
    missing = [axis for axis in expected if axis not in values]
    if missing:
        raise InterpolationError(
            f"{canonical} interpolation requires target coordinates: {', '.join(missing)}."
        )
    unexpected = sorted(set(values) - set(expected) - {"humidity_branch"})
    if unexpected:
        raise InterpolationError(
            f"Unsupported interpolation coordinates for {canonical}: {', '.join(unexpected)}."
        )
    if "relative_humidity" in values:
        rh = float(values["relative_humidity"])
        if not 0.0 <= rh <= 1.0:
            raise InterpolationError("relative_humidity must use unit 1 and lie in [0, 1].")
    for axis in expected:
        specification = profile.parameter(axis)
        numeric = float(values[axis])
        if not enforce_profile_bounds:
            if not math.isfinite(numeric):
                raise InterpolationError(f"{axis} must be finite")
            continue  # Selected database nodes define BC coverage.
        if specification.minimum is not None and numeric < specification.minimum:
            raise InterpolationError(
                f"{axis}={numeric:g} is below the profile minimum {specification.minimum:g}."
            )
        if specification.maximum is not None and numeric > specification.maximum:
            raise InterpolationError(
                f"{axis}={numeric:g} is above the profile maximum {specification.maximum:g}."
            )

    prepared: list[OpticalNode] = []
    for node in nodes:
        coords = _canonical_coordinates(node.coordinates)
        if all(axis in coords for axis in expected):
            prepared.append(OpticalNode(coords, node.optics, node.source))
    if not prepared:
        raise InterpolationError("No source node contains every required profile coordinate.")

    branches = {n.coordinates.get("humidity_branch") for n in prepared}
    branches.discard(None)
    requested_branch = values.get("humidity_branch")
    if requested_branch is not None:
        prepared = [n for n in prepared if n.coordinates.get("humidity_branch") == requested_branch]
        if not prepared:
            raise InterpolationError(f"No source nodes match humidity_branch={requested_branch!r}.")
    elif len(branches) > 1:
        raise InterpolationError(
            "Multiple humidity branches are present; specify humidity_branch explicitly."
        )
    return canonical, expected, values, prepared


def _axis_transform(axis: str, values: Iterable[float]) -> tuple[Callable[[float], float], str]:
    numeric = [float(v) for v in values]
    if not _is_imaginary_axis(axis):
        return float, "linear"
    positives = [v for v in numeric if v > 0]
    floor = max(min(positives) / 10.0, 1e-12) if positives else 1e-12
    return lambda value: math.log10(max(float(value), floor)), f"log10(floor={floor:g})"


def _select_neighbors(
    axes: Sequence[str],
    target: Mapping[str, float | str],
    nodes: Sequence[OpticalNode],
    *,
    sparse_power: float,
) -> tuple[str, list[OpticalNode], list[float], list[float], dict[str, str]]:
    transforms: dict[str, Callable[[float], float]] = {}
    transform_names: dict[str, str] = {}
    for axis in axes:
        transform, name = _axis_transform(axis, (float(n.coordinates[axis]) for n in nodes))
        transforms[axis] = transform
        transform_names[axis] = name

    exact = [
        node
        for node in nodes
        if all(
            _close(
                transforms[axis](float(node.coordinates[axis])),
                transforms[axis](float(target[axis])),
            )
            for axis in axes
        )
    ]
    if exact:
        return "exact", [exact[0]], [1.0], [0.0], transform_names

    bounds: dict[str, tuple[float, float]] = {}
    for axis in axes:
        available = sorted({transforms[axis](float(node.coordinates[axis])) for node in nodes})
        wanted = transforms[axis](float(target[axis]))
        lower = [value for value in available if value < wanted or _close(value, wanted)]
        upper = [value for value in available if value > wanted or _close(value, wanted)]
        if not lower or not upper:
            raw_min = min(float(n.coordinates[axis]) for n in nodes)
            raw_max = max(float(n.coordinates[axis]) for n in nodes)
            raise InterpolationBoundaryError(
                f"No extrapolation is allowed: target {axis}={target[axis]} lies outside "
                f"the source interval [{raw_min}, {raw_max}]."
            )
        bounds[axis] = (max(lower), min(upper))

    corner_values = [(lo,) if _close(lo, hi) else (lo, hi) for lo, hi in (bounds[a] for a in axes)]
    corner_nodes: list[OpticalNode] = []
    corner_weights: list[float] = []
    missing_corner = False
    for corner in product(*corner_values):
        matches = [
            node
            for node in nodes
            if all(
                _close(transforms[axis](float(node.coordinates[axis])), value)
                for axis, value in zip(axes, corner)
            )
        ]
        if not matches:
            missing_corner = True
            break
        weight = 1.0
        for axis, corner_value in zip(axes, corner):
            lo, hi = bounds[axis]
            if _close(lo, hi):
                continue
            fraction = (transforms[axis](float(target[axis])) - lo) / (hi - lo)
            weight *= fraction if _close(corner_value, hi) else 1.0 - fraction
        corner_nodes.append(matches[0])
        corner_weights.append(weight)
    if not missing_corner:
        distances = _normalized_distances(axes, target, nodes, corner_nodes, transforms)
        return "multilinear", corner_nodes, corner_weights, distances, transform_names

    distances_all = _normalized_distances(axes, target, nodes, nodes, transforms)
    ranked = sorted(zip(distances_all, nodes), key=lambda item: item[0])
    # Fixed geometry coordinates do not add interpolation dimensions. A sparse
    # RI plane at one native shape needs three nodes, not five just because its
    # records also carry roundness and aspect-ratio coordinates.
    dimensions = sum(
        not _close(
            min(transforms[axis](float(node.coordinates[axis])) for node in nodes),
            max(transforms[axis](float(node.coordinates[axis])) for node in nodes),
        )
        for axis in axes
    )
    needed = min(len(nodes), max(dimensions + 1, 2 ** min(dimensions, 4)))
    if len(nodes) < dimensions + 1:
        raise InterpolationError(
            f"Sparse interpolation in {dimensions} dimensions requires at least "
            f"{dimensions + 1} nodes; received {len(nodes)}."
        )
    selected = ranked[:needed]
    raw_weights = [1.0 / max(distance, 1e-15) ** sparse_power for distance, _ in selected]
    total = sum(raw_weights)
    return (
        "inverse_distance_sparse",
        [node for _, node in selected],
        [weight / total for weight in raw_weights],
        [distance for distance, _ in selected],
        transform_names,
    )


def _normalized_distances(
    axes: Sequence[str],
    target: Mapping[str, float | str],
    all_nodes: Sequence[OpticalNode],
    selected: Sequence[OpticalNode],
    transforms: Mapping[str, Callable[[float], float]],
) -> list[float]:
    spans: dict[str, float] = {}
    for axis in axes:
        values = [transforms[axis](float(n.coordinates[axis])) for n in all_nodes]
        spans[axis] = max(max(values) - min(values), 1e-15)
    return [
        math.sqrt(
            sum(
                (
                    (
                        transforms[axis](float(node.coordinates[axis]))
                        - transforms[axis](float(target[axis]))
                    )
                    / spans[axis]
                )
                ** 2
                for axis in axes
            )
        )
        for node in selected
    ]


def _linear(x: Sequence[float], y: Sequence[float], targets: Sequence[float]) -> list[float]:
    if len(x) != len(y) or not x:
        raise InterpolationError("Interpolation coordinate and data lengths must match.")
    ordered = sorted(zip(map(float, x), map(float, y)))
    xs, ys = zip(*ordered)
    result: list[float] = []
    for target in targets:
        value = float(target)
        if value < xs[0] and not _close(value, xs[0]):
            raise InterpolationError(f"Target {value} is below source coverage {xs[0]}.")
        if value > xs[-1] and not _close(value, xs[-1]):
            raise InterpolationError(f"Target {value} is above source coverage {xs[-1]}.")
        if _close(value, xs[0]):
            result.append(ys[0])
            continue
        index = bisect_left(xs, value, lo=1)
        # Preserve the former scan's tolerance near an interior right endpoint.
        while index > 1 and _close(value, xs[index - 1]):
            index -= 1
        fraction = (value - xs[index - 1]) / (xs[index] - xs[index - 1])
        result.append(ys[index - 1] + fraction * (ys[index] - ys[index - 1]))
    return result


def _common_grid(
    grids: Sequence[Sequence[float]], requested: Sequence[float] | None
) -> list[float]:
    lower = max(min(map(float, grid)) for grid in grids)
    upper = min(max(map(float, grid)) for grid in grids)
    if lower > upper and not _close(lower, upper):
        raise InterpolationBoundaryError("Source products have no common size/angle coverage.")
    values = (
        sorted({float(value) for grid in grids for value in grid if lower <= float(value) <= upper})
        if requested is None
        else [float(value) for value in requested]
    )
    if not values:
        raise InterpolationError("The requested common interpolation grid is empty.")
    if min(values) < lower and not _close(min(values), lower):
        raise InterpolationBoundaryError("Requested grid extends below common source coverage.")
    if max(values) > upper and not _close(max(values), upper):
        raise InterpolationBoundaryError("Requested grid extends above common source coverage.")
    return values


def _resample_node(
    node: OpticalNode, sizes: Sequence[float], angles: Sequence[float]
) -> dict[str, Any]:
    optics = node.optics
    log_source_size = [math.log(max(float(value), 1e-30)) for value in optics.sizes]
    log_target_size = [math.log(max(float(value), 1e-30)) for value in sizes]

    def size_values(
        values: Sequence[float] | None, *, positive: bool = False
    ) -> list[float] | None:
        if values is None:
            return None
        if len(optics.sizes) == len(sizes) and all(
            _close(float(source), float(target)) for source, target in zip(optics.sizes, sizes)
        ):
            return list(map(float, values))
        if positive and all(float(value) > 0 for value in values):
            return [
                math.exp(value)
                for value in _linear(
                    log_source_size,
                    [math.log(float(value)) for value in values],
                    log_target_size,
                )
            ]
        return _linear(log_source_size, values, log_target_size)

    phase_basis = None
    if optics.phase_matrix is not None:
        if not optics.scattering_angles:
            raise InterpolationError("A phase matrix requires scattering_angles.")
        # Normalize at each original database node before interpolating over
        # angle, size, or any external optical-coordinate axis.
        source_basis: dict[str, list[list[float]]] = {
            "p11": [],
            **{name: [] for name in _PHASE_RATIO_POSITIONS},
        }
        for size_matrix in optics.phase_matrix:
            p11_values: list[float] = []
            ratio_values = {name: [] for name in _PHASE_RATIO_POSITIONS}
            for matrix in size_matrix:
                p11 = float(matrix[0][0])
                if not math.isfinite(p11) or p11 <= 0.0:
                    raise InterpolationError(
                        "P11 must be finite and positive before phase-ratio interpolation."
                    )
                p11_values.append(p11)
                for name, (row, column) in _PHASE_RATIO_POSITIONS.items():
                    ratio = float(matrix[row][column]) / p11
                    if not math.isfinite(ratio):
                        raise InterpolationError(f"Non-finite normalized phase ratio {name}.")
                    ratio_values[name].append(ratio)
            source_basis["p11"].append(p11_values)
            for name, values in ratio_values.items():
                source_basis[name].append(values)

        angle_aligned = {
            name: [_linear(optics.scattering_angles, values, angles) for values in by_size]
            for name, by_size in source_basis.items()
        }
        # Evaluate all target sizes together for each angle. The scalar form
        # rebuilt and sorted the same source column once per target size.
        # Transpose back to the established [size][angle] layout afterwards.
        phase_basis = {}
        for name, by_size in angle_aligned.items():
            columns = [
                _linear(
                    log_source_size,
                    [row[angle_index] for row in by_size],
                    log_target_size,
                )
                for angle_index in range(len(angles))
            ]
            phase_basis[name] = [list(row) for row in zip(*columns)]
    source_area = optics.projected_area
    source_cext = optics.extinction_cross_section
    if source_cext is None and optics.extinction_efficiency is not None and source_area is not None:
        source_cext = [
            efficiency * area for efficiency, area in zip(optics.extinction_efficiency, source_area)
        ]
    source_csca = optics.scattering_cross_section
    if source_csca is None and optics.scattering_efficiency is not None and source_area is not None:
        source_csca = [
            efficiency * area for efficiency, area in zip(optics.scattering_efficiency, source_area)
        ]
    if (
        source_csca is None
        and source_cext is not None
        and optics.single_scattering_albedo is not None
    ):
        source_csca = [
            extinction * ssa
            for extinction, ssa in zip(source_cext, optics.single_scattering_albedo)
        ]
    return {
        "cext": size_values(source_cext, positive=True),
        "csca": size_values(source_csca, positive=True),
        "area": size_values(optics.projected_area, positive=True),
        "g": size_values(optics.asymmetry_factor),
        "phase_basis": phase_basis,
    }


def _weighted(
    values: Sequence[Sequence[float] | None],
    weights: Sequence[float],
    name: str,
    corrections: list[str],
) -> list[float] | None:
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise InterpolationError(f"Source nodes inconsistently provide {name}.")
    arrays = [value for value in values if value is not None]
    if len({len(value) for value in arrays}) != 1:
        raise InterpolationError(f"Source nodes have inconsistent {name} lengths.")
    if len(arrays) == 1:
        return list(arrays[0])
    positive_names = {"cext", "csca", "area"}
    if name in positive_names and all(value > 0 for array in arrays for value in array):
        result = [
            math.exp(sum(weight * math.log(array[i]) for weight, array in zip(weights, arrays)))
            for i in range(len(arrays[0]))
        ]
    else:
        result = [
            sum(weight * array[i] for weight, array in zip(weights, arrays))
            for i in range(len(arrays[0]))
        ]
    if name in positive_names:
        clipped = [max(0.0, value) for value in result]
        if clipped != result:
            corrections.append(f"{name}:clipped_nonnegative")
        result = clipped
    if name == "g":
        clipped = [min(1.0, max(-1.0, value)) for value in result]
        if clipped != result:
            corrections.append("g:clipped_to_minus1_plus1")
        result = clipped
    return result


def _weighted_phase_basis(
    bases: Sequence[Any], weights: Sequence[float], corrections: list[str]
) -> Any:
    if all(basis is None for basis in bases):
        return None
    if any(basis is None for basis in bases):
        raise InterpolationError("Source nodes inconsistently provide phase_matrix.")
    fields = ("p11", *_PHASE_RATIO_POSITIONS)
    interpolated: dict[str, list[list[float]]] = {name: [] for name in fields}
    for name in fields:
        for size_index in range(len(bases[0][name])):
            interpolated[name].append(
                [
                    sum(
                        weight * basis[name][size_index][angle_index]
                        for weight, basis in zip(weights, bases)
                    )
                    for angle_index in range(len(bases[0][name][size_index]))
                ]
            )
    result = []
    for size_index in range(len(interpolated["p11"])):
        angle_result = []
        for angle_index in range(len(interpolated["p11"][size_index])):
            p11 = interpolated["p11"][size_index][angle_index]
            if p11 < 0.0:
                p11 = 0.0
                if "p11:clipped_nonnegative" not in corrections:
                    corrections.append("p11:clipped_nonnegative")
            p12 = interpolated["p12_over_p11"][size_index][angle_index] * p11
            p22 = interpolated["p22_over_p11"][size_index][angle_index] * p11
            p33 = interpolated["p33_over_p11"][size_index][angle_index] * p11
            p44 = interpolated["p44_over_p11"][size_index][angle_index] * p11
            p43 = interpolated["p43_over_p11"][size_index][angle_index] * p11
            matrix = [
                [p11, p12, 0.0, 0.0],
                [p12, p22, 0.0, 0.0],
                [0.0, 0.0, p33, -p43],
                [0.0, 0.0, p43, p44],
            ]
            angle_result.append(matrix)
        result.append(angle_result)
    return result


def _normalize_phase(phase: Any, angles: Sequence[float]) -> None:
    radians = [math.radians(value) for value in angles]
    for size_matrix in phase:
        integral = 0.0
        for index in range(1, len(radians)):
            y0 = size_matrix[index - 1][0][0] * math.sin(radians[index - 1])
            y1 = size_matrix[index][0][0] * math.sin(radians[index])
            integral += 0.5 * (y0 + y1) * (radians[index] - radians[index - 1])
        norm = 0.5 * integral
        if norm <= 0:
            raise InterpolationError(
                "P11 cannot be normalized because its angular integral is non-positive."
            )
        for matrix in size_matrix:
            for row in range(4):
                for column in range(4):
                    matrix[row][column] /= norm


@_registration_required
def solid_angle_weighted_relative_l2_error(
    interpolated: Sequence[float],
    truth: Sequence[float],
    angles_degrees: Sequence[float],
) -> float:
    """Return the nonuniform-angle, solid-angle-weighted relative L2 error (%)."""

    if not (len(interpolated) == len(truth) == len(angles_degrees)):
        raise InterpolationError("Interpolated, truth, and angle arrays must have equal lengths.")
    if len(angles_degrees) < 2:
        raise InterpolationError("Solid-angle L2 error requires at least two angles.")
    angles = [math.radians(float(value)) for value in angles_degrees]
    if any(right <= left for left, right in zip(angles, angles[1:])):
        raise InterpolationError("Scattering angles must be strictly increasing.")
    candidate = [float(value) for value in interpolated]
    reference = [float(value) for value in truth]
    if any(not math.isfinite(value) for value in (*candidate, *reference)):
        raise InterpolationError("Phase validation arrays must be finite.")
    numerator = 0.0
    denominator = 0.0
    for index in range(1, len(angles)):
        width = angles[index] - angles[index - 1]
        left_weight = math.sin(angles[index - 1])
        right_weight = math.sin(angles[index])
        left_difference = candidate[index - 1] - reference[index - 1]
        right_difference = candidate[index] - reference[index]
        numerator += (
            0.5 * width * (left_difference**2 * left_weight + right_difference**2 * right_weight)
        )
        denominator += (
            0.5
            * width
            * (reference[index - 1] ** 2 * left_weight + reference[index] ** 2 * right_weight)
        )
    if denominator <= 0.0:
        if numerator <= 0.0:
            return 0.0
        raise InterpolationError(
            "Relative phase error is undefined because the truth norm is zero."
        )
    return 100.0 * math.sqrt(numerator / denominator)


@_registration_required
def phase_matrix_solid_angle_relative_l2_errors(
    interpolated_phase: Sequence[Any],
    true_phase: Sequence[Any],
    angles_degrees: Sequence[float],
    xsize: Sequence[float],
    *,
    minimum_xsize: float = 0.1,
    maximum_xsize: float = 50.0,
) -> dict[str, float]:
    """Average phase-basis L2 errors arithmetically over selected size points."""

    if not (len(interpolated_phase) == len(true_phase) == len(xsize)):
        raise InterpolationError(
            "Interpolated phase, true phase, and xsize arrays must have equal lengths."
        )
    if minimum_xsize > maximum_xsize:
        raise InterpolationError("minimum_xsize cannot exceed maximum_xsize.")
    selected = [
        index for index, value in enumerate(xsize) if minimum_xsize <= float(value) <= maximum_xsize
    ]
    if not selected:
        raise InterpolationError("No xsize samples lie in the requested validation range.")

    def basis(size_matrix: Any) -> dict[str, list[float]]:
        result = {"p11": [], **{name: [] for name in _PHASE_RATIO_POSITIONS}}
        if len(size_matrix) != len(angles_degrees):
            raise InterpolationError("Phase angle dimension does not match angles_degrees.")
        for matrix in size_matrix:
            p11 = float(matrix[0][0])
            if not math.isfinite(p11) or p11 <= 0.0:
                raise InterpolationError(
                    "P11 must be finite and positive for phase-ratio validation."
                )
            result["p11"].append(p11)
            for name, (row, column) in _PHASE_RATIO_POSITIONS.items():
                result[name].append(float(matrix[row][column]) / p11)
        return result

    errors = {"p11": [], **{name: [] for name in _PHASE_RATIO_POSITIONS}}
    for index in selected:
        candidate = basis(interpolated_phase[index])
        reference = basis(true_phase[index])
        for name in errors:
            errors[name].append(
                solid_angle_weighted_relative_l2_error(
                    candidate[name], reference[name], angles_degrees
                )
            )
    return {name: sum(values) / len(values) for name, values in errors.items()}


@_registration_required
def interpolate_nodes(
    particle_type: str,
    nodes: Sequence[OpticalNode],
    target_coordinates: Mapping[str, float | str],
    *,
    target_size_um: Sequence[float] | None = None,
    target_angles_degrees: Sequence[float] | None = None,
    sparse_power: float = 2.0,
    phase_normalization: str = "preserve",
) -> InterpolatedOpticalProduct:
    """Generate an actual in-domain interpolated single-particle optical product."""

    if not nodes:
        raise InterpolationError("At least one optical source node is required.")
    if phase_normalization not in {"preserve", "unit_solid_angle"}:
        raise InterpolationError("phase_normalization must be 'preserve' or 'unit_solid_angle'.")
    canonical, axes, target, prepared = _validate_target(particle_type, target_coordinates, nodes)
    method, selected, weights, distances, transforms = _select_neighbors(
        axes, target, prepared, sparse_power=sparse_power
    )
    sizes = _common_grid([node.optics.sizes for node in selected], target_size_um)
    phase_nodes = [node for node in selected if node.optics.phase_matrix is not None]
    angles: list[float] = []
    if phase_nodes:
        if len(phase_nodes) != len(selected):
            raise InterpolationError("Source nodes inconsistently provide phase matrices.")
        angles = _common_grid(
            [node.optics.scattering_angles or [] for node in selected],
            target_angles_degrees,
        )
        if len(angles) < 2:
            raise InterpolationError("Phase-matrix interpolation requires at least two angles.")

    aligned = [_resample_node(node, sizes, angles) for node in selected]
    corrections: list[str] = []
    if any(entry["cext"] is None for entry in aligned):
        raise InterpolationError(
            "Physical interpolation requires Cext at every source node, either "
            "directly or derived from Qext and projected_area."
        )
    values = {
        name: _weighted([entry[name] for entry in aligned], weights, name, corrections)
        for name in ("cext", "csca", "area", "g")
    }
    phase = _weighted_phase_basis([entry["phase_basis"] for entry in aligned], weights, corrections)
    if phase is not None and phase_normalization == "unit_solid_angle":
        _normalize_phase(phase, angles)

    if values["cext"] is not None and values["csca"] is not None:
        adjusted = [min(cext, max(0.0, csca)) for cext, csca in zip(values["cext"], values["csca"])]
        if adjusted != values["csca"]:
            corrections.append("csca:clipped_to_cext")
            values["csca"] = adjusted
        cabs = [max(0.0, cext - csca) for cext, csca in zip(values["cext"], values["csca"])]
        corrections.append("cabs:derived_as_cext_minus_csca")
        ssa = [
            csca / cext if cext > 0.0 else 0.0 for cext, csca in zip(values["cext"], values["csca"])
        ]
        if any(not 0.0 <= value <= 1.0 for value in ssa):
            raise InterpolationError("Derived SSA lies outside its physical range [0, 1].")
    else:
        cabs = None
        ssa = None
    area = values["area"]
    qext = (
        [cext / projected for cext, projected in zip(values["cext"], area)]
        if area is not None
        else None
    )
    qsca = (
        [csca / projected for csca, projected in zip(values["csca"], area)]
        if area is not None and values["csca"] is not None
        else None
    )
    qabs = (
        [absorption / projected for absorption, projected in zip(cabs, area)]
        if area is not None and cabs is not None
        else None
    )

    provenance = InterpolationProvenance(
        method=method,
        particle_type=canonical,
        target_coordinates=dict(target),
        axis_transforms=transforms,
        optical_transforms={
            "extinction_and_scattering_cross_sections": "log_value",
            "projected_area": "log_value",
            "efficiencies": "derived_from_cross_section_divided_by_projected_area",
            "single_scattering_albedo": "derived_as_csca_divided_by_cext",
            "size": "log_coordinate",
            "asymmetry_factor": "linear",
            "phase_p11": "linear",
            "phase_ratios": "normalized_at_source_node_then_linear",
        },
        neighbors=[
            InterpolationNeighbor(
                source=node.source,
                coordinates=dict(node.coordinates),
                weight=float(weight),
                normalized_distance=float(distance),
            )
            for node, weight, distance in zip(selected, weights, distances)
        ],
        size_grid_um=list(sizes),
        angle_grid_degrees=list(angles),
        phase_normalization=phase_normalization,
        constraint_corrections=corrections,
        warnings=(
            ["Sparse-grid inverse-distance fallback used because a rectangular corner was missing."]
            if method == "inverse_distance_sparse"
            else []
        ),
    )
    optics = SingleParticleOptics(
        sizes=list(sizes),
        size_unit="um",
        extinction_cross_section=values["cext"],
        scattering_cross_section=values["csca"],
        absorption_cross_section=cabs,
        extinction_efficiency=qext,
        scattering_efficiency=qsca,
        absorption_efficiency=qabs,
        asymmetry_factor=values["g"],
        phase_matrix=phase,
        scattering_angles=list(angles) if angles else None,
        cross_section_unit="m2",
        metadata={
            "particle_type": canonical,
            "interpolation_provenance": provenance.to_dict(),
        },
        projected_area=area,
        single_scattering_albedo=ssa,
    )
    return InterpolatedOpticalProduct(canonical, dict(target), optics, provenance)


@_registration_required
def interpolate_sources(
    particle_type: str,
    sources: Sequence[OpticalSourceRequest],
    target_coordinates: Mapping[str, float | str],
    **kwargs: Any,
) -> InterpolatedOpticalProduct:
    """Load cached/local L1 files and interpolate them into one optical product."""

    nodes = [
        OpticalNode(
            coordinates=source.coordinates,
            optics=load_single(
                source.path,
                include_phase_matrix=source.include_phase_matrix,
                size_dataset=source.size_dataset,
                coordinate_indices=dict(source.coordinate_indices),
                wavelength_um=source.wavelength_um,
            ),
            source=str(Path(source.path)),
        )
        for source in sources
    ]
    return interpolate_nodes(particle_type, nodes, target_coordinates, **kwargs)


def _netcdf_attributes(value: Any) -> dict[str, Any]:
    return {name: value.getncattr(name) for name in value.ncattrs()}


def _native_schema_matches(path: Path, template_path: Path, target: float) -> bool:
    """Return whether a cached output retains the template's complete NC schema."""

    try:
        import numpy as np
        from netCDF4 import Dataset

        from zju_scatt_interface.optics.retrieval.native import _attributes_equal

        with Dataset(template_path) as template, Dataset(path) as output:
            if not _attributes_equal(output, template):
                return False
            if set(output.dimensions) != set(template.dimensions):
                return False
            for name, dimension in template.dimensions.items():
                candidate = output.dimensions[name]
                if (
                    len(candidate) != len(dimension)
                    or candidate.isunlimited() != dimension.isunlimited()
                ):
                    return False
            if set(output.variables) != set(template.variables):
                return False
            for name, source in template.variables.items():
                candidate = output.variables[name]
                if candidate.dimensions != source.dimensions:
                    return False
                if candidate.dtype != source.dtype:
                    return False
                if not _attributes_equal(candidate, source):
                    return False
            return math.isclose(
                float(output.variables["wavelength"][:]),
                target,
                rel_tol=0.0,
                abs_tol=max(
                    1e-12, float(np.finfo(output.variables["wavelength"].dtype).eps) * abs(target)
                ),
            )
    except (OSError, KeyError, RuntimeError, ValueError):
        return False


def _native_product_matches_candidate(path: Path, candidate_path: Path) -> bool:
    """Return whether a cached native product has the current numerical result."""

    try:
        import numpy as np
        from netCDF4 import Dataset

        from zju_scatt_interface.optics.retrieval.native import _attributes_equal

        with Dataset(candidate_path) as candidate, Dataset(path) as cached:
            if not _attributes_equal(cached, candidate):
                return False
            if set(cached.dimensions) != set(candidate.dimensions):
                return False
            if set(cached.variables) != set(candidate.variables):
                return False
            for name, expected in candidate.variables.items():
                actual = cached.variables[name]
                if (
                    actual.dimensions != expected.dimensions
                    or actual.dtype != expected.dtype
                    or not _attributes_equal(actual, expected)
                ):
                    return False
                left = np.ma.filled(actual[:], np.nan)
                right = np.ma.filled(expected[:], np.nan)
                if np.issubdtype(np.asarray(left).dtype, np.number):
                    if not np.allclose(left, right, rtol=1e-12, atol=1e-14, equal_nan=True):
                        return False
                elif not np.array_equal(left, right):
                    return False
            return True
    except (OSError, KeyError, RuntimeError, TypeError, ValueError):
        return False


def _create_native_variable(dataset: Any, name: str, source: Any) -> Any:
    attributes = _netcdf_attributes(source)
    fill_value = attributes.pop("_FillValue", None)
    filters = source.filters() or {}
    chunking = source.chunking()
    options: dict[str, Any] = {}
    if fill_value is not None:
        options["fill_value"] = fill_value
    if filters.get("zlib"):
        options.update(
            zlib=True,
            complevel=filters.get("complevel", 4),
            shuffle=filters.get("shuffle", True),
        )
    if filters.get("fletcher32"):
        options["fletcher32"] = True
    if isinstance(chunking, list):
        options["chunksizes"] = tuple(chunking)
    elif chunking == "contiguous" and source.dimensions:
        options["contiguous"] = True
    variable = dataset.createVariable(name, source.dtype, source.dimensions, **options)
    variable.setncatts(attributes)
    return variable


def _weighted_native(
    lower: Any,
    upper: Any,
    fraction: float,
    *,
    positive: bool = False,
) -> Any:
    import numpy as np

    left = np.asarray(lower, dtype=float)
    right = np.asarray(upper, dtype=float)
    if positive and np.all(left > 0) and np.all(right > 0):
        return np.exp((1.0 - fraction) * np.log(left) + fraction * np.log(right))
    return (1.0 - fraction) * left + fraction * right


def _align_native_size_axis(
    values: Any,
    source_grid: Any,
    target_grid: Any,
    axis: int,
    *,
    positive: bool = False,
) -> tuple[Any, int]:
    """Align one native variable to a size grid without changing its shape."""

    import numpy as np

    source = np.asarray(source_grid, dtype=float)
    target = np.asarray(target_grid, dtype=float)
    if np.any(source <= 0.0) or np.any(target <= 0.0):
        raise InterpolationError("xsize_veq values must be positive.")
    array = np.asarray(values, dtype=float)
    moved = np.moveaxis(array, axis, 0)
    columns = moved.reshape(len(source), -1)
    aligned = np.empty((len(target), columns.shape[1]), dtype=float)
    repaired = 0
    log_source = np.log(source)
    log_target = np.log(target)
    for column_index in range(columns.shape[1]):
        column = columns[:, column_index]
        valid = np.isfinite(column) & np.isfinite(log_source)
        if positive:
            valid &= column > 0.0
        if np.count_nonzero(valid) < 2:
            raise InterpolationError(
                "A native size-dependent variable has fewer than two valid points."
            )
        valid_x = log_source[valid]
        valid_y = np.log(column[valid]) if positive else column[valid]
        epsilon = 1e-12
        if log_target[0] < valid_x[0] - epsilon or log_target[-1] > valid_x[-1] + epsilon:
            raise InterpolationError(
                "A bracketing file does not cover the native template size grid."
            )
        result = np.interp(log_target, valid_x, valid_y)
        aligned[:, column_index] = np.exp(result) if positive else result
        if len(source) == len(target) and np.allclose(source, target, rtol=1e-10, atol=1e-12):
            repaired += int(np.count_nonzero(~valid))
    restored = aligned.reshape((len(target),) + moved.shape[1:])
    return np.moveaxis(restored, 0, axis), repaired


def _native_phase_ratio(numerator: Any, p11: Any) -> Any:
    """Normalize a native phase element at its original database nodes."""

    import numpy as np

    numerator_array = np.asarray(numerator, dtype=float)
    p11_array = np.asarray(p11, dtype=float)
    if numerator_array.shape != p11_array.shape:
        raise InterpolationError("Native phase elements do not share the P11 shape.")
    return np.divide(
        numerator_array,
        p11_array,
        out=np.full_like(numerator_array, np.nan),
        where=np.isfinite(p11_array) & (p11_array > 0.0),
    )


def _native_phase_variable_stores_ratio(variable: Any) -> bool:
    descriptions = []
    for name in ("description", "long_name"):
        if name in variable.ncattrs():
            descriptions.append(str(variable.getncattr(name)).strip().casefold())
    text = " ".join(descriptions)
    return any(
        marker in text for marker in ("scaled by p11", "normalized by p11", "divided by p11")
    )


def _align_native_angle_axis(
    values: Any,
    angles: Any,
    axis: int,
) -> tuple[Any, int]:
    """Fill only interior nonfinite padding on a native angular union grid."""

    import numpy as np

    coordinates = np.asarray(angles, dtype=float)
    if coordinates.ndim != 1 or np.any(np.diff(coordinates) <= 0.0):
        raise InterpolationError("Native scattering angles must be one-dimensional and increasing.")
    array = np.asarray(values, dtype=float)
    moved = np.moveaxis(array, axis, 0)
    columns = moved.reshape(len(coordinates), -1)
    aligned = np.empty_like(columns)
    repaired = 0
    for column_index in range(columns.shape[1]):
        column = columns[:, column_index]
        valid = np.isfinite(column)
        if np.count_nonzero(valid) < 2:
            raise InterpolationError(
                "A native phase basis has fewer than two finite angular points."
            )
        valid_indices = np.flatnonzero(valid)
        if valid_indices[0] != 0 or valid_indices[-1] != len(coordinates) - 1:
            raise InterpolationError("Native phase-angle padding would require extrapolation.")
        aligned[:, column_index] = np.interp(coordinates, coordinates[valid], column[valid])
        repaired += int(np.count_nonzero(~valid))
    restored = aligned.reshape(moved.shape)
    return np.moveaxis(restored, 0, axis), repaired


def write_native_interpolated_ice_netcdf(
    lower_path: str | Path,
    upper_path: str | Path,
    target_wavelength_um: float,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, str, dict[str, Any]]:
    """Clone the native L1.5 schema and interpolate all native data variables."""

    try:
        import numpy as np
        from netCDF4 import Dataset
    except ImportError as exc:  # pragma: no cover - installation-dependent
        raise RuntimeError("Native NetCDF interpolation requires numpy and netCDF4.") from exc

    lower_source = Path(lower_path).expanduser().resolve()
    upper_source = Path(upper_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    target = float(target_wavelength_um)

    with Dataset(lower_source) as lower, Dataset(upper_source) as upper:
        from zju_scatt_interface.optics.retrieval.native import _attributes_equal

        if not _attributes_equal(lower, upper):
            raise InterpolationError("Bracketing files have different global attributes.")
        if set(lower.dimensions) != set(upper.dimensions):
            raise InterpolationError("Bracketing files have different dimensions.")
        if set(lower.variables) != set(upper.variables):
            raise InterpolationError("Bracketing files have different variables.")
        for name, left in lower.variables.items():
            right = upper.variables[name]
            if (
                left.dimensions != right.dimensions
                or left.dtype != right.dtype
                or not _attributes_equal(left, right)
            ):
                raise InterpolationError(
                    f"Bracketing files have incompatible definitions for {name!r}."
                )

        lower_wavelength = float(lower.variables["wavelength"][:])
        upper_wavelength = float(upper.variables["wavelength"][:])
        if not lower_wavelength < target < upper_wavelength:
            raise InterpolationError(
                f"Target {target:g} um is not bracketed by "
                f"{lower_wavelength:g} and {upper_wavelength:g} um."
            )
        fraction = (target - lower_wavelength) / (upper_wavelength - lower_wavelength)
        size_dimension = lower.variables["xsize_veq"].dimensions[0]
        lower_sizes = np.asarray(lower.variables["xsize_veq"][:], dtype=float)
        upper_sizes = np.asarray(upper.variables["xsize_veq"][:], dtype=float)
        if lower_sizes.ndim != 1 or upper_sizes.ndim != 1:
            raise InterpolationError("xsize_veq must be a one-dimensional grid.")
        if np.any(np.diff(lower_sizes) <= 0) or np.any(np.diff(upper_sizes) <= 0):
            raise InterpolationError("xsize_veq grids must be strictly increasing.")
        epsilon = 1e-12
        lower_covered = (
            lower_sizes[0] >= upper_sizes[0] - epsilon
            and lower_sizes[-1] <= upper_sizes[-1] + epsilon
        )
        upper_covered = (
            upper_sizes[0] >= lower_sizes[0] - epsilon
            and upper_sizes[-1] <= lower_sizes[-1] + epsilon
        )
        if lower_covered:
            template = lower
            template_source = lower_source
            template_sizes = lower_sizes
        elif upper_covered:
            template = upper
            template_source = upper_source
            template_sizes = upper_sizes
        else:
            raise InterpolationError(
                "Neither native size grid is fully covered by the other source."
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".part")
        repaired_nonfinite = 0
        try:
            with Dataset(temporary, "w", format=template.data_model) as destination:
                for name, dimension in template.dimensions.items():
                    length = None if dimension.isunlimited() else len(dimension)
                    destination.createDimension(name, length)
                destination.setncatts(_netcdf_attributes(template))
                for name, source in template.variables.items():
                    _create_native_variable(destination, name, source)

                fixed_scalars = {"temperature", "ssph_n", "ssph_asp"}
                phase_variables = {"p11", "p12", "p22", "p33", "p43", "p44"}
                scattering_cross_sections = {"csca", "c_sca", "scattering_cross_section"}
                absorption_cross_sections = {"cabs", "c_abs", "absorption_cross_section"}
                efficiency_variables = {"qext", "qsca", "qabs", "q_ext", "q_sca", "q_abs"}
                source_csca_name = next(
                    (name for name in scattering_cross_sections if name in lower.variables),
                    None,
                )
                available_phase = phase_variables.intersection(template.variables)
                if available_phase and available_phase != phase_variables:
                    missing = ", ".join(sorted(phase_variables - available_phase))
                    raise InterpolationError(
                        "Native phase-ratio interpolation requires all six elements; "
                        f"missing {missing}."
                    )
                for name, definition in template.variables.items():
                    target_variable = destination.variables[name]
                    source = lower.variables[name]
                    right = upper.variables[name]
                    if name == "wavelength":
                        target_variable.assignValue(target)
                        continue
                    if name in {"mr", "mi"}:
                        target_variable.assignValue(
                            float(_weighted_native(source[:], right[:], fraction))
                        )
                        continue
                    if not definition.dimensions:
                        left_value = source[:]
                        right_value = right[:]
                        if name in fixed_scalars and not np.allclose(
                            left_value, right_value, rtol=0.0, atol=1e-12
                        ):
                            raise InterpolationError(
                                f"Fixed coordinate {name!r} differs between sources."
                            )
                        target_variable.assignValue(float(definition[:]))
                        continue
                    if size_dimension not in definition.dimensions:
                        left_value = np.asarray(source[:])
                        right_value = np.asarray(right[:])
                        if not np.array_equal(left_value, right_value):
                            raise InterpolationError(f"Non-wavelength coordinate {name!r} differs.")
                        target_variable[:] = np.asarray(definition[:])
                        continue
                    axis = definition.dimensions.index(size_dimension)
                    if name in {"xsize_maxd", "xsize_veq"}:
                        value = np.asarray(definition[:])
                        target_variable[:] = value
                        continue
                    if name in phase_variables:
                        p11_left = lower.variables["p11"]
                        p11_right = upper.variables["p11"]
                        if source.dimensions != p11_left.dimensions:
                            raise InterpolationError(
                                f"Native phase element {name!r} does not share P11 dimensions."
                            )
                        stores_ratio = name != "p11" and _native_phase_variable_stores_ratio(
                            definition
                        )
                        left_ratio = (
                            np.asarray(source[:], dtype=float)
                            if name == "p11" or stores_ratio
                            else _native_phase_ratio(source[:], p11_left[:])
                        )
                        right_ratio = (
                            np.asarray(right[:], dtype=float)
                            if name == "p11" or stores_ratio
                            else _native_phase_ratio(right[:], p11_right[:])
                        )
                        if "sca_angle" not in source.dimensions:
                            raise InterpolationError(
                                f"Native phase element {name!r} has no sca_angle dimension."
                            )
                        angle_axis = source.dimensions.index("sca_angle")
                        left_ratio, repaired = _align_native_angle_axis(
                            left_ratio,
                            lower.variables["sca_angle"][:],
                            angle_axis,
                        )
                        repaired_nonfinite += repaired
                        right_ratio, repaired = _align_native_angle_axis(
                            right_ratio,
                            upper.variables["sca_angle"][:],
                            angle_axis,
                        )
                        repaired_nonfinite += repaired
                        left_value, repaired = _align_native_size_axis(
                            left_ratio,
                            lower_sizes,
                            template_sizes,
                            axis,
                        )
                        repaired_nonfinite += repaired
                        right_value, repaired = _align_native_size_axis(
                            right_ratio,
                            upper_sizes,
                            template_sizes,
                            axis,
                        )
                        repaired_nonfinite += repaired
                    elif (
                        name == "ssa"
                        or name in efficiency_variables
                        or name in absorption_cross_sections
                    ):
                        # These variables are derived below from cross sections,
                        # so raw normalized values are never interpolated.
                        left_value = right_value = None
                    else:
                        size_positive = (
                            name in {"cext", "proj_area"} or name in scattering_cross_sections
                        )
                        left_value, repaired = _align_native_size_axis(
                            source[:],
                            lower_sizes,
                            template_sizes,
                            axis,
                            positive=size_positive,
                        )
                        repaired_nonfinite += repaired
                        right_value, repaired = _align_native_size_axis(
                            right[:],
                            upper_sizes,
                            template_sizes,
                            axis,
                            positive=size_positive,
                        )
                        repaired_nonfinite += repaired
                    if name == "cext":
                        lower_physical = left_value * (lower_wavelength / (2.0 * math.pi)) ** 2
                        upper_physical = right_value * (upper_wavelength / (2.0 * math.pi)) ** 2
                        physical = _weighted_native(
                            lower_physical,
                            upper_physical,
                            fraction,
                            positive=True,
                        )
                        value = physical / (target / (2.0 * math.pi)) ** 2
                    elif name in scattering_cross_sections:
                        lower_physical = left_value * (lower_wavelength / (2.0 * math.pi)) ** 2
                        upper_physical = right_value * (upper_wavelength / (2.0 * math.pi)) ** 2
                        physical = _weighted_native(
                            lower_physical,
                            upper_physical,
                            fraction,
                            positive=True,
                        )
                        value = physical / (target / (2.0 * math.pi)) ** 2
                    elif name == "ssa":
                        cext_axis = lower.variables["cext"].dimensions.index(size_dimension)
                        lower_ext_source = np.asarray(lower.variables["cext"][:], dtype=float)
                        upper_ext_source = np.asarray(upper.variables["cext"][:], dtype=float)
                        lower_ssa_source = np.asarray(source[:], dtype=float)
                        upper_ssa_source = np.asarray(right[:], dtype=float)
                        lower_ext, _ = _align_native_size_axis(
                            lower_ext_source,
                            lower_sizes,
                            template_sizes,
                            cext_axis,
                            positive=True,
                        )
                        upper_ext, _ = _align_native_size_axis(
                            upper_ext_source,
                            upper_sizes,
                            template_sizes,
                            cext_axis,
                            positive=True,
                        )
                        lower_sca_source = (
                            np.asarray(lower.variables[source_csca_name][:], dtype=float)
                            if source_csca_name is not None
                            else lower_ext_source * lower_ssa_source
                        )
                        upper_sca_source = (
                            np.asarray(upper.variables[source_csca_name][:], dtype=float)
                            if source_csca_name is not None
                            else upper_ext_source * upper_ssa_source
                        )
                        csca_axis = (
                            lower.variables[source_csca_name].dimensions.index(size_dimension)
                            if source_csca_name is not None
                            else cext_axis
                        )
                        lower_sca, _ = _align_native_size_axis(
                            lower_sca_source,
                            lower_sizes,
                            template_sizes,
                            csca_axis,
                            positive=True,
                        )
                        upper_sca, _ = _align_native_size_axis(
                            upper_sca_source,
                            upper_sizes,
                            template_sizes,
                            csca_axis,
                            positive=True,
                        )
                        lower_ext *= (lower_wavelength / (2.0 * math.pi)) ** 2
                        upper_ext *= (upper_wavelength / (2.0 * math.pi)) ** 2
                        extinction = _weighted_native(lower_ext, upper_ext, fraction, positive=True)
                        scattering = _weighted_native(
                            lower_sca * (lower_wavelength / (2.0 * math.pi)) ** 2,
                            upper_sca * (upper_wavelength / (2.0 * math.pi)) ** 2,
                            fraction,
                            positive=True,
                        )
                        value = np.divide(
                            scattering,
                            extinction,
                            out=np.zeros_like(scattering),
                            where=extinction != 0,
                        )
                        if (
                            np.any(~np.isfinite(value))
                            or np.any(value < -1e-12)
                            or np.any(value > 1.0 + 1e-12)
                        ):
                            raise InterpolationError("Derived native SSA lies outside [0, 1].")
                        value = np.clip(value, 0.0, 1.0)
                    elif name in absorption_cross_sections:
                        cext_axis = lower.variables["cext"].dimensions.index(size_dimension)
                        lower_ext, _ = _align_native_size_axis(
                            lower.variables["cext"][:],
                            lower_sizes,
                            template_sizes,
                            cext_axis,
                            positive=True,
                        )
                        upper_ext, _ = _align_native_size_axis(
                            upper.variables["cext"][:],
                            upper_sizes,
                            template_sizes,
                            cext_axis,
                            positive=True,
                        )
                        if source_csca_name is not None:
                            csca_axis = lower.variables[source_csca_name].dimensions.index(
                                size_dimension
                            )
                            lower_sca, _ = _align_native_size_axis(
                                lower.variables[source_csca_name][:],
                                lower_sizes,
                                template_sizes,
                                csca_axis,
                                positive=True,
                            )
                            upper_sca, _ = _align_native_size_axis(
                                upper.variables[source_csca_name][:],
                                upper_sizes,
                                template_sizes,
                                csca_axis,
                                positive=True,
                            )
                        else:
                            lower_sca, _ = _align_native_size_axis(
                                np.asarray(lower.variables["cext"][:], dtype=float)
                                * np.asarray(lower.variables["ssa"][:], dtype=float),
                                lower_sizes,
                                template_sizes,
                                cext_axis,
                                positive=True,
                            )
                            upper_sca, _ = _align_native_size_axis(
                                np.asarray(upper.variables["cext"][:], dtype=float)
                                * np.asarray(upper.variables["ssa"][:], dtype=float),
                                upper_sizes,
                                template_sizes,
                                cext_axis,
                                positive=True,
                            )
                        extinction = _weighted_native(
                            lower_ext * (lower_wavelength / (2.0 * math.pi)) ** 2,
                            upper_ext * (upper_wavelength / (2.0 * math.pi)) ** 2,
                            fraction,
                            positive=True,
                        )
                        scattering = _weighted_native(
                            lower_sca * (lower_wavelength / (2.0 * math.pi)) ** 2,
                            upper_sca * (upper_wavelength / (2.0 * math.pi)) ** 2,
                            fraction,
                            positive=True,
                        )
                        value = (
                            np.maximum(extinction - scattering, 0.0)
                            / (target / (2.0 * math.pi)) ** 2
                        )
                    elif name in efficiency_variables:
                        if "proj_area" not in lower.variables:
                            raise InterpolationError(
                                "Efficiency output requires native projected area."
                            )
                        cext_axis = lower.variables["cext"].dimensions.index(size_dimension)
                        area_axis = lower.variables["proj_area"].dimensions.index(size_dimension)
                        lower_ext, _ = _align_native_size_axis(
                            lower.variables["cext"][:],
                            lower_sizes,
                            template_sizes,
                            cext_axis,
                            positive=True,
                        )
                        upper_ext, _ = _align_native_size_axis(
                            upper.variables["cext"][:],
                            upper_sizes,
                            template_sizes,
                            cext_axis,
                            positive=True,
                        )
                        lower_area, _ = _align_native_size_axis(
                            lower.variables["proj_area"][:],
                            lower_sizes,
                            template_sizes,
                            area_axis,
                            positive=True,
                        )
                        upper_area, _ = _align_native_size_axis(
                            upper.variables["proj_area"][:],
                            upper_sizes,
                            template_sizes,
                            area_axis,
                            positive=True,
                        )
                        extinction = _weighted_native(
                            lower_ext * (lower_wavelength / (2.0 * math.pi)) ** 2,
                            upper_ext * (upper_wavelength / (2.0 * math.pi)) ** 2,
                            fraction,
                            positive=True,
                        )
                        if name in {"qsca", "q_sca", "qabs", "q_abs"}:
                            if source_csca_name is not None:
                                csca_axis = lower.variables[source_csca_name].dimensions.index(
                                    size_dimension
                                )
                                lower_sca, _ = _align_native_size_axis(
                                    lower.variables[source_csca_name][:],
                                    lower_sizes,
                                    template_sizes,
                                    csca_axis,
                                    positive=True,
                                )
                                upper_sca, _ = _align_native_size_axis(
                                    upper.variables[source_csca_name][:],
                                    upper_sizes,
                                    template_sizes,
                                    csca_axis,
                                    positive=True,
                                )
                            else:
                                lower_sca, _ = _align_native_size_axis(
                                    np.asarray(lower.variables["cext"][:], dtype=float)
                                    * np.asarray(lower.variables["ssa"][:], dtype=float),
                                    lower_sizes,
                                    template_sizes,
                                    cext_axis,
                                    positive=True,
                                )
                                upper_sca, _ = _align_native_size_axis(
                                    np.asarray(upper.variables["cext"][:], dtype=float)
                                    * np.asarray(upper.variables["ssa"][:], dtype=float),
                                    upper_sizes,
                                    template_sizes,
                                    cext_axis,
                                    positive=True,
                                )
                            scattering = _weighted_native(
                                lower_sca * (lower_wavelength / (2.0 * math.pi)) ** 2,
                                upper_sca * (upper_wavelength / (2.0 * math.pi)) ** 2,
                                fraction,
                                positive=True,
                            )
                            numerator = (
                                scattering
                                if name in {"qsca", "q_sca"}
                                else np.maximum(extinction - scattering, 0.0)
                            )
                        else:
                            numerator = extinction
                        area = _weighted_native(
                            lower_area * (lower_wavelength / (2.0 * math.pi)) ** 2,
                            upper_area * (upper_wavelength / (2.0 * math.pi)) ** 2,
                            fraction,
                            positive=True,
                        )
                        value = np.divide(
                            numerator,
                            area,
                            out=np.zeros_like(extinction),
                            where=area > 0.0,
                        )
                    elif name == "proj_area":
                        lower_area = left_value * (lower_wavelength / (2.0 * math.pi)) ** 2
                        upper_area = right_value * (upper_wavelength / (2.0 * math.pi)) ** 2
                        area = _weighted_native(lower_area, upper_area, fraction, positive=True)
                        value = area / (target / (2.0 * math.pi)) ** 2
                    elif name in phase_variables - {"p11"}:
                        ratio = _weighted_native(left_value, right_value, fraction)
                        if _native_phase_variable_stores_ratio(definition):
                            value = ratio
                            target_variable[:] = value
                            continue
                        p11_axis = lower.variables["p11"].dimensions.index(size_dimension)
                        p11_angle_axis = lower.variables["p11"].dimensions.index("sca_angle")
                        lower_p11_source, _ = _align_native_angle_axis(
                            lower.variables["p11"][:],
                            lower.variables["sca_angle"][:],
                            p11_angle_axis,
                        )
                        upper_p11_source, _ = _align_native_angle_axis(
                            upper.variables["p11"][:],
                            upper.variables["sca_angle"][:],
                            p11_angle_axis,
                        )
                        lower_p11, _ = _align_native_size_axis(
                            lower_p11_source, lower_sizes, template_sizes, p11_axis
                        )
                        upper_p11, _ = _align_native_size_axis(
                            upper_p11_source, upper_sizes, template_sizes, p11_axis
                        )
                        p11 = _weighted_native(lower_p11, upper_p11, fraction)
                        value = ratio * np.maximum(p11, 0.0)
                    else:
                        value = _weighted_native(
                            left_value,
                            right_value,
                            fraction,
                            positive=(
                                name in {"cext", "proj_area"} or name in scattering_cross_sections
                            ),
                        )
                        if name == "g":
                            value = np.clip(value, -1.0, 1.0)
                        elif name == "p11":
                            value = np.maximum(value, 0.0)
                        elif name not in phase_variables and not np.all(np.isfinite(value)):
                            raise InterpolationError(f"Interpolation produced non-finite {name!r}.")
                    target_variable[:] = value
            if (
                output.is_file()
                and not overwrite
                and _native_product_matches_candidate(output, temporary)
            ):
                status = "skipped"
            else:
                temporary.replace(output)
                status = "created"
        finally:
            if temporary.exists():
                temporary.unlink()

    details = {
        "native_schema_verified": _native_schema_matches(output, template_source, target),
        "lower_wavelength_um": lower_wavelength,
        "upper_wavelength_um": upper_wavelength,
        "fraction": fraction,
        "size_count": len(template_sizes),
        "template_size_grid_preserved": True,
        "template_source": str(template_source),
        "source_size_grids_aligned": not (
            len(lower_sizes) == len(upper_sizes)
            and np.allclose(lower_sizes, upper_sizes, rtol=1e-10, atol=1e-12)
        ),
        "repaired_nonfinite_values": repaired_nonfinite,
        "interpolation_weight_coordinate": "wavelength_um",
        "refractive_index_role": "output_metadata_only_not_weight_coordinate",
        "scalar_method": "log_cext_log_csca_then_derive_ssa_and_qext",
        "phase_method": "linear_p11_and_source_normalized_ratios",
    }
    if not details["native_schema_verified"]:
        raise InterpolationError("Generated file does not match the native source schema.")
    return output, status, details


def _user_derived_ice_filename(
    lower_path: Path,
    upper_path: Path,
    target_wavelength_um: float,
) -> str:
    """Build a native-style name for a user-derived ice product."""

    try:
        from netCDF4 import Dataset
    except ImportError as exc:  # pragma: no cover - installation-dependent
        raise RuntimeError("Native NetCDF interpolation requires netCDF4.") from exc

    with Dataset(lower_path) as lower, Dataset(upper_path) as upper:
        lower_wavelength = float(lower.variables["wavelength"][:])
        upper_wavelength = float(upper.variables["wavelength"][:])
        fraction = (target_wavelength_um - lower_wavelength) / (upper_wavelength - lower_wavelength)
        target_real = float(
            _weighted_native(lower.variables["mr"][:], upper.variables["mr"][:], fraction)
        )
        target_imaginary = float(
            _weighted_native(lower.variables["mi"][:], upper.variables["mi"][:], fraction)
        )

    replacement = f"_wl_{target_wavelength_um:.3f}_um_ref_{target_real:.3e}_{target_imaginary:.3e}"
    stem = lower_path.name[:-3] if lower_path.name.endswith(".nc") else lower_path.name
    derived_stem, replacements = re.subn(
        r"_wl_[^_]+_um_ref_[^_]+_[^_]+(?=_t_)",
        replacement,
        stem,
        count=1,
    )
    if replacements != 1:
        raise InterpolationError(
            f"Cannot construct a native derived-product filename from {lower_path.name!r}."
        )
    return f"{derived_stem}_user_derived.nc"


def interpolate_downloaded_ice_series(
    downloaded_sources: Sequence[tuple[Any, Path]],
    target_wavelengths_um: Sequence[float],
    output_dir: str | Path,
    *,
    tolerance_um: float = 1e-9,
    include_phase_matrix: bool = False,
    overwrite: bool = False,
) -> list[InterpolatedFileResult]:
    """Interpolate wavelength while preserving every ice series' other axes.

    ``downloaded_sources`` contains ``(RemoteObject, local_path)`` pairs.  Files
    are grouped by their remote series identity, which removes only wavelength
    and wavelength-dependent refractive-index tokens.  Temperature, roundness,
    aspect ratio, database revision, and the source size grid therefore remain
    attached to the original series.
    """

    if tolerance_um < 0:
        raise InterpolationError("Target wavelength tolerance cannot be negative.")
    # Native retrieval products always preserve every source variable, including
    # the phase-matrix elements.  Keep this argument for API compatibility.
    del include_phase_matrix
    targets = [float(value) for value in target_wavelengths_um]
    destination = Path(output_dir).expanduser().resolve()
    groups: dict[str, list[tuple[Any, Path, dict[str, float]]]] = {}
    for remote, raw_path in downloaded_sources:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise InterpolationError(f"Downloaded source file is missing: {path}")
        metadata = extract_scatt_metadata(path.name)
        required = ("wavelength_um", "temperature_k", "n", "aspect_ratio")
        if any(name not in metadata for name in required):
            continue
        if "super_spheroid_ice" not in path.name.casefold():
            continue
        groups.setdefault(object_series_key(remote), []).append((remote, path, metadata))

    results: list[InterpolatedFileResult] = []
    for _, records in sorted(groups.items()):
        records.sort(key=lambda item: item[2]["wavelength_um"])
        reference = records[0][2]
        fixed_coordinates: dict[str, float | str] = {
            "temperature": reference["temperature_k"],
            "roundness": reference["n"],
            "aspect_ratio": reference["aspect_ratio"],
        }
        for target in targets:
            if any(abs(record[2]["wavelength_um"] - target) <= tolerance_um for record in records):
                continue
            lower = [record for record in records if record[2]["wavelength_um"] < target]
            upper = [record for record in records if record[2]["wavelength_um"] > target]
            if not lower or not upper:
                continue
            neighbors = (lower[-1], upper[0])
            source_paths = tuple(record[1] for record in neighbors)
            name = _user_derived_ice_filename(source_paths[0], source_paths[1], target)
            output = destination / name
            output, status, native_details = write_native_interpolated_ice_netcdf(
                source_paths[0],
                source_paths[1],
                target,
                output,
                overwrite=overwrite,
            )
            lower_wavelength = neighbors[0][2]["wavelength_um"]
            upper_wavelength = neighbors[1][2]["wavelength_um"]
            fraction = (target - lower_wavelength) / (upper_wavelength - lower_wavelength)
            provenance = {
                "method": "multilinear",
                "particle_type": "super_spheroid_ice",
                "target_coordinates": {
                    "wavelength": target,
                    **fixed_coordinates,
                },
                "neighbors": [
                    {
                        "source": str(source_paths[0]),
                        "wavelength": lower_wavelength,
                        "weight": 1.0 - fraction,
                    },
                    {
                        "source": str(source_paths[1]),
                        "wavelength": upper_wavelength,
                        "weight": fraction,
                    },
                ],
                "native_schema": native_details,
                "phase_matrix": "preserved_native_variables",
            }
            results.append(
                InterpolatedFileResult(
                    path=output,
                    particle_type="super_spheroid_ice",
                    target_wavelength_um=target,
                    fixed_coordinates=fixed_coordinates,
                    source_paths=source_paths,
                    status=status,
                    provenance=provenance,
                )
            )
    return results


@_registration_required
def write_interpolated_optics_netcdf(product: InterpolatedOpticalProduct, path: str | Path) -> Path:
    """Write a Phase 5 single-particle product with compact provenance."""

    try:
        import numpy as np
        from netCDF4 import Dataset
    except ImportError as exc:  # pragma: no cover - installation-dependent
        raise RuntimeError(
            "NetCDF output requires netCDF4 and numpy; install zju-scatt-interface[netcdf]."
        ) from exc

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    optics = product.optics
    with Dataset(output, "w", format="NETCDF4") as dataset:
        dataset.createDimension("size", len(optics.sizes))
        size_variable = dataset.createVariable("size", "f8", ("size",))
        size_variable[:] = np.asarray(optics.sizes)
        size_variable.units = "um"
        size_parameter_grid = optics.metadata.get("size_parameter_grid")
        if size_parameter_grid is not None:
            if len(size_parameter_grid) != len(optics.sizes):
                raise InterpolationError(
                    "size_parameter_grid must match the interpolated size grid"
                )
            size_parameter = dataset.createVariable(
                str(optics.metadata.get("size_parameter_name", "size_parameter")),
                "f8",
                ("size",),
            )
            size_parameter[:] = np.asarray(size_parameter_grid)
            size_parameter.units = "1"
        if optics.scattering_angles:
            dataset.createDimension("scattering_angle", len(optics.scattering_angles))
            angle_variable = dataset.createVariable("scattering_angle", "f8", ("scattering_angle",))
            angle_variable[:] = np.asarray(optics.scattering_angles)
            angle_variable.units = "degree"
        for name, values, unit in (
            ("extinction_cross_section", optics.extinction_cross_section, "m2"),
            ("scattering_cross_section", optics.scattering_cross_section, "m2"),
            ("absorption_cross_section", optics.absorption_cross_section, "m2"),
            ("projected_area", optics.projected_area, "m2"),
            ("single_scattering_albedo", optics.single_scattering_albedo, "1"),
            ("extinction_efficiency", optics.extinction_efficiency, "1"),
            ("scattering_efficiency", optics.scattering_efficiency, "1"),
            ("absorption_efficiency", optics.absorption_efficiency, "1"),
            ("asymmetry_factor", optics.asymmetry_factor, "1"),
        ):
            if values is not None:
                variable = dataset.createVariable(name, "f8", ("size",))
                variable[:] = np.asarray(values)
                variable.units = optics.cross_section_unit if unit == "m2" else unit
        if optics.phase_matrix is not None:
            dataset.createDimension("stokes_row", 4)
            dataset.createDimension("stokes_column", 4)
            variable = dataset.createVariable(
                "phase_matrix",
                "f8",
                ("size", "scattering_angle", "stokes_row", "stokes_column"),
            )
            variable[:] = np.asarray(optics.phase_matrix)
            variable.units = "1"
        for name, value in product.coordinates.items():
            if isinstance(value, (int, float)):
                variable = dataset.createVariable(name, "f8")
                variable.assignValue(float(value))
                variable.units = (
                    "um" if name == "wavelength" else "K" if name == "temperature" else "1"
                )
            else:
                dataset.setncattr(f"target_{name}", str(value))
        dataset.setncattr("particle_type", product.particle_type)
        dataset.setncattr("interpolation_method", product.provenance.method)
        if "size_grid_alignment" in optics.metadata:
            dataset.setncattr("size_grid_alignment", optics.metadata["size_grid_alignment"])
        dataset.setncattr(
            "interpolation_provenance_json",
            json.dumps(product.provenance.to_dict(), sort_keys=True),
        )
    return output
