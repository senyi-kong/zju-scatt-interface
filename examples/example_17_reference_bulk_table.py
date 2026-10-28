"""Run a bulk table from an editable input file.

Role:
    Production example

Inputs:
    Optional bulk-table Python/JSON input, or configs/bulk_table.example.py.

Outputs:
    Configured bulk NC/CSV products and source/assumption reports.

Run:
    From the package root: python examples/example_17_reference_bulk_table.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Run a bulk table from an editable input file.

    Usage: python examples/example_17_reference_bulk_table.py [input.py|input.json]
"""

import argparse
from pathlib import Path

from zju_scatt_interface.bulk.tables import build_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "configs" / "bulk_table.example.py",
    )
    args = parser.parse_args()
    result = build_table(args.config)
    print(f"Completed {len(result.rows)} rows")


if __name__ == "__main__":
    main()
