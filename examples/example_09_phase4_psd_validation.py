"""Detailed Phase 4 validation with synthetic bulk optics and diagnostic graphics.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_09_phase4_psd_validation.py --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Detailed Phase 4 validation with synthetic bulk optics and diagnostic graphics.

    Run from the project root:

        python examples/example_09_phase4_psd_validation.py --output-dir phase4_validation_output

    The script creates an array-first PSD from a Python function, performs CSV
    round-tripping, conservative full-coverage and truncated remapping, a synthetic bulk
    optical integration, a JSON report, and a four-panel PNG diagnostic.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Sequence

from zju_scatt_interface.bulk.integration import integrate_arrays
from zju_scatt_interface.psd.models import SizeDistribution


def geometric_grid(minimum: float, maximum: float, count: int) -> list[float]:
    if minimum <= 0 or maximum <= minimum or count < 2:
        raise ValueError("invalid geometric grid")
    start = math.log(minimum)
    step = (math.log(maximum) - start) / (count - 1)
    return [math.exp(start + index * step) for index in range(count)]


def lognormal_shape(
    radius_um: float,
    median_radius_um: float = 0.5,
    geometric_stddev: float = 1.8,
) -> float:
    """Unnormalized lognormal shape sampled as discrete represented-bin weights."""

    sigma = math.log(geometric_stddev)
    exponent = -0.5 * (math.log(radius_um / median_radius_um) / sigma) ** 2
    return math.exp(exponent) / radius_um


def cumulative(values: Sequence[float]) -> list[float]:
    total = 0.0
    result = []
    for value in values:
        total += value
        result.append(total)
    return result


def positive_pairs(
    coordinates: Sequence[float],
    values: Sequence[float],
) -> tuple[list[float], list[float]]:
    pairs = [(coordinate, value) for coordinate, value in zip(coordinates, values) if value > 0]
    return [item[0] for item in pairs], [item[1] for item in pairs]


def write_csv(path: Path, distribution: SizeDistribution) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["radius_um", "dndr"])
        writer.writerows(zip(distribution.size_um, distribution.dndr_cm3))


def build_figure(
    path: Path,
    original: SizeDistribution,
    remapped: SizeDistribution,
    truncated: SizeDistribution,
    contributions_m1: Sequence[float],
    outside_fraction: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    axis = axes[0, 0]
    axis.loglog(
        original.size_um,
        original.dndr_cm3,
        "o-",
        label="Function-generated input",
    )
    remapped_positive_size, remapped_positive_dndr = positive_pairs(
        remapped.size_um,
        remapped.dndr_cm3,
    )
    axis.loglog(
        remapped_positive_size,
        remapped_positive_dndr,
        "s-",
        markersize=3,
        label="Conservative database-grid remap",
    )
    axis.set(xlabel="Radius (µm)", ylabel="Per-bin number concentration (cm⁻³)")
    axis.set_title("A  Array-first PSD and remapping", loc="left", fontweight="bold")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(frameon=False)

    axis = axes[0, 1]
    axis.semilogx(
        original.size_um,
        cumulative(original.dndr_cm3),
        "o-",
        label="Input cumulative N",
    )
    axis.semilogx(
        remapped.size_um,
        cumulative(remapped.dndr_cm3),
        "s-",
        markersize=3,
        label="Remapped cumulative N",
    )
    axis.axhline(
        original.number_concentration_cm3,
        color="black",
        linestyle=":",
        linewidth=1,
    )
    axis.set(xlabel="Radius (µm)", ylabel="Cumulative concentration (cm⁻³)")
    axis.set_title("B  Conservation check", loc="left", fontweight="bold")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(frameon=False)

    axis = axes[1, 0]
    axis.semilogx(
        remapped.size_um,
        remapped.dndr_cm3,
        "o-",
        label="Full database coverage",
    )
    axis.semilogx(
        truncated.size_um,
        truncated.dndr_cm3,
        "s-",
        label="Explicit truncation",
    )
    axis.text(
        0.03,
        0.95,
        "Outside fraction = {:.2%}".format(outside_fraction),
        transform=axis.transAxes,
        va="top",
    )
    axis.set(xlabel="Radius (µm)", ylabel="Per-bin concentration (cm⁻³)")
    axis.set_title("C  Coverage and truncation", loc="left", fontweight="bold")
    axis.grid(True, which="both", alpha=0.25)
    axis.legend(frameon=False)

    axis = axes[1, 1]
    contribution_size, positive_contributions = positive_pairs(
        remapped.size_um,
        contributions_m1,
    )
    axis.loglog(contribution_size, positive_contributions, "o-", color="#b33c2e")
    axis.set(xlabel="Radius (µm)", ylabel="Extinction contribution (m⁻¹ bin⁻¹)")
    axis.set_title("D  Synthetic bulk-extinction weights", loc="left", fontweight="bold")
    axis.grid(True, which="both", alpha=0.25)

    figure.suptitle(
        "ZJU-SCATT Interface — Phase 4 PSD validation",
        fontsize=14,
        fontweight="bold",
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_validation(output_dir: Path) -> dict[str, object]:
    """Run the PSD round-trip, remapping, integration, and plotting checks."""

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build a normalized, array-first PSD and prove that CSV serialization
    # preserves its total number concentration.
    input_grid = geometric_grid(0.05, 8.0, 25)
    original = SizeDistribution.from_callable(
        input_grid,
        lognormal_shape,
        size_definition="volume_equivalent_sphere_radius",
        source="phase4_lognormal_test_function",
    ).normalized(1000.0)

    csv_path = output_dir / "phase4_input_psd.csv"
    write_csv(csv_path, original)
    round_trip = SizeDistribution.from_delimited(
        csv_path,
        size_column="radius_um",
        dndr_column="dndr",
    )
    if not math.isclose(
        round_trip.number_concentration_cm3,
        original.number_concentration_cm3,
        rel_tol=1e-12,
    ):
        raise AssertionError("CSV round-trip changed total concentration")

    # 2. Remap once onto a fully covering database grid and once onto a
    # deliberately truncated grid.  The default policy must reject the latter
    # so a user cannot lose particles silently.
    database_grid = geometric_grid(0.035, 12.0, 41)
    remapped, full_report = round_trip.remap(database_grid)
    if full_report.outside_fraction > 1e-12:
        raise AssertionError("full-coverage remap unexpectedly truncated particles")
    if not math.isclose(
        remapped.number_concentration_cm3,
        original.number_concentration_cm3,
        rel_tol=1e-12,
    ):
        raise AssertionError("conservative remap did not preserve concentration")

    truncated_grid = geometric_grid(0.2, 3.0, 21)
    try:
        round_trip.remap(truncated_grid)
    except ValueError:
        silent_truncation_rejected = True
    else:
        silent_truncation_rejected = False
        raise AssertionError("default remap silently accepted incomplete coverage")
    truncated, truncation_report = round_trip.remap(
        truncated_grid,
        truncation_policy="truncate",
    )

    # 3. Integrate synthetic cross sections against the remapped PSD.  The
    # cross sections are analytic test values, not a substitute for L1 data.
    sizes_m = [radius * 1e-6 for radius in database_grid]
    extinction_cross_section_m2 = [2.0 * math.pi * radius**2 for radius in sizes_m]
    scattering_cross_section_m2 = [0.8 * value for value in extinction_cross_section_m2]
    asymmetry_factor = [
        0.55 + 0.3 * index / (len(database_grid) - 1) for index in range(len(database_grid))
    ]
    bulk, integration_report = integrate_arrays(
        round_trip,
        database_grid,
        extinction_cross_section_m2=extinction_cross_section_m2,
        scattering_cross_section_m2=scattering_cross_section_m2,
        asymmetry_factor=asymmetry_factor,
    )
    contributions = [
        cross_section * count * 1e6
        for cross_section, count in zip(
            extinction_cross_section_m2,
            remapped.dndr_cm3,
        )
    ]

    # 4. Save a visual diagnostic and a JSON report so the result is inspectable
    # both by a reader and by automated tests.
    figure_path = output_dir / "phase4_psd_validation.png"
    build_figure(
        figure_path,
        original,
        remapped,
        truncated,
        contributions,
        truncation_report.outside_fraction,
    )

    summary = {
        "phase": 4,
        "status": "pass",
        "input_points": len(original.size_um),
        "database_grid_points": len(database_grid),
        "number_concentration_cm3": original.number_concentration_cm3,
        "full_remap": full_report.to_dict(),
        "truncated_remap": truncation_report.to_dict(),
        "silent_truncation_rejected": silent_truncation_rejected,
        "bulk": bulk.to_dict(),
        "bulk_integration_remap": integration_report.to_dict(),
        "artifacts": {
            "input_csv": str(csv_path.resolve()),
            "figure": str(figure_path.resolve()),
        },
    }
    report_path = output_dir / "phase4_validation_report.json"
    report_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    summary["artifacts"]["report"] = str(report_path.resolve())
    return summary


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the PSD validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("phase4_validation_output"),
    )
    args = parser.parse_args(argv)
    summary = run_validation(args.output_dir.expanduser().resolve())
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
