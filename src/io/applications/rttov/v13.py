"""io / applications / rttov / v13 domain implementation."""

from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.io.applications.common import AEROSOL_NAMES
from zju_scatt_interface.io.native import (
    bulk_model_fields,
    rttov13_aerosol_output_template,
    scalar_phase_to_model,
    write_native_optical_output,
)

ICE_GROUP = "ICE_CLOUD_ZJU_SUPER_SPHEROID"
WATER_GROUP = "WATER_CLOUD_ZJU_GAMMA"


def _cloud_template(nchannels, max_moments):
    # All three groups are required by RTTOV13. The five OPAC slots are
    # explicitly aliases of our ONE reference water PSD, not OPAC climatology.
    variables = {}
    for group, names, identifier in (
        ("WATER_CLOUD_OPAC", ("STCO", "STMA", "CUCC", "CUCP", "CUMA"), 1),
        (WATER_GROUP, ("WATR",), 1),
        (ICE_GROUP, ("ICES",), 0),
    ):
        source = rttov13_aerosol_output_template(
            nchannels,
            {name: {"relative_humidity": [0.0], "confac": 0.0} for name in names},
            max_moments=max_moments,
        )
        for name, spec in source["variables"].items():
            target = name.replace("SCAER", "SCCLD/" + group, 1)
            spec = copy.deepcopy(spec)
            if "source" in spec:
                spec["source"] = target
            if name == "SCAER/ID":
                spec["data"] = [identifier]
            if group != "WATER_CLOUD_OPAC" and name.rsplit("/", 1)[-1] in {"ABS", "SCA"}:
                spec["attributes"]["UNITS"] = "m2.g-1"
            variables[target] = spec
    return {
        "schema_version": 1,
        "model": "rttov13",
        "cloud_variant": "zju_clouds",
        "format": "hdf5",
        "variables": variables,
    }


