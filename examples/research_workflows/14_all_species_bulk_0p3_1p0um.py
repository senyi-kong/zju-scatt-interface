"""Calculate separate default-PSD bulk optical tables for all species over 0.3-1.0 um.

Role:
    Production example

Inputs:
    14_bulk_table_config.py; optional species/wavelength/destination overrides.

Outputs:
    Canonical NC/CSV tables, source/coverage reports and documented assumptions.

Run:
    python 14_all_species_bulk_0p3_1p0um.py; append --help for options.

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
                        default=Path(__file__).with_name("14_bulk_table_config.py"))
    parser.add_argument("--species", nargs="+", help="Override selected species")
    parser.add_argument("--wavelengths", nargs="+", type=float, help="Override wavelengths in um")
    parser.add_argument("--offline", action="store_true", help="Use verified saved source dependencies")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = load_table_config(args.config)
    changes = {}
    if args.species:
        changes["species"] = args.species
    if args.wavelengths:
        changes["wavelengths"] = args.wavelengths
    if args.offline:
        changes["offline"] = True
    if args.output_dir:
        changes["output_dir"] = args.output_dir
    result = build_table(replace(config, **changes))
    print(f"Completed: {len(result.rows)} rows; output: {changes.get('output_dir', config.output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
