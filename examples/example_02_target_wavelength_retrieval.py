"""Select and download source files required for target wavelengths.

Role:
    Production example

Inputs:
    Ice wavelength targets, tolerance, cache directory and optional file limit.

Outputs:
    Downloaded ice sources and native-schema target products.

Run:
    From the package root: python examples/example_02_target_wavelength_retrieval.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Select and download source files required for target wavelengths.

    ``target_wavelength_mode="interp"`` selects bracketing database files when an
    exact wavelength is unavailable, then creates one local target-wavelength product
    for every original ice temperature/roundness/aspect-ratio series.
    Each product retains the complete native source NetCDF schema: dimensions,
    variables, phase-matrix elements, comments, descriptions, and attributes.
    User-created products keep the native filename convention with an
    ``interp_from`` processing marker, version and creation date.

    Install the NetCDF extra first: ``python -m pip install zju-scatt-interface[netcdf]``.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from zju_scatt_interface.access.cache import initialize_data_directory
from zju_scatt_interface.access.retrieval import retrieve_sources


def run_example(
    data_dir: Path,
    *,
    target_wavelengths_um: tuple[float, ...] = (0.67, 10.8, 12.0),
    target_tolerance_um: float = 1e-9,
    max_files: int | None = None,
):
    """Download the source files needed by the requested target wavelengths.

    The retrieval object contains both the selected catalog entries and the
    locally generated wavelength products, which makes it useful for follow-up
    processing in a notebook or another Python script.
    """

    # Initialize the cache before retrieval so repeated runs reuse files that
    # are already present instead of downloading the same source data again.
    initialize_data_directory(data_dir)
    # ``max_files`` is optional; a small limit can omit required interpolation
    # support, in which case the retrieval must fail rather than claim completion.
    result = retrieve_sources(
        particle_types="super_spheroid_ice",
        target_wavelengths=list(target_wavelengths_um),
        target_wavelength_mode="interp",
        target_tolerance_um=target_tolerance_um,
        max_files=max_files,
        download=True,
    )
    result.raise_for_status(download=True, require_matches=True, require_products=True)
    print(f"Selected {len(result.objects)} source files")
    processing = result.wavelength_processing
    print(f"Target wavelengths: {processing.target_wavelengths_um} um")
    print(f"Selected source wavelengths: {processing.selected_wavelengths_um} um")
    print(f"Exact-match tolerance: {target_tolerance_um:g} um")
    print(f"Interpolation required: {processing.interpolation_required}")
    print(f"Interpolation applied during retrieval: {processing.interpolation_applied}")
    print(f"Interpolated local products: {len(result.interpolated_products)}")
    for product in result.interpolated_products[:10]:
        print(f"  [{product.status}] {product.path}")
    print(processing.message)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Parse cache and tolerance options, then run the retrieval example."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-wavelengths-um",
        nargs="+",
        type=float,
        default=[0.67, 10.8, 12.0],
        help="one or more target wavelengths in um (default: %(default)s)",
    )
    parser.add_argument(
        "--target-tolerance-um",
        type=float,
        default=1e-9,
        help=(
            "maximum wavelength difference, in um, treated as an exact catalog "
            "match (default: %(default)g)"
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("zju_scatt_data"),
        help="download/cache directory (default: %(default)s)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="optional download limit for a small smoke test",
    )
    args = parser.parse_args(argv)
    result = run_example(
        args.data_dir,
        target_wavelengths_um=tuple(args.target_wavelengths_um),
        target_tolerance_um=args.target_tolerance_um,
        max_files=args.max_files,
    )
    return result.status_code


if __name__ == "__main__":
    raise SystemExit(main())
