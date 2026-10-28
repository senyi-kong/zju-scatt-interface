"""Internal numerical integration kernels and optical file integration."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.errors import ScattError
from zju_scatt_interface.optics.models import BulkOptics, SingleParticleOptics


def _finite_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ScattError(f"{label} must be numeric; got {value!r}") from exc
    if not math.isfinite(result):
        raise ScattError(f"{label} must be finite; got {value!r}")
    return result


def _finite_float_list(values: Sequence[Any], label: str) -> list[float]:
    result = [_finite_float(value, label) for value in values]
    if not result:
        raise ScattError(f"{label} cannot be empty")
    return result


def _optional_float_list(
    values: Optional[Sequence[Any]],
    label: str,
    size: int,
) -> Optional[list[float]]:
    if values is None:
        return None
    result = _finite_float_list(values, label)
    if len(result) != size:
        raise ScattError(f"{label} must contain {size} values, got {len(result)}")
    return result


def _integrate_grid(sizes: Sequence[float], values: Sequence[float], mode: str) -> float:
    if len(sizes) != len(values):
        raise ScattError("Integration grid and values must have the same length")
    if mode == "bin":
        return sum(values)
    if len(sizes) < 2:
        raise ScattError(
            "Density-mode integration requires at least two size points; "
            "use distribution_mode='bin' for monodisperse or per-bin values"
        )
    total = 0.0
    for index in range(1, len(sizes)):
        step = sizes[index] - sizes[index - 1]
        if step <= 0:
            raise ScattError("Density-mode size grids must be strictly increasing")
        total += 0.5 * (values[index - 1] + values[index]) * step
    return total


def _cross_section_from_inputs(
    label: str,
    cross_section: Optional[Sequence[Any]],
    efficiency: Optional[Sequence[Any]],
    areas: Sequence[float],
    size: int,
) -> Optional[list[float]]:
    cross_values = _optional_float_list(cross_section, f"{label} cross section", size)
    efficiency_values = _optional_float_list(efficiency, f"{label} efficiency", size)
    if cross_values is not None and efficiency_values is not None:
        raise ScattError(f"Provide either {label}_cross_section or {label}_efficiency, not both")
    if cross_values is not None:
        return cross_values
    if efficiency_values is not None:
        return [value * area for value, area in zip(efficiency_values, areas)]
    return None


def _is_nested_sequence(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray, dict)):
        return False
    try:
        len(value)
        value[0]
    except (TypeError, KeyError, IndexError):
        return False
    return True


def _integrate_nested_over_size(
    sizes: Sequence[float],
    values_by_size: Sequence[Any],
    weights: Sequence[float],
    denominator: float,
    mode: str,
    label: str,
) -> Any:
    if not values_by_size:
        raise ScattError(f"{label} cannot be empty")
    first = values_by_size[0]
    if _is_nested_sequence(first):
        expected_length = len(first)
        for value in values_by_size:
            if not _is_nested_sequence(value) or len(value) != expected_length:
                raise ScattError(f"{label} must have the same nested shape at every size")
        return [
            _integrate_nested_over_size(
                sizes,
                [value[index] for value in values_by_size],
                weights,
                denominator,
                mode,
                label,
            )
            for index in range(expected_length)
        ]
    weighted_values = [
        _finite_float(value, label) * weight for value, weight in zip(values_by_size, weights)
    ]
    return _integrate_grid(sizes, weighted_values, mode) / denominator


def normalize_number_distribution(
    sizes: Sequence[Any],
    number_distribution: Sequence[Any],
    number_concentration: float,
    *,
    distribution_mode: str = "density",
) -> list[float]:
    """Scale a number distribution to a desired total concentration."""
    mode = distribution_mode.casefold()
    if mode not in {"density", "bin"}:
        raise ScattError("distribution_mode must be 'density' or 'bin'")
    size_values = _finite_float_list(sizes, "size")
    distribution = _finite_float_list(number_distribution, "number_distribution")
    if len(distribution) != len(size_values):
        raise ScattError("number_distribution must have the same length as sizes")
    if any(value < 0 for value in distribution):
        raise ScattError("number_distribution cannot contain negative values")
    target = _finite_float(number_concentration, "number_concentration")
    if target < 0:
        raise ScattError("number_concentration cannot be negative")
    current = _integrate_grid(size_values, distribution, mode)
    if current <= 0:
        raise ScattError("Cannot normalize a zero number distribution")
    scale = target / current
    return [value * scale for value in distribution]


@_registration_required
def _integrate_kernel(
    sizes: Sequence[Any],
    number_distribution: Sequence[Any],
    *,
    extinction_cross_section: Optional[Sequence[Any]] = None,
    scattering_cross_section: Optional[Sequence[Any]] = None,
    absorption_cross_section: Optional[Sequence[Any]] = None,
    extinction_efficiency: Optional[Sequence[Any]] = None,
    scattering_efficiency: Optional[Sequence[Any]] = None,
    absorption_efficiency: Optional[Sequence[Any]] = None,
    asymmetry_factor: Optional[Sequence[Any]] = None,
    phase_matrix: Optional[Sequence[Any]] = None,
    size_is_radius: bool = True,
    distribution_mode: str = "density",
    metadata: Optional[Mapping[str, Any]] = None,
) -> BulkOptics:
    """Integrate single-particle optical properties over a size distribution.

    ``number_distribution`` is interpreted as dN/dsize when
    ``distribution_mode='density'`` and as per-bin number concentration when
    ``distribution_mode='bin'``. Cross sections may be supplied directly, or
    efficiencies may be supplied and converted with the geometric area from
    ``sizes``.
    """
    from zju_scatt_interface.optics.models import BulkOptics

    mode = distribution_mode.casefold()
    if mode not in {"density", "bin"}:
        raise ScattError("distribution_mode must be 'density' or 'bin'")

    size_values = _finite_float_list(sizes, "size")
    number_values = _finite_float_list(number_distribution, "number_distribution")
    if len(number_values) != len(size_values):
        raise ScattError("number_distribution must have the same length as sizes")
    if any(value <= 0 for value in size_values):
        raise ScattError("sizes must be positive")
    if any(value < 0 for value in number_values):
        raise ScattError("number_distribution cannot contain negative values")

    areas = [math.pi * (size if size_is_radius else size / 2.0) ** 2 for size in size_values]
    size_count = len(size_values)
    ext_values = _cross_section_from_inputs(
        "extinction",
        extinction_cross_section,
        extinction_efficiency,
        areas,
        size_count,
    )
    sca_values = _cross_section_from_inputs(
        "scattering",
        scattering_cross_section,
        scattering_efficiency,
        areas,
        size_count,
    )
    abs_values = _cross_section_from_inputs(
        "absorption",
        absorption_cross_section,
        absorption_efficiency,
        areas,
        size_count,
    )

    if ext_values is None and sca_values is None and abs_values is None:
        raise ScattError(
            "Provide at least one extinction, scattering, or absorption cross section or efficiency"
        )
    absorption_was_derived = False
    extinction_was_derived = False
    scattering_was_derived = False
    if abs_values is None and ext_values is not None and sca_values is not None:
        abs_values = [ext_value - sca_value for ext_value, sca_value in zip(ext_values, sca_values)]
        absorption_was_derived = True
    if ext_values is None and sca_values is not None and abs_values is not None:
        ext_values = [sca_value + abs_value for sca_value, abs_value in zip(sca_values, abs_values)]
        extinction_was_derived = True
    if sca_values is None and ext_values is not None and abs_values is not None:
        sca_values = [ext_value - abs_value for ext_value, abs_value in zip(ext_values, abs_values)]
        scattering_was_derived = True

    number_concentration = _integrate_grid(size_values, number_values, mode)

    def integrate_cross_section(values: Optional[Sequence[float]]) -> Optional[float]:
        if values is None:
            return None
        return _integrate_grid(
            size_values,
            [cross_section * number for cross_section, number in zip(values, number_values)],
            mode,
        )

    beta_ext = integrate_cross_section(ext_values)
    beta_sca = integrate_cross_section(sca_values)
    beta_abs = integrate_cross_section(abs_values)
    single_scattering_albedo = (
        beta_sca / beta_ext if beta_ext not in (None, 0.0) and beta_sca is not None else None
    )

    bulk_g: Optional[float] = None
    scattering_weights: Optional[list[float]] = None
    if asymmetry_factor is not None:
        if sca_values is None:
            raise ScattError("asymmetry_factor requires scattering cross sections or efficiencies")
        g_values = _optional_float_list(asymmetry_factor, "asymmetry_factor", size_count)
        scattering_weights = [
            scattering * number for scattering, number in zip(sca_values, number_values)
        ]
        if beta_sca not in (None, 0.0):
            bulk_g = (
                _integrate_grid(
                    size_values,
                    [g * weight for g, weight in zip(g_values, scattering_weights)],
                    mode,
                )
                / beta_sca
            )

    bulk_phase_matrix: Optional[Any] = None
    if phase_matrix is not None:
        if sca_values is None:
            raise ScattError("phase_matrix requires scattering cross sections or efficiencies")
        phase_values = list(phase_matrix)
        if len(phase_values) != size_count:
            raise ScattError(f"phase_matrix must contain {size_count} size entries")
        if beta_sca in (None, 0.0):
            bulk_phase_matrix = None
        else:
            if scattering_weights is None:
                scattering_weights = [
                    scattering * number for scattering, number in zip(sca_values, number_values)
                ]
            bulk_phase_matrix = _integrate_nested_over_size(
                size_values,
                phase_values,
                scattering_weights,
                beta_sca,
                mode,
                "phase_matrix",
            )

    result_metadata = {
        "distribution_mode": mode,
        "size_interpretation": "radius" if size_is_radius else "diameter",
        "number_distribution": "dN/dsize" if mode == "density" else "per-bin number",
        "extinction_from": (
            "derived from scattering + absorption"
            if extinction_was_derived
            else "input"
            if ext_values is not None
            else "not available"
        ),
        "scattering_from": (
            "derived from extinction - absorption"
            if scattering_was_derived
            else "input"
            if sca_values is not None
            else "not available"
        ),
        "absorption_from": (
            "derived from extinction - scattering"
            if absorption_was_derived
            else "input"
            if abs_values is not None
            else "not available"
        ),
    }
    if metadata:
        result_metadata.update(dict(metadata))

    return BulkOptics(
        extinction_coefficient=beta_ext,
        scattering_coefficient=beta_sca,
        absorption_coefficient=beta_abs,
        single_scattering_albedo=single_scattering_albedo,
        asymmetry_factor=bulk_g,
        phase_matrix=bulk_phase_matrix,
        number_concentration=number_concentration,
        size_count=size_count,
        metadata=result_metadata,
    )


@_registration_required
def calculate_bulk_optics_from_file(
    path: Union[str, Path],
    number_distribution: Union[
        Sequence[Any],
        Callable[[SingleParticleOptics], Sequence[Any]],
    ],
    *,
    include_phase_matrix: bool = False,
    distribution_mode: str = "density",
    size_dataset: Optional[str] = None,
    coordinate_indices: Optional[Mapping[str, int]] = None,
    cext_mode: str = "auto",
    wavelength_um: Optional[float] = None,
    number_concentration_unit: str = "cm-3",
    metadata: Optional[Mapping[str, Any]] = None,
) -> BulkOptics:
    """Load a ZJU-SCATT file and integrate it over a user-supplied distribution."""
    from zju_scatt_interface.optics.loading import load_single

    optics = load_single(
        path,
        include_phase_matrix=include_phase_matrix,
        size_dataset=size_dataset,
        coordinate_indices=coordinate_indices,
        cext_mode=cext_mode,
        wavelength_um=wavelength_um,
    )
    distribution_values = (
        number_distribution(optics) if callable(number_distribution) else number_distribution
    )
    concentration_unit = number_concentration_unit.strip().casefold()
    if concentration_unit not in {"cm-3", "m-3"}:
        raise ScattError("number_concentration_unit must be 'cm-3' or 'm-3'")
    concentration_factor = 1.0e6 if concentration_unit == "cm-3" else 1.0
    distribution_values = [
        _finite_float(value, "number_distribution") * concentration_factor
        for value in distribution_values
    ]
    result_metadata = dict(optics.metadata)
    result_metadata.update(
        {
            "number_concentration_input_unit": concentration_unit,
            "number_distribution_input_unit": (
                concentration_unit
                if distribution_mode.casefold() == "bin"
                else concentration_unit + " um-1"
            ),
            "number_concentration_to_m3_factor": concentration_factor,
            "number_concentration_output_unit": concentration_unit,
            "extinction_coefficient_unit": "m-1",
            "scattering_coefficient_unit": "m-1",
            "absorption_coefficient_unit": "m-1",
        }
    )
    if metadata:
        result_metadata.update(dict(metadata))
    result = _integrate_kernel(
        optics.sizes,
        distribution_values,
        extinction_cross_section=optics.extinction_cross_section,
        scattering_cross_section=optics.scattering_cross_section,
        absorption_cross_section=optics.absorption_cross_section,
        # Loaded records may retain both representations for inspection.
        # The integrator accepts one representation per optical quantity.
        extinction_efficiency=None
        if optics.extinction_cross_section is not None
        else optics.extinction_efficiency,
        scattering_efficiency=None
        if optics.scattering_cross_section is not None
        else optics.scattering_efficiency,
        absorption_efficiency=None
        if optics.absorption_cross_section is not None
        else optics.absorption_efficiency,
        asymmetry_factor=optics.asymmetry_factor,
        phase_matrix=optics.phase_matrix,
        distribution_mode=distribution_mode,
        metadata=result_metadata,
    )
    result.number_concentration /= concentration_factor
    return result


def bulk_phase_matrix_element(
    result: BulkOptics,
    *,
    angle: float = 180.0,
    row: int = 0,
    column: int = 0,
) -> tuple[float, Optional[float]]:
    """Return one bulk phase-matrix element and the matched scattering angle."""
    if result.phase_matrix is None:
        raise ScattError("Bulk result does not contain a phase matrix")
    phase = result.phase_matrix
    angles = result.metadata.get("scattering_angles")
    if angles:
        angle_values = [float(value) for value in angles]
        angle_index = min(
            range(len(angle_values)),
            key=lambda index: abs(angle_values[index] - angle),
        )
        matched_angle: Optional[float] = angle_values[angle_index]
    else:
        angle_index = len(phase) - 1 if angle >= 90.0 else 0
        matched_angle = None
    return float(phase[angle_index][row][column]), matched_angle
