"""optics / retrieval / workflow domain implementation."""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from zju_scatt_interface.access.models import DownloadResult, WavelengthProcessing
from zju_scatt_interface.errors import ScattError


def apply_downloaded_wavelength_interpolation(
    runtime: argparse.Namespace,
    processing: WavelengthProcessing,
    download_results: Sequence[DownloadResult],
) -> tuple[WavelengthProcessing, list[Any]]:
    """Create derived physical products while preserving native series coordinates."""
    from zju_scatt_interface.access.metadata import (
        expand_string_list,
        particle_type_matches,
    )

    if (
        not (
            processing.interpolation_required
            or any(
                item.get("database_type") != "wavelength"
                for item in processing.refractive_index_resolutions
            )
        )
        or processing.selection_mode != "interp"
        or not getattr(runtime, "apply_interpolation", True)
    ):
        return processing, []
    requested = expand_string_list(getattr(runtime, "particle_type", None) or [])
    local_sources = [
        (result.obj, result.target)
        for result in download_results
        if result.status in {"downloaded", "skipped"} and result.target.is_file()
    ]
    if not local_sources:
        raise ScattError(
            "Wavelength interpolation was requested, but no complete downloaded "
            "source files are available."
        )
    try:
        from zju_scatt_interface.optics.interpolation import (
            interpolate_downloaded_ice_series,
        )

        pass

        destination = getattr(runtime, "interpolation_output_dir", None) or (
            runtime.output_dir / "interpolated"
        )
        products = interpolate_downloaded_particle_series(
            local_sources,
            processing.target_wavelengths_um,
            processing,
            destination,
            tolerance_um=runtime.target_tolerance or 0.0,
            include_phase_matrix=bool(
                getattr(runtime, "interpolation_include_phase_matrix", False)
            ),
            overwrite=bool(runtime.overwrite),
        )
        temperatures = getattr(runtime, "target_temperatures", None)
        if temperatures:
            from zju_scatt_interface.optics.retrieval.ice import write_products

            products.extend(
                write_products(
                    local_sources,
                    processing.target_wavelengths_um,
                    temperatures,
                    destination,
                    overwrite=bool(runtime.overwrite),
                    shapes=getattr(runtime, "shapes", None),
                )
            )
        elif any(particle_type_matches("super_spheroid_ice", item) for item in requested) or any(
            "super_spheroid_ice" in obj.key.split("/") for obj, _ in local_sources
        ):
            products.extend(
                interpolate_downloaded_ice_series(
                    local_sources,
                    processing.target_wavelengths_um,
                    getattr(runtime, "interpolation_output_dir", None)
                    or (destination / "super_spheroid_ice"),
                    tolerance_um=runtime.target_tolerance or 0.0,
                    include_phase_matrix=bool(
                        getattr(runtime, "interpolation_include_phase_matrix", False)
                    ),
                    overwrite=bool(runtime.overwrite),
                )
            )
    except (ImportError, RuntimeError, ValueError) as exc:
        raise ScattError(f"Downloaded wavelength interpolation failed: {exc}") from exc
    from zju_scatt_interface.extensions.particles import particle_definitions

    for definition in particle_definitions():
        if definition.downloaded_interpolator is None:
            continue
        selected = [
            (obj, path)
            for obj, path in local_sources
            if particle_type_matches(obj.key, definition.profile.particle_type)
        ]
        if selected:
            products.extend(
                definition.downloaded_interpolator(runtime, processing, selected, Path(destination))
            )
    if not products:
        raise ScattError(
            "Wavelength interpolation was required, but no complete source "
            "series brackets the requested target. Avoid max_files/max_bytes limits "
            "or inspect the downloaded source set."
        )
    created = sum(product.status == "created" for product in products)
    reused = sum(product.status == "skipped" for product in products)
    message = (
        processing.message.replace(
            "optical interpolation has not been applied.", "derived products follow."
        )
        + f" Created {created} and reused {reused} derived target-wavelength products. "
        "All products preserve the native source schema, variable units, internal dimensions and phase elements."
    )
    return replace(
        processing,
        interpolation_applied=True,
        message=message,
    ), products


def _series(obj, family):
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN
    from zju_scatt_interface.optics.retrieval.grid import _series_key

    key = _series_key(obj, family)
    key = re.sub(rf"wl_({NUMBER_PATTERN})_um", "wl_TARGET_um", key, flags=re.I)
    key = re.sub(rf"ref_({NUMBER_PATTERN})_({NUMBER_PATTERN})", "ref_TARGET", key, flags=re.I)
    return re.sub(rf"water_({NUMBER_PATTERN})_({NUMBER_PATTERN})", "water_TARGET", key, flags=re.I)


