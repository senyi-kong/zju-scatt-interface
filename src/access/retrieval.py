"""Source selection, downloads and interpolation orchestration."""

from __future__ import annotations

import argparse
import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.models import (
    DownloadResult,
    NumericSelectionProcessing,
    RemoteObject,
    RetrievalResult,
    ScanStats,
    WavelengthProcessing,
)
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.errors import ScattError


@_registration_required
def retrieve_sources(
    *,
    client: Optional[ApiClient] = None,
    timeout: float = 30.0,
    retries: int = 3,
    insecure: bool = False,
    **parameters,
) -> RetrievalResult:
    """Search, select, and optionally download ZJU-SCATT source data.

    Parameters are ordinary Python values, e.g. ``particle_types="ice"``,
    ``wavelength_range=(0.4, 0.8)``, ``ref_real_targets=[1.306]``, or
    ``shapes={"n": 2, "asp": 1}``.

    ``shapes`` accepts a mapping for one shape selection, or a list of mappings
    for paired selections (OR across entries, AND within each entry). Numbers
    select exact coordinates and two-number tuples select inclusive ranges.
    For a dust or refractive-index-grid BC request with target_wavelengths and
    mode='interp', complete scalar shapes are interpolation targets (n/asp for
    dust, df for BC). Actual catalog nodes supply the joint shape/RI stencil;
    no source-selection helper or manual bracket ranges are needed. Sources
    prefer L1.5 at identical coordinates, and ambiguous revisions are rejected.
    Selection details are in each RI resolution's shape_stencils. Set
    apply_interpolation=False to obtain only the required source files for bulk
    calculation; otherwise native-schema products are written per target shape.
    Range or partial shape mappings retain filename-filter semantics.
    For ice with temperature/wavelength targets, scalar shape coordinates are
    also interpolated when non-native; native geometry brackets are selected
    automatically. Raw retrieval retains exact scalar shape selection.
    For example ``shapes=[{"n": 2, "asp": 1}, {"n": 3, "asp": 2}]`` selects
    only those two combinations. Omit shapes to keep all available geometry.
    Supported filename axes are roundness/n, aspect_ratio/asp, and df. Internal
    size/vf/RH axes stay intact. ``shapes`` is the sole Python retrieval
    parameter for geometry selection.

    For dust and encapsulated black carbon, ``target_wavelengths`` resolves
    missing refractive indices using the packaged material tables and selects
    native index-grid source files. The default is announced in the output and
    recorded in ``result.wavelength_processing.refractive_index_resolutions``.
    Use ``refractive_index_parameters={"dust": {"mr": ..., "mi": ...}}``
    (or all four canonical BC/coating components under ``"black_carbon"``)
    to override the default. Raw ``wavelength_range`` filtering retains its
    filename-filter semantics. With ``download=True`` and
    ``apply_interpolation=True`` (the default), source stencils also produce
    derived target-wavelength values in ``result.interpolated_products``.
    All products preserve the native source variable names, units, dimensions,
    dtypes, attributes and phase elements. Internal vf/rh axes stay in one file.
    Exact wavelength products are reused directly without interpolation.

    Complete explicit RI components can also be supplied without a wavelength.
    This selects/interpolates the native dimensionless RI/shape grid without
    assigning a physical wavelength. ``run_retrieval`` adds configuration-file
    loading, multi-species execution, strict completion checks and reports.

    For ice, ``target_temperatures=[250]`` (kelvin) together with
    ``target_wavelengths=[1.6]`` selects and interpolates both coordinates.
    Omit temperatures to retain all native temperatures. Positive temperatures
    outside available coverage produce native-schema NaN optical products and
    a boundary warning; nonfinite/nonpositive temperatures are invalid.

    With ``download=True``, ``target_wavelength_mode="interp"`` creates local
    target-wavelength products after downloading exact or bracketing source
    files. Ice retains its complete native schema. Set
    ``apply_interpolation=False`` to request source selection/download only.
    """
    from zju_scatt_interface.access.catalog import objects_from_args
    from zju_scatt_interface.access.download import (
        download_selected_objects,
        limit_download_set,
    )
    from zju_scatt_interface.access.manifests import write_manifest
    from zju_scatt_interface.access.models import RetrievalResult
    from zju_scatt_interface.access.reports import write_operation_log
    from zju_scatt_interface.access.requests import (
        DEFAULT_RETRIEVE_MANIFEST,
        _api_client,
        build_retrieve_runtime_args,
        make_retrieval_args,
    )
    from zju_scatt_interface.optics.retrieval.workflow import (
        apply_downloaded_wavelength_interpolation,
    )

    removed = {"shape_ranges", "shape_targets", "shape_target_tolerance"}.intersection(parameters)
    if removed:
        raise ScattError(
            f"Removed retrieval argument(s): {', '.join(sorted(removed))}. Use shapes instead."
        )
    api_args = make_retrieval_args(**parameters)
    client = _api_client(
        client,
        timeout=timeout,
        retries=retries,
        insecure=insecure,
        quiet=bool(api_args.quiet),
    )
    runtime, _config = build_retrieve_runtime_args(api_args)
    runtime.api_mode = True
    runtime.refractive_index_parameters = api_args.refractive_index_parameters
    runtime.target_temperatures = api_args.target_temperatures
    if runtime.refractive_index_parameters is not None and not runtime.target_wavelengths:
        from zju_scatt_interface.optics.retrieval.indices import retrieve_native_indices

        return retrieve_native_indices(parameters, client=client, runtime=runtime)
    objects, stats = objects_from_args(runtime, client)
    objects, wavelength_processing, target_processings = apply_retrieval_processing(
        objects,
        runtime,
    )
    limited = limit_download_set(objects, runtime.max_files, runtime.max_bytes)
    if len(limited) != len(objects) and any(
        item.get("shape_stencils") for item in wavelength_processing.refractive_index_resolutions
    ):
        raise ScattError(
            "max_files/max_bytes would truncate an interpolation stencil; increase or remove the limit"
        )
    objects = limited
    stats.matched = len(objects)
    stats.bytes = sum(item.size for item in objects)

    manifest_path = runtime.manifest_output
    if manifest_path:
        write_manifest(objects, manifest_path, runtime.format)

    status = 0
    download_results: list[DownloadResult] = []
    interpolated_products: list[Any] = []
    if runtime.download:
        status, download_results = download_selected_objects(
            runtime,
            client,
            objects,
            stats,
        )
        if status == 0:
            wavelength_processing, interpolated_products = (
                apply_downloaded_wavelength_interpolation(
                    runtime,
                    wavelength_processing,
                    download_results,
                )
            )

    operation_log_path = runtime.operation_log
    if operation_log_path:
        write_operation_log(
            operation_log_path,
            args=runtime,
            config_path=getattr(api_args, "config", None),
            stats=stats,
            objects=objects,
            manifest_path=manifest_path or DEFAULT_RETRIEVE_MANIFEST,
            wavelength_processing=wavelength_processing,
            target_processings=target_processings,
            download_enabled=runtime.download,
            results=download_results,
            exit_code=status,
        )

    return RetrievalResult(
        objects=objects,
        stats=stats,
        wavelength_processing=wavelength_processing,
        target_processings=target_processings,
        manifest_path=manifest_path,
        operation_log_path=operation_log_path,
        download_results=download_results,
        interpolated_products=interpolated_products,
        status_code=status,
    )


