"""Construction of the complete command-line parser."""

from __future__ import annotations

import argparse
from pathlib import Path as _external_Path

import zju_scatt_interface.cli.arguments as _domain_cli_arguments


def build_parser() -> argparse.ArgumentParser:
    from zju_scatt_interface.cli.bulk import (
        _cmd_bulk_opt_build,
        _cmd_bulk_opt_plan,
        _cmd_bulk_opt_schema,
        _cmd_bulk_opt_validate,
        _cmd_psd_check,
        _cmd_scheme,
        _cmd_scheme_sources,
    )
    from zju_scatt_interface.cli.catalog import _cmd_describe, _cmd_resolve_ri
    from zju_scatt_interface.cli.doctor import _cmd_doctor
    from zju_scatt_interface.cli.plotting import _cmd_plot

    parser = _domain_cli_arguments.build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    plot = subparsers.add_parser(
        "plot",
        help="Generate diagnostic plots from an existing optical data file",
    )
    plot.add_argument(
        "file",
        type=_external_Path,
        help="Single-particle or canonical bulk NetCDF4/HDF5 file",
    )
    plot.add_argument(
        "--kind",
        choices=("auto", "single", "bulk"),
        default="auto",
        help="Input type (default: detect automatically)",
    )
    plot.add_argument(
        "--output-dir",
        type=_external_Path,
        help="Directory for generated PNG, PDF, SVG, CSV, and inspection files",
    )
    plot.add_argument(
        "--wavelength-um",
        type=float,
        help="Wavelength for a single-particle RI-grid file without wavelength metadata",
    )
    plot.add_argument(
        "--index",
        action="append",
        default=[],
        metavar="DIM=INDEX",
        help="Select an extra single-particle axis (repeatable, zero-based)",
    )
    plot.add_argument(
        "--show",
        action="store_true",
        help="Also display figures interactively",
    )
    plot.set_defaults(
        func=_cmd_plot,
        timeout=30.0,
        retries=0,
        insecure=False,
        quiet=True,
    )

    scheme = subparsers.add_parser("scheme", help="Validate a user-defined bulk optical scheme")
    scheme.add_argument("config", type=_external_Path, help="Bulk-scheme JSON configuration")
    scheme.add_argument("--json", action="store_true", help="Print a machine-readable summary")
    scheme.set_defaults(func=_cmd_scheme, timeout=30.0, retries=0, insecure=False)

    bulk_opt = subparsers.add_parser(
        "bulk-opt",
        help="Validate, plan, or build a user-defined bulk optical product",
    )
    bulk_opt_actions = bulk_opt.add_subparsers(
        dest="bulk_opt_action",
        required=True,
    )
    bulk_schema = bulk_opt_actions.add_parser(
        "schema",
        help="Print the machine-readable scheme/command reference",
    )
    bulk_schema.add_argument(
        "--particle-type",
        help="Restrict the reference to one particle profile or alias",
    )
    bulk_schema.add_argument(
        "--output",
        type=_external_Path,
        help="Write the reference as JSON",
    )
    bulk_schema.add_argument(
        "--json",
        action="store_true",
        help="Print the complete machine-readable reference",
    )
    bulk_schema.set_defaults(
        func=_cmd_bulk_opt_schema,
        timeout=30.0,
        retries=0,
        insecure=False,
        quiet=True,
    )
    bulk_validate = bulk_opt_actions.add_parser(
        "validate",
        help="Normalize and validate a versioned scheme without network access",
    )
    bulk_validate.add_argument("scheme", type=_external_Path)
    bulk_validate.add_argument(
        "--report",
        type=_external_Path,
        help="Atomically write the complete JSON validation report",
    )
    bulk_validate.add_argument("--json", action="store_true", help="Print the complete JSON report")
    bulk_validate.set_defaults(
        func=_cmd_bulk_opt_validate,
        timeout=30.0,
        retries=0,
        insecure=False,
        quiet=True,
    )

    bulk_plan = bulk_opt_actions.add_parser(
        "plan",
        help="Resolve dependencies without downloading or calculating",
    )
    bulk_plan.add_argument("scheme", type=_external_Path)
    bulk_plan.add_argument(
        "--workspace",
        type=_external_Path,
        default=_external_Path("zju_scatt_data"),
        help="Cache/work/manifest/output root",
    )
    bulk_plan.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="COMPONENT=PATH",
        help="Use a local L1 source directory/file for one component",
    )
    bulk_plan.add_argument(
        "--offline",
        action="store_true",
        help="Inspect only a saved manifest and verified cache",
    )
    bulk_plan.add_argument(
        "--dry-run",
        action="store_true",
        help="Compile deterministic dependency queries without network access",
    )
    bulk_plan.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow resumable downloads in a later build (default: enabled)",
    )
    bulk_plan.add_argument(
        "--no-schema-validation",
        action="store_true",
        help="Skip L1 NetCDF schema inspection",
    )
    bulk_plan.add_argument("--session", help="Explicit website session token")
    bulk_plan.add_argument(
        "--no-track",
        action="store_true",
        help="Disable download tracking; registration is still required",
    )
    bulk_plan.add_argument("--report", type=_external_Path)
    bulk_plan.add_argument("--json", action="store_true")
    _domain_cli_arguments.add_network_options(bulk_plan)
    bulk_plan.set_defaults(func=_cmd_bulk_opt_plan, quiet=True)

    bulk_build = bulk_opt_actions.add_parser(
        "build",
        help="Download, interpolate, integrate, validate, and write the product",
    )
    bulk_build.add_argument("scheme", type=_external_Path)
    bulk_build.add_argument(
        "--workspace",
        type=_external_Path,
        default=_external_Path("zju_scatt_data"),
        help="Cache/work/manifest/output root",
    )
    bulk_build.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="COMPONENT=PATH",
        help="Use a local L1 source directory/file for one component",
    )
    bulk_build.add_argument(
        "--output",
        type=_external_Path,
        help="Override the scheme output path",
    )
    bulk_build.add_argument(
        "--format",
        choices=("netcdf4", "hdf5"),
        help="Override the scheme output format",
    )
    bulk_build.add_argument(
        "--offline",
        action="store_true",
        help="Use only the verified local cache/saved manifest",
    )
    bulk_build.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show the build without network or calculation",
    )
    bulk_build.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume partial source downloads (default: enabled)",
    )
    bulk_build.add_argument(
        "--phase-matrix",
        action="store_true",
        help="Calculate and store the six independent phase elements",
    )
    bulk_build.add_argument(
        "--angle-step",
        type=float,
        help="Common scattering-angle spacing in degrees",
    )
    bulk_build.add_argument(
        "--truncation-policy",
        choices=("error", "truncate"),
        default=None,
        help="Override PSD coverage handling",
    )
    bulk_build.add_argument(
        "--check-convergence",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    bulk_build.add_argument(
        "--convergence-tolerance",
        type=float,
        default=None,
    )
    bulk_build.add_argument(
        "--strict-convergence",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    bulk_build.add_argument(
        "--strict-qa",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    bulk_build.add_argument(
        "--compression-level",
        type=int,
        choices=range(10),
        metavar="0..9",
    )
    bulk_build.add_argument(
        "--no-schema-validation",
        action="store_true",
        help="Skip L1 NetCDF schema inspection",
    )
    bulk_build.add_argument("--session", help="Explicit website session token")
    bulk_build.add_argument(
        "--no-track",
        action="store_true",
        help="Disable download tracking; registration is still required",
    )
    bulk_build.add_argument("--report", type=_external_Path)
    bulk_build.add_argument("--json", action="store_true")
    _domain_cli_arguments.add_network_options(bulk_build)
    bulk_build.set_defaults(func=_cmd_bulk_opt_build, quiet=True)

    scheme_sources = subparsers.add_parser(
        "scheme-sources",
        help="Plan, download, validate, and cache every source required by a scheme",
    )
    scheme_sources.add_argument(
        "config",
        type=_external_Path,
        help="Validated bulk-scheme JSON configuration",
    )
    scheme_sources.add_argument(
        "--workspace",
        type=_external_Path,
        default=_external_Path("zju_scatt_data"),
        help="Cache/work/manifest root (default: ./zju_scatt_data)",
    )
    scheme_sources.add_argument(
        "--offline",
        action="store_true",
        help="Use only the saved source manifest and verified local cache",
    )
    scheme_sources.add_argument(
        "--no-download",
        action="store_true",
        help="Write the dependency plan without downloading missing/invalid files",
    )
    scheme_sources.add_argument(
        "--no-schema-validation",
        action="store_true",
        help="Skip NetCDF schema checks (size/hash checks still run)",
    )
    scheme_sources.add_argument(
        "--session",
        help="Explicit website session token instead of saved/environment token",
    )
    scheme_sources.add_argument(
        "--no-track",
        action="store_true",
        help="Disable download tracking; registration is still required",
    )
    scheme_sources.add_argument(
        "--json",
        action="store_true",
        help="Print the complete machine-readable source plan",
    )
    _domain_cli_arguments.add_network_options(scheme_sources)
    scheme_sources.set_defaults(func=_cmd_scheme_sources, quiet=True)

    psd_check = subparsers.add_parser(
        "psd-check",
        help="Validate and summarize array-first PSD inputs in a bulk scheme",
    )
    psd_check.add_argument(
        "config",
        type=_external_Path,
        help="Bulk-scheme JSON configuration",
    )
    psd_check.add_argument(
        "--component",
        help="Check one named component instead of every component",
    )
    psd_check.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable PSD report",
    )
    psd_check.set_defaults(
        func=_cmd_psd_check,
        timeout=30.0,
        retries=0,
        insecure=False,
        quiet=True,
    )

    doctor = subparsers.add_parser(
        "doctor",
        help="Check installation, paths, optional dependencies, session, and connectivity",
    )
    doctor.add_argument(
        "--data-dir",
        type=_external_Path,
        default=_external_Path("zju_scatt_data"),
        help="Data/cache directory to check (default: ./zju_scatt_data)",
    )
    doctor.add_argument(
        "--offline",
        action="store_true",
        help="Skip database connectivity and remote session validation",
    )
    doctor.add_argument("--json", action="store_true", help="Print a machine-readable report")
    _domain_cli_arguments.add_network_options(doctor)
    doctor.set_defaults(func=_cmd_doctor, quiet=True)

    describe = subparsers.add_parser(
        "describe",
        help="Explain a particle profile and optionally validate an L1 source file",
    )
    describe.add_argument(
        "particle_type",
        nargs="?",
        help="Canonical particle type or alias; omit to list all profiles",
    )
    describe.add_argument(
        "--source",
        type=_external_Path,
        help="Optional local L1 NetCDF file to inspect against this profile",
    )
    describe.add_argument("--json", action="store_true", help="Print machine-readable metadata")
    describe.set_defaults(
        func=_cmd_describe,
        timeout=30.0,
        retries=0,
        insecure=False,
        quiet=True,
    )

    resolve_ri = subparsers.add_parser(
        "resolve-ri",
        help="Resolve wrapper wavelengths to native mr/mi grid coordinates",
    )
    resolve_ri.add_argument(
        "particle_type",
        help="Black-carbon or generic super-spheroid particle type/alias",
    )
    resolve_ri.add_argument(
        "--wavelength",
        nargs="+",
        type=float,
        required=True,
        help="One or more wavelength/wavenumber values",
    )
    resolve_ri.add_argument(
        "--wavelength-unit",
        choices=("nm", "um", "cm-1"),
        default="um",
        help="Input unit; all values are normalized to um",
    )
    resolve_ri.add_argument(
        "--table",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help=(
            "External material table; use particle=PATH for super-spheroid, or "
            "black_carbon=PATH and hygroscopic=PATH for BC"
        ),
    )
    resolve_ri.add_argument("--mr", type=float, help="Advanced native real-index override")
    resolve_ri.add_argument("--mi", type=float, help="Advanced native imaginary-index override")
    resolve_ri.add_argument("--bc-mr", type=float, help="Advanced BC real-index override")
    resolve_ri.add_argument("--bc-mi", type=float, help="Advanced BC imaginary-index override")
    resolve_ri.add_argument(
        "--hygroscopic-mr",
        type=float,
        help="Advanced hygroscopic-material real-index override",
    )
    resolve_ri.add_argument(
        "--hygroscopic-mi",
        type=float,
        help="Advanced hygroscopic-material imaginary-index override",
    )
    resolve_ri.add_argument("--json", action="store_true", help="Print machine-readable output")
    resolve_ri.set_defaults(
        func=_cmd_resolve_ri,
        timeout=30.0,
        retries=0,
        insecure=False,
        quiet=True,
    )
    return parser


def builtin_command_names():
    parser = build_parser()
    return tuple(
        next(
            action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
        ).choices
    )
