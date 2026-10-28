"""Scheme validation/planning/building and bulk calculation commands."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from pathlib import Path
from typing import Mapping, Optional, Sequence

import zju_scatt_interface.access.client as _domain_access_client
from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.bulk.workflow import build_dataset
from zju_scatt_interface.config.reference import scheme_reference
from zju_scatt_interface.config.scheme import SCHEME_SCHEMA_VERSION, load_scheme
from zju_scatt_interface.io.canonical import OutputOptions, _write_dataset
from zju_scatt_interface.sources.planning import (
    WorkspaceLayout,
    build_dependency_queries,
    prepare_scheme_dependencies,
)


def cmd_compute_bulk(args: argparse.Namespace, _client: ApiClient) -> int:
    from zju_scatt_interface.access.reports import write_bulk_operation_log
    from zju_scatt_interface.bulk.lowlevel import _integrate_kernel
    from zju_scatt_interface.io.scalar_tables import (
        _normalize_table_column,
        load_bulk_optics_table,
    )
    from zju_scatt_interface.plotting.diagnostics import plot_optical_properties

    def step(message: str) -> None:
        if not args.quiet:
            print(message, file=sys.stderr)

    step("Step 1/3: Reading the size-distribution table.")
    table, columns = load_bulk_optics_table(
        args.input,
        size_column=args.size_column,
        number_column=args.number_column,
        extinction_column=args.extinction_column,
        scattering_column=args.scattering_column,
        absorption_column=args.absorption_column,
        extinction_efficiency_column=args.extinction_efficiency_column,
        scattering_efficiency_column=args.scattering_efficiency_column,
        absorption_efficiency_column=args.absorption_efficiency_column,
        asymmetry_column=args.asymmetry_column,
    )
    size_column = columns.get("size") or ""
    auto_diameter = _normalize_table_column(size_column) in {"diameter", "diam", "d"}
    size_is_radius = not args.size_is_diameter and not auto_diameter
    if args.size_is_radius:
        size_is_radius = True

    step("Step 2/3: Integrating single-particle properties over particle size.")
    result = _integrate_kernel(
        table["sizes"] or [],
        table["number_distribution"] or [],
        extinction_cross_section=table["extinction_cross_section"],
        scattering_cross_section=table["scattering_cross_section"],
        absorption_cross_section=table["absorption_cross_section"],
        extinction_efficiency=table["extinction_efficiency"],
        scattering_efficiency=table["scattering_efficiency"],
        absorption_efficiency=table["absorption_efficiency"],
        asymmetry_factor=table["asymmetry_factor"],
        size_is_radius=size_is_radius,
        distribution_mode=args.distribution_mode,
        metadata={
            "input_table": str(Path(args.input).expanduser().resolve()),
            "size_unit": args.size_unit,
            "number_unit": args.number_unit,
        },
    )

    step("Step 3/3: Writing the bulk optical result.")
    indent = None if args.compact else 2
    payload = json.dumps(result.to_dict(), indent=indent)
    if args.output:
        result.write_json(args.output, indent=indent)
        step(f"Result written to: {Path(args.output).expanduser().resolve()}")
    else:
        print(payload)

    if args.operation_log:
        write_bulk_operation_log(
            args.operation_log,
            result=result,
            input_path=args.input,
            columns=columns,
            output_path=args.output,
        )
        step(f"Operation log written to: {Path(args.operation_log).expanduser().resolve()}")

    if args.plot:
        plot_optical_properties(
            result,
            output=args.plot,
            title=args.plot_title or "ZJU-SCATT bulk optical properties",
            close=True,
        )
        step(f"Plot written to: {Path(args.plot).expanduser().resolve()}")

    step("BULK OPTICAL CALCULATION SUCCESSFUL")
    return 0


def _cmd_scheme(args: argparse.Namespace, _client: _domain_access_client.ApiClient) -> int:
    from zju_scatt_interface.config.scheme import load_scheme

    config = load_scheme(args.config)
    queries = build_dependency_queries(config)
    if args.json:
        print(
            json.dumps(
                {
                    "name": config.name,
                    "wavelength_count": len(config.wavelengths_um),
                    "wavelength_min_um": min(config.wavelengths_um),
                    "wavelength_max_um": max(config.wavelengths_um),
                    "particle_components": [item.name for item in config.particles],
                    "dependency_query_count": len(queries),
                    "output": config.output,
                    "valid": True,
                },
                indent=2,
            )
        )
    else:
        print(f"Valid scheme: {config.name}")
        print(f"Wavelengths: {len(config.wavelengths_um)}")
        print("Particle components: " + ", ".join(item.name for item in config.particles))
        print(f"Dependency queries: {len(queries)}")
        print(f"Output: {config.output}")
    return 0


def _atomic_json_report(path: Path, value: object) -> Path:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except BaseException:
        if temporary.is_file():
            temporary.unlink()
        raise
    return target


def _emit_bulk_opt_report(
    report: Mapping[str, object],
    *,
    json_output: bool,
    report_path: Optional[Path],
) -> None:
    if report_path is not None:
        _atomic_json_report(report_path, report)
    if json_output:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return
    print(f"Scheme: {report['scheme_name']}")
    print(f"Stage: {report['stage']}")
    print(f"Status: {report['status']}")
    if report.get("output"):
        print(f"Output: {report['output']}")
    if report_path is not None:
        print(f"Report: {report_path.expanduser().resolve()}")


def _validated_scheme(path: Path):
    from zju_scatt_interface.config.scheme import load_scheme

    config = load_scheme(path)
    try:
        queries = build_dependency_queries(config)
    except ValueError as exc:
        profiles = ", ".join(sorted({component.particle_type for component in config.particles}))
        raise ValueError(
            f"{exc} Inspect allowed parameters with "
            f"'zju-scatt describe PARTICLE_TYPE'. Scheme particle types: {profiles}."
        ) from exc
    return config, queries


def _parse_component_sources(
    values: Sequence[str],
    config: object,
) -> dict[str, Path]:
    result = {
        component.name: Path(component.source).expanduser().resolve()
        for component in config.particles
        if component.source is not None
    }
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name.strip() or not path.strip():
            raise ValueError("--source must use COMPONENT=PATH")
        result[name.strip()] = Path(path.strip()).expanduser().resolve()
    known = {component.name for component in config.particles}
    unknown = sorted(set(result) - known)
    if unknown:
        raise ValueError(
            "unknown --source component(s): "
            + ", ".join(unknown)
            + "; available: "
            + ", ".join(sorted(known))
        )
    if result and set(result) != known:
        missing = sorted(known - set(result))
        raise ValueError(
            "local source overrides must cover every component; missing: " + ", ".join(missing)
        )
    for name, path in result.items():
        if not path.exists():
            raise ValueError(f"local source for {name!r} does not exist: {path}")
    return result


def _cmd_bulk_opt_validate(
    args: argparse.Namespace,
    _client: _domain_access_client.ApiClient,
) -> int:
    config, queries = _validated_scheme(args.scheme)
    report = {
        "schema_version": SCHEME_SCHEMA_VERSION,
        "stage": "validate",
        "status": "valid",
        "scheme_name": config.name,
        "config_path": str(args.scheme.expanduser().resolve()),
        "component_names": [component.name for component in config.particles],
        "particle_types": [component.particle_type for component in config.particles],
        "wavelengths_um": list(config.wavelengths_um),
        "dependency_query_count": len(queries),
        "output": config.output_settings.to_dict(),
        "normalized_scheme": config.to_dict(),
    }
    _emit_bulk_opt_report(report, json_output=args.json, report_path=args.report)
    return 0


def _cmd_bulk_opt_schema(
    args: argparse.Namespace,
    _client: _domain_access_client.ApiClient,
) -> int:
    reference = scheme_reference(args.particle_type)
    if args.output is not None:
        _atomic_json_report(args.output, reference)
    if args.json:
        print(json.dumps(reference, indent=2, ensure_ascii=False))
    else:
        print("ZJU-SCATT scheme schema " + str(reference["schema_version"]))
        print("Particle profiles:")
        for profile in reference["particle_profiles"]:
            print(
                "  {} -> {}".format(
                    profile["particle_type"],
                    profile["typed_component"],
                )
            )
        print("Commands:")
        for name, command in reference["commands"].items():
            print(f"  {name}: {command}")
        if args.output is not None:
            print(f"Reference: {args.output.expanduser().resolve()}")
    return 0


def _cmd_bulk_opt_plan(
    args: argparse.Namespace,
    client: _domain_access_client.ApiClient,
) -> int:
    config, queries = _validated_scheme(args.scheme)
    sources = _parse_component_sources(args.source, config)
    if args.dry_run or sources:
        report = {
            "schema_version": SCHEME_SCHEMA_VERSION,
            "stage": "plan",
            "status": "ready" if sources else "dry_run",
            "scheme_name": config.name,
            "dry_run": bool(args.dry_run),
            "offline": bool(args.offline),
            "download_performed": False,
            "dependency_queries": [query.to_dict() for query in queries],
            "local_sources": {name: str(path) for name, path in sources.items()},
            "output": config.output_settings.to_dict(),
        }
        status = 0
    else:
        plan = prepare_scheme_dependencies(
            config,
            workspace=args.workspace,
            offline=args.offline,
            download=False,
            validate_schema=not args.no_schema_validation,
            client=client,
            session=args.session,
            no_track=args.no_track,
            resume=args.resume,
        )
        report = {
            "schema_version": SCHEME_SCHEMA_VERSION,
            "stage": "plan",
            "status": "ready" if plan.complete else "incomplete",
            "scheme_name": config.name,
            "dry_run": False,
            "offline": bool(args.offline),
            "download_performed": False,
            "plan": plan.to_dict(),
            "output": str(plan.workspace.output_file),
        }
        status = 0 if plan.complete else 2
    _emit_bulk_opt_report(report, json_output=args.json, report_path=args.report)
    return status


def _angle_grid(step: Optional[float]) -> Optional[list[float]]:
    if step is None:
        return None
    value = float(step)
    if not 0 < value <= 180:
        raise ValueError("--angle-step must be greater than 0 and at most 180")
    count = int(math.floor(180.0 / value))
    result = [index * value for index in range(count + 1)]
    if not math.isclose(result[-1], 180.0):
        result.append(180.0)
    return result


def _cmd_bulk_opt_build(
    args: argparse.Namespace,
    client: _domain_access_client.ApiClient,
) -> int:
    from zju_scatt_interface.config.scheme import SCHEME_SCHEMA_VERSION
    from zju_scatt_interface.sources.planning import prepare_scheme_dependencies

    config, queries = _validated_scheme(args.scheme)
    sources = _parse_component_sources(args.source, config)
    requested = (
        args.output.expanduser() if args.output is not None else Path(config.output).expanduser()
    )
    output = (
        requested.resolve()
        if requested.is_absolute() or args.output is not None
        else Path(args.workspace).expanduser().resolve() / requested
    )
    format_name = args.format or config.output_settings.format
    valid_suffixes = (
        {".nc", ".nc4", ".cdf"} if format_name == "netcdf4" else {".h5", ".hdf", ".hdf5"}
    )
    preferred_suffix = ".nc" if format_name == "netcdf4" else ".h5"
    if output.suffix.casefold() not in valid_suffixes:
        if args.output is not None:
            raise ValueError(
                f"output extension {output.suffix!r} does not match "
                f"--format {format_name}; use {preferred_suffix}"
            )
        output = output.with_suffix(preferred_suffix)
    if args.dry_run:
        report = {
            "schema_version": SCHEME_SCHEMA_VERSION,
            "stage": "build",
            "status": "dry_run",
            "scheme_name": config.name,
            "dry_run": True,
            "offline": bool(args.offline),
            "dependency_queries": [query.to_dict() for query in queries],
            "local_sources": {name: str(path) for name, path in sources.items()},
            "output": str(output),
            "format": format_name,
        }
        _emit_bulk_opt_report(report, json_output=args.json, report_path=args.report)
        return 0

    layout = WorkspaceLayout.create(args.workspace, config.output)
    if args.output is None:
        output = layout.output_file
    plan = None
    if not sources:
        plan = prepare_scheme_dependencies(
            config,
            workspace=args.workspace,
            offline=args.offline,
            download=True,
            validate_schema=not args.no_schema_validation,
            client=client,
            session=args.session,
            no_track=args.no_track,
            resume=args.resume,
        )
        if not plan.complete:
            report = {
                "schema_version": SCHEME_SCHEMA_VERSION,
                "stage": "build",
                "status": "incomplete_dependencies",
                "scheme_name": config.name,
                "plan": plan.to_dict(),
                "output": str(output),
            }
            _emit_bulk_opt_report(report, json_output=args.json, report_path=args.report)
            return 2
    result = build_dataset(
        config,
        source_paths=sources or None,
        dependency_plan=plan,
        workspace=args.workspace,
        offline=args.offline,
        include_phase_matrix=(True if args.phase_matrix else None),
        target_angles_degrees=_angle_grid(args.angle_step),
        truncation_policy=args.truncation_policy,
        check_convergence=args.check_convergence,
        convergence_tolerance=args.convergence_tolerance,
        strict_convergence=args.strict_convergence,
        strict_qa=args.strict_qa,
    )
    settings = config.output_settings
    options = OutputOptions(
        compression=settings.compression,
        compression_level=(
            args.compression_level
            if args.compression_level is not None
            else settings.compression_level
        ),
        shuffle=settings.shuffle,
        chunk_wavelength=settings.chunk_wavelength,
        atomic=settings.atomic,
    )
    _write_dataset(
        output,
        result,
        format=format_name,
        scheme=config,
        source_manifest=(
            plan.to_dict()
            if plan is not None
            else {"local_sources": {name: str(path) for name, path in sources.items()}}
        ),
        options=options,
    )
    report = {
        "schema_version": SCHEME_SCHEMA_VERSION,
        "stage": "build",
        "status": "complete",
        "scheme_name": config.name,
        "output": str(output),
        "format": format_name,
        "component_names": list(result.components),
        "wavelength_count": len(result.wavelengths_um),
        "components_stored_separately": True,
        "phase_matrix_included": any(
            calculation.bulk.phase_matrix is not None
            for calculations in result.components.values()
            for calculation in calculations
        ),
        "all_qa_passed": all(
            calculation.qa.passed
            for calculations in result.components.values()
            for calculation in calculations
        ),
        "dependency_plan": (plan.to_dict() if plan is not None else None),
    }
    _emit_bulk_opt_report(report, json_output=args.json, report_path=args.report)
    return 0


def _cmd_scheme_sources(
    args: argparse.Namespace,
    client: _domain_access_client.ApiClient,
) -> int:
    config = load_scheme(args.config)
    plan = prepare_scheme_dependencies(
        config,
        workspace=args.workspace,
        offline=args.offline,
        download=not args.no_download,
        validate_schema=not args.no_schema_validation,
        client=client,
        session=args.session,
        no_track=args.no_track,
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        print("Scheme source plan: {}".format(plan.scheme_name))
        print("Complete: {}".format("yes" if plan.complete else "no"))
        print(
            "Sources: {} ready / {} expected".format(
                sum(source.ready for source in plan.sources),
                len(plan.sources),
            )
        )
        print("Cache: {}".format(plan.workspace.cache_dir))
        print("Manifest: {}".format(plan.manifest_path))
        for issue in plan.issues:
            print(
                "  [{}] {}\n    Action: {}".format(
                    issue.component_name,
                    issue.reason,
                    issue.action,
                )
            )
    return 0 if plan.complete else 2


def _cmd_psd_check(
    args: argparse.Namespace,
    _client: _domain_access_client.ApiClient,
) -> int:
    config = load_scheme(args.config)
    selected = [
        component
        for component in config.particles
        if args.component is None or component.name == args.component
    ]
    if not selected:
        raise ValueError(
            "component {!r} does not exist; available: {}".format(
                args.component,
                ", ".join(component.name for component in config.particles),
            )
        )
    records = []
    for component in selected:
        distribution = component.size_distribution
        records.append(
            {
                "component": component.name,
                "particle_type": component.particle_type,
                "point_count": len(distribution.size_um),
                "size_min_um": distribution.size_um[0],
                "size_max_um": distribution.size_um[-1],
                "size_definition": distribution.size_definition,
                "integration_mode": distribution.integration_mode,
                "dndr_unit": "cm-3",
                "number_concentration_cm3": (distribution.number_concentration_cm3),
                "source": distribution.source,
                "validation_messages": list(distribution.validation_messages),
                "valid": True,
            }
        )
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        for record in records:
            print("{} ({})".format(record["component"], record["particle_type"]))
            print(
                "  {} points; {}..{} um; N={} cm-3".format(
                    record["point_count"],
                    record["size_min_um"],
                    record["size_max_um"],
                    record["number_concentration_cm3"],
                )
            )
            print(
                "  size_definition={}; integration_mode={}".format(
                    record["size_definition"],
                    record["integration_mode"],
                )
            )
            for message in record["validation_messages"]:
                print("  Warning: " + message)
    return 0
