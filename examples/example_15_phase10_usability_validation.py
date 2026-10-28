"""Validate Phase 10 recipes, reference metadata, units, and graphics.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_15_phase10_usability_validation.py --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Validate Phase 10 recipes, reference metadata, units, and graphics.

    Run from the project root:

        python examples/example_15_phase10_usability_validation.py         --output-dir phase10_validation_output
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from zju_scatt_interface.config.reference import scheme_reference
from zju_scatt_interface.config.scheme import load_scheme
from zju_scatt_interface.psd.models import SizeDistribution

RECIPE_NAMES = (
    "black_carbon_bulk.json",
    "dust_bulk.json",
    "sea_salt_bulk.json",
    "ice_multi_temperature_bulk.json",
)


def _build_figure(
    path: Path,
    distribution: SizeDistribution,
    schemes: list,
    reference: dict[str, object],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    axes[0, 0].loglog(
        distribution.size_um,
        distribution.dndr_cm3,
        "o-",
        color="#4C72B0",
    )
    axes[0, 0].set(
        xlabel="Volume-equivalent sphere radius (um)",
        ylabel="Concentration per represented bin (cm-3)",
        title="Observed PSD input",
    )
    axes[0, 0].grid(True, which="both", alpha=0.25)

    for scheme in schemes:
        axes[0, 1].scatter(
            scheme.wavelengths_um,
            [scheme.name] * len(scheme.wavelengths_um),
            s=45,
            label=scheme.name,
        )
    axes[0, 1].set_xscale("log")
    axes[0, 1].set(
        xlabel="Normalized wavelength (um)",
        title="Recipe spectral coordinates",
    )
    axes[0, 1].grid(True, which="both", axis="x", alpha=0.25)

    labels = [scheme.name for scheme in schemes]
    counts = [len(scheme.particles) for scheme in schemes]
    axes[1, 0].barh(labels, counts, color="#55A868")
    axes[1, 0].set(
        xlabel="Distinct output components",
        title="Multi-temperature ice remains separate",
        xlim=(0, max(counts) + 0.5),
    )

    profiles = reference["particle_profiles"]
    structures = [item["data_structure"] for item in profiles]
    grid_count = structures.count("grid_based")
    wavelength_count = structures.count("wavelength_based")
    axes[1, 1].bar(
        ["RI-grid native", "Wavelength native"],
        [grid_count, wavelength_count],
        color=["#C44E52", "#8172B2"],
    )
    axes[1, 1].set(
        ylabel="Registered particle profiles",
        title="Native database organization",
        ylim=(0, wavelength_count + 1),
    )
    figure.suptitle("ZJU-SCATT Phase 10 usability validation", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_validation(output_dir: Path) -> dict[str, object]:
    """Validate the bundled recipes and the machine-readable reference."""

    output_dir.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).parents[1]
    recipes = project / "configs" / "recipes"

    # Load every documented recipe through the public configuration loader.
    # Calling ``validate`` here checks that each recipe produces dependency
    # queries without requiring the private L1 database.
    schemes = [load_scheme(recipes / name) for name in RECIPE_NAMES]
    query_counts = [len(scheme.validate()) for scheme in schemes]

    # Reuse the reader-facing PSD example so the usability check covers both
    # recipe metadata and a realistic observed-input convention.
    distribution = SizeDistribution.from_delimited(
        project / "examples" / "data" / "observed_psd_example.csv",
        size_column="radius_um",
        dndr_column="dndr_cm3",
        size_unit="um",
        size_definition="volume_equivalent_sphere_radius",
    )
    # ``scheme_reference`` is the canonical source for supported particle
    # profiles, units, size definitions, and data-structure descriptions.
    reference = scheme_reference()
    reference_path = output_dir / "zju_scatt_scheme_reference.json"
    reference_path.write_text(
        json.dumps(reference, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    figure = output_dir / "phase10_usability_validation.png"
    _build_figure(figure, distribution, schemes, reference)

    report = {
        "status": "passed",
        "schema_version": reference["schema_version"],
        "recipe_names": list(RECIPE_NAMES),
        "recipe_component_counts": [len(scheme.particles) for scheme in schemes],
        "dependency_query_counts": query_counts,
        "normalized_wavelengths_um": [list(scheme.wavelengths_um) for scheme in schemes],
        "observed_psd_points": len(distribution.size_um),
        "observed_number_concentration_cm3": (distribution.number_concentration_cm3),
        "registered_profile_count": len(reference["particle_profiles"]),
        "machine_reference": str(reference_path),
        "figure": str(figure),
    }
    (output_dir / "phase10_validation_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the usability validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("phase10_validation_output"),
    )
    args = parser.parse_args(argv)
    report = run_validation(args.output_dir)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
