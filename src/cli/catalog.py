"""Catalog, registration/session and particle-description commands."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path as _external_Path
from pathlib import PurePosixPath
from typing import Sequence

import zju_scatt_interface.access.client as _domain_access_client
from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.endpoints import (
    DOWNLOAD_PAGE_URL,
    ROOT_PREFIX,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    list_particle_profiles,
)
from zju_scatt_interface.errors import ScattError
from zju_scatt_interface.optics.refractive_index import resolve_grid_refractive_indices
from zju_scatt_interface.sources.validation import inspect_source_file


def cmd_browse(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.catalog import (
        discover_source,
        download_page_url,
        relative_remote_key,
    )
    from zju_scatt_interface.access.filters import human_size
    from zju_scatt_interface.access.progress import print_table

    key, exact = discover_source(client, args.source)
    if exact:
        print_table([exact], limit=0, include_urls=args.urls)
        return 0
    directories, objects, pages = client.list_directory(key)
    print(f"Remote directory: {relative_remote_key(key) or '/'}")
    print(f"Web page: {download_page_url(key)}")
    print(f"Listing pages read: {pages}")
    if directories:
        print("\nDirectories:")
        for item in directories:
            print(f"  [DIR] {item.name}/")
    if objects:
        print("\nFiles:")
        print_table(objects, limit=args.display_limit, include_urls=args.urls)
        print(f"Directory files: {len(objects):,}, {human_size(sum(o.size for o in objects))}")
    if not directories and not objects:
        print("Directory is empty or does not exist.")
    return 0


def cmd_list_or_search(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.catalog import objects_from_args
    from zju_scatt_interface.access.manifests import write_manifest
    from zju_scatt_interface.access.progress import print_summary, print_table

    objects, stats = objects_from_args(args, client)
    print_table(objects, limit=args.display_limit, include_urls=args.urls)
    print_summary(stats)
    if args.output:
        write_manifest(objects, args.output, args.format)
        print(f"Complete manifest written to: {args.output.resolve()}")
    return 0


def cmd_estimate(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.catalog import objects_from_args
    from zju_scatt_interface.access.manifests import write_manifest
    from zju_scatt_interface.access.progress import print_summary

    objects, stats = objects_from_args(args, client)
    print_summary(stats)
    if args.output:
        write_manifest(objects, args.output, args.format)
        print(f"Manifest written to: {args.output.resolve()}")
    return 0


def cmd_download(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.catalog import objects_from_args
    from zju_scatt_interface.access.download import (
        download_selected_objects,
        limit_download_set,
    )

    objects, stats = objects_from_args(args, client)
    objects = limit_download_set(objects, args.max_files, args.max_bytes)
    stats.matched = len(objects)
    stats.bytes = sum(item.size for item in objects)
    status, _results = download_selected_objects(args, client, objects, stats)
    return status


def cmd_register(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.registration import (
        CONFIG_FILE,
        load_session_token,
        offer_registration_page,
        register_interactively,
        save_session_token,
    )

    existing = load_session_token()
    if isinstance(existing, str) and existing.strip():
        print("Already registered. The saved session will be reused automatically.")
        return 0
    method = getattr(args, "method", None)
    if method is None:
        method = "browser" if getattr(args, "browser_assisted", False) else "direct"
    if method == "browser":
        if not sys.stdin.isatty():
            raise ScattError("browser registration requires an interactive terminal")
        offer_registration_page(no_open=args.no_open)
        print(
            "\n1. Complete the Download Information form in the opened page.\n"
            "2. In that same tab, open Developer Tools > Console.\n"
            '3. Run: sessionStorage.getItem("scatt_download_session")\n'
            "4. Copy the returned token and paste it below.\n"
            "   (The token is hidden while you paste.)"
        )
        token = getpass.getpass("Browser session token: ").strip()
        if not token:
            raise ScattError("No browser session token was provided")
        if not client.validate_session(token):
            raise ScattError(
                "The browser token is invalid or expired. Keep the registered "
                "download tab open and copy the token again."
            )
        save_session_token(token, {"source": "browser-assisted"})
        print(f"Valid browser session saved to: {CONFIG_FILE}")
        return 0
    token = register_interactively(client, args)
    print(f"Registration complete. Session saved to: {CONFIG_FILE}")
    print(f"Session prefix: {token[:8]}...")
    return 0


def cmd_session(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.registration import (
        CONFIG_FILE,
        load_session_token,
        save_session_token,
    )

    if args.save:
        token = args.save.strip()
        if not token:
            raise ScattError("The session token cannot be empty")
        if not client.validate_session(token):
            raise ScattError(
                "The supplied session token is invalid or expired. If TLS "
                "validation of the website is the problem, retry once with --insecure."
            )
        save_session_token(token)
        print(f"Valid session saved to: {CONFIG_FILE}")
        return 0
    if args.clear:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
            print(f"Removed session file: {CONFIG_FILE}")
        else:
            print("No saved session file exists.")
        return 0
    token = load_session_token(args.session)
    if not token:
        print("No session is configured.")
        return 1
    valid = client.validate_session(token)
    print(f"Session prefix: {token[:8]}...")
    print(f"Valid: {'yes' if valid else 'no'}")
    print(
        f"Source: {'--session/environment' if args.session or os.environ.get('ZJU_SCATT_SESSION') else CONFIG_FILE}"
    )
    return 0 if valid else 1


def cmd_metadata(args: argparse.Namespace, _client: ApiClient) -> int:
    from zju_scatt_interface.access.metadata import extract_scatt_metadata

    for value in args.name:
        name = PurePosixPath(value).name
        metadata = extract_scatt_metadata(name)
        print(name)
        print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


def cmd_check(_args: argparse.Namespace, client: ApiClient) -> int:
    directories, objects, pages = client.list_directory(ROOT_PREFIX)
    print(f"Listing API: OK ({pages} page)")
    print(f"Root directories: {', '.join(item.name for item in directories) or '-'}")
    if objects:
        probe = client.stat_object(objects[0].key)
        print(f"OSS object access: {'OK' if probe else 'unavailable'}")
    else:
        print("OSS object access: not tested (no root-level file)")
    print(f"Website: {DOWNLOAD_PAGE_URL}")
    return 0


def _parse_named_paths(values: Sequence[str]) -> dict[str, _external_Path]:
    result = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name.strip() or not path.strip():
            raise ValueError("--table must use NAME=PATH")
        key = name.strip().lower()
        if key in result:
            raise ValueError("duplicate --table name: {}".format(key))
        result[key] = _external_Path(path.strip())
    return result


def _cmd_resolve_ri(args: argparse.Namespace, _client: _domain_access_client.ApiClient) -> int:
    parameters = {
        name: value
        for name, value in {
            "refractive_index_real": args.mr,
            "refractive_index_imaginary": args.mi,
            "black_carbon_refractive_index_real": args.bc_mr,
            "black_carbon_refractive_index_imaginary": args.bc_mi,
            "hygroscopic_refractive_index_real": args.hygroscopic_mr,
            "hygroscopic_refractive_index_imaginary": args.hygroscopic_mi,
        }.items()
        if value is not None
    }
    points = resolve_grid_refractive_indices(
        args.particle_type,
        args.wavelength,
        wavelength_unit=args.wavelength_unit,
        parameters=parameters,
        tables=_parse_named_paths(args.table),
    )
    records = [
        {
            "particle_type": point.particle_type,
            "wavelength_um": point.wavelength_um,
            "input_mode": point.input_mode,
            "native_refractive_index_coordinates": dict(point.values),
            "sources": dict(point.sources),
        }
        for point in points
    ]
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        for record in records:
            print(
                "{} um -> {}".format(
                    record["wavelength_um"],
                    ", ".join(
                        "{}={:g}".format(name, value)
                        for name, value in record["native_refractive_index_coordinates"].items()
                    ),
                )
            )
            print("  mode: {}".format(record["input_mode"]))
            print(
                "  sources: "
                + ", ".join(
                    "{}={}".format(name, source) for name, source in record["sources"].items()
                )
            )
    return 0


def _parameter_range(parameter: object) -> str:
    choices = getattr(parameter, "choices", ())
    if choices:
        return "choices: " + ", ".join(str(value) for value in choices)
    minimum = getattr(parameter, "minimum", None)
    maximum = getattr(parameter, "maximum", None)
    if minimum is not None and maximum is not None:
        result = "{}..{}".format(minimum, maximum)
        grid_values = getattr(parameter, "grid_values", ())
        if grid_values and len(grid_values) <= 12:
            result += "; source nodes: " + ", ".join(str(value) for value in grid_values)
        return result
    if minimum is not None:
        return ">={}".format(minimum)
    if maximum is not None:
        return "<={}".format(maximum)
    if (
        getattr(parameter, "name", None) == "wavelength"
        and getattr(parameter, "source_variable", None) is None
    ):
        return "finite positive; table/native coverage applies"
    return "database coverage"


def _cmd_describe(args: argparse.Namespace, _client: _domain_access_client.ApiClient) -> int:
    if args.particle_type is None:
        profiles = list_particle_profiles()
        if args.json:
            print(json.dumps([profile.to_dict() for profile in profiles], indent=2))
        else:
            print("Supported particle types:")
            for profile in profiles:
                print(
                    "  {:48} {:18} {}".format(
                        profile.particle_type,
                        profile.data_structure.value,
                        profile.display_name,
                    )
                )
            print("\nRun 'zju-scatt describe PARTICLE_TYPE' for its input contract.")
        return 0

    profile = get_particle_profile(args.particle_type)
    inspection = inspect_source_file(args.source, profile) if args.source else None
    if args.json:
        result = profile.to_dict()
        if inspection is not None:
            result["source_inspection"] = inspection.to_dict()
        print(json.dumps(result, indent=2))
        return 0 if inspection is None or inspection.valid else 2

    print("{} ({})".format(profile.display_name, profile.particle_type))
    print("Data structure: {}".format(profile.data_structure.value))
    print("Database directory: {}".format(profile.database_directory))
    print("Default wrapper input mode: {}".format(profile.default_wrapper_input_mode))
    for mode, contract in profile.to_dict().get("input_modes", {}).items():
        print("Input mode {}: {}".format(mode, ", ".join(contract["required_inputs"])))
        print("  " + contract["description"])
    if profile.native_lookup_coordinates:
        print("Native database coordinates: " + ", ".join(profile.native_lookup_coordinates))
    print("Default size definition: {}".format(profile.default_size_definition))
    print("Supported size definitions: {}".format(", ".join(profile.supported_size_definitions)))
    print("Native size variables: {}".format(", ".join(profile.native_size_variables)))
    if profile.forbidden_parameters:
        print("Forbidden user inputs: {}".format(", ".join(profile.forbidden_parameters)))
    print("\nParameters:")
    for parameter in profile.parameters:
        unit = "" if parameter.unit == "1" else " [{}]".format(parameter.unit)
        multiple = "; weighted multiple values supported" if parameter.multiple else ""
        print(
            "  {:42} {:9} {}{}{}".format(
                parameter.name,
                parameter.role.value,
                _parameter_range(parameter),
                unit,
                multiple,
            )
        )
        print("    " + parameter.description)
        if parameter.aliases:
            print("    aliases: " + ", ".join(parameter.aliases))
    if profile.notes:
        print("\nNotes:")
        for note in profile.notes:
            print("  - " + note)
    if inspection is not None:
        print("\nSource inspection: {}".format("PASS" if inspection.valid else "FAIL"))
        print("  File: {}".format(inspection.path))
        print("  dataset_name: {}".format(inspection.dataset_name))
        print("  data_version: {}".format(inspection.data_version))
        for error in inspection.errors:
            print("  Error: " + error)
    return 0 if inspection is None or inspection.valid else 2
