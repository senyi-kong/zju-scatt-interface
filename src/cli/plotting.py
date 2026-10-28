"""Single-particle and bulk plotting command drivers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import zju_scatt_interface.access.client as _domain_access_client
from zju_scatt_interface.plotting.bulk import plot_bulk_optics
from zju_scatt_interface.plotting.single import plot_single_scattering


def _plot_kind(source: Path) -> str:
    """Identify canonical bulk products; other supported files use the L1 loader."""

    from zju_scatt_interface.io.tables import _normalize_content

    try:
        content = _normalize_content(source)
    except (KeyError, OSError, TypeError, ValueError):
        return "single"
    containers = [content.get("datasets", {})]
    containers.extend(
        component.get("datasets", {}) for component in content.get("components", {}).values()
    )
    bulk_fields = {
        "beta_ext",
        "beta_sca",
        "beta_abs",
        "extinction_coefficient",
        "scattering_coefficient",
        "absorption_coefficient",
    }
    if any(bulk_fields.intersection(name.lower() for name in datasets) for datasets in containers):
        return "bulk"
    return "single"


def _coordinate_indices(values: Sequence[str]) -> dict[str, int]:
    result = {}
    for value in values:
        name, separator, index = value.partition("=")
        if not separator or not name.strip() or not index.strip():
            raise ValueError("--index must use DIM=INTEGER (zero-based)")
        try:
            parsed = int(index)
        except ValueError as exc:
            raise ValueError("--index must use DIM=INTEGER (zero-based)") from exc
        if parsed < 0:
            raise ValueError("--index values must be zero or greater")
        if name.strip() in result:
            raise ValueError(f"duplicate --index dimension: {name.strip()}")
        result[name.strip()] = parsed
    return result


def _cmd_plot(args: argparse.Namespace, _client: _domain_access_client.ApiClient) -> int:
    from zju_scatt_interface.plotting.bulk import plot_bulk_optics
    from zju_scatt_interface.plotting.single import plot_single_scattering

    source = args.file.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"optical data file does not exist: {source}")
    try:
        kind = _plot_kind(source) if args.kind == "auto" else args.kind
        if kind == "bulk":
            if args.wavelength_um is not None or args.index:
                raise ValueError("--wavelength-um and --index apply only to single-particle files")
            result = plot_bulk_optics(
                source,
                output_dir=args.output_dir,
                show=args.show,
            )
        else:
            result = plot_single_scattering(
                source,
                output_dir=args.output_dir,
                wavelength_um=args.wavelength_um,
                coordinate_indices=_coordinate_indices(args.index),
                show=args.show,
            )
    except ImportError as exc:
        raise ValueError(
            "file plotting requires optional dependencies; install zju-scatt-interface[plot]"
        ) from exc
    print(f"{kind.capitalize()} plots saved to: {result['output_dir']}")
    return 0


def run_single_scattering_plot(argv=None, *, default_file=None, default_output_dir=None):
    """Read command-line options and generate standard single-scattering plots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", help="Obtained single-scattering NetCDF file")
    parser.add_argument("--file", dest="file_option", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", default=default_output_dir)
    parser.add_argument(
        "--wavelength-um", type=float, help="For RI-grid files without a wavelength"
    )
    parser.add_argument(
        "--index",
        action="append",
        default=[],
        metavar="DIM=INDEX",
        help="Select an extra native axis, e.g. rh=0",
    )
    parser.add_argument("--show", action="store_true", help="Also display figures interactively")
    args = parser.parse_args(argv)
    source = args.file or args.file_option or default_file
    if source is None:
        parser.error("Provide an obtained NetCDF file")
    try:
        indices = dict(item.split("=", 1) for item in args.index)
        indices = {key: int(value) for key, value in indices.items()}
    except ValueError:
        parser.error("Use --index DIM=INTEGER (zero-based)")
    result = plot_single_scattering(
        source,
        output_dir=args.output_dir,
        wavelength_um=args.wavelength_um,
        coordinate_indices=indices,
        show=args.show,
    )
    print(f"Plots saved to: {result['output_dir']}")
    return result


def run_bulk_optics_plot(argv=None, *, default_file=None, default_output_dir=None):
    """Read a bulk data file and save standard dimension-aware inspection plots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", default=default_file, help="Obtained bulk NC/HDF5 file")
    parser.add_argument("--output-dir", default=default_output_dir)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)
    if args.file is None:
        parser.error("Provide an obtained bulk optics file")
    result = plot_bulk_optics(args.file, output_dir=args.output_dir, show=args.show)
    print(f"Bulk plots saved to: {result['output_dir']}")
    return result
