"""Retrieval and bulk operation reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from zju_scatt_interface._version import __version__
from zju_scatt_interface.access.models import (
    DownloadResult,
    NumericSelectionProcessing,
    RemoteObject,
    ScanStats,
    WavelengthProcessing,
)
from zju_scatt_interface.optics.models import BulkOptics


def write_operation_log(
    path: Path,
    *,
    args: argparse.Namespace,
    config_path: Optional[Path],
    stats: ScanStats,
    objects: Sequence[RemoteObject],
    manifest_path: Path,
    wavelength_processing: WavelengthProcessing,
    target_processings: Sequence[NumericSelectionProcessing],
    download_enabled: bool,
    results: Sequence[DownloadResult],
    exit_code: int,
) -> None:
    from zju_scatt_interface.access.catalog import relative_remote_key
    from zju_scatt_interface.access.filters import human_size
    from zju_scatt_interface.access.metadata import expand_string_list
    from zju_scatt_interface.sources.coordinates import object_wavelength_um

    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    result_counts = {
        status: sum(result.status == status for result in results)
        for status in ("downloaded", "skipped", "failed")
    }
    unique_wavelengths = sorted(
        {
            round(value, 12)
            for value in (object_wavelength_um(item) for item in objects)
            if value is not None
        }
    )
    with path.open("w", encoding="utf-8") as stream:
        stream.write("ZJU-SCATT retrieval operation log\n")
        stream.write(f"Generated UTC: {datetime.now(timezone.utc).isoformat()}\n")
        stream.write(f"Software version: {__version__}\n")
        stream.write(
            f"Config file: {config_path.expanduser() if config_path else 'command line only'}\n\n"
        )

        stream.write("Request\n")
        manifest_input = getattr(args, "manifest", None)
        source_text = ", ".join(args.source) if not manifest_input else "manifest input"
        stream.write(f"  Sources: {source_text}\n")
        stream.write(f"  Manifest input: {manifest_input or 'not used'}\n")
        stream.write(
            f"  Particle types: {', '.join(expand_string_list(args.particle_type or [])) or 'all'}\n"
        )
        stream.write(f"  Wavelength range: {args.wavelength or 'all'}\n")
        stream.write(f"  Wavelength input unit: {getattr(args, 'wavelength_unit', 'um')}\n")
        targets = getattr(args, "target_wavelengths", None) or []
        target_text = ", ".join(f"{value:g}" for value in targets) or "not specified"
        stream.write(f"  Target wavelengths (um): {target_text}\n")
        stream.write(
            f"  Target wavelength mode: {getattr(args, 'target_wavelength_mode', 'interp')}\n"
        )
        stream.write(f"  Size range: {args.size_range or 'all sizes'}\n")
        stream.write(f"  Target size: {getattr(args, 'target_size', None) or 'not specified'}\n")
        stream.write(f"  Refractive real range: {args.ref_real or 'all'}\n")
        stream.write(
            f"  Refractive real targets: {getattr(args, 'ref_real_target', None) or 'not specified'}\n"
        )
        stream.write(f"  Refractive imaginary range: {args.ref_imag or 'all'}\n")
        stream.write(
            f"  Refractive imaginary targets: {getattr(args, 'ref_imag_target', None) or 'not specified'}\n"
        )
        stream.write(f"  Shape n range: {args.n_range or 'all'}\n")
        stream.write(f"  Aspect-ratio range: {args.aspect_ratio or 'all'}\n")
        shape_targets = getattr(args, "shape_targets", None) or []
        stream.write(f"  Shape targets: {shape_targets or 'not specified'}\n")
        stream.write(f"  Shapes: {getattr(args, 'shapes', None) or 'not specified'}\n")
        stream.write(f"  Extensions: {', '.join(args.extension or []) or 'all'}\n\n")

        stream.write("Database operations\n")
        stream.write(f"  Scanned {stats.scanned:,} objects across {stats.pages:,} listing pages.\n")
        stream.write(
            f"  Selected {len(objects):,} files, {human_size(sum(item.size for item in objects))}.\n"
        )
        stream.write(
            "  Wavelength scattering data read: "
            f"{', '.join(f'{value:g} um' for value in unique_wavelengths) or 'none parsed'}\n"
        )
        stream.write(f"  Wavelength processing: {wavelength_processing.message}\n")
        for resolution in wavelength_processing.refractive_index_resolutions:
            stream.write(
                "  Refractive-index resolution: " + json.dumps(resolution, sort_keys=True) + "\n"
            )
        if wavelength_processing.target_refractive_points:
            stream.write(
                "  Target refractive-index points (n,k): "
                + ", ".join(
                    f"({real:.12g}, {imag:.12g})"
                    for real, imag in wavelength_processing.target_refractive_points
                )
                + "\n"
            )
        if wavelength_processing.selected_refractive_points:
            stream.write(
                "  Selected refractive-index points (n,k): "
                + ", ".join(
                    f"({real:.12g}, {imag:.12g})"
                    for real, imag in wavelength_processing.selected_refractive_points
                )
                + "\n"
            )
        stream.write(
            "  Interpolation source selection: "
            f"{'yes' if wavelength_processing.interpolation_required else 'no'}\n"
        )
        stream.write(
            "  Interpolated data product generated: "
            f"{'yes' if wavelength_processing.interpolation_applied else 'no'}\n"
        )
        stream.write(f"  Interpolation basis: {wavelength_processing.interpolation_basis}\n")
        for processing in target_processings:
            stream.write(f"  {processing.label} processing: {processing.message}\n")
            stream.write(
                f"  {processing.label} interpolation source selection: "
                f"{'yes' if processing.interpolation_required else 'no'}\n"
            )
            stream.write(
                f"  {processing.label} interpolated data product generated: "
                f"{'yes' if processing.interpolation_applied else 'no'}\n"
            )
            stream.write(
                f"  {processing.label} interpolation basis: {processing.interpolation_basis}\n"
            )
        if wavelength_processing.interpolation_required:
            if wavelength_processing.interpolation_basis == "refractive_index_nk":
                stream.write(
                    "  Processing note: source files were selected for "
                    "interpolation using distance in the refractive-index "
                    "(n,k) plane; this dependency-free CLI did not generate "
                    "a new interpolated NetCDF product.\n"
                )
            else:
                stream.write(
                    "  Processing note: source files were selected for "
                    "target-wavelength interpolation; this dependency-free "
                    "CLI did not generate a new interpolated NetCDF product.\n"
                )
        if any(processing.interpolation_required for processing in target_processings):
            stream.write(
                "  Processing note: bracketing source files were selected for one "
                "or more non-wavelength target parameters; this dependency-free "
                "CLI did not generate a new interpolated NetCDF product.\n"
            )
        stream.write("\n")

        stream.write("Outputs\n")
        stream.write(f"  Manifest: {manifest_path.expanduser().resolve()}\n")
        stream.write(f"  Operation log: {path.resolve()}\n")
        stream.write(f"  Download requested: {'yes' if download_enabled else 'no'}\n")
        if download_enabled:
            stream.write(f"  Destination: {args.output_dir.expanduser().resolve()}\n")
            stream.write(
                "  Download results: "
                f"{result_counts['downloaded']} downloaded, "
                f"{result_counts['skipped']} skipped, "
                f"{result_counts['failed']} failed.\n"
            )
        stream.write("\nSelected files\n")
        for item in objects:
            stream.write(f"  - {relative_remote_key(item.key)} | {human_size(item.size)}\n")

        stream.write("\nStatus\n")
        if exit_code == 0:
            stream.write("  DATA RETRIEVAL SUCCESSFUL\n")
        else:
            stream.write("  DATA RETRIEVAL FINISHED WITH FAILURES\n")


def write_bulk_operation_log(
    path: Union[str, Path],
    *,
    result: BulkOptics,
    input_path: Union[str, Path],
    columns: Mapping[str, Optional[str]],
    output_path: Optional[Union[str, Path]],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as stream:
        stream.write("ZJU-SCATT bulk optical calculation log\n")
        stream.write(f"Created: {datetime.now(timezone.utc).isoformat()}\n")
        stream.write(f"Input table: {Path(input_path).expanduser().resolve()}\n")
        if output_path:
            stream.write(f"Output JSON: {Path(output_path).expanduser().resolve()}\n")
        stream.write("\nColumns\n")
        for key, value in columns.items():
            stream.write(f"  {key}: {value or 'not provided'}\n")
        stream.write("\nIntegration settings\n")
        for key, value in result.metadata.items():
            stream.write(f"  {key}: {value}\n")
        stream.write("\nBulk optical properties\n")
        stream.write(f"  Number concentration: {result.number_concentration:.12g}\n")
        stream.write(f"  Extinction coefficient: {result.extinction_coefficient}\n")
        stream.write(f"  Scattering coefficient: {result.scattering_coefficient}\n")
        stream.write(f"  Absorption coefficient: {result.absorption_coefficient}\n")
        stream.write(f"  Single-scattering albedo: {result.single_scattering_albedo}\n")
        stream.write(f"  Asymmetry factor g: {result.asymmetry_factor}\n")
        stream.write("\nBULK OPTICAL CALCULATION SUCCESSFUL\n")
