"""Generate RTTOV 13/13.2 HDF5 tables from default particle populations.

Role:
    Production example

Inputs:
    17_rttov13_config.py: wavelength sequence, default PSDs and export settings.

Outputs:
    Aerosol/cloud HDF5 tables and channel metadata; ZJU names require reader adaptation.

Run:
    python 17_default_bulk_rttov13.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import argparse
from dataclasses import replace
from pathlib import Path
import runpy

from local_environment import verify_local_import

verify_local_import()

from zju_scatt_interface.bulk.tables import load_table_config
from zju_scatt_interface.bulk.tables import build_table
from zju_scatt_interface.io.applications.rttov.v13 import write_rttov13_bulk_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
        default=Path(__file__).with_name("17_rttov13_config.py"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    config = load_table_config(args.config)
    if args.offline:
        config = replace(config, offline=True)
    result = build_table(config)
    options = runpy.run_path(str(args.config)).get("rttov_output", {})
    exported = write_rttov13_bulk_tables(result, Path(config.output_dir)/"rttov13", **options)
    for path in exported["outputs"].values():
        print(f"RTTOV13: {path}")
    print("Use channel_wavelengths.csv to match the gas-coefficient channel ordering.")
    print("Use number concentrations for aerosols and g/m^3 for clouds (mmr_cldaer=False).")
    print("Cloud reader adaptation required: ICE_CLOUD_ZJU_SUPER_SPHEROID and WATER_CLOUD_ZJU_GAMMA.")
    print("Aerosol reader adaptation required: full lowercase names, without four-character truncation.")


if __name__ == "__main__":
    main()
