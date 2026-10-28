"""Find matching database files without downloading them.

Role:
    Production example

Inputs:
    Particle/wavelength/extension catalog filters.

Outputs:
    Console metadata matches; no optical download.

Run:
    From the package root: python examples/example_01_catalog_search.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Find matching database files without downloading them.

    This is the smallest catalog example.  It only asks the ZJU-SCATT catalog for
    metadata, so it is useful for checking connectivity and search filters before a
    larger download is started.

    Run from the project root::

        python examples/example_01_catalog_search.py
        python examples/example_01_catalog_search.py --min-wavelength-um 10 --max-wavelength-um 13
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from zju_scatt_interface.access.retrieval import search_data


def run_example(
    *,
    particle_type: str = "super_spheroid_ice",
    min_wavelength_um: float = 10.0,
    max_wavelength_um: float = 13.0,
    extension: str = "nc",
    display_limit: int = 10,
) -> list[object]:
    """Search the catalog and print at most ``display_limit`` matching keys.

    The returned list is deliberately kept intact so that readers can reuse
    this function in a notebook instead of parsing the printed output.
    """

    if display_limit < 0:
        raise ValueError("display_limit must be non-negative")
    if max_wavelength_um < min_wavelength_um:
        raise ValueError("max_wavelength_um must be >= min_wavelength_um")

    # ``search_data`` performs a catalog query only; it does not fetch file
    # contents.  The wavelength bounds are inclusive search limits in um.
    matches = search_data(
        particle_types=particle_type,
        wavelength_range=(min_wavelength_um, max_wavelength_um),
        extension=extension,
    )
    for item in matches[:display_limit]:
        print(item.key)
    print(f"Matches: {len(matches)}")
    return matches


def main(argv: Sequence[str] | None = None) -> int:
    """Parse command-line filters and run the catalog search."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--particle-type",
        default="super_spheroid_ice",
        help="catalog particle type (default: %(default)s)",
    )
    parser.add_argument(
        "--min-wavelength-um",
        type=float,
        default=10.0,
        help="lower wavelength bound in um (default: %(default)s)",
    )
    parser.add_argument(
        "--max-wavelength-um",
        type=float,
        default=13.0,
        help="upper wavelength bound in um (default: %(default)s)",
    )
    parser.add_argument(
        "--extension",
        default="nc",
        help="file extension to search for (default: %(default)s)",
    )
    parser.add_argument(
        "--display-limit",
        type=int,
        default=10,
        help="maximum number of keys to print (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    run_example(
        particle_type=args.particle_type,
        min_wavelength_um=args.min_wavelength_um,
        max_wavelength_um=args.max_wavelength_um,
        extension=args.extension,
        display_limit=args.display_limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
