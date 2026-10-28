"""Shared command argument definitions and validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from zju_scatt_interface._version import __version__
from zju_scatt_interface.access.endpoints import (
    ROOT_PREFIX,
)
from zju_scatt_interface.errors import ScattError


def add_network_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Request timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retries after transient network failures (default: 3)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (only for diagnosing the website's certificate)",
    )


def add_filter_options(parser: argparse.ArgumentParser) -> None:
    from zju_scatt_interface.access.filters import parse_date_argument, parse_size

    group = parser.add_argument_group("file filters (all different filter types are ANDed)")
    group.add_argument("--glob", action="append", help="Include path/name glob; repeat for OR")
    group.add_argument("--exclude-glob", action="append", help="Exclude path/name glob")
    group.add_argument("--contains", action="append", help="Require text in the full key")
    group.add_argument("--exclude", action="append", help="Reject text in the full key")
    group.add_argument("--regex", action="append", help="Require a regular-expression match")
    group.add_argument(
        "--ignore-case", action="store_true", help="Make --regex and --value-regex case-insensitive"
    )
    group.add_argument("--extension", action="append", help="File extension such as nc or .json")
    group.add_argument("--min-size", type=parse_size, help="Minimum file size, e.g. 5MiB")
    group.add_argument("--max-size", type=parse_size, help="Maximum file size, e.g. 2GB")
    group.add_argument("--after", type=parse_date_argument, help="Modified on/after ISO date")
    group.add_argument("--before", type=parse_date_argument, help="Modified on/before ISO date")
    group.add_argument(
        "--particle-type",
        action="append",
        help="Particle label such as sulfate, super_spheroid_ice, or black carbon; repeat or comma-separate for OR",
    )
    group.add_argument(
        "--wavelength",
        "--wavelength-range",
        dest="wavelength",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Wavelength range in --wavelength-unit units (default: um)",
    )
    group.add_argument(
        "--wavelength-unit",
        default=None,
        help="Unit for wavelength range and bare target wavelengths: um by default, or cm-1",
    )
    group.add_argument(
        "--size-range",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Particle-size range; matches known filename tokens such as L, size, radius, diameter, or reff",
    )
    group.add_argument(
        "--target-size",
        nargs="+",
        metavar="VALUE",
        help="One or more target particle-size values; uses known tokens such as L, size, radius, diameter, or reff",
    )
    group.add_argument(
        "--target-size-tolerance",
        type=float,
        help="Tolerance for exact target-size matches",
    )
    group.add_argument(
        "--ref-real",
        "--ref-real-range",
        dest="ref_real",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Real refractive-index range",
    )
    group.add_argument(
        "--ref-real-target",
        nargs="+",
        metavar="VALUE",
        help="One or more target real refractive-index values",
    )
    group.add_argument(
        "--ref-real-target-tolerance",
        type=float,
        help="Tolerance for exact real refractive-index target matches",
    )
    group.add_argument(
        "--ref-imag",
        "--ref-imag-range",
        dest="ref_imag",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Imaginary refractive-index range",
    )
    group.add_argument(
        "--ref-imag-target",
        nargs="+",
        metavar="VALUE",
        help="One or more target imaginary refractive-index values",
    )
    group.add_argument(
        "--ref-imag-target-tolerance",
        type=float,
        help="Tolerance for exact imaginary refractive-index target matches",
    )
    group.add_argument(
        "--n-range",
        nargs=2,
        type=float,
        metavar=("MIN", "MAX"),
        help="Range for the filename token n",
    )
    group.add_argument(
        "--aspect-ratio", nargs=2, type=float, metavar=("MIN", "MAX"), help="Range for asp/ar"
    )
    group.add_argument(
        "--param",
        "--shape-param",
        dest="param",
        nargs=3,
        action="append",
        metavar=("NAME", "MIN", "MAX"),
        help="Range for any model/shape token encoded as NAME_number; repeatable",
    )
    group.add_argument(
        "--shape-target",
        nargs="+",
        action="append",
        metavar=("NAME", "VALUE"),
        help="One model-specific shape parameter target, e.g. --shape-target roundness 0.3",
    )
    group.add_argument(
        "--shape-target-tolerance",
        type=float,
        help="Default tolerance for shape target matches",
    )
    group.add_argument(
        "--value-regex",
        nargs=3,
        action="append",
        metavar=("REGEX", "MIN", "MAX"),
        help="Custom numeric regex with one capture group or (?P<value>...)",
    )


def add_scan_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Read a previous CSV/JSONL/TXT manifest instead of scanning the website",
    )
    parser.add_argument(
        "--max-scan", type=int, help="Stop after scanning this many objects (safety/testing option)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Hide scan progress and the routine website TLS note",
    )


def add_output_options(parser: argparse.ArgumentParser, include_display: bool = True) -> None:
    parser.add_argument("-o", "--output", type=Path, help="Write the complete matching manifest")
    parser.add_argument(
        "--format",
        choices=("csv", "jsonl", "txt"),
        help="Manifest format; inferred from suffix by default",
    )
    if include_display:
        parser.add_argument(
            "--display-limit",
            type=int,
            default=200,
            help="Rows printed to screen; 0 means all (default: 200)",
        )
        parser.add_argument("--urls", action="store_true", help="Also print direct OSS URLs")


def build_parser() -> argparse.ArgumentParser:
    from zju_scatt_interface.access.filters import parse_size
    from zju_scatt_interface.access.requests import (
        DEFAULT_OPERATION_LOG,
        DEFAULT_RETRIEVE_MANIFEST,
    )
    from zju_scatt_interface.cli.bulk import cmd_compute_bulk
    from zju_scatt_interface.cli.catalog import (
        cmd_browse,
        cmd_check,
        cmd_download,
        cmd_estimate,
        cmd_list_or_search,
        cmd_metadata,
        cmd_register,
        cmd_session,
    )
    from zju_scatt_interface.cli.retrieval import cmd_retrieve

    parser = argparse.ArgumentParser(
        description=(
            "Browse, retrieve, download, and compute with public ZJU-SCATT optical data. "
            "Relative paths start at the BAMS download root."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s browse Single_opt/sphere_sulfate/data/\n"
            "  %(prog)s search Single_opt --wavelength 0.4 0.8 --extension nc -o files.csv\n"
            "  %(prog)s search Single_opt/super_spheroid --ref-real 1.3 1.5 --ref-imag 0 0.1\n"
            "  %(prog)s retrieve --particle-type super_spheroid_ice --wavelength-range 0.4 0.8 --no-download\n"
            "  %(prog)s retrieve --config zju_scatt_request.json\n"
            "  %(prog)s bulk --input single_particle_table.csv --output bulk_optics.json\n"
            "  %(prog)s download Single_opt/sphere_sulfate/data/ -d ./data --yes\n"
            "  %(prog)s download --manifest files.csv -d ./data --yes\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    browse = subparsers.add_parser("browse", help="Show one directory without downloading")
    browse.add_argument(
        "source",
        nargs="?",
        default=ROOT_PREFIX,
        help="Relative path, full key, or download-page URL",
    )
    browse.add_argument(
        "--display-limit", type=int, default=200, help="File rows shown; 0 means all"
    )
    browse.add_argument("--urls", action="store_true", help="Print direct file URLs")
    add_network_options(browse)
    browse.set_defaults(func=cmd_browse)

    listing = subparsers.add_parser(
        "list", help="Recursively inventory files below one or more paths"
    )
    listing.add_argument(
        "source", nargs="*", default=[ROOT_PREFIX], help="Paths or URLs (default: database root)"
    )
    add_filter_options(listing)
    add_scan_options(listing)
    add_output_options(listing)
    add_network_options(listing)
    listing.set_defaults(func=cmd_list_or_search)

    search = subparsers.add_parser(
        "search", help="Recursively search by scientific or custom conditions"
    )
    search.add_argument(
        "source", nargs="*", default=[ROOT_PREFIX], help="Paths or URLs (default: database root)"
    )
    add_filter_options(search)
    add_scan_options(search)
    add_output_options(search)
    add_network_options(search)
    search.set_defaults(func=cmd_list_or_search)

    estimate = subparsers.add_parser("estimate", help="Count files and storage without downloading")
    estimate.add_argument("source", nargs="*", default=[ROOT_PREFIX], help="Paths or URLs")
    add_filter_options(estimate)
    add_scan_options(estimate)
    add_output_options(estimate, include_display=False)
    add_network_options(estimate)
    estimate.set_defaults(func=cmd_estimate)

    bulk = subparsers.add_parser(
        "bulk",
        help="Compute bulk optical properties from a size distribution table",
    )
    bulk.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="CSV table with size, number distribution, and single-particle optical columns",
    )
    bulk.add_argument("-o", "--output", type=Path, help="Write the result as JSON")
    bulk.add_argument(
        "--operation-log",
        type=Path,
        help="Write a calculation operation log",
    )
    bulk.add_argument(
        "--distribution-mode",
        choices=("density", "bin"),
        default="density",
        help="Interpret the number column as dN/dsize or per-bin number (default: density)",
    )
    size_mode = bulk.add_mutually_exclusive_group()
    size_mode.add_argument(
        "--size-is-radius",
        action="store_true",
        help="Interpret the size column as particle radius",
    )
    size_mode.add_argument(
        "--size-is-diameter",
        action="store_true",
        help="Interpret the size column as particle diameter",
    )
    bulk.add_argument(
        "--size-unit",
        default="unspecified",
        help="Size unit label stored in output metadata, e.g. um or m",
    )
    bulk.add_argument(
        "--number-unit",
        default="unspecified",
        help="Number-distribution unit label stored in output metadata",
    )
    bulk.add_argument("--size-column", help="CSV column containing size values")
    bulk.add_argument("--number-column", help="CSV column containing number distribution")
    bulk.add_argument("--extinction-column", help="CSV column containing Cext")
    bulk.add_argument("--scattering-column", help="CSV column containing Csca")
    bulk.add_argument("--absorption-column", help="CSV column containing Cabs")
    bulk.add_argument(
        "--extinction-efficiency-column",
        help="CSV column containing Qext; converted using geometric area",
    )
    bulk.add_argument(
        "--scattering-efficiency-column",
        help="CSV column containing Qsca; converted using geometric area",
    )
    bulk.add_argument(
        "--absorption-efficiency-column",
        help="CSV column containing Qabs; converted using geometric area",
    )
    bulk.add_argument("--asymmetry-column", help="CSV column containing g")
    bulk.add_argument(
        "--plot", type=Path, help="Write a PNG/PDF/SVG plot of the calculated bulk optics"
    )
    bulk.add_argument("--plot-title", help="Title for --plot output")
    bulk.add_argument("--compact", action="store_true", help="Write compact JSON")
    bulk.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    bulk.set_defaults(
        func=cmd_compute_bulk,
        timeout=30.0,
        retries=0,
        insecure=False,
    )

    retrieve = subparsers.add_parser(
        "retrieve",
        help="Retrieve data by particle type, wavelength range, size range, or config file",
    )
    retrieve.add_argument(
        "source", nargs="*", help="Optional paths or URLs; defaults to config or database root"
    )
    retrieve.add_argument(
        "--config", type=Path, help="Read retrieval parameters from a JSON config file"
    )
    retrieve.add_argument(
        "--write-config-template",
        type=Path,
        help="Write a sample JSON retrieval config and exit",
    )
    retrieve.add_argument(
        "--force",
        action="store_true",
        help="Allow --write-config-template to replace an existing file",
    )
    add_filter_options(retrieve)
    add_scan_options(retrieve)
    retrieve.add_argument(
        "--target-wavelength",
        nargs="+",
        metavar="VALUE",
        help=(
            "Request one or more specific wavelengths. Values use "
            "--wavelength-unit unless a unit is attached, e.g. 0.55, "
            "0.55um, 550nm, or 10000cm-1."
        ),
    )
    retrieve.add_argument(
        "--target-wavelength-mode",
        choices=("interp", "nearest"),
        help=(
            "For target wavelengths without an exact product, select source "
            "points for interpolation in refractive-index (n,k) space or use "
            "the nearest available wavelength (default: interp)."
        ),
    )
    retrieve.add_argument(
        "--target-tolerance",
        type=float,
        metavar="UM",
        help="Tolerance for treating a target wavelength as exact (default: 1e-9)",
    )
    retrieve.add_argument(
        "--manifest-output",
        type=Path,
        help=f"Write the selected manifest here (default: {DEFAULT_RETRIEVE_MANIFEST})",
    )
    retrieve.add_argument(
        "--operation-log",
        type=Path,
        help=f"Write the retrieval operation log here (default: {DEFAULT_OPERATION_LOG})",
    )
    retrieve.add_argument("--format", choices=("csv", "jsonl", "txt"), help="Manifest format")
    retrieve.add_argument(
        "--download",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Download selected files after writing the manifest (default: true)",
    )
    retrieve.add_argument("-d", "--output-dir", type=Path, help="Local destination")
    retrieve.add_argument(
        "--apply-interpolation",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Generate derived values after downloading target sources (default: true)",
    )
    retrieve.add_argument(
        "--interpolation-output-dir", type=Path, help="Directory for derived NetCDF products"
    )
    retrieve.add_argument(
        "--interpolation-include-phase-matrix",
        action="store_true",
        default=None,
        help="Compatibility option; native retrieval products always retain source phase matrices",
    )
    retrieve.add_argument("--workers", type=int, help="Concurrent files, 1-32")
    retrieve.add_argument("--max-files", type=int, help="Download at most this many matched files")
    retrieve.add_argument("--max-bytes", help="Download at most this total listed size, e.g. 2GiB")
    retrieve.add_argument(
        "--flat", action="store_true", default=None, help="Put all files in one directory"
    )
    retrieve.add_argument(
        "--overwrite",
        action="store_true",
        default=None,
        help="Replace complete destination files with different sizes",
    )
    retrieve.add_argument(
        "--no-resume",
        action="store_true",
        default=None,
        help="Restart .part files instead of resuming",
    )
    retrieve.add_argument(
        "--verify-etag", action="store_true", default=None, help="Verify simple MD5 ETags"
    )
    retrieve.add_argument(
        "--ignore-space",
        action="store_true",
        default=None,
        help="Continue when listed size exceeds free disk space",
    )
    retrieve.add_argument(
        "--dry-run", action="store_true", default=None, help="Show selection without downloading"
    )
    retrieve.add_argument(
        "--no-progress", action="store_true", default=None, help="Disable download progress bar"
    )
    retrieve.add_argument(
        "-y", "--yes", action="store_true", default=None, help="Do not ask for final confirmation"
    )
    retrieve.add_argument("--display-limit", type=int, help="Rows printed to screen; 0 means all")
    retrieve.add_argument(
        "--urls", action="store_true", default=None, help="Also print direct OSS URLs"
    )
    retrieve.add_argument("--session", help="Website download-tracking session token")
    retrieve.add_argument(
        "--no-track",
        action="store_true",
        default=None,
        help="Disable download tracking; registration is still required",
    )
    add_network_options(retrieve)
    retrieve.set_defaults(
        func=cmd_retrieve,
        ignore_case=None,
        quiet=None,
    )

    download = subparsers.add_parser(
        "download", help="Download selected files with resume and concurrency"
    )
    download.add_argument("source", nargs="*", help="Paths or URLs; omit when using --manifest")
    add_filter_options(download)
    add_scan_options(download)
    download.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=Path("zju_scatt_data"),
        help="Local destination (default: ./zju_scatt_data)",
    )
    download.add_argument(
        "--workers", type=int, default=4, help="Concurrent files, 1-32 (default: 4)"
    )
    download.add_argument("--max-files", type=int, help="Download at most this many matched files")
    download.add_argument(
        "--max-bytes", type=parse_size, help="Download at most this total listed size"
    )
    download.add_argument(
        "--flat", action="store_true", help="Put all files in one directory; fails on collisions"
    )
    download.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace complete destination files with different sizes",
    )
    download.add_argument(
        "--no-resume", action="store_true", help="Restart .part files instead of using HTTP Range"
    )
    download.add_argument(
        "--verify-etag",
        action="store_true",
        help="Verify MD5 when the OSS ETag is a simple MD5 (multipart ETags cannot be verified this way)",
    )
    download.add_argument(
        "--ignore-space",
        action="store_true",
        help="Continue when listed size exceeds free disk space",
    )
    download.add_argument(
        "--dry-run", action="store_true", help="Show selection and storage estimate only"
    )
    download.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the interactive aggregate download progress bar",
    )
    download.add_argument(
        "-y", "--yes", action="store_true", help="Do not ask for final confirmation"
    )
    download.add_argument(
        "--display-limit", type=int, default=200, help="Dry-run rows shown; 0 means all"
    )
    download.add_argument("--urls", action="store_true", help="Show URLs in dry-run output")
    download.add_argument("--session", help="Website download-tracking session token")
    download.add_argument(
        "--no-track",
        action="store_true",
        help="Disable download tracking; registration is still required",
    )
    add_network_options(download)
    download.set_defaults(func=cmd_download)

    register = subparsers.add_parser(
        "register",
        help="Register directly in the CLI or import a browser-created token",
    )
    register.add_argument("--name", help="Name or username (optional)")
    register.add_argument("--organization", help="Organization (required)")
    register.add_argument("--country", help="Country/region code such as CN or US (required)")
    register.add_argument("--email", help="Email (optional)")
    register.add_argument("--intended-use", help="Intended use (optional)")
    register.add_argument(
        "--dataset-need",
        action="append",
        choices=("single_optical", "bulk_optical", "ml_model"),
        help="Dataset interest; repeatable",
    )
    register.add_argument(
        "--consent",
        action="store_true",
        help="Consent to usage/impact reporting (required non-interactively)",
    )
    register.add_argument(
        "--minimal",
        action="store_true",
        help="Submit only organization, country/region, and consent",
    )
    register.add_argument(
        "--debug",
        action="store_true",
        help="Print the outgoing request structure with personal values redacted",
    )
    registration_method = register.add_mutually_exclusive_group()
    registration_method.add_argument(
        "--method",
        choices=("direct", "browser"),
        default="direct",
        help="Registration path: direct CLI form or browser token import (default: direct)",
    )
    registration_method.add_argument(
        "--browser-assisted",
        dest="method",
        action="store_const",
        const="browser",
        help="Deprecated alias for --method browser",
    )
    register.add_argument(
        "--no-open",
        action="store_true",
        help="Print the registration URL without trying to launch a browser",
    )
    add_network_options(register)
    register.set_defaults(func=cmd_register)

    session = subparsers.add_parser("session", help="Validate or clear a saved tracking session")
    session_group = session.add_mutually_exclusive_group()
    session_group.add_argument(
        "--session", help="Explicit token instead of saved/environment token"
    )
    session_group.add_argument(
        "--save", metavar="TOKEN", help="Validate and save a token obtained from the website"
    )
    session_group.add_argument(
        "--clear", action="store_true", help="Remove the one saved session file"
    )
    add_network_options(session)
    session.set_defaults(func=cmd_session)

    metadata = subparsers.add_parser(
        "metadata", help="Show scientific values parsed from file names"
    )
    metadata.add_argument("name", nargs="+", help="One or more file names/keys")
    metadata.set_defaults(func=cmd_metadata, timeout=30.0, retries=0)

    check = subparsers.add_parser("check", help="Test read-only connectivity to the listing API")
    add_network_options(check)
    check.set_defaults(func=cmd_check)
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    workers = getattr(args, "workers", None)
    if workers is not None and (workers < 1 or workers > 32):
        raise ScattError("--workers must be between 1 and 32")
    if getattr(args, "retries", 0) < 0:
        raise ScattError("--retries cannot be negative")
    if getattr(args, "timeout", 1) <= 0:
        raise ScattError("--timeout must be positive")
    for name in ("display_limit", "max_scan", "max_files"):
        value = getattr(args, name, None)
        if value is not None and value < 0:
            raise ScattError(f"--{name.replace('_', '-')} cannot be negative")
    if args.command == "download" and args.manifest and args.source:
        raise ScattError("Use either source paths or --manifest, not both")
    if args.command == "download" and not args.manifest and not args.source:
        raise ScattError("download needs at least one source path or --manifest")
