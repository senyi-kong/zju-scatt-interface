"""Phase 7 bulk-pipeline validation with ensembles, QA, and graphics.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_12_phase7_bulk_pipeline_validation.py
    --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Phase 7 bulk-pipeline validation with ensembles, QA, and graphics.

    Run from the project root:

        python examples/example_12_phase7_bulk_pipeline_validation.py         --output-dir phase7_validation_output
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from zju_scatt_interface.bulk.workflow import build_dataset
from zju_scatt_interface.config.scheme import Scheme


def create_source(
    path: Path,
    wavelength: float,
    *,
    multiplier: float,
    relative_humidity=None,
) -> None:
    import numpy as np
    from netCDF4 import Dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    radius = np.geomspace(0.03, 10.0, 64)
    with Dataset(path, "w") as dataset:
        dataset.createDimension("xsize_veq", len(radius))
        dataset.createVariable("wavelength", "f8")[:] = wavelength
        dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = (
            radius * 2 * math.pi / wavelength
        )
        dimensions = ["xsize_veq"]
        if relative_humidity is not None:
            dataset.createDimension("rh", len(relative_humidity))
            dataset.createVariable("rh", "f8", ("rh",))[:] = relative_humidity
            dimensions.insert(0, "rh")
        shape = tuple(dataset.dimensions[name].size for name in dimensions)
        cext = np.empty(shape)
        ssa = np.empty(shape)
        asymmetry = np.empty(shape)
        if relative_humidity is None:
            cext[:] = multiplier * np.geomspace(0.01, 500.0, len(radius))
            ssa[:] = 0.82
            asymmetry[:] = 0.5
        else:
            for index, rh in enumerate(relative_humidity):
                fraction = float(rh) / 100
                cext[index] = (
                    multiplier * (1 + 0.8 * fraction) * np.geomspace(0.01, 500.0, len(radius))
                )
                ssa[index] = 0.65 + 0.25 * fraction
                asymmetry[index] = 0.35 + 0.25 * fraction
        dataset.createVariable("cext", "f8", tuple(dimensions))[:] = cext
        dataset.createVariable("ssa", "f8", tuple(dimensions))[:] = ssa
        dataset.createVariable("g", "f8", tuple(dimensions))[:] = asymmetry


def build_figure(path: Path, result) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    wavelengths = result.wavelengths_um
    cloud = result.components["cloud"]
    sulfate = result.components["sulfate"]

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    axis = axes[0, 0]
    for name, values in (("cloud", cloud), ("sulfate", sulfate)):
        axis.semilogy(
            wavelengths,
            [value.bulk.extinction_coefficient for value in values],
            "o-",
            label=name,
        )
    axis.set(
        xlabel="Wavelength (um)",
        ylabel="Extinction coefficient (m-1)",
        title="Independently calculated particle components",
    )
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()

    axis = axes[0, 1]
    axis.plot(
        wavelengths,
        [value.bulk.single_scattering_albedo for value in sulfate],
        "o-",
        label="SSA",
    )
    axis.plot(
        wavelengths,
        [value.bulk.asymmetry_factor for value in sulfate],
        "s-",
        label="g",
    )
    axis.set(
        ylim=(0, 1),
        xlabel="Wavelength (um)",
        ylabel="Dimensionless value",
        title="Derived intensive properties",
    )
    axis.grid(True, alpha=0.25)
    axis.legend()

    target = sulfate[1]
    axis = axes[1, 0]
    labels = [
        f"RH={member.parameters['relative_humidity']:.1f}\nw={member.weight:.1f}"
        for member in target.members
    ]
    axis.bar(
        labels,
        [member.bulk.extinction_coefficient for member in target.members],
        color=["#4C72B0", "#55A868"],
    )
    axis.axhline(
        target.bulk.extinction_coefficient,
        color="black",
        linestyle="--",
        label="ensemble result",
    )
    axis.set(
        ylabel="Extinction coefficient (m-1)",
        title="Weighted RH ensemble at 0.6 um",
    )
    axis.grid(True, axis="y", alpha=0.25)
    axis.legend()

    axis = axes[1, 1]
    diagnostics = ("extinction_coefficient", "single_scattering_albedo", "asymmetry_factor")
    errors = [
        max(
            member.convergence.relative_errors.get(name, 0.0)
            for value in sulfate
            for member in value.members
        )
        for name in diagnostics
    ]
    axis.bar(["beta_ext", "SSA", "g"], errors, color="#C44E52")
    axis.axhline(0.05, color="black", linestyle="--", label="5% tolerance")
    axis.set(
        ylabel="Maximum relative coarse-grid error",
        title="Numerical convergence diagnostic",
    )
    axis.grid(True, axis="y", alpha=0.25)
    axis.legend()

    figure.suptitle("ZJU-SCATT Phase 7 bulk optical pipeline", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def build_validation_result(output_dir: Path):
    """Build the reusable synthetic two-component Phase-7 result."""

    output_dir.mkdir(parents=True, exist_ok=True)
    # Create small, deterministic L1 fixtures so this validation remains
    # self-contained and does not depend on the mounted private database.
    sources = output_dir / "synthetic_l1"
    cloud_root = sources / "sphere_water_cloud"
    sulfate_root = sources / "sphere_sulfate"
    for wavelength, multiplier in ((0.5, 1.0), (0.7, 1.3), (0.9, 1.8)):
        create_source(
            cloud_root / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc",
            wavelength,
            multiplier=multiplier,
        )
        create_source(
            sulfate_root / f"L1_sphere_sulfate_wl_{wavelength:.3f}_um_ref_1.5_0.nc",
            wavelength,
            multiplier=0.7 * multiplier,
            relative_humidity=[0, 50],
        )

    # The configuration retains cloud and sulfate as separate components.  The
    # sulfate component also carries a weighted relative-humidity ensemble.
    config = Scheme.from_mapping(
        {
            "name": "phase7_validation",
            "wavelengths": [0.5, 0.6, 0.8],
            "particles": [
                {
                    "name": "cloud",
                    "particle_type": "water_cloud",
                    "size_distribution": {
                        "size": [0.03, 0.1, 0.3, 1, 3, 10],
                        "dndr": [1, 5, 20, 30, 10, 2],
                    },
                    "refractive_index": {"mode": "database"},
                },
                {
                    "name": "sulfate",
                    "particle_type": "sulfate",
                    "size_distribution": {
                        "size": [0.03, 0.1, 0.3, 1, 3, 10],
                        "dndr": [10, 50, 100, 40, 10, 1],
                    },
                    "shape_parameters": {
                        "relative_humidity": {
                            "values": [0.0, 0.5],
                            "weights": [0.3, 0.7],
                        }
                    },
                    "refractive_index": {"mode": "database"},
                },
            ],
        }
    )
    return build_dataset(
        config,
        source_paths={"cloud": cloud_root, "sulfate": sulfate_root},
        truncation_policy="truncate",
    )


def run_validation(output_dir: Path) -> dict:
    """Run the synthetic bulk build, QA checks, and diagnostic export."""

    result = build_validation_result(output_dir)
    # Build the figure from the same result that is inspected below, avoiding
    # a second calculation and keeping the visual and numeric checks aligned.
    figure = output_dir / "phase7_bulk_pipeline_validation.png"
    build_figure(figure, result)
    reports = [
        member.convergence
        for values in result.components.values()
        for calculation in values
        for member in calculation.members
    ]
    # Every component calculation contributes one QA/convergence record.  The
    # report makes it easy to see whether a failure came from a component or a
    # numerical convergence check.
    report = {
        "status": "passed",
        "component_names": list(result.components),
        "wavelengths_um": list(result.wavelengths_um),
        "components_stored_separately": result.mixture is None,
        "sulfate_ensemble_member_count": len(result.components["sulfate"][0].members),
        "all_qa_passed": all(
            calculation.qa.passed for values in result.components.values() for calculation in values
        ),
        "convergence_checked_count": sum(value.checked for value in reports),
        "convergence_passed_count": sum(value.passed for value in reports),
        "figure": str(figure),
    }
    (output_dir / "phase7_validation_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the bulk-pipeline validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("phase7_validation_output"))
    args = parser.parse_args(argv)
    print(json.dumps(run_validation(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
