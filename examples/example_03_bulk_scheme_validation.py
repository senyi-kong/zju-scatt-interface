"""Validate a Python-dictionary multi-particle bulk-optics scheme.

Role:
    Validation demonstration

Inputs:
    A trusted Python/JSON bulk scheme.

Outputs:
    Structural validation and dependency summary; no optical calculation.

Run:
    From the package root: python examples/example_03_bulk_scheme_validation.py --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Validate a Python-dictionary multi-particle bulk-optics scheme.

    This example loads the checked-in configuration without building optical
    products.  It is a quick way to confirm that particle definitions, wavelength
    coordinates, and dependency metadata are structurally valid.

    Run from the project root::

        python examples/example_03_bulk_scheme_validation.py
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from zju_scatt_interface.config.scheme import load_scheme


def run_example(config_path: Path) -> dict[str, object]:
    """Load, validate, and summarize one scheme configuration."""

    # ``load_scheme_config`` normalizes Python and JSON configurations to the
    # same typed object.  ``validate`` checks the scheme without downloading or
    # calculating any optical data.
    config = load_scheme(config_path)
    queries = config.validate()
    summary = {
        "name": config.name,
        "wavelength_count": len(config.wavelengths_um),
        "particle_names": [item.name for item in config.particles],
        "dependency_query_count": len(queries),
    }
    print(config.name)
    print(f"Wavelengths: {summary['wavelength_count']}")
    print("Particles:", ", ".join(summary["particle_names"]))
    print(f"Dependency queries: {summary['dependency_query_count']}")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """Parse a scheme path and print its validation summary."""

    default_config = Path(__file__).parents[1] / "configs" / "bulk_scheme.example.py"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=default_config,
        help="scheme configuration (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    run_example(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
