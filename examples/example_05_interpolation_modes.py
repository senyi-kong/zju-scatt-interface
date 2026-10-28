"""Demonstrate exact, interpolation, nearest-source planning, and failure.

Role:
    Validation demonstration

Inputs:
    Synthetic nodes and exact/interpolation/nearest/out-of-range queries.

Outputs:
    Mode-selection reports and example artifacts.

Run:
    From the package root: python examples/example_05_interpolation_modes.py --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Demonstrate exact, interpolation, nearest-source planning, and failure.

    Run:

        python examples/example_05_interpolation_modes.py         --output-dir interpolation_modes_output
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from zju_scatt_interface.config.scheme import Scheme, WaterCloudComponent
from zju_scatt_interface.optics.interpolation import (
    InterpolationError,
    OpticalNode,
    interpolate_nodes,
)
from zju_scatt_interface.optics.models import SingleParticleOptics


def _node(wavelength: float, extinction: float) -> OpticalNode:
    """Create one small synthetic source node for the demonstration."""

    # Two nodes are enough to show exact retrieval and linear interpolation.
    # Keeping the arrays tiny makes the example fast while retaining the same
    # optics/provenance objects used by database-backed workflows.
    return OpticalNode(
        {"wavelength": wavelength},
        SingleParticleOptics(
            sizes=[0.1, 1.0],
            extinction_cross_section=[extinction, 10 * extinction],
            scattering_cross_section=[0.8 * extinction, 8 * extinction],
            absorption_cross_section=[0.2 * extinction, 2 * extinction],
            asymmetry_factor=[0.4, 0.6],
            size_unit="um",
            cross_section_unit="m2",
        ),
        source=f"synthetic_{wavelength:.1f}_um",
    )


def run_example(output_dir: Path) -> dict[str, object]:
    """Compare exact, interpolated, nearest, and rejected requests."""

    output_dir.mkdir(parents=True, exist_ok=True)
    nodes = [_node(0.4, 1.0), _node(0.8, 4.0)]

    # An exact request reuses a source node; an in-domain request blends the
    # two bracketing nodes.  The third request intentionally probes outside
    # the source domain and must raise instead of silently extrapolating.
    exact = interpolate_nodes("water_cloud", nodes, {"wavelength": 0.4})
    interpolated = interpolate_nodes("water_cloud", nodes, {"wavelength": 0.6})
    try:
        interpolate_nodes("water_cloud", nodes, {"wavelength": 1.0})
    except InterpolationError as exc:
        out_of_domain = str(exc)
    else:
        raise AssertionError("out-of-domain interpolation unexpectedly succeeded")

    component = WaterCloudComponent("cloud", size=[0.1, 1.0], dndr=[1.0, 1.0])

    # Scheme validation records how source data should be retrieved.  This is
    # separate from the direct interpolation above, so readers can see both
    # low-level optics interpolation and high-level planning modes.
    linear = Scheme("linear", (0.6,), (component,), interpolation="linear").validate()[0]
    nearest = Scheme("nearest", (0.6,), (component,), interpolation="nearest").validate()[0]

    # Plot the source nodes and the accepted/rejected target locations.  The
    # Agg backend keeps the example usable from a headless WSL shell.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(7.5, 5.0), constrained_layout=True)
    axis.plot(
        [0.4, 0.8],
        [1.0, 4.0],
        "o",
        markersize=9,
        label="source nodes",
    )
    axis.plot(
        [0.6],
        [interpolated.optics.extinction_cross_section[0]],
        "s",
        markersize=9,
        label="interpolated product",
    )
    axis.axvspan(0.4, 0.8, color="#55A868", alpha=0.12, label="valid domain")
    axis.axvline(1.0, color="#C44E52", linestyle="--", label="rejected target")
    axis.set(
        xlabel="Wavelength (um)",
        ylabel="First-size extinction cross section (arbitrary m2)",
        title="Interpolation is in-domain; extrapolation is rejected",
    )
    axis.grid(True, alpha=0.25)
    axis.legend()
    figure_path = output_dir / "interpolation_modes.png"
    figure.savefig(figure_path, dpi=180)
    plt.close(figure)
    report = {
        "status": "passed",
        "exact_method": exact.provenance.method,
        "interpolated_method": interpolated.provenance.method,
        "interpolated_neighbors": [
            neighbor.source for neighbor in interpolated.provenance.neighbors
        ],
        "linear_retrieval_mode": linear.retrieval_parameters["target_wavelength_mode"],
        "nearest_retrieval_mode": nearest.retrieval_parameters["target_wavelength_mode"],
        "out_of_domain_error": out_of_domain,
        "figure": str(figure_path),
    }
    (output_dir / "interpolation_modes_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the output directory and run the interpolation demonstration."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("interpolation_modes_output"),
    )
    args = parser.parse_args(argv)
    print(json.dumps(run_example(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