@_registration_required
def write_rttov13_bulk_tables(
    result,
    directory,
    *,
    max_moments=32,
    water_density_kg_m3=1000.0,
    ice_density_kg_m3=917.0,
    phase_normalization="preserve",
):
    """Write SCAER and fixed-PSD SCCLD files with ZJU-named cloud groups.

    The cloud file is a named extension of RTTOV13's layout. An unmodified
    RTTOV13 cloud reader does not recognize ICE_CLOUD_ZJU_SUPER_SPHEROID or
    WATER_CLOUD_ZJU_GAMMA; adapt its group lookups before use. Aerosol layout
    uses full lowercase species names, also requiring reader adaptation.

    Requires all eight species and include_phase_matrix=True. Channel order is
    the supplied wavelength order, with no sensor convolution or channel guess.
    Aerosols require profiles%mmr_cldaer=.FALSE. and number inputs in cm^-3;
    no aerosol dry masses are assumed (CONFAC=0 disables mass conversion).
    Cloud inputs are g/m^3. The cloud file represents one fixed PSD per phase,
    not a variable effective-size grid or the original model populations.
    PSD counts are never modified; only the output coefficient units change.
    Optional phase_normalization='renormalize' explicitly normalizes angular
    P11 only, recording its original integral; the PSD and bulk beta stay fixed.
    """
    import numpy as np

    expected = set(AEROSOL_NAMES) | {"sphere_water_cloud", "super_spheroid_ice"}
    if set(result.scheme.components) != expected:
        raise ValueError("RTTOV default bulk export requires all eight particle types")
    if not isinstance(max_moments, int) or not 1 <= max_moments <= 255:
        raise ValueError("max_moments must be an integer from 1 to 255")
    if phase_normalization not in {"preserve", "renormalize"}:
        raise ValueError("phase_normalization must be preserve or renormalize")
    for value in (water_density_kg_m3, ice_density_kg_m3):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Cloud material densities must be finite and positive")
    wavelengths = tuple(result.scheme.wavelengths_um)
    if any(w < 3.0 for w in wavelengths):
        raise ValueError(
            "This thermal-IR exporter requires wavelengths >=3 um (no solar PHA channels)"
        )
    channels = len(wavelengths)
    specs = {
        short: {
            "relative_humidity": [
                100
                * result.report["species"][name]["effective_parameters"].get(
                    "relative_humidity", 0.0
                )
            ],
            "confac": 0.0,
        }
        for name, short in AEROSOL_NAMES.items()
    }
    aerosol_template = rttov13_aerosol_output_template(
        channels, specs, max_moments=max_moments, species_naming="descriptive"
    )
    cloud_template = _cloud_template(channels, max_moments)
    aerosol, cloud, populations, phase_checks = {}, {}, {}, {}
    for family, calculations in result.scheme.components.items():
        if tuple(c.wavelength_um for c in calculations) != wavelengths:
            raise ValueError(f"Incomplete or reordered wavelengths for {family}")
        psd = result.report["species"][family]["psd"]
        count = float(psd["number_concentration_cm3"])
        mass = None
        if family not in AEROSOL_NAMES:
            density = water_density_kg_m3 if family == "sphere_water_cloud" else ice_density_kg_m3
            # Bin counts cm^-3 -> m^-3, radius um -> m, kg -> g.
            mass = (
                sum(n * (r * 1e-6) ** 3 for r, n in zip(psd["size"], psd["dndr"]))
                * (4 * math.pi / 3)
                * density
                * 1e9
            )
            if not math.isfinite(mass) or mass <= 0:
                raise ValueError(f"Invalid cloud mass concentration for {family}")
        populations[family] = {"number_concentration_cm3": count, "mass_concentration_g_m3": mass}
        records = []
        phase_checks[family] = []
        for calculation in calculations:
            bulk = calculation.bulk
            if bulk.phase_matrix is None:
                raise ValueError(
                    "RTTOV BPR/Legendre coefficients require include_phase_matrix=True"
                )
            phase = np.asarray(bulk.phase_matrix)[:, 0, 0]
            angles = np.asarray(bulk.metadata["scattering_angles_degrees"])
            mu = np.cos(np.deg2rad(angles))[::-1]
            reversed_phase = phase[::-1]
            integral = float(np.sum(np.diff(mu) * (reversed_phase[1:] + reversed_phase[:-1]) / 4))
            if not math.isfinite(integral) or integral <= 0:
                raise ValueError(f"Invalid phase-function integral for {family}")
            scale = 1 / integral if phase_normalization == "renormalize" else 1.0
            phase = phase * scale
            projected = scalar_phase_to_model(
                bulk.metadata["scattering_angles_degrees"],
                phase,
                model="rttov13",
                max_moments=max_moments,
                quadrature_points=max(512, 2 * max_moments + 1),
            )
            phase_checks[family].append(
                {
                    "wavelength_um": calculation.wavelength_um,
                    "input_half_integral": integral,
                    "applied_phase_scale": scale,
                    "projected_half_integral": projected["normalization"],
                }
            )
            if family in AEROSOL_NAMES:
                fields = bulk_model_fields(bulk, model="rttov13", number_density_m3=count * 1e6)
            else:
                fields = {
                    "ABS": bulk.absorption_coefficient / mass,
                    "SCA": bulk.scattering_coefficient / mass,
                }
            records.append({**fields, **projected})

        def fill(output, base, normalization):
            for key in ("ABS", "SCA", "BPR"):
                output[base + key] = np.asarray([r[key] for r in records])[:, None, None]
            output[base + "NMOM"] = np.full((channels, 1), max_moments, dtype="int32")
            output[base + "LEGCOEF"] = np.asarray([r["LEGCOEF"] for r in records])[:, None, None, :]
            if normalization == "number_cloud":
                # OPAC cloud slots are per particle/cm^3, with mass conversion.
                output[base + "ABS"] *= mass / count
                output[base + "SCA"] *= mass / count

        if family in AEROSOL_NAMES:
            fill(aerosol, "SCAER/" + AEROSOL_NAMES[family] + "/", "number")
        elif family == "sphere_water_cloud":
            fill(cloud, "SCCLD/" + WATER_GROUP + "/DATA/", "mass")
            # Fixed-PSD tables use a single size slot; DEFF=0 denotes no size grid.
            for slot in ("STCO", "STMA", "CUCC", "CUCP", "CUMA"):
                base = "SCCLD/WATER_CLOUD_OPAC/" + slot + "/"
                fill(cloud, base, "number_cloud")
                cloud_template["variables"][base + "CONFAC"]["data"] = [count / mass]
        else:
            fill(cloud, "SCCLD/" + ICE_GROUP + "/DATA/", "mass")
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    # Assemble/validate all scientific arrays before replacing either product.
    from zju_scatt_interface.io.native import _resolve_arrays, _validate_native

    for data, template in ((aerosol, aerosol_template), (cloud, cloud_template)):
        _validate_native(_resolve_arrays(data, template), template)
    paths = {}
    for name, data, template in (
        ("scaercoef_zju_default.H5", aerosol, aerosol_template),
        ("sccldcoef_zju_default.H5", cloud, cloud_template),
    ):
        paths[name] = str(
            write_native_optical_output(output / name, data, template, overwrite=True)
        )
        (output / (name + ".template.json")).write_text(
            json.dumps(template, indent=2), encoding="utf-8"
        )
    with (output / "channel_wavelengths.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["table_channel_index", "wavelength_um", "wavenumber_cm-1"])
        writer.writerows((i, w, 1e4 / w) for i, w in enumerate(wavelengths, 1))
    manifest = {
        "model": "RTTOV 13/13.2 layout with descriptive ZJU aerosol/cloud names",
        "direct_rttov13_aerosol_read_compatible": False,
        "aerosol_reader_adaptation": "Use full species names without four-character truncation; preserve lowercase group names",
        "direct_rttov13_cloud_read_compatible": False,
        "cloud_reader_adaptation": "Recognize both ZJU cloud groups and load them into the internal water/ice optics structures",
        "outputs": paths,
        "wavelengths_um": wavelengths,
        "spectral_sampling": "Monochromatic at user wavelengths; not sensor-response averaged",
        "channel_requirement": "Match gas-coefficient channel count and ordering before radiance use",
        "aerosol_species": AEROSOL_NAMES,
        "profiles_mmr_cldaer": False,
        "aerosol_input_units": "particles cm^-3; CONFAC=0, mass-mixing-ratio inputs unsupported",
        "cloud_input_units": "g m^-3",
        "cloud_size_dependence": "Fixed PSD, one DEFF=0 slot; size inputs do not select a different PSD",
        "water_cloud_opac_slots": "All five slots alias the same ZJU default water PSD, not the OPAC climatologies",
        "ice_cloud_group": "SCCLD/" + ICE_GROUP,
        "water_cloud_group": "SCCLD/" + WATER_GROUP,
        "water_optics_source": "ZJU-SCATT water cloud with the configured PSD (default gamma)",
        "ice_optics_source": "ZJU-SCATT super-spheroid ice",
        "water_density_kg_m3": water_density_kg_m3,
        "ice_density_kg_m3": ice_density_kg_m3,
        "populations": populations,
        "phase_max_moments": max_moments,
        "phase_method": "P11 projected with scalar_phase_to_model; no phase synthesis",
        "phase_normalization": phase_normalization,
        "phase_checks": phase_checks,
        "rttov_radiance_simulation_tested": False,
    }
    (output / "rttov_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
