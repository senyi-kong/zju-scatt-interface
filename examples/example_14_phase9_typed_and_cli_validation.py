"""Phase 9 typed-Python and declarative-CLI equivalence validation.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_14_phase9_typed_and_cli_validation.py
    --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Phase 9 typed-Python and declarative-CLI equivalence validation.

    Run from the project root:

        python examples/example_14_phase9_typed_and_cli_validation.py         --output-dir phase9_validation_output
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
from pathlib import Path

from zju_scatt_interface.cli.main import main as cli_main
from zju_scatt_interface.config.scheme import Scheme, SchemeOutput, WaterCloudComponent
from zju_scatt_interface.io import write
from zju_scatt_interface.io.canonical import read, validate_file


def lognormal_bin_concentration() -> tuple[list[float], list[float]]:
    """Example user function evaluated outside the scheme interface."""

    import numpy as np

    radius = np.geomspace(0.1, 10.0, 21)
    median = 1.0
    sigma = 1.7
    density = np.exp(-(np.log(radius / median) ** 2) / (2 * math.log(sigma) ** 2))
    concentration = 100.0 * density / density.sum()
    return radius.tolist(), concentration.tolist()


def create_sources(root: Path) -> None:
    import numpy as np
    from netCDF4 import Dataset

    root.mkdir(parents=True, exist_ok=True)
    # These compact NetCDF files provide the same source interface as L1 data
    # while keeping the typed-Python and CLI paths deterministic.
    radius = np.geomspace(0.1, 10.0, 48)
    for wavelength, multiplier in ((0.5, 1.0), (0.7, 1.5), (0.9, 2.0)):
        path = root / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc"
        with Dataset(path, "w") as dataset:
            dataset.createDimension("xsize_veq", len(radius))
            dataset.createVariable("wavelength", "f8")[:] = wavelength
            dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = (
                radius * 2 * math.pi / wavelength
            )
            dataset.createVariable("cext", "f8", ("xsize_veq",))[:] = multiplier * np.geomspace(
                0.1, 300.0, len(radius)
            )
            dataset.createVariable("ssa", "f8", ("xsize_veq",))[:] = 0.75 + 0.05 * wavelength
            dataset.createVariable("g", "f8", ("xsize_veq",))[:] = 0.4 + 0.1 * wavelength


def _scientific_equal(first: dict, second: dict) -> bool:
    left = first["components"]["cloud"]["datasets"]
    right = second["components"]["cloud"]["datasets"]
    for name in ("wavelength", "beta_ext", "beta_sca", "beta_abs", "ssa", "g"):
        if left[name]["data"] != right[name]["data"]:
            return False
        if left[name]["units"] != right[name]["units"]:
            return False
    return True


def build_figure(path: Path, content: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    datasets = content["components"]["cloud"]["datasets"]
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    axes[0, 0].loglog(
        datasets["psd_size"]["data"],
        datasets["psd_dndr"]["data"],
        "o-",
        color="#55A868",
    )
    axes[0, 0].set(
        xlabel="Volume-equivalent sphere radius (um)",
        ylabel="Concentration per represented bin (cm-3)",
        title="Function-generated PSD",
    )
    axes[0, 0].grid(True, which="both", alpha=0.25)

    wavelength = datasets["wavelength"]["data"]
    axes[0, 1].semilogy(wavelength, datasets["beta_ext"]["data"], "o-", label="beta_ext")
    axes[0, 1].semilogy(wavelength, datasets["beta_sca"]["data"], "s-", label="beta_sca")
    axes[0, 1].semilogy(wavelength, datasets["beta_abs"]["data"], "^-", label="beta_abs")
    axes[0, 1].set(
        xlabel="Wavelength (um)",
        ylabel="Coefficient (m-1)",
        title="CLI-built bulk coefficients",
    )
    axes[0, 1].grid(True, which="both", alpha=0.25)
    axes[0, 1].legend()

    axes[1, 0].plot(wavelength, datasets["ssa"]["data"], "o-", label="SSA")
    axes[1, 0].plot(wavelength, datasets["g"]["data"], "s-", label="g")
    axes[1, 0].set(
        ylim=(0, 1),
        xlabel="Wavelength (um)",
        ylabel="Dimensionless value",
        title="Stored intensive properties",
    )
    axes[1, 0].grid(True, alpha=0.25)
    axes[1, 0].legend()

    axes[1, 1].axis("off")
    axes[1, 1].text(
        0.05,
        0.75,
        "One normalized scheme\n\n"
        "Typed Python → HDF5\n"
        "JSON + CLI → NetCDF4\n\n"
        "Scientific arrays equivalent",
        fontsize=15,
        va="top",
        bbox={"boxstyle": "round", "facecolor": "#EAF2F8", "alpha": 0.9},
    )
    figure.suptitle("ZJU-SCATT Phase 9 workflow equivalence", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_validation(output_dir: Path) -> dict:
    """Compare typed-Python and declarative-CLI products from one scheme."""

    output_dir.mkdir(parents=True, exist_ok=True)
    # Build one normalized scheme and serialize it before invoking either
    # execution path.  This makes the comparison about interfaces, not inputs.
    sources = output_dir / "synthetic_l1"
    create_sources(sources)
    radius, concentration = lognormal_bin_concentration()
    component = WaterCloudComponent(
        "cloud",
        size=radius,
        dndr=concentration,
        source=sources,
    )
    scheme = Scheme(
        name="phase9_equivalence",
        wavelengths_um=(0.5, 0.6, 0.8),
        particles=(component,),
        output_settings=SchemeOutput(
            "phase9_cli_product.nc",
            "netcdf4",
            compression_level=4,
        ),
        truncation_policy="truncate",
        check_convergence=False,
    )
    scheme_path = scheme.write_json(output_dir / "phase9_scheme.json")

    python_result = scheme.build()
    python_path = write(
        python_result, output_dir / "phase9_python_product.h5", scheme=scheme, format="hdf5"
    )

    # The CLI consumes the JSON scheme and writes NetCDF4.  Capture its streams
    # so the example can raise a useful Python error without noisy duplication.
    cli_path = output_dir / "phase9_cli_product.nc"
    cli_report = output_dir / "phase9_cli_report.json"
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        cli_status = cli_main(
            [
                "bulk-opt",
                "build",
                str(scheme_path),
                "--output",
                str(cli_path),
                "--format",
                "netcdf4",
                "--report",
                str(cli_report),
                "--json",
            ]
        )
    if cli_status:
        raise RuntimeError(f"Phase 9 CLI validation failed ({cli_status}): {stderr.getvalue()}")

    python_validation = validate_file(python_path)
    cli_validation = validate_file(cli_path)
    python_content = read(python_path)
    cli_content = read(cli_path)
    # Compare scientific datasets and units after reading both outputs through
    # the public reader; container format differences are intentionally ignored.
    equivalent = _scientific_equal(python_content, cli_content)
    figure = output_dir / "phase9_workflow_validation.png"
    build_figure(figure, cli_content)
    report = {
        "status": (
            "passed"
            if python_validation.passed and cli_validation.passed and equivalent
            else "failed"
        ),
        "schema_version": scheme.schema_version,
        "normalized_round_trip": (Scheme.from_dict(scheme.to_dict()).to_dict() == scheme.to_dict()),
        "python_output": python_validation.to_dict(),
        "cli_output": cli_validation.to_dict(),
        "scientific_content_equivalent": equivalent,
        "cli_report": str(cli_report),
        "figure": str(figure),
    }
    (output_dir / "phase9_validation_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the equivalence validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("phase9_validation_output"))
    args = parser.parse_args(argv)
    report = run_validation(args.output_dir)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
