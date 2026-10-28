"""Shared adapter errors, boundary policy and black-carbon coordinates."""

from __future__ import annotations

import re

FAMILY = "encapsulated_fractal_aggregates_black_carbon"


def database_type(path):
    name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    return "wavelength" if re.search(r"_wl_\d+(?:\.\d+)?_um_", name) else "refractive_index_grid"


def refractive_index_scheme(path):
    name = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    match = re.search(r"_(v1\.2\.[12])(?:_|\.)", name)
    return match.group(1) if match else None


class AdapterError(ValueError):
    """Public parameters cannot be resolved to native L1 nodes."""


class DatabaseBoundaryError(AdapterError):
    """A valid request falls outside the selected database's support."""


class DatabaseBoundaryWarning(UserWarning):
    """Optical results are NaN because database support is insufficient."""


def nan_product(particle_type, coordinates, sizes, angles, reason):
    import warnings

    from zju_scatt_interface.optics.interpolation import (
        InterpolatedOpticalProduct,
        InterpolationProvenance,
    )
    from zju_scatt_interface.optics.models import SingleParticleOptics

    message = f"{reason} Optical values returned as NaN; no extrapolation applied."
    warnings.warn(message, DatabaseBoundaryWarning, stacklevel=3)
    sizes = list(sizes)
    angles = list(angles or [])
    fields = {
        name: [float("nan")] * len(sizes)
        for name in (
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
    }
    provenance = InterpolationProvenance(
        method="out_of_database_bounds",
        particle_type=particle_type,
        target_coordinates=dict(coordinates),
        axis_transforms={},
        optical_transforms={},
        neighbors=[],
        size_grid_um=sizes,
        angle_grid_degrees=angles,
        warnings=[message],
    )
    optics = SingleParticleOptics(
        sizes=sizes,
        scattering_angles=angles or None,
        phase_matrix=[[[[float("nan")] * 4 for _ in range(4)] for _ in angles] for _ in sizes]
        if angles
        else None,
        size_unit="um",
        cross_section_unit="um2",
        **fields,
        metadata={"status": "out_of_database_bounds", "warnings": [message]},
    )
    return InterpolatedOpticalProduct(particle_type, dict(coordinates), optics, provenance)
