"""Export calculated synthetic optics to ARTS, CRTM and RTTOV native files.

Role:
    Validation demonstration

Inputs:
    Synthetic fixtures, reference metadata and test settings generated/selected by this
    script.

Outputs:
    Validation reports, example artifacts and diagnostic figures in the configured output
    directory.

Run:
    From the package root: python examples/example_17_native_model_formats.py --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Export calculated synthetic optics to ARTS, CRTM and RTTOV native files.

    Run: python examples/example_17_native_model_formats.py --output native_model_output
    The isotropic, depolarizing fixture tests serialization, not a realistic habit.
    RTTOV's two example channels must be paired with matching gas coefficients in a
    real simulation. Optional --rttov-cloud-reference preserves a supplied cloud
    table and explicitly replaces its ICE_CLOUD_BAUM optical arrays for a format test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from zju_scatt_interface.bulk.integration import integrate
from zju_scatt_interface.bulk.models import BulkDataset, PopulationResult
from zju_scatt_interface.bulk.quality import validate_bulk_optics
from zju_scatt_interface.io import write
from zju_scatt_interface.io.native import (
    arts_arrays_from_bulk,
    arts_output_template,
    bulk_model_fields,
    crtm_cloud_output_template,
    native_template_from_reference,
    read_native_optical_arrays,
    rttov13_aerosol_output_template,
    scalar_phase_to_model,
    write_native_optical_output,
)
from zju_scatt_interface.optics.models import SingleParticleOptics
from zju_scatt_interface.psd.models import SizeDistribution


def calculate_fixture():
    angles = np.linspace(0, 180, 181)
    phase = np.zeros((2, len(angles), 4, 4))
    phase[:, :, 0, 0] = 1.0  # P11 = 1; integral over solid angle = 4 pi.
    optics = SingleParticleOptics(
        sizes=[1.0, 2.0],
        extinction_cross_section=[1e-12, 4e-12],
        scattering_cross_section=[0.8e-12, 3.2e-12],
        absorption_cross_section=[0.2e-12, 0.8e-12],
        asymmetry_factor=[0.0, 0.0],
        phase_matrix=phase.tolist(),
        scattering_angles=angles.tolist(),
        size_unit="um",
        cross_section_unit="m2",
        metadata={"scattering_angles_degrees": angles.tolist(), "fixture": "isotropic"},
    )
    distribution = SizeDistribution([1, 2], [1, 2])
    bulk, _ = integrate(
        optics, distribution, database_size_definition="volume_equivalent_sphere_radius"
    )
    results = tuple(
        PopulationResult("synthetic", wavelength, bulk, validate_bulk_optics(bulk), (), {}, {})
        for wavelength in (10.0, 11.0)
    )
    scheme = BulkDataset("Native format fixture", (10.0, 11.0), {"demo": results})
    # Explicit particle material density of 1000 kg/m3 and bin counts in m^-3.
    mass = float(
        np.sum(4 / 3 * np.pi * (np.array([1, 2]) * 1e-6) ** 3 * 1000 * np.array([1, 2]) * 1e6)
    )
    return bulk, scheme, mass


def run_example(output, rttov_cloud_reference=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    bulk, scheme, mass = calculate_fixture()
    write(scheme, output / "canonical.nc", format="netcdf4")
    products = {}

    def emit(name, arrays, template):
        template_path = output / (name + ".template.json")
        template_path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        products[name] = str(
            write_native_optical_output(output / name, arrays, template_path, overwrite=True)
        )

    arts = arts_arrays_from_bulk(scheme, component="demo", number_density_m3=3e6, temperature_k=250)
    emit("arts_ssd.xml", arts, arts_output_template(2, 1, 181))

    crtm_values = bulk_model_fields(bulk, model="crtm-cloud-v3", mass_concentration_kg_m3=mass)
    dimensions = {
        "n_MW_Frequencies": 2,
        "n_MW_Radii": 2,
        "n_IR_Frequencies": 2,
        "n_IR_Radii": 2,
        "n_Temperatures": 2,
        "n_Densities": 3,
        "n_IR_Densities": 4,
        "n_Legendre_Terms": 39,
        "n_Phase_Elements": 1,
    }
    crtm = {
        "Frequency_MW": [30.0, 90.0],
        "Frequency_IR": [1e4 / 11, 1000.0],
        "Reff_MW": [1.0, 2.0],
        "Reff_IR": [1.0, 2.0],
        "Temperature": [250.0, 270.0],
        "Density": [100.0, 400.0, 900.0],
    }
    template = crtm_cloud_output_template(dimensions)
    angle_grid = bulk.metadata["scattering_angles_degrees"]
    p11 = np.asarray(bulk.phase_matrix)[:, 0, 0]
    crtm_phase = scalar_phase_to_model(angle_grid, p11, model="crtm-cloud-v3")
    for name, spec in template["variables"].items():
        if name in crtm:
            continue
        shape = tuple(dimensions[d] for d in spec["dimensions"])
        prefix = name.split("_")[0]
        crtm[name] = np.full(shape, crtm_values[prefix] if prefix != "pcoeff" else 0.0)
        if prefix == "pcoeff":
            phase_shape = [1] * len(shape)
            phase_shape[spec["dimensions"].index("n_Legendre_Terms")] = 39
            crtm[name][:] = crtm_phase["pcoeff"].reshape(phase_shape)
    emit("CloudCoeff.nc", crtm, template)
    emit("CloudCoeff.bin", crtm, crtm_cloud_output_template(dimensions, binary=True))

    fields = bulk_model_fields(bulk, model="rttov13", number_density_m3=3e6)
    rttov_phase = scalar_phase_to_model(angle_grid, p11, model="rttov13", max_moments=32)
    rttov = {
        "SCAER/DATA/ABS": np.full((2, 1, 1), fields["ABS"]),
        "SCAER/DATA/SCA": np.full((2, 1, 1), fields["SCA"]),
        "SCAER/DATA/BPR": np.full((2, 1, 1), rttov_phase["BPR"]),
        "SCAER/DATA/NMOM": np.full((2, 1), 32, dtype="int32"),
        "SCAER/DATA/LEGCOEF": np.zeros((2, 1, 1, 33)),
        "SCAER/DATA/PHA": np.ones((2, 1, 1, 181)),
    }
    rttov["SCAER/DATA/LEGCOEF"][:] = rttov_phase["LEGCOEF"]
    template = rttov13_aerosol_output_template(
        2,
        {"demo": {"relative_humidity": [0.0], "confac": 3 / (mass * 1000)}},
        max_moments=32,
        phase_angles=np.linspace(0, 180, 181),
        solar_channels=[1, 2],
    )
    emit("scaercoef_demo.H5", rttov, template)

    if rttov_cloud_reference:
        template = native_template_from_reference(rttov_cloud_reference, model="rttov13")
        cloud = read_native_optical_arrays(rttov_cloud_reference, model="rttov13")
        # Retain other cloud schemes explicitly. Replace every optical field for
        # ICE_CLOUD_BAUM consistently; its normalization is 1 g/m3 of ice water.
        base = "SCCLD/ICE_CLOUD_BAUM/DATA/"
        cloud[base + "ABS"].fill(bulk.absorption_coefficient / (mass * 1000))
        cloud[base + "SCA"].fill(bulk.scattering_coefficient / (mass * 1000))
        cloud[base + "BPR"].fill(0.5)
        cloud[base + "LEGCOEF"].fill(0.0)
        cloud[base + "LEGCOEF"][..., 0] = 1.0
        cloud[base + "PHA"].fill(1.0)
        cloud[base + "NMOM"].fill(int(cloud["SCCLD/ICE_CLOUD_BAUM/MAXNMOM"][0]))
        emit("sccldcoef_demo.H5", cloud, template)

    (output / "manifest.json").write_text(
        json.dumps(
            {
                "purpose": "Synthetic format/integration fixture; not production optical coefficients",
                "number_density_m3": 3e6,
                "mass_concentration_kg_m3": mass,
                "rttov_channel_wavelength_um": [10.0, 11.0],
                "products": products,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return products


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("native_model_output"))
    parser.add_argument("--rttov-cloud-reference", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_example(args.output, args.rttov_cloud_reference), indent=2))
