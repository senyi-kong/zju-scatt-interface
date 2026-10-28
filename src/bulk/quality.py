"""Bulk optical QA, phase checks and integration convergence."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.optics.models import BulkOptics, SingleParticleOptics
from zju_scatt_interface.psd.models import SizeDistribution


@dataclass(frozen=True)
class BulkQualityReport:
    passed: bool
    checks: Mapping[str, bool]
    metrics: Mapping[str, float]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": dict(self.checks),
            "metrics": dict(self.metrics),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class BulkConvergenceReport:
    checked: bool
    passed: bool
    tolerance: float
    full_size_count: int
    coarse_size_count: int
    relative_errors: Mapping[str, float]
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _relative_error(reference: float | None, candidate: float | None) -> float:
    if reference is None or candidate is None:
        return 0.0
    return abs(candidate - reference) / max(abs(reference), 1.0e-30)


def _phase_integral(phase_matrix: object, angles: Sequence[float]) -> float | None:
    try:
        p11 = [float(matrix[0][0]) for matrix in phase_matrix]  # type: ignore[index]
    except (IndexError, TypeError, ValueError):
        return None
    if len(p11) != len(angles) or len(angles) < 2:
        return None
    radians = [math.radians(float(value)) for value in angles]
    integral = 0.0
    for index in range(1, len(radians)):
        left = p11[index - 1] * math.sin(radians[index - 1])
        right = p11[index] * math.sin(radians[index])
        integral += 0.25 * (left + right) * (radians[index] - radians[index - 1])
    return integral


@_registration_required
def validate_bulk_optics(
    result: BulkOptics,
    *,
    scattering_angles: Sequence[float] | None = None,
    tolerance: float = 1.0e-8,
    phase_normalization_tolerance: float = 0.05,
) -> BulkQualityReport:
    """Run non-destructive physical checks on one bulk optical result."""

    checks: dict[str, bool] = {}
    metrics: dict[str, float] = {}
    errors: list[str] = []
    warnings: list[str] = []
    coefficients = {
        "extinction": result.extinction_coefficient,
        "scattering": result.scattering_coefficient,
        "absorption": result.absorption_coefficient,
    }
    for name, value in coefficients.items():
        passed = value is None or (math.isfinite(float(value)) and float(value) >= -tolerance)
        checks[f"{name}_nonnegative"] = passed
        if not passed:
            errors.append(f"{name} coefficient is negative or non-finite")
    if all(value is not None for value in coefficients.values()):
        closure = abs(
            float(result.extinction_coefficient)
            - float(result.scattering_coefficient)
            - float(result.absorption_coefficient)
        )
        scale = max(abs(float(result.extinction_coefficient)), 1.0e-30)
        metrics["extinction_closure_relative_error"] = closure / scale
        checks["extinction_closure"] = closure <= tolerance * scale + 1.0e-30
        if not checks["extinction_closure"]:
            errors.append("extinction != scattering + absorption")
    ssa = result.single_scattering_albedo
    checks["single_scattering_albedo_range"] = ssa is None or (
        math.isfinite(float(ssa)) and -tolerance <= float(ssa) <= 1.0 + tolerance
    )
    if not checks["single_scattering_albedo_range"]:
        errors.append("single-scattering albedo lies outside [0, 1]")
    if (
        ssa is not None
        and result.extinction_coefficient not in (None, 0.0)
        and result.scattering_coefficient is not None
    ):
        expected = float(result.scattering_coefficient) / float(result.extinction_coefficient)
        metrics["single_scattering_albedo_derived_error"] = abs(float(ssa) - expected)
        checks["single_scattering_albedo_derived"] = math.isclose(
            float(ssa), expected, rel_tol=tolerance, abs_tol=tolerance
        )
        if not checks["single_scattering_albedo_derived"]:
            errors.append("single-scattering albedo is not derived from coefficients")
    g = result.asymmetry_factor
    checks["asymmetry_factor_range"] = g is None or (
        math.isfinite(float(g)) and -1.0 - tolerance <= float(g) <= 1.0 + tolerance
    )
    if not checks["asymmetry_factor_range"]:
        errors.append("asymmetry factor lies outside [-1, 1]")

    phase = result.phase_matrix
    if phase is not None:
        try:
            p11_nonnegative = all(float(matrix[0][0]) >= -tolerance for matrix in phase)
            symmetric = all(
                math.isclose(
                    float(matrix[0][1]),
                    float(matrix[1][0]),
                    rel_tol=tolerance,
                    abs_tol=tolerance,
                )
                and math.isclose(
                    float(matrix[2][3]),
                    -float(matrix[3][2]),
                    rel_tol=tolerance,
                    abs_tol=tolerance,
                )
                for matrix in phase
            )
        except (IndexError, TypeError, ValueError):
            p11_nonnegative = False
            symmetric = False
        checks["phase_p11_nonnegative"] = p11_nonnegative
        checks["phase_random_orientation_symmetry"] = symmetric
        if not p11_nonnegative:
            errors.append("phase P11 contains negative or malformed values")
        if not symmetric:
            errors.append("phase matrix violates random-orientation symmetry")
        if scattering_angles:
            normalization = _phase_integral(phase, scattering_angles)
            if normalization is not None:
                metrics["phase_p11_half_solid_angle_integral"] = normalization
                checks["phase_normalization_near_unity"] = (
                    abs(normalization - 1.0) <= phase_normalization_tolerance
                )
                if not checks["phase_normalization_near_unity"]:
                    warnings.append(
                        "P11 angular integral is not near unity; preserved source "
                        "normalization/forward-diffraction convention"
                    )
    return BulkQualityReport(
        passed=not errors,
        checks=checks,
        metrics=metrics,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def _slice_optics(optics: SingleParticleOptics, indices: Sequence[int]) -> SingleParticleOptics:
    from zju_scatt_interface.optics.models import SingleParticleOptics

    def selected(values: Sequence[Any] | None) -> list[Any] | None:
        return None if values is None else [values[index] for index in indices]

    return SingleParticleOptics(
        sizes=selected(optics.sizes) or [],
        extinction_cross_section=selected(optics.extinction_cross_section),
        scattering_cross_section=selected(optics.scattering_cross_section),
        absorption_cross_section=selected(optics.absorption_cross_section),
        extinction_efficiency=selected(optics.extinction_efficiency),
        scattering_efficiency=selected(optics.scattering_efficiency),
        absorption_efficiency=selected(optics.absorption_efficiency),
        asymmetry_factor=selected(optics.asymmetry_factor),
        phase_matrix=selected(optics.phase_matrix),
        scattering_angles=(
            list(optics.scattering_angles) if optics.scattering_angles is not None else None
        ),
        size_unit=optics.size_unit,
        cross_section_unit=optics.cross_section_unit,
        metadata=dict(optics.metadata),
        projected_area=selected(optics.projected_area),
        single_scattering_albedo=selected(optics.single_scattering_albedo),
    )


def _convergence_check(
    optics: SingleParticleOptics,
    distribution: SizeDistribution,
    full: BulkOptics,
    *,
    database_size_definition: str,
    truncation_policy: str,
    tolerance: float,
) -> BulkConvergenceReport:
    from zju_scatt_interface.bulk.integration import integrate

    count = len(optics.sizes)
    if count < 5:
        return BulkConvergenceReport(
            checked=False,
            passed=True,
            tolerance=tolerance,
            full_size_count=count,
            coarse_size_count=count,
            relative_errors={},
            message="At least five optical size nodes are required for a coarsening check.",
        )
    indices = list(range(0, count, 2))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    coarse_optics = _slice_optics(optics, indices)
    coarse, _ = integrate(
        coarse_optics,
        distribution,
        database_size_definition=database_size_definition,
        truncation_policy=truncation_policy,
    )
    errors = {
        "extinction_coefficient": _relative_error(
            full.extinction_coefficient, coarse.extinction_coefficient
        ),
        "single_scattering_albedo": _relative_error(
            full.single_scattering_albedo, coarse.single_scattering_albedo
        ),
        "asymmetry_factor": _relative_error(full.asymmetry_factor, coarse.asymmetry_factor),
    }
    passed = all(value <= tolerance for value in errors.values())
    return BulkConvergenceReport(
        checked=True,
        passed=passed,
        tolerance=tolerance,
        full_size_count=count,
        coarse_size_count=len(indices),
        relative_errors=errors,
        message=(
            "Coarsened-grid result is within tolerance."
            if passed
            else "One or more coarsened-grid diagnostics exceed tolerance."
        ),
    )