def search_data(**parameters) -> list[RemoteObject]:
    """Return matching remote files without writing manifests or downloading."""
    parameters.setdefault("download", False)
    return retrieve_sources(**parameters).objects


def estimate_data(**parameters) -> ScanStats:
    """Return count/storage statistics for a script-friendly query."""
    parameters.setdefault("download", False)
    return retrieve_sources(**parameters).stats


def download_data(
    objects: Sequence[RemoteObject],
    *,
    output_dir: Optional[Union[str, Path]] = None,
    client: Optional[ApiClient] = None,
    timeout: float = 30.0,
    retries: int = 3,
    insecure: bool = False,
    workers: int = 4,
    flat: bool = False,
    overwrite: bool = False,
    resume: bool = True,
    verify_etag: bool = False,
    ignore_space: bool = False,
    session: Optional[str] = None,
    no_track: bool = False,
    quiet: bool = True,
) -> list[DownloadResult]:
    """Download an explicit list of ``RemoteObject`` values from Python."""
    from zju_scatt_interface.access.download import download_selected_objects
    from zju_scatt_interface.access.models import (
        ScanStats,
    )
    from zju_scatt_interface.access.requests import API_DATA_DIR, _api_client

    client = _api_client(
        client,
        timeout=timeout,
        retries=retries,
        insecure=insecure,
        quiet=quiet,
    )
    args = argparse.Namespace(
        output_dir=Path(output_dir) if output_dir is not None else API_DATA_DIR,
        flat=flat,
        workers=workers,
        max_files=None,
        max_bytes=None,
        overwrite=overwrite,
        no_resume=not resume,
        verify_etag=verify_etag,
        ignore_space=ignore_space,
        dry_run=False,
        no_progress=True,
        yes=True,
        display_limit=0,
        urls=False,
        session=session,
        no_track=no_track,
    )
    selected = list(objects)
    stats = ScanStats(
        pages=0,
        scanned=len(selected),
        matched=len(selected),
        bytes=sum(item.size for item in selected),
    )
    _status, results = download_selected_objects(args, client, selected, stats)
    return results


