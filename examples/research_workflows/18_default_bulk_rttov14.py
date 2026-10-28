"""Generate RTTOV14 version-4 NetCDF tables from default fixed populations.

Role:
    Production example

Inputs:
    18_rttov14_config.py; --reuse-bulk optionally supplies an existing canonical file.

Outputs:
    RTTOV14 aerosol/cloud tables and validation/channel metadata.

Run:
    python 18_default_bulk_rttov14.py; append --help for options.

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
from zju_scatt_interface.io.applications.rttov.v14 import write_rttov14_bulk_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
        default=Path(__file__).with_name("18_rttov14_config.py"))
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
    options = runpy.run_path(str(args.config)).get("rttov_output", {})
    result = write_rttov14_bulk_tables(data, Path(config.output_dir)/"rttov14", **options)
    for path in result["outputs"].values():
        print(f"RTTOV14: {path}")
    print("Use full names in table order; match the gas-coefficient channel ordering.")
    print("Profiles: mmr_aer=False (cm^-3), mmr_hydro=False (g/m^3), nhydro=2.")


if __name__ == "__main__":
    main()
