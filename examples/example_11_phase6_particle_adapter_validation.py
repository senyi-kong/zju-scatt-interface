"""Phase 6 particle-adapter validation with diagnostic graphics.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_11_phase6_particle_adapter_validation.py
    --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Phase 6 particle-adapter validation with diagnostic graphics.

    Run from the project root:

        python examples/example_11_phase6_particle_adapter_validation.py         --output-dir phase6_validation_output
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from zju_scatt_interface.sources.adapters.registry import (
    interpolate_particle,
    resolve_particle_sources,
)


def create_l1(path: Path, wavelength: float, *, rh=None, multiplier: float = 1.0) -> None:
    import numpy as np
    from netCDF4 import Dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(path, "w") as dataset:
        dataset.createDimension("xsize_veq", 36)
        radii = np.geomspace(0.1, 10.0, 36)
        dataset.createVariable("wavelength", "f8")[:] = wavelength
        dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = (
            radii * 2 * math.pi / wavelength
        )
        dimensions = ["xsize_veq"]
        rh_values = None
        if rh is not None:
            rh_values = np.asarray(rh, dtype=float)
            dataset.createDimension("rh", len(rh_values))
            dataset.createVariable("rh", "f8", ("rh",))[:] = rh_values
            dimensions.insert(0, "rh")
        shape = tuple(dataset.dimensions[name].size for name in dimensions)
        cext = np.empty(shape)
        if rh_values is None:
            cext[:] = multiplier * np.geomspace(0.1, 1000.0, 36)
        else:
            for index, stored_rh in enumerate(rh_values):
                cext[index] = (
                    multiplier * (1.0 + abs(stored_rh) / 100.0) * np.geomspace(0.1, 1000.0, 36)
                )
        dataset.createVariable("cext", "f8", tuple(dimensions))[:] = cext
        dataset.createVariable("ssa", "f8", tuple(dimensions))[:] = 0.75
        dataset.createVariable("g", "f8", tuple(dimensions))[:] = 0.4


def build_figure(path: Path, water_sources, water, sulfate, sea) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    axis = axes[0, 0]
    for source in water_sources:
        axis.loglog(
            source.optics.sizes,
            source.optics.extinction_cross_section,
            alpha=0.6,
            label=f"source {source.coordinates['wavelength']:.2f} um",
        )
    axis.loglog(
        water.optics.sizes,
        water.optics.extinction_cross_section,
        "k--",
        linewidth=2.5,
        label="adapter target 0.60 um",
    )
    axis.set(
        xlabel="Volume-equivalent sphere radius (um)",
        ylabel="Cext (m2)",
        title="Water-cloud wavelength adapter",
    )
    axis.grid(True, which="both", alpha=0.25)
    axis.legend()

    axis = axes[0, 1]
    labels = [
        f"{neighbor.coordinates['wavelength']:.1f} um\n"
        f"RH={neighbor.coordinates['relative_humidity']:.2f}"
        for neighbor in sulfate.provenance.neighbors
    ]
    axis.bar(labels, [neighbor.weight for neighbor in sulfate.provenance.neighbors])
    axis.set(
        ylim=(0, 1),
        ylabel="Interpolation weight",
        title="Sulfate wavelength-RH source resolution",
    )
    axis.grid(True, axis="y", alpha=0.25)

    axis = axes[1, 0]
    stored = [-75, -50, 50, 80]
    colors = ["#C44E52" if value < 0 else "#4C72B0" for value in stored]
    axis.scatter(stored, [abs(value) / 100 for value in stored], c=colors, s=90)
    axis.axvline(0, color="0.4", linewidth=1)
    axis.set(
        xlabel="Stored RH coordinate",
        ylabel="Public relative_humidity (1)",
        title="Sea-salt branch conversion",
    )
    axis.text(-72, 0.42, "crystallization", color="#C44E52")
    axis.text(20, 0.42, "deliquescence", color="#4C72B0")
    axis.grid(True, alpha=0.25)

    axis = axes[1, 1]
    names = ["water cloud", "sulfate", "sea salt"]
    counts = [
        water.provenance.adapter["selected_node_count"],
        sulfate.provenance.adapter["selected_node_count"],
        sea.provenance.adapter["selected_node_count"],
    ]
    axis.bar(names, counts, color=["#55A868", "#4C72B0", "#C44E52"])
    axis.set(
        ylabel="Minimally loaded L1 nodes",
        title="Profile-specific source selection",
    )
    axis.grid(True, axis="y", alpha=0.25)

    figure.suptitle("ZJU-SCATT Phase 6 particle-adapter validation", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_validation(output_dir: Path) -> dict:
    """Create synthetic L1 files and exercise three particle adapters."""

    output_dir.mkdir(parents=True, exist_ok=True)
    sources = output_dir / "synthetic_l1"

    # Water-cloud sources vary only by wavelength.  The adapter must select
    # both bracketing files before interpolating the requested 600 nm node.
    water_root = sources / "sphere_water_cloud"
    for wavelength, multiplier in ((0.5, 1.0), (0.7, 2.0)):
        create_l1(
            water_root / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_1e-8.nc",
            wavelength,
            multiplier=multiplier,
        )
    water_resolution = resolve_particle_sources(
        "water_cloud", water_root, wavelength=600, wavelength_unit="nm"
    )
    water_nodes = []
    from zju_scatt_interface.optics.interpolation import OpticalNode
    from zju_scatt_interface.optics.loading import load_single

    for source in water_resolution.sources:
        water_nodes.append(
            OpticalNode(
                source.coordinates,
                load_single(source.path),
                str(source.path),
            )
        )
    water = water_resolution.interpolate()

    # Sulfate adds relative humidity as a second interpolation coordinate and
    # therefore checks a small 2-D source grid.
    sulfate_root = sources / "sphere_sulfate"
    for wavelength in (0.5, 0.7):
        create_l1(
            sulfate_root / f"L1_sphere_sulfate_wl_{wavelength:.3f}_um_ref_1.5_1e-8.nc",
            wavelength,
            rh=[0, 50],
            multiplier=1.0 + wavelength,
        )
    sulfate = interpolate_particle(
        "sulfate",
        sulfate_root,
        wavelength=0.6,
        parameters={"relative_humidity": 0.25},
    )

    # Sea-salt filenames encode a humidity branch.  Passing the branch
    # explicitly verifies that the adapter retains this semantic coordinate.
    sea_root = sources / "coated_super_spheroid_seasalt"
    create_l1(
        sea_root / "L1_coated_super_spheroid_seasalt_multiparas_wl_00.700_um_ref_1.49_2e-7.nc",
        0.7,
        rh=[-75, -50, 50, 80],
    )
    sea = interpolate_particle(
        "sea_salt",
        sea_root,
        wavelength=0.7,
        parameters={"relative_humidity": 0.5, "humidity_branch": "crystallization"},
    )

    # The figure and JSON report expose both the selected nodes and the
    # resulting provenance, which are the important reader-facing outcomes.
    figure = output_dir / "phase6_adapter_validation.png"
    build_figure(figure, water_nodes, water, sulfate, sea)
    report = {
        "status": "passed",
        "water_method": water.provenance.method,
        "water_selected_nodes": water.provenance.adapter["selected_node_count"],
        "sulfate_method": sulfate.provenance.method,
        "sulfate_selected_nodes": sulfate.provenance.adapter["selected_node_count"],
        "sea_method": sea.provenance.method,
        "sea_branch": sea.coordinates["humidity_branch"],
        "sea_source_index": sea.provenance.neighbors[0].coordinates["relative_humidity"],
        "figure": str(figure),
    }
    (output_dir / "phase6_validation_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the particle-adapter validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("phase6_validation_output"))
    args = parser.parse_args(argv)
    print(json.dumps(run_validation(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
