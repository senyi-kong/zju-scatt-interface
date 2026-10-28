"""Configuration-driven retrieval commands and reusable example driver."""

from __future__ import annotations

import argparse
from pathlib import Path

from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.workflow import (
    RetrievalRunError,
    load_retrieval_config,
    retrieve,
)


def cmd_retrieve(args: argparse.Namespace, client: ApiClient) -> int:
    from zju_scatt_interface.access.catalog import objects_from_args
    from zju_scatt_interface.access.download import (
        download_selected_objects,
        limit_download_set,
    )
    from zju_scatt_interface.access.manifests import write_manifest
    from zju_scatt_interface.access.models import DownloadResult
    from zju_scatt_interface.access.progress import print_summary, print_table
    from zju_scatt_interface.access.reports import write_operation_log
    from zju_scatt_interface.access.requests import (
        build_retrieve_runtime_args,
        write_retrieve_config_template,
    )
    from zju_scatt_interface.access.retrieval import (
        apply_retrieval_processing,
        print_retrieve_step,
    )
    from zju_scatt_interface.optics.retrieval.workflow import (
        apply_downloaded_wavelength_interpolation,
    )

    if args.write_config_template:
        write_retrieve_config_template(
            args.write_config_template,
            overwrite=bool(getattr(args, "force", False)),
        )
        print(f"Example retrieval config written to: {args.write_config_template.resolve()}")
        return 0

    print("Step 1/5: Loading retrieval request.")
    runtime, _config = build_retrieve_runtime_args(args)
    config_path = getattr(args, "config", None)

    print_retrieve_step(runtime, "Step 2/5: Scanning the ZJU-SCATT database.")
    objects, stats = objects_from_args(runtime, client)

    print_retrieve_step(runtime, "Step 3/5: Applying wavelength processing rules.")
    objects, wavelength_processing, target_processings = apply_retrieval_processing(
        objects,
        runtime,
    )
    objects = limit_download_set(objects, runtime.max_files, runtime.max_bytes)
    stats.matched = len(objects)
    stats.bytes = sum(item.size for item in objects)

    print_retrieve_step(runtime, "Step 4/5: Writing retrieval manifest.")
    write_manifest(objects, runtime.manifest_output, runtime.format)
    print_summary(stats, label="Selected")
    print(f"Manifest written to: {runtime.manifest_output.expanduser().resolve()}")

    results: list[DownloadResult] = []
    status = 0
    if runtime.download and not runtime.dry_run:
        print_retrieve_step(runtime, "Step 5/5: Downloading selected data.")
        status, results = download_selected_objects(runtime, client, objects, stats)
        if status == 0:
            wavelength_processing, products = apply_downloaded_wavelength_interpolation(
                runtime, wavelength_processing, results
            )
            for product in products:
                print(f"[{product.status}] Derived product: {product.path}")
    else:
        print_retrieve_step(runtime, "Step 5/5: Reporting selected data without downloading.")
        print_table(objects, limit=runtime.display_limit, include_urls=runtime.urls)
        if runtime.dry_run:
            print("Dry run: no files were downloaded.")
        elif not runtime.download:
            print("Download disabled: manifest and operation log were produced.")

    write_operation_log(
        runtime.operation_log,
        args=runtime,
        config_path=config_path,
        stats=stats,
        objects=objects,
        manifest_path=runtime.manifest_output,
        wavelength_processing=wavelength_processing,
        target_processings=target_processings,
        download_enabled=runtime.download and not runtime.dry_run,
        results=results,
        exit_code=status,
    )
    print(f"Operation log written to: {runtime.operation_log.expanduser().resolve()}")
    if status == 0:
        print("DATA RETRIEVAL SUCCESSFUL")
    return status


def retrieve_from_config(default_config=None, argv=None):
    """Retrieve configured optical data, applying command-line options.

    Supply an input-file path and optionally an argument list. With argv=None,
    options come from the command line; use argv=[] to use only the input file.
    Returns zero on success or one when a retrieval batch fails. For direct
    Python access to the results, use run_retrieval instead.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=default_config, required=default_config is None
    )
    parser.add_argument(
        "--list-only", action="store_true", help="Select sources without downloading optical files"
    )
    parser.add_argument(
        "--manifest", type=Path, help="Use a saved catalog instead of scanning the database"
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true", default=None)
    parser.add_argument("--diagnostics", action="store_true", default=None)
    parser.add_argument("--dust-manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--bc-manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", action="store_true", help="Restrict dust/BC to one shape")
    parser.add_argument("--wavelength", type=float, help="Override the target wavelength (um)")
    parser.add_argument(
        "--ri-scheme", choices=("v1.2.1", "v1.2.2"), help="Override the BC default RI scheme"
    )
    args = parser.parse_args(argv)
    config = load_retrieval_config(args.config)
    if args.wavelength is not None:
        config["target_wavelengths"] = [args.wavelength]
    if args.ri_scheme is not None:
        config.setdefault("refractive_index_parameters", {}).setdefault("black_carbon", {}).update(
            database_type="wavelength", ri_scheme=args.ri_scheme
        )
    for name, manifest in (("dust", args.dust_manifest), ("black_carbon", args.bc_manifest)):
        if manifest is not None:
            config["requests"][name]["manifest"] = manifest.resolve()
    if args.smoke_test:
        for name, shape in (("dust", {"n": 2.0, "asp": 1.0}), ("black_carbon", {"df": 1.8})):
            config["requests"][name]["shapes"] = shape
        if args.output_dir is None:
            directory = Path(config["output_dir"])
            config["output_dir"] = directory.with_name(directory.name + "_smoke")
    try:
        retrieve(
            config,
            download=False if args.list_only else None,
            output_dir=args.output_dir,
            manifest=args.manifest,
            overwrite=args.overwrite,
            diagnostics=args.diagnostics,
        )
    except RetrievalRunError as exc:
        print(exc)
        return 1
    return 0
