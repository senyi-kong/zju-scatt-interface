"""Export fixed-PSD infrared tables for the custom CRTM IR-only workflow.

Role:
    Production example

Inputs:
    19_crtm_ir_config.py; optional existing canonical bulk via --reuse-bulk.

Outputs:
    Custom IR-only tables, not a complete native microwave/size-grid CloudCoeff table.

Run:
    python 19_default_bulk_crtm_ir.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import runpy

from local_environment import verify_local_import
verify_local_import()
from zju_scatt_interface.bulk.tables import load_table_config
from zju_scatt_interface.bulk.tables import build_table
from zju_scatt_interface.io.applications.crtm.ir import write_crtm_ir_bulk_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
        default=Path(__file__).with_name("19_crtm_ir_config.py"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--reuse-bulk", type=Path,
        help="Export an existing canonical bulk NetCDF plus its sibling report.json, without recomputation")
    args = parser.parse_args()
    config = load_table_config(args.config)
    if args.offline:
        config = replace(config, offline=True)
    if args.reuse_bulk:
        # Explicit reuse exports the populations already in that file. Reject
        # conflicting settings rather than silently ignoring a changed config.
        report = json.loads(args.reuse_bulk.with_name("report.json").read_text(encoding="utf-8"))
        if (tuple(report["wavelengths_um"]) != config.wavelengths or
                set(report["species"]) != set(config.species) or config.overrides or
                report["preset"] != config.preset or any(
                    not entry["psd"]["metadata"].get("uses_preset_psd") or
                    abs(entry["psd"]["number_concentration_cm3"]-config.number_concentration_cm3) > 1e-10
                    for entry in report["species"].values())):
            raise ValueError("Reused bulk table does not match the configured default populations/wavelengths")
        data = args.reuse_bulk
    else:
        data = build_table(config)
    options = runpy.run_path(str(args.config))["crtm_output"]
    result = write_crtm_ir_bulk_tables(data, Path(config.output_dir)/"crtm_ir", **options)
    for path in result["outputs"].values():
        print(f"CRTM IR-only: {path}")
    print("Fixed PSDs; custom adapter required for CRTM. No microwave or size-grid blocks.")
    print("ke: m2/kg of dry constituent (BC core for black_carbon), or cloud water/ice.")


if __name__ == "__main__":
    main()
