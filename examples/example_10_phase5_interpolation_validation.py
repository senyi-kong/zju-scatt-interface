"""Detailed Phase 5 interpolation validation and diagnostic graphics.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_10_phase5_interpolation_validation.py
    --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Detailed Phase 5 interpolation validation and diagnostic graphics.

    Run from the project root:

        python examples/example_10_phase5_interpolation_validation.py         --output-dir phase5_validation_output
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from zju_scatt_interface.optics.interpolation import (
    OpticalNode,
    interpolate_nodes,
    write_interpolated_optics_netcdf,
)
from zju_scatt_interface.optics.models import SingleParticleOptics


def size_grid(count: int = 48) -> list[float]:
    return [10 ** (-1.0 + 2.0 * index / (count - 1)) for index in range(count)]


def phase_matrix(sizes, angles, wavelength, rh):
    matrices = []
    for radius in sizes:
        asymmetry = min(0.85, 0.15 + 0.08 * radius + 0.04 * rh)
        size_matrices = []
        for angle in angles:
            mu = math.cos(math.radians(angle))
            denominator = (1 + asymmetry**2 - 2 * asymmetry * mu) ** 1.5
            p11 = (1 - asymmetry**2) / denominator
            matrix = [[0.0] * 4 for _ in range(4)]
            matrix[0][0] = p11 * (1 + 0.01 * wavelength)
            matrix[1][1] = 0.8 * matrix[0][0]
            matrix[2][2] = 0.7 * matrix[0][0]
            matrix[3][3] = 0.6 * matrix[0][0]
            size_matrices.append(matrix)
        matrices.append(size_matrices)
    return matrices


def analytic_optics(wavelength: float, rh: float, angles) -> SingleParticleOptics:
    sizes = size_grid()
    cext = [
        1.0e-12
        * math.pi
        * radius**2
        * (1.5 + 0.3 * math.log1p(radius) + 0.2 * wavelength + 0.5 * rh)
        for radius in sizes
    ]
    ssa = [min(0.98, 0.55 + 0.15 * rh + 0.02 * radius) for radius in sizes]
    return SingleParticleOptics(
        sizes=sizes,
        extinction_cross_section=cext,
        scattering_cross_section=[value * omega for value, omega in zip(cext, ssa)],
        absorption_cross_section=[value * (1 - omega) for value, omega in zip(cext, ssa)],
        asymmetry_factor=[min(0.9, 0.15 + 0.08 * radius + 0.04 * rh) for radius in sizes],
        scattering_angles=list(angles),
        phase_matrix=phase_matrix(sizes, angles, wavelength, rh),
        size_unit="um",
        cross_section_unit="m2",
    )


def build_figure(path: Path, nodes, target, result) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    axis = axes[0, 0]
    for node in nodes:
        axis.loglog(
            node.optics.sizes,
            node.optics.extinction_cross_section,
            alpha=0.55,
            label=f"{node.coordinates['wavelength']} um, RH={node.coordinates['relative_humidity']}",
        )
    axis.loglog(
        result.optics.sizes,
        result.optics.extinction_cross_section,
        "k--",
        linewidth=2.5,
        label="Interpolated target",
    )
    axis.set(xlabel="Radius (um)", ylabel="Cext (m2)", title="Source and target Cext")
    axis.legend(fontsize=8)
    axis.grid(True, which="both", alpha=0.25)

    axis = axes[0, 1]
    wavelengths = sorted({node.coordinates["wavelength"] for node in nodes})
    humidities = sorted({node.coordinates["relative_humidity"] for node in nodes})
    surface = [
        [
            next(
                node.optics.extinction_cross_section[25]
                for node in nodes
                if node.coordinates == {"wavelength": wavelength, "relative_humidity": rh}
            )
            for wavelength in wavelengths
        ]
        for rh in humidities
    ]
    image = axis.imshow(
        surface,
        origin="lower",
        aspect="auto",
        extent=[min(wavelengths), max(wavelengths), min(humidities), max(humidities)],
    )
    axis.plot(target["wavelength"], target["relative_humidity"], "wx", markersize=12, mew=2)
    axis.set(xlabel="Wavelength (um)", ylabel="Relative humidity (1)", title="Interpolation domain")
    figure.colorbar(image, ax=axis, label="Cext (m2)")

    axis = axes[1, 0]
    size_index = len(result.optics.sizes) // 2
    for node in nodes:
        axis.semilogy(
            node.optics.scattering_angles,
            [matrix[0][0] for matrix in node.optics.phase_matrix[size_index]],
            alpha=0.45,
        )
    axis.semilogy(
        result.optics.scattering_angles,
        [matrix[0][0] for matrix in result.optics.phase_matrix[size_index]],
        "k--",
        linewidth=2.5,
        label="Aligned and interpolated P11",
    )
    axis.set(xlabel="Scattering angle (degree)", ylabel="P11 (1)", title="Angular-grid alignment")
    axis.legend()
    axis.grid(True, which="both", alpha=0.25)

    axis = axes[1, 1]
    labels = [
        f"{item.coordinates['wavelength']} um\nRH={item.coordinates['relative_humidity']}"
        for item in result.provenance.neighbors
    ]
    weights = [item.weight for item in result.provenance.neighbors]
    axis.bar(labels, weights, color="#4472C4")
    axis.set(ylim=(0, 1), ylabel="Weight", title=f"Provenance: {result.provenance.method}")
    axis.tick_params(axis="x", labelsize=8)
    axis.grid(True, axis="y", alpha=0.25)

    figure.suptitle("ZJU-SCATT Phase 5 interpolation validation", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_validation(output_dir: Path) -> dict:
    """Run multidimensional interpolation and NetCDF output checks."""

    output_dir.mkdir(parents=True, exist_ok=True)

    # The four synthetic nodes form a 2-D rectangle in wavelength and relative
    # humidity.  Their angle grids intentionally differ so alignment is tested
    # alongside coordinate interpolation.
    nodes = []
    angle_grids = ([0, 30, 60, 90, 120, 150, 180], [0, 45, 90, 135, 180])
    for index, (wavelength, rh) in enumerate(((0.55, 0.2), (1.05, 0.2), (0.55, 0.8), (1.05, 0.8))):
        nodes.append(
            OpticalNode(
                {"wavelength": wavelength, "relative_humidity": rh},
                analytic_optics(wavelength, rh, angle_grids[index % 2]),
                f"synthetic_source_{index}.nc",
            )
        )

    target = {"wavelength": 0.75, "relative_humidity": 0.5}
    target_angles = list(range(0, 181, 5))

    # Interpolate the full optical object, including phase-matrix arrays, onto
    # the requested target coordinates and a common 5-degree angle grid.
    result = interpolate_nodes(
        "sphere_sulfate",
        nodes,
        target,
        target_angles_degrees=target_angles,
        phase_normalization="preserve",
    )
    nc_path = write_interpolated_optics_netcdf(
        result, output_dir / "phase5_interpolated_product.nc"
    )

    # Keep both a plot and a machine-readable report: the plot explains the
    # geometry, while the report records exact neighbor and weight counts.
    figure_path = output_dir / "phase5_interpolation_validation.png"
    build_figure(figure_path, nodes, target, result)
    report = {
        "status": "passed",
        "target": target,
        "method": result.provenance.method,
        "neighbor_count": len(result.provenance.neighbors),
        "weight_sum": sum(item.weight for item in result.provenance.neighbors),
        "size_count": len(result.optics.sizes),
        "angle_count": len(result.optics.scattering_angles),
        "constraint_corrections": result.provenance.constraint_corrections,
        "netcdf": str(nc_path),
        "figure": str(figure_path),
    }
    (output_dir / "phase5_validation_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the interpolation validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("phase5_validation_output"))
    args = parser.parse_args(argv)
    report = run_validation(args.output_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
