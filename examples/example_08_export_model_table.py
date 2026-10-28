"""Render a canonical bulk-optics product using a custom table specification.

Role:
    Production example

Inputs:
    Canonical bulk file and trusted Python/JSON table-format specification.

Outputs:
    Formatted optical table; no new optical calculation.

Run:
    From the package root: python examples/example_08_export_model_table.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Render a canonical bulk-optics product using a custom table specification.

    The input is normally produced by one of the bulk calculation examples.  The
    format specification controls the model-table columns and can be written in
    trusted Python or JSON form.

    Run from the project root::

        python examples/example_08_export_model_table.py canonical.nc         --output radiative_transfer_optics.dat
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from zju_scatt_interface.io.tables import load_optical_table_format, write_formatted_optical_output


def run_example(
    input_path: Path,
    format_spec_path: Path,
    output_path: Path,
) -> tuple[Path, ...]:
    """Load a table specification and write its formatted output file(s)."""

    # The canonical NetCDF/HDF5 product remains the source of scientific data;
    # this example only changes its presentation for a downstream model.
    format_spec = load_optical_table_format(format_spec_path)
    outputs = write_formatted_optical_output(
        output_path,
        input_path,
        format_spec,
    )
    paths = outputs if isinstance(outputs, tuple) else (outputs,)
    for path in paths:
        print(path)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the input product, table specification, and output path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Canonical bulk NC or HDF5 product")
    parser.add_argument(
        "--format-spec",
        type=Path,
        default=Path(__file__).parents[1] / "configs" / "optical_table_format.example.py",
        help="Trusted Python or JSON table specification",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("radiative_transfer_optics.dat"),
    )
    args = parser.parse_args(argv)
    run_example(args.input, args.format_spec, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
