"""Calculate bulk optics from separate user-supplied, unnormalized PSD tables.

Role:
    Production example

Inputs:
    16_measured_psd_config.py and per-species CSVs; counts are cm^-3 per bin.

Outputs:
    Bulk NC/CSV products preserving supplied counts under the selected coverage policy.

Run:
    python 16_all_species_measured_psd_bulk.py; append --help for options.

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
        default=Path(__file__).with_name("16_measured_psd_config.py"))
    parser.add_argument("--offline", action="store_true", help="Use verified cached sources")
    args = parser.parse_args()
    config = load_table_config(args.config)
    if args.offline:
        config = replace(config, offline=True)

    # The interface reads the PSD files, checks coverage and preserves counts.
    result = build_table(config)
    for name, entry in result.report["species"].items():
        check = entry["psd_handling"]
        print(f"[PASS] {name}: N={check['used_number_concentration_cm3']:g} cm^-3; "
              f"input bins preserved={check['input_bins_preserved']}")
    output = Path(config.output_dir)
    print(f"Saved {len(result.rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