def print_retrieve_step(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message)


def apply_retrieval_processing(
    objects: Sequence[RemoteObject], runtime: argparse.Namespace
) -> tuple[list[RemoteObject], WavelengthProcessing, list[NumericSelectionProcessing]]:
    from zju_scatt_interface.access.metadata import SIZE_METADATA_FIELDS
    from zju_scatt_interface.access.requests import _api_sequence
    from zju_scatt_interface.sources.coordinates import (
        normalize_target_refractive_points,
        select_for_numeric_targets,
        select_for_target_wavelength,
    )

    temperatures = getattr(runtime, "target_temperatures", None)
    ice_objects = []
    ice_required = False
    if temperatures is not None:
        from zju_scatt_interface.optics.retrieval.ice import select_sources

        try:
            temperatures = tuple(
                dict.fromkeys(float(value) for value in _api_sequence(temperatures))
            )
        except (TypeError, ValueError) as exc:
            raise ScattError(
                "target_temperatures must contain finite positive kelvin values"
            ) from exc
        if not temperatures or any(
            not math.isfinite(value) or value <= 0 for value in temperatures
        ):
            raise ScattError("target_temperatures must contain finite positive kelvin values")
        if not runtime.target_wavelengths:
            raise ScattError("target_temperatures requires target_wavelengths")
        if getattr(runtime, "target_wavelength_mode", "interp") != "interp":
            raise ScattError("target_temperatures requires target_wavelength_mode='interp'")
        runtime.target_temperatures = temperatures
        ice = [obj for obj in objects if "super_spheroid_ice" in obj.key.split("/")]
        if not ice:
            raise ScattError("target_temperatures requires matching ice source files")
        ice_objects, ice_required = select_sources(
            ice, temperatures, runtime.target_wavelengths, shapes=getattr(runtime, "shapes", None)
        )
        ice_keys = {obj.key for obj in ice}
        objects = [obj for obj in objects if obj.key not in ice_keys]
    if runtime.target_wavelengths:
        from zju_scatt_interface.optics.retrieval.grid import grid_family

        has_grid = any(grid_family(obj) for obj in objects)
        if has_grid and bool(runtime.ref_real_target) != bool(runtime.ref_imag_target):
            raise ScattError(
                "Explicit grid indices require both ref_real_targets and ref_imag_targets; "
                "use refractive_index_parameters for BC/coating indices."
            )
        if has_grid and (runtime.ref_real or runtime.ref_imag):
            raise ScattError(
                "Use refractive_index_parameters or paired index targets with target_wavelengths; "
                "index-range filters are for raw retrieval without a wavelength target."
            )
    target_ref_points = (
        normalize_target_refractive_points(
            runtime.ref_real_target,
            runtime.ref_imag_target,
            len(runtime.target_wavelengths),
        )
        if runtime.target_wavelengths
        else []
    )
    objects, wavelength_processing = select_for_target_wavelength(
        objects,
        runtime.target_wavelengths if objects or not temperatures else None,
        tolerance_um=runtime.target_tolerance or 0.0,
        mode=getattr(runtime, "target_wavelength_mode", "interp"),
        target_refractive_points=target_ref_points,
        refractive_index_parameters=getattr(runtime, "refractive_index_parameters", None),
        shapes=getattr(runtime, "shapes", None),
    )
    if temperatures:
        objects = sorted(objects + ice_objects, key=lambda obj: obj.key)
        wavelength_processing = replace(
            wavelength_processing,
            target_temperatures_k=temperatures,
            target_um=runtime.target_wavelengths[0]
            if len(runtime.target_wavelengths) == 1
            else None,
            target_wavelengths_um=tuple(runtime.target_wavelengths),
            interpolation_required=wavelength_processing.interpolation_required or ice_required,
            interpolation_basis="wavelength_temperature",
            message=wavelength_processing.message
            + " Ice sources selected for wavelength/temperature targets; out-of-coverage temperatures produce NaN optics.",
        )
    for resolution in wavelength_processing.refractive_index_resolutions:
        print(
            f"{resolution['particle_type']} at {resolution['wavelength_um']:g} um: "
            f"{resolution['message']} Resolved indices: {resolution['target_indices']}",
            flush=True,
        )
        for material, relative_path in resolution["table_relative_paths"].items():
            print(
                f"  Default refractive-index table ({material}; relative to zju_scatt_interface/): "
                f"{relative_path}",
                flush=True,
            )
        if resolution["unsupported_series"]:
            print(
                f"{resolution['particle_type']}: omitted {len(resolution['unsupported_series'])} "
                "source series outside index coverage; details are recorded in the provenance.",
                flush=True,
            )
    target_processings: list[NumericSelectionProcessing] = []
    for targets, names, label, tolerance in (
        (
            runtime.ref_real_target,
            ("ref_real",),
            "real refractive index",
            runtime.ref_real_target_tolerance,
        ),
        (
            runtime.ref_imag_target,
            ("ref_imag",),
            "imaginary refractive index",
            runtime.ref_imag_target_tolerance,
        ),
        (
            runtime.target_size,
            SIZE_METADATA_FIELDS,
            "particle size",
            runtime.target_size_tolerance,
        ),
    ):
        if wavelength_processing.refractive_index_resolutions and names in {
            ("ref_real",),
            ("ref_imag",),
        }:
            continue
        objects, processing = select_for_numeric_targets(
            objects,
            targets,
            names,
            label,
            tolerance=tolerance if tolerance is not None else 1e-9,
        )
        if targets:
            target_processings.append(processing)
    for name, targets, tolerance in runtime.shape_targets:
        objects, processing = select_for_numeric_targets(
            objects,
            targets,
            (name,),
            f"shape parameter {name}",
            tolerance=(
                tolerance
                if tolerance is not None
                else runtime.shape_target_tolerance
                if runtime.shape_target_tolerance is not None
                else 1e-9
            ),
        )
        target_processings.append(processing)
    return list(objects), wavelength_processing, target_processings
