"""optics / retrieval / indices domain implementation."""

from __future__ import annotations

import re
from dataclasses import replace

import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.metadata as _domain_access_metadata
import zju_scatt_interface.access.reports as _domain_access_reports
import zju_scatt_interface.access.requests as _domain_access_requests
import zju_scatt_interface.access.retrieval as _domain_access_retrieval


def retrieve_native_indices(parameters, *, client, runtime):
    pass
    from zju_scatt_interface.config.particles import (
        get_particle_profile,
        normalize_parameter_name,
    )
    from zju_scatt_interface.errors import ScattError
    from zju_scatt_interface.optics.refractive_index import (
        ComplexRefractiveIndex,
        ResolvedGridRefractiveIndex,
    )
    from zju_scatt_interface.optics.retrieval.grid import GRID_FAMILIES
    from zju_scatt_interface.optics.retrieval.workflow import (
        interpolate_downloaded_particle_series,
    )
    from zju_scatt_interface.sources.adapters.boundaries import database_type
    from zju_scatt_interface.sources.selection import (
        select_shape_grid_sources,
        shape_targets,
    )

    supplied = {
        get_particle_profile(name).particle_type: value
        for name, value in parameters["refractive_index_parameters"].items()
    }
    requested = _domain_access_requests._api_sequence(parameters.get("particle_types")) or list(
        supplied
    )
    families = list(dict.fromkeys(get_particle_profile(name).particle_type for name in requested))
    if len(families) != 1 or families[0] not in GRID_FAMILIES or set(supplied) != set(families):
        raise ScattError(
            "Wavelength-free explicit RI requires one dust/BC family and its complete indices; use run_retrieval for batches"
        )
    if (
        parameters.get("target_temperatures") is not None
        or parameters.get("wavelength_range") is not None
    ):
        raise ScattError(
            "Wavelength-free RI retrieval cannot also select wavelength/temperature coordinates"
        )
    family = families[0]
    values = {normalize_parameter_name(key): value for key, value in supplied[family].items()}
    if values.get("database_type", "refractive_index_grid") != "refractive_index_grid":
        raise ScattError(
            "Wavelength-free explicit RI requires database_type='refractive_index_grid'"
        )
    axes = (
        ("refractive_index_real", "refractive_index_imaginary")
        if family == "super_spheroid"
        else (
            "black_carbon_refractive_index_real",
            "black_carbon_refractive_index_imaginary",
            "hygroscopic_refractive_index_real",
            "hygroscopic_refractive_index_imaginary",
        )
    )
    if set(values) - set(axes) - {"database_type"} or any(axis not in values for axis in axes):
        raise ScattError(
            "A wavelength is required for default RI schemes; without it provide the complete explicit RI components"
        )
    values = {axis: float(values[axis]) for axis in axes}
    for real, imag in zip(axes[::2], axes[1::2]):
        ComplexRefractiveIndex(values[real], values[imag])
    shapes = parameters.get("shapes")
    targets = shape_targets(shapes, family)
    raw = dict(parameters)
    for name in (
        "refractive_index_parameters",
        "manifest_output",
        "operation_log",
        "max_files",
        "max_bytes",
    ):
        raw.pop(name, None)
    raw.update(particle_types=family, download=False, shapes=None if targets else shapes)
    result = _domain_access_retrieval.retrieve_sources(client=client, **raw)
    objects = [
        obj
        for obj in result.objects
        if family == "super_spheroid" or database_type(obj.name) == "refractive_index_grid"
    ]
    if not targets:
        geometries = set()
        for obj in objects:
            if family == "super_spheroid":
                meta = _domain_access_metadata.extract_scatt_metadata(obj.name)
                geometries.add((meta["n"], meta["aspect_ratio"]))
            else:
                geometries.add(
                    (
                        float(
                            re.search(
                                rf"_df_({_domain_access_metadata.NUMBER_PATTERN})_", obj.name, re.I
                            ).group(1)
                        ),
                    )
                )
        names = ("roundness", "aspect_ratio") if family == "super_spheroid" else ("df",)
        targets = [dict(zip(names, geometry)) for geometry in sorted(geometries)]
    if not targets:
        raise ScattError("No native RI-grid source geometries match the request")
    point = ResolvedGridRefractiveIndex(family, None, values, "explicit_refractive_index", {})
    selected, resolutions, required = select_shape_grid_sources(objects, family, [point], targets)
    limited = _domain_access_download.limit_download_set(
        selected, runtime.max_files, runtime.max_bytes
    )
    if len(limited) != len(selected):
        raise ScattError("max_files/max_bytes would truncate an explicit-RI interpolation stencil")
    result.objects = selected
    result.stats.matched = len(selected)
    result.stats.bytes = sum(obj.size for obj in selected)
    result.wavelength_processing = replace(
        result.wavelength_processing,
        interpolation_required=required,
        interpolation_basis="refractive_index_shape",
        refractive_index_resolutions=resolutions,
        message="Explicit RI on the native dimensionless grid; no wavelength assigned.",
    )
    if runtime.manifest_output:
        result.write_manifest(runtime.manifest_output, runtime.format)
    if runtime.download:
        result.status_code, result.download_results = (
            _domain_access_download.download_selected_objects(
                runtime, client, selected, result.stats
            )
        )
        if result.status_code == 0 and runtime.apply_interpolation:
            sources = [
                (item.obj, item.target)
                for item in result.download_results
                if item.status in {"downloaded", "skipped"} and item.target.is_file()
            ]
            destination = runtime.interpolation_output_dir or runtime.output_dir / "interpolated"
            result.interpolated_products = interpolate_downloaded_particle_series(
                sources,
                [None],
                result.wavelength_processing,
                destination,
                overwrite=runtime.overwrite,
            )
            if not result.interpolated_products:
                raise ScattError("Explicit-RI interpolation returned no complete native products")
            result.wavelength_processing = replace(
                result.wavelength_processing, interpolation_applied=True
            )
    if runtime.operation_log:
        _domain_access_reports.write_operation_log(
            runtime.operation_log,
            args=runtime,
            config_path=None,
            stats=result.stats,
            objects=selected,
            manifest_path=result.manifest_path or _domain_access_requests.DEFAULT_RETRIEVE_MANIFEST,
            wavelength_processing=result.wavelength_processing,
            target_processings=result.target_processings,
            download_enabled=runtime.download,
            results=result.download_results,
            exit_code=result.status_code,
        )
        result.operation_log_path = runtime.operation_log
    return result
