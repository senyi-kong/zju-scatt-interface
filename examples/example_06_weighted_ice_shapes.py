"""Explicitly average independently calculated ice-shape bulk properties.

Role:
    Production example

Inputs:
    Compatible local ice sources covering three shapes, wavelength and temperature.

Outputs:
    Weighted ice NC after per-shape integration with explicit common-range truncation.

Run:
    From the package root: python examples/example_06_weighted_ice_shapes.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Explicitly average independently calculated ice-shape bulk properties.

    This workflow is intentionally data-dependent: pass one or more compatible
    ZJU-SCATT L1 files with ``--source`` before running it.  The script calculates
    each shape separately and combines the resulting bulk properties only after
    those calculations finish.

    Run from the project root::

        python examples/example_06_weighted_ice_shapes.py         --source /path/to/ice_source.nc --output weighted_ice.nc
"""

from __future__ import annotations

import argparse
from pathlib import Path

from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble
from zju_scatt_interface.bulk.models import PopulationResult
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.io import write
from zju_scatt_interface.psd.models import SizeDistribution

# These are shape-ensemble weights chosen by the user. They are not mixing
# fractions between different particle types.
bulk_scheme_entries = [
    {"roundness": 2.0, "aspect_ratio": 1.0, "weight": 0.25},
    {"roundness": 2.5, "aspect_ratio": 1.0, "weight": 0.50},
    {"roundness": 3.0, "aspect_ratio": 1.0, "weight": 0.25},
]


def calculate_weighted_ice(
    source: Path | list[Path],
    wavelength_um: float,
    temperature_k: float,
) -> PopulationResult:
    """Calculate and weight the three independent ice-shape members."""

    # Sizes are volume-equivalent radii in um. Values are represented-bin
    # concentrations, kept constant to isolate shape-ensemble weighting.
    ice_psd = SizeDistribution(
        [5.0, 10.0, 20.0, 40.0, 80.0],
        [50.0, 200.0, 400.0, 250.0, 100.0],
        size_unit="um",
        size_definition="volume_equivalent_sphere_radius",
    )
    # The interface finds a common physical size range, integrates each shape,
    # and combines extensive coefficients before deriving SSA/g/phase.
    return compute_population(
        "super_spheroid_ice",
        source,
        ice_psd,
        wavelength=wavelength_um,
        parameters={"temperature": temperature_k},
        shape_ensemble=WeightedShapeEnsemble(bulk_scheme_entries),
        truncation_policy="truncate",
        strict_convergence=False,
    )


def run_example(
    source: Path | list[Path],
    wavelength_um: float,
    temperature_k: float,
    output_path: Path,
) -> Path:
    """Calculate the weighted ensemble and write one canonical product."""

    calculation = calculate_weighted_ice(source, wavelength_um, temperature_k)
    return write(calculation, output_path, component_name="weighted_ice_shapes", format="netcdf4")


def main(argv: list[str] | None = None) -> int:
    """Parse the L1 source and output path, then write the weighted product."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        nargs="+",
        required=True,
        help="Files/directories spanning all requested ice shapes and temperatures",
    )
    parser.add_argument("--wavelength-um", type=float, default=0.67)
    parser.add_argument("--temperature-k", type=float, default=220.0)
    parser.add_argument("--output", type=Path, default=Path("weighted_ice.nc"))
    args = parser.parse_args(argv)

    # The public output writer creates parent directories and stores the result
    # as a canonical one-wavelength bulk-optics product.
    path = run_example(
        args.source,
        args.wavelength_um,
        args.temperature_k,
        args.output,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