def interpolate_downloaded_particle_series(
    downloaded_sources,
    targets,
    processing,
    output_dir,
    *,
    include_phase_matrix=False,
    overwrite=False,
    tolerance_um=1e-9,
    progress=None,
):
    """Write one native-schema product per source series and wavelength.

    All original variables (including all phase elements), dimensions and
    variable attributes are retained. Internal vf/rh dimensions are not split
    into separate files. The old phase option is accepted for API compatibility;
    native retrieval products always preserve every source variable.
    """
    from zju_scatt_interface.access.metadata import (
        NUMBER_PATTERN,
        extract_scatt_metadata,
    )
    from zju_scatt_interface.config.particles import list_particle_profiles
    from zju_scatt_interface.optics.interpolation import (
        InterpolatedFileResult,
        InterpolationError,
    )
    from zju_scatt_interface.optics.retrieval.grid import (
        grid_coordinates,
        grid_family,
        prefer_index_sources,
    )
    from zju_scatt_interface.optics.retrieval.native import write_native_source_product
    from zju_scatt_interface.sources.adapters.boundaries import FAMILY, database_type

    wavelength_families = {
        profile.particle_type
        for profile in list_particle_profiles()
        if profile.data_structure.value == "wavelength_based"
        and profile.particle_type != "super_spheroid_ice"
    }

    downloaded_sources = list(downloaded_sources)
    preferred_keys = set()
    for family in ("super_spheroid", FAMILY):
        candidates = [
            obj
            for obj, _ in downloaded_sources
            if grid_family(obj) == family
            and (family == "super_spheroid" or database_type(obj.name) == "refractive_index_grid")
        ]
        preferred_keys.update(obj.key for obj in prefer_index_sources(candidates, family))
    groups = {}
    for obj, path in downloaded_sources:
        family = grid_family(obj)
        if family is None:
            family = next(
                (name for name in wavelength_families if name in obj.key.split("/")), None
            )
            if family is None:
                continue
        metadata = extract_scatt_metadata(obj.name)
        is_grid = family == "super_spheroid" or (
            family == FAMILY and database_type(obj.name) == "refractive_index_grid"
        )
        if is_grid and obj.key not in preferred_keys:
            continue
        coordinates = (
            grid_coordinates(obj, family) if is_grid else {"wavelength": metadata["wavelength_um"]}
        )
        if family == "super_spheroid":
            coordinates.update(roundness=metadata["n"], aspect_ratio=metadata["aspect_ratio"])
        elif family == FAMILY:
            match = re.search(rf"_df_({NUMBER_PATTERN})_", obj.name, re.I)
            coordinates["df"] = float(match.group(1))
        series = _series(obj, family)
        if any(
            item.get("shape_stencils") and item["particle_type"] == family
            for item in processing.refractive_index_resolutions
        ):
            series = re.sub(rf"_(n|asp|df)_({NUMBER_PATTERN})", r"_\1_GRID", series)
        groups.setdefault((family, series), []).append(
            {
                "obj": obj,
                "path": Path(path),
                "coordinates": coordinates,
                "is_grid": is_grid,
            }
        )

    results = []
    for (family, series), records in groups.items():
        for wavelength in targets:
            resolution = next(
                (
                    item
                    for item in processing.refractive_index_resolutions
                    if item["particle_type"] == family
                    and (
                        (item["wavelength_um"] is None and wavelength is None)
                        or (
                            item["wavelength_um"] is not None
                            and wavelength is not None
                            and math.isclose(item["wavelength_um"], wavelength)
                        )
                    )
                ),
                {},
            )
            if records[0]["is_grid"]:
                if any(
                    item["series"] == series for item in resolution.get("unsupported_series", [])
                ):
                    continue
                if not resolution.get("target_indices"):
                    raise InterpolationError(f"Missing resolved target indices for {family}")
            elif any(
                abs(record["coordinates"]["wavelength"] - wavelength) <= tolerance_um
                for record in records
            ):
                continue  # The exact native wavelength file already exists.
            stencils = resolution.get("shape_stencils")
            work = []
            if stencils:
                for stencil in stencils:
                    if stencil["series"] != series:
                        continue
                    keys = set(stencil["source_keys"])
                    work.append(
                        (
                            [record for record in records if record["obj"].key in keys],
                            {
                                **resolution,
                                "target_shape_parameters": stencil["target_shape_parameters"],
                            },
                        )
                    )
            else:
                work.append((records, resolution))
            for source_records, target_resolution in work:
                output, status, provenance, paths = write_native_source_product(
                    source_records,
                    family,
                    wavelength,
                    target_resolution,
                    output_dir,
                    overwrite=overwrite,
                )
                fixed = target_resolution.get("target_shape_parameters") or {
                    name: value
                    for name, value in source_records[0]["coordinates"].items()
                    if name in {"roundness", "aspect_ratio", "df"}
                }
                results.append(
                    InterpolatedFileResult(
                        output, family, wavelength, fixed, paths, status, provenance
                    )
                )
                if progress is not None:
                    progress(len(results), output)
    return results
