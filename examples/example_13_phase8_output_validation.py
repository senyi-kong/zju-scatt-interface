"""Phase 8 NetCDF4/HDF5 round-trip and graphical validation.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_13_phase8_output_validation.py --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Phase 8 NetCDF4/HDF5 round-trip and graphical validation.

    Run from the project root:

        python examples/example_13_phase8_output_validation.py         --output-dir phase8_validation_output
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from example_12_phase7_bulk_pipeline_validation import build_validation_result

from zju_scatt_interface.bulk.ensemble import combine
from zju_scatt_interface.bulk.models import BulkDataset
from zju_scatt_interface.io import write
from zju_scatt_interface.io.canonical import OutputOptions, read, validate_file


def build_figure(path: Path, netcdf: dict, hdf5: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    colors = {"cloud": "#4C72B0", "sulfate": "#DD8452", "mixture": "#222222"}
    for name in ("cloud", "sulfate", "mixture"):
        nc_group = netcdf["components"][name]["datasets"]
        h5_group = hdf5["components"][name]["datasets"]
        axes[0, 0].semilogy(
            nc_group["wavelength"]["data"],
            nc_group["beta_ext"]["data"],
            "o-",
            color=colors[name],
            label=f"{name} NetCDF4",
        )
        axes[0, 0].semilogy(
            h5_group["wavelength"]["data"],
            h5_group["beta_ext"]["data"],
            "x",
            color=colors[name],
            markersize=8,
            label=f"{name} HDF5",
        )
    axes[0, 0].set(
        xlabel="Wavelength (um)",
        ylabel="Extinction coefficient (m-1)",
        title="Format round-trip overlay",
    )
    axes[0, 0].grid(True, which="both", alpha=0.25)
    axes[0, 0].legend(fontsize=8, ncol=2)

    sulfate = netcdf["components"]["sulfate"]["datasets"]
    axes[0, 1].plot(sulfate["wavelength"]["data"], sulfate["ssa"]["data"], "o-", label="SSA")
    axes[0, 1].plot(sulfate["wavelength"]["data"], sulfate["g"]["data"], "s-", label="g")
    axes[0, 1].set(
        ylim=(0, 1),
        xlabel="Wavelength (um)",
        ylabel="Dimensionless value",
        title="Stored intensive properties",
    )
    axes[0, 1].grid(True, alpha=0.25)
    axes[0, 1].legend()

    size = sulfate["psd_size"]["data"]
    dndr = sulfate["psd_dndr"]["data"]
    axes[1, 0].loglog(size, dndr, "o-", color="#55A868")
    axes[1, 0].set(
        xlabel="Volume-equivalent sphere radius (um)",
        ylabel="Concentration per represented bin (cm-3)",
        title="PSD preserved in output",
    )
    axes[1, 0].grid(True, which="both", alpha=0.25)

    weights = sulfate["shape_weight"]["data"][0]
    labels = [f"RH={value:.1f}" for value in sulfate["relative_humidity"]["data"][0]]
    axes[1, 1].bar(labels, weights, color="#C44E52")
    axes[1, 1].set(
        ylim=(0, 1),
        ylabel="Normalized weight",
        title="Stored ensemble coordinates",
    )
    axes[1, 1].grid(True, axis="y", alpha=0.25)

    figure.suptitle("ZJU-SCATT Phase 8 output validation", fontsize=15)
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _equivalent(netcdf: dict, hdf5: dict) -> bool:
    if set(netcdf["components"]) != set(hdf5["components"]):
        return False
    for name in netcdf["components"]:
        nc_variables = netcdf["components"][name]["datasets"]
        h5_variables = hdf5["components"][name]["datasets"]
        if set(nc_variables) != set(h5_variables):
            return False
        for variable in nc_variables:
            if nc_variables[variable]["data"] != h5_variables[variable]["data"]:
                return False
            if nc_variables[variable]["units"] != h5_variables[variable]["units"]:
                return False
    return True


def run_validation(output_dir: Path) -> dict:
    """Write, validate, read, and compare NetCDF4 and HDF5 products."""

    output_dir.mkdir(parents=True, exist_ok=True)
    result = build_validation_result(output_dir / "pipeline")
    # Phase 7 intentionally keeps particle components separate.  Phase 8 also
    # demonstrates the optional external-mixture output group by combining the
    # two component bulk products at each wavelength.
    mixture = tuple(
        combine(
            [
                result.components["cloud"][index].bulk,
                result.components["sulfate"][index].bulk,
            ],
            weights=[0.6, 0.4],
            metadata={"example": "Phase 8 external mixture"},
        )
        for index in range(len(result.wavelengths_um))
    )
    result = BulkDataset(
        name=result.name,
        wavelengths_um=result.wavelengths_um,
        components=result.components,
        mixture=mixture,
        dependency_plan=result.dependency_plan,
    )
    # Use identical compression and atomic-write settings for both formats so
    # the comparison focuses on scientific content rather than writer options.
    controls = OutputOptions(compression=True, compression_level=4, atomic=True)
    netcdf_path = write(
        result,
        output_dir / "phase8_bulk_scheme.nc",
        scheme={"name": result.name, "example": "Phase 8 validation"},
        source_manifest={"kind": "synthetic validation sources"},
        options=controls,
        format="netcdf4",
    )
    hdf5_path = write(
        result,
        output_dir / "phase8_bulk_scheme.h5",
        scheme={"name": result.name, "example": "Phase 8 validation"},
        source_manifest={"kind": "synthetic validation sources"},
        options=controls,
        format="hdf5",
    )
    netcdf_report = validate_file(netcdf_path)
    hdf5_report = validate_file(hdf5_path)
    # Read both files back through the public reader before comparing them.  A
    # successful write alone would not prove that the stored arrays are usable.
    netcdf = read(netcdf_path)
    hdf5 = read(hdf5_path)
    equivalent = _equivalent(netcdf, hdf5)
    figure = output_dir / "phase8_output_validation.png"
    build_figure(figure, netcdf, hdf5)
    report = {
        "status": (
            "passed" if netcdf_report.passed and hdf5_report.passed and equivalent else "failed"
        ),
        "netcdf": netcdf_report.to_dict(),
        "hdf5": hdf5_report.to_dict(),
        "equivalent_scientific_content": equivalent,
        "component_names": list(netcdf["components"]),
        "netcdf_size_bytes": netcdf_path.stat().st_size,
        "hdf5_size_bytes": hdf5_path.stat().st_size,
        "figure": str(figure),
    }
    (output_dir / "phase8_validation_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run the dual-format validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("phase8_validation_output"))
    args = parser.parse_args(argv)
    report = run_validation(args.output_dir)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
