"""Build multiple retained particle-specific bulk-optics grids at once.

Role:
    Production example

Inputs:
    Multidimensional scheme and compatible ice/sulfate sources.

Outputs:
    NC retaining separate particle-specific output grids.

Run:
    From the package root: python examples/example_07_multidimensional_bulk_scheme.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Build multiple retained particle-specific bulk-optics grids at once.

    The scheme keeps independent particle populations in separate dimensions.  It
    therefore requires compatible ice and sulfate L1 sources and is a useful
    example when a model needs to preserve component-specific lookup tables.

    Run from the project root::

        python examples/example_07_multidimensional_bulk_scheme.py         --ice-source /path/to/ice.nc         --sulfate-source /path/to/sulfate.nc         --output multidimensional_bulk_optics.nc
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from zju_scatt_interface.bulk.grid import build_grids, load_grid_scheme
from zju_scatt_interface.io import write


def run_example(
    scheme_path: Path,
    ice_source: Path | list[Path],
    sulfate_source: Path | list[Path],
    output_path: Path,
) -> Path:
    """Build, write, and summarize the multidimensional product."""

    # The Python scheme defines the retained coordinates and the component
    # names.  The source mapping below connects each component to its L1 file.
    scheme = load_grid_scheme(scheme_path)
    result = build_grids(
        scheme,
        source_paths={"ice": ice_source, "sulfate": sulfate_source},
        truncation_policy="truncate",
        strict_convergence=False,
    )

    # This writer preserves each component's grid instead of collapsing the
    # result into one mixed population.
    output = write(result, output_path, scheme=scheme)
    for name, component in result.components.items():
        print(f"{name}: shape={component.shape}, points={len(component.calculations)}")
    print(output)
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """Parse source/output paths and run the multidimensional workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scheme",
        type=Path,
        default=(Path(__file__).parents[1] / "configs" / "multidimensional_bulk_scheme.example.py"),
    )
    parser.add_argument(
        "--ice-source",
        type=Path,
        nargs="+",
        required=True,
        help="Files/directories spanning the declared ice grid",
    )
    parser.add_argument(
        "--sulfate-source",
        type=Path,
        nargs="+",
        required=True,
        help="Files/directories spanning the declared sulfate grid",
    )
    parser.add_argument("--output", type=Path, default=Path("multidimensional_bulk_optics.nc"))
    args = parser.parse_args(argv)
    run_example(
        args.scheme,
        args.ice_source,
        args.sulfate_source,
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
