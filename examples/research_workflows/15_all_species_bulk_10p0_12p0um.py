"""Calculate separate default-PSD bulk optical tables for all species over 10-12 um.

Role:
    Production example

Inputs:
    15_bulk_table_10p0_12p0um_config.py; default wavelength step 0.1 um.

Outputs:
    Canonical NC/CSV tables and reports; species are independent populations.

Run:
    python 15_all_species_bulk_10p0_12p0um.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import argparse
from dataclasses import replace
from pathlib import Path

from local_environment import verify_local_import

verify_local_import()

from zju_scatt_interface.bulk.tables import load_table_config
from zju_scatt_interface.bulk.tables import build_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
        default=Path(__file__).with_name("15_bulk_table_10p0_12p0um_config.py"))
    parser.add_argument("--offline", action="store_true", help="Use saved verified source dependencies")
    parser.add_argument("--output-dir", type=Path, help="Override the configured output directory")
    args = parser.parse_args()
    config = load_table_config(args.config)
    if args.offline:
        config = replace(config, offline=True)
    if args.output_dir:
        config = replace(config, output_dir=args.output_dir)
    result = build_table(config)
    expected_rows = len(config.species) * len(config.wavelengths)
    if len(result.rows) != expected_rows:
        raise RuntimeError(f"Incomplete bulk table: expected {expected_rows} rows, got {len(result.rows)}")
    print(f"Completed: {len(config.species)} species, {len(config.wavelengths)} wavelengths, {len(result.rows)} rows")
    print(f"CSV: {Path(config.output_dir)/'bulk_optics_all_species.csv'}")
    print(f"NetCDF: {Path(config.output_dir)/'bulk_optics_all_species.nc'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
