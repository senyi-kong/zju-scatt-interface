"""Typed single-particle/PSD integration and advanced raw-array inputs."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.bulk.lowlevel import (
    _integrate_kernel,
)
from zju_scatt_interface.optics.models import BulkOptics, SingleParticleOptics
from zju_scatt_interface.psd.models import RemapReport, SizeDistribution


@_registration_required
def integrate_arrays(
    distribution: SizeDistribution,
    database_size_um: Sequence[float],
    *,
    database_size_definition: Optional[str] = None,
    geometry_converter: Optional[Callable] = None,
    geometry_source: Optional[str] = None,
    truncation_policy: str = "error",
    extinction_cross_section_m2: Optional[Sequence[float]] = None,
    scattering_cross_section_m2: Optional[Sequence[float]] = None,
    absorption_cross_section_m2: Optional[Sequence[float]] = None,
    extinction_efficiency: Optional[Sequence[float]] = None,
    scattering_efficiency: Optional[Sequence[float]] = None,
    absorption_efficiency: Optional[Sequence[float]] = None,
    asymmetry_factor: Optional[Sequence[float]] = None,
    phase_matrix: Optional[Sequence[object]] = None,
    metadata: Optional[dict] = None,
) -> tuple[BulkOptics, RemapReport]:
    """Remap a public PSD and integrate matching single-particle optical arrays.

    Public per-bin concentrations are converted from ``cm-3`` to ``m-3`` before
    integration so cross sections in ``m2`` produce bulk coefficients in ``m-1``.
    """

    working = distribution
    if database_size_definition is not None and database_size_definition != working.size_definition:
        working = working.convert_size_definition(
            database_size_definition,
            converter=geometry_converter,
            geometry_source=geometry_source,
        )
    remapped, report = working.remap(
        database_size_um,
        truncation_policy=truncation_policy,
    )
    counts_m3 = [value * 1.0e6 for value in remapped.dndr_cm3]
    sizes_m = [value * 1.0e-6 for value in remapped.size_um]
    result = _integrate_kernel(
        sizes_m,
        counts_m3,
        extinction_cross_section=extinction_cross_section_m2,
        scattering_cross_section=scattering_cross_section_m2,
        absorption_cross_section=absorption_cross_section_m2,
        extinction_efficiency=extinction_efficiency,
        scattering_efficiency=scattering_efficiency,
        absorption_efficiency=absorption_efficiency,
        asymmetry_factor=asymmetry_factor,
        phase_matrix=phase_matrix,
        size_is_radius=True,
        distribution_mode="bin",
        metadata={
            **(metadata or {}),
            "psd": distribution.to_dict(),
            "psd_remap": report.to_dict(),
            "number_concentration_input_unit": "cm-3",
            "number_concentration_internal_unit": "m-3",
            "bulk_coefficient_unit": "m-1",
        },
    )
    result.number_concentration = remapped.number_concentration_cm3
    result.metadata["number_concentration_output_unit"] = "cm-3"
    return result, report


@_registration_required
def integrate(
    optics: SingleParticleOptics,
    distribution: SizeDistribution,
    *,
    database_size_definition: Optional[str] = None,
    geometry_converter: Optional[Callable] = None,
    geometry_source: Optional[str] = None,
    truncation_policy: str = "error",
) -> tuple[BulkOptics, RemapReport]:
    """Integrate a loaded L1 optical slice using an array-first PSD."""

    if optics.size_unit not in {"um", "micrometer", "micrometre"}:
        raise ValueError(
            "SingleParticleOptics sizes must be physical radii in um; found {!r}".format(
                optics.size_unit
            )
        )
    if optics.cross_section_unit not in {"m2", "m^2"}:
        raise ValueError(
            "SingleParticleOptics cross sections must use m2; found {!r}".format(
                optics.cross_section_unit
            )
        )
    return integrate_arrays(
        distribution,
        optics.sizes,
        database_size_definition=database_size_definition,
        geometry_converter=geometry_converter,
        geometry_source=geometry_source,
        truncation_policy=truncation_policy,
        extinction_cross_section_m2=optics.extinction_cross_section,
        scattering_cross_section_m2=optics.scattering_cross_section,
        absorption_cross_section_m2=optics.absorption_cross_section,
        asymmetry_factor=optics.asymmetry_factor,
        phase_matrix=optics.phase_matrix,
        metadata=dict(optics.metadata),
    )
