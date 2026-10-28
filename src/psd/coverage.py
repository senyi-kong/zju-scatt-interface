"""psd / coverage domain implementation."""

from __future__ import annotations

import math

import zju_scatt_interface.optics.loading as _domain_optics_loading
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)


@_registration_required
def check_size_coverage(
    particle_type,
    source_paths,
    size_distribution,
    *,
    wavelength,
    wavelength_unit="um",
    parameters=None,
    shape_ensemble=None,
    refractive_index_tables=None,
    size_definition=None,
    truncation_policy="error",
):
    """Check the selected sources' common physical radius and PSD bin coverage.

    Source coordinates use the requested size definition and physical wavelength;
    matching xsize_maxd or array positions across shapes is never assumed.
    Error mode rejects missing PSD mass. Explicit truncate mode supplies one
    common integration grid so every shape discards the same population mass.
    The returned dictionary is JSON serializable; no phase arrays are loaded.
    """
    pass
    from zju_scatt_interface.bulk.ensemble import _ensemble_members
    from zju_scatt_interface.optics.refractive_index import wavelength_to_um
    from zju_scatt_interface.psd.models import _bin_edges
    from zju_scatt_interface.sources.adapters.registry import get_particle_adapter

    if truncation_policy not in {"error", "truncate"}:
        raise ValueError("truncation_policy must be 'error' or 'truncate'")
    definition = size_definition or size_distribution.size_definition
    if definition != size_distribution.size_definition:
        raise ValueError(
            "PSD and database size definitions must match for a physical coverage check"
        )
    wavelength_um = wavelength_to_um(wavelength, wavelength_unit)
    members, _ = _ensemble_members(parameters, shape_ensemble)
    adapter = get_particle_adapter(particle_type)
    grids, ranges = {}, []
    for coordinates, weight in members:
        if weight == 0:
            continue
        resolution = adapter.resolve(
            source_paths,
            wavelength=wavelength_um,
            parameters=coordinates,
            refractive_index_tables=refractive_index_tables,
            size_definition=definition,
            include_phase_matrix=False,
        )
        for request in resolution.sources:
            key = (
                str(request.path),
                request.size_dataset,
                request.wavelength_um,
                tuple(sorted(request.coordinate_indices.items())),
            )
            if key in grids:
                continue
            optics = _domain_optics_loading.load_single(
                request.path,
                size_dataset=request.size_dataset,
                coordinate_indices=dict(request.coordinate_indices),
                wavelength_um=request.wavelength_um,
                include_phase_matrix=False,
                allow_nan_asymmetry=True,
            )
            values = list(map(float, optics.sizes))
            if (
                not values
                or any(not math.isfinite(x) or x <= 0 for x in values)
                or any(right <= left for left, right in zip(values, values[1:]))
            ):
                raise ValueError(f"Invalid physical size axis in {request.path}")
            if optics.size_unit != "um":
                raise ValueError(f"Expected physical sizes in um, found {optics.size_unit}")
            grids[key] = values
            ranges.append({"source": str(request.path), "radius_um": [values[0], values[-1]]})
    if not grids:
        raise ValueError("No positive-weight source grids are available")
    lower = max(values[0] for values in grids.values())
    upper = min(values[-1] for values in grids.values())
    if lower > upper:
        raise ValueError("Selected sources have no common physical size range")
    common = sorted({value for grid in grids.values() for value in grid if lower <= value <= upper})
    # Use the same conservative bin convention as the bulk integrator. Source
    # sample endpoints are not the edges of their represented size bins.
    remapped, remap = size_distribution.remap(common, truncation_policy="truncate")
    outside = remap.outside_fraction
    if outside > 1e-12 and truncation_policy == "error":
        raise ValueError(
            f"PSD is not fully covered by the common physical size range [{lower:g}, {upper:g}] um; "
            f"outside number fraction={outside:.6g}. Choose a shared restricted PSD or "
            "set truncation_policy='truncate' explicitly."
        )
    edges = (
        _bin_edges(size_distribution.size_um)
        if len(size_distribution.size_um) > 1
        else (size_distribution.size_um[0], size_distribution.size_um[0])
    )
    report = {
        "coordinate": definition,
        "source_ranges": ranges,
        "common_source_radius_um": [lower, upper],
        "common_integration_bin_edges_um": list(_bin_edges(common))
        if len(common) > 1
        else [lower, upper],
        "integration_radius_bin_edges_um": [edges[0], edges[-1]],
        "fully_covered": outside <= 1e-12,
        "outside_number_fraction": outside,
        "retained_number_concentration_cm3": remapped.number_concentration_cm3,
        "truncation_policy": truncation_policy,
        "additional_psd_clipping_required": outside > 1e-12,
    }
    if outside > 1e-12:
        report["common_integration_grid_um"] = common
    return report
