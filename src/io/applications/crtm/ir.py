"""CRTM infrared optical tables, mass conversion and validation."""

from __future__ import annotations

import csv
import json
import math
import uuid
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.io.applications.common import (
    AEROSOL_NAMES,
    HYDROMETEOR_NAMES,
)
from zju_scatt_interface.io.applications.common import (
    characters as _characters,
)
from zju_scatt_interface.io.applications.common import (
    input_spectrum as _input_spectrum,
)
from zju_scatt_interface.io.native import scalar_phase_to_model

HYGROSCOPIC = {
    "coated_super_spheroid_seasalt",
    "sphere_sulfate",
    "sphere_nitrate",
    "sphere_organic_carbon",
}


def _growth_factor(entry):
    """Interpolate native radius growth factors on the selected humidity branch."""
    import numpy as np
    from netCDF4 import Dataset

    parameters = entry["effective_parameters"]
    target = float(parameters["relative_humidity"]) * 100
    crystallization = parameters.get("humidity_branch") == "crystallization"
    factors = []
    for source in entry.get("sources", []):
        with Dataset(source["path"]) as nc:
            rh, gf = np.asarray(nc["rh"][:]), np.asarray(nc["gf"][:])
        selected = (rh < 0) if crystallization else (rh >= 0)
        x, y = np.abs(rh[selected]), gf[selected]
        order = np.argsort(x)
        x, y = x[order], y[order]
        if (
            not len(x)
            or not np.isfinite(x).all()
            or not np.isfinite(y).all()
            or np.any(y <= 0)
            or np.any(np.diff(x) <= 0)
            or target < x[0]
            or target > x[-1]
        ):
            raise ValueError("Native growth-factor grid cannot bracket the selected RH/branch")
        factors.append(float(np.interp(target, x, y)))
    if not factors or not np.allclose(factors, factors[0], rtol=1e-6, atol=0):
        raise ValueError(
            "Missing or inconsistent native growth factors; provide an explicit growth_factors override"
        )
    return factors[0]


def _population_mass(family, entry, density, growth_factors):
    import numpy as np

    psd = entry["psd"]
    if (
        psd.get("size_definition") != "volume_equivalent_sphere_radius"
        or psd.get("size_unit") != "um"
        or psd.get("dndr_unit") != "cm-3"
        or psd.get("integration_mode") != "discrete_bin"
    ):
        raise ValueError(
            "Mass conversion requires volume-equivalent radius [um] and discrete bin counts [cm-3]"
        )
    radii, counts = np.asarray(psd["size"], dtype=float), np.asarray(psd["dndr"], dtype=float)
    if (
        radii.ndim != 1
        or not len(radii)
        or radii.shape != counts.shape
        or not np.isfinite(radii).all()
        or not np.isfinite(counts).all()
        or np.any(radii <= 0)
        or np.any(counts < 0)
        or counts.sum() <= 0
    ):
        raise ValueError("Expected positive volume-equivalent radii and nonnegative bin counts")
    if not math.isfinite(density) or density <= 0:
        raise ValueError("Material density must be finite and positive")
    volume = float(np.sum(counts * radii**3)) * 4 * math.pi / 3 * 1e-12
    fraction, gf, basis = 1.0, 1.0, "dry particle mass"
    if family == "encapsulated_fractal_aggregates_black_carbon":
        fraction = float(entry["effective_parameters"]["vf"])
        if not 0 < fraction <= 1:
            raise ValueError("Black-carbon vf must be in (0, 1]")
        basis = "black-carbon core mass; hygroscopic coating excluded"
    elif family in HYGROSCOPIC:
        gf = float(growth_factors[family]) if family in growth_factors else _growth_factor(entry)
        if not math.isfinite(gf) or gf < 1:
            raise ValueError("Radius growth factor must be finite and >= 1")
        fraction = gf**-3
        basis = "dry constituent mass; water excluded; dry volume = wet volume / gf^3"
    elif family in HYDROMETEOR_NAMES:
        basis = "water/ice mass from volume-equivalent particle volume"
    return {
        "mass_kg_m3": volume * density * fraction,
        "material_density_kg_m3": density,
        "radius_growth_factor": gf,
        "mass_volume_fraction": fraction,
        "mass_basis": basis,
        "volume_equivalent_reff_um": float(np.sum(counts * radii**3) / np.sum(counts * radii**2)),
        "number_concentration_cm3": float(counts.sum()),
    }


@_registration_required
def write_crtm_ir_bulk_tables(
    data, output_dir, *, material_densities_kg_m3, growth_factors=None, phase_normalization="error"
):
    """Export computed fixed populations; preserve PSD bin counts exactly.

    Densities are explicitly supplied by full output species name. Aerosol ke
    is per kg of dry constituent (BC core for coated BC); cloud ke is per kg
    of water/ice. Native radius growth factors are used for hygroscopic species,
    unless overridden by a family-keyed growth_factors mapping. PSD size must be
    physical volume-equivalent radius in micrometers, dndr integrated bin N/cm3
    as produced by run_bulk_table. See the manifest for conversion assumptions.
    """
    import numpy as np
    from netCDF4 import Dataset

    if phase_normalization not in {"error", "renormalize"}:
        raise ValueError("phase_normalization must be error or renormalize")
    wavelengths, records, report = _input_spectrum(data)
    names = {**AEROSOL_NAMES, **HYDROMETEOR_NAMES}
    if set(records) - set(names):
        raise ValueError("Unsupported particle family")
    wl = np.asarray(wavelengths, dtype=float)
    if (
        wl.ndim != 1
        or not len(wl)
        or not np.isfinite(wl).all()
        or np.any(wl <= 0)
        or len(set(wl)) != len(wl)
    ):
        raise ValueError("Wavelengths must be finite, positive and unique")
    order = np.argsort(1e4 / wl)
    populations, optics, phase_checks = {}, {}, {}
    for family, rows in records.items():
        name = names[family]
        population = _population_mass(
            family,
            report["species"][family],
            float(material_densities_kg_m3[name]),
            growth_factors or {},
        )
        populations[name] = population
        optics[name], phase_checks[name] = [], []
        for index in order:
            row = rows[index]
            if not math.isclose(
                row["number"], population["number_concentration_cm3"], rel_tol=1e-8
            ):
                raise ValueError("Optical population and mass PSD have different concentrations")
            angles, phase = np.asarray(row["angles"]), np.asarray(row["p11"])
            mu, reverse = np.cos(np.deg2rad(angles))[::-1], phase[::-1]
            integral = float(np.sum(np.diff(mu) * (reverse[1:] + reverse[:-1]) / 4))
            if not math.isfinite(integral) or integral <= 0:
                raise ValueError("Invalid phase normalization integral")
            scale = 1 / integral if phase_normalization == "renormalize" else 1.0
            projected = scalar_phase_to_model(angles, phase * scale, model="crtm-cloud-v3")
            optics[name].append(
                {
                    "ke": row["ext"] / population["mass_kg_m3"],
                    "w": row["ssa"],
                    "g": row["g"],
                    "pcoeff": projected["pcoeff"],
                }
            )
            phase_checks[name].append(
                {
                    "input_half_integral": integral,
                    "applied_phase_scale": scale,
                    "phase_derived_g": projected["g"],
                }
            )
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for kind, families in (("aerosol", AEROSOL_NAMES), ("cloud", HYDROMETEOR_NAMES)):
        selected = [names[f] for f in families if f in records]
        if not selected:
            continue
        path = directory / f"{kind}_zju_ir_fixed_psd.nc"
        temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with Dataset(temporary, "w", format="NETCDF4") as nc:
                nc.title = f"ZJU-SCATT {kind} fixed-PSD infrared optical table"
                nc.format_id = "ZJU_CRTM_IR_FIXED_PSD_V1"
                nc.native_crtm_compatible = 0
                nc.reader_requirement = (
                    "Custom adapter required; no microwave blocks or size-grid lookup"
                )
                nc.phase_convention = "Scalar CRTM release-3 packing, alpha_l/2; no delta scaling"
                nc.phase_blocks = (
                    "zero-based offsets 0,5,12,21; maximum orders 4,6,8,16; index 38 padding"
                )
                nc.mass_loading_usage = (
                    "optical depth = ke * layer constituent mass loading [kg m-2]"
                )
                nc.reff_definition = (
                    "Volume-equivalent radius M3/M2; descriptive fixed PSD, not a lookup axis"
                )
                for dim, size in (
                    ("n_Types", len(selected)),
                    ("n_IR_Frequencies", len(wl)),
                    ("n_Phase_Elements", 1),
                    ("n_Packed_Coefficients", 39),
                    ("name_length", 80),
                ):
                    nc.createDimension(dim, size)

                def put(name, values, dims, units="1", dtype="f8"):
                    var = nc.createVariable(name, dtype, dims)
                    var[:] = values
                    var.units = units

                put("Type_Name", _characters(selected, 80), ("n_Types", "name_length"), dtype="S1")
                put("Wavelength", wl[order], ("n_IR_Frequencies",), "um")
                put("Frequency_IR", 1e4 / wl[order], ("n_IR_Frequencies",), "cm-1")
                put(
                    "Reff",
                    [populations[n]["volume_equivalent_reff_um"] for n in selected],
                    ("n_Types",),
                    "um",
                )
                for field in ("ke", "w", "g"):
                    put(
                        field,
                        [[r[field] for r in optics[n]] for n in selected],
                        ("n_Types", "n_IR_Frequencies"),
                        "m2 kg-1" if field == "ke" else "1",
                    )
                phase = np.asarray([[r["pcoeff"] for r in optics[n]] for n in selected])
                put(
                    "pcoeff",
                    phase.transpose(2, 0, 1)[None],
                    ("n_Phase_Elements", "n_Packed_Coefficients", "n_Types", "n_IR_Frequencies"),
                )
            validate_crtm_ir_optical_table(temporary)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        outputs[kind] = str(path)
    mapping = directory / "wavelength_mapping.csv"
    with mapping.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["table_index_1based", "requested_index_1based", "wavelength_um", "wavenumber_cm-1"]
        )
        writer.writerows((i + 1, int(j) + 1, wl[j], 1e4 / wl[j]) for i, j in enumerate(order))
    manifest = {
        "format": "ZJU_CRTM_IR_FIXED_PSD_V1",
        "native_crtm_compatible": False,
        "requested_wavelengths_um": list(wavelengths),
        "table_wavelengths_um": wl[order].tolist(),
        "outputs": {**outputs, "wavelength_mapping": str(mapping)},
        "populations": populations,
        "phase_normalization": phase_normalization,
        "phase_checks": phase_checks,
        "source_report": report,
        "usage": "Adapter required. tau=ke*layer constituent mass [kg/m2]. Fixed PSD/shape/RH/T; scalar phase only.",
    }
    manifest_path = directory / "crtm_ir_manifest.json"
    manifest["outputs"]["manifest"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


@_registration_required
def validate_crtm_ir_optical_table(path):
    """Check our IR-only subset, without implying native CRTM reader acceptance."""
    import numpy as np
    from netCDF4 import Dataset, chartostring

    with Dataset(path) as nc:
        if nc.format_id != "ZJU_CRTM_IR_FIXED_PSD_V1" or nc.native_crtm_compatible != 0:
            raise ValueError("Expected explicitly custom fixed-PSD IR table")
        frequency = nc["Frequency_IR"][:]
        if (
            not np.isfinite(frequency).all()
            or np.any(frequency <= 0)
            or np.any(np.diff(frequency) <= 0)
        ):
            raise ValueError("IR wavenumbers must increase strictly")
        if not np.allclose(nc["Wavelength"][:] * frequency, 1e4):
            raise ValueError("Wavelength/wavenumber mismatch")
        names = [str(n).strip() for n in chartostring(nc["Type_Name"][:])]
        if len(set(names)) != len(names) or any(not n for n in names):
            raise ValueError("Invalid particle names")
        for field, lower, upper in (
            ("ke", 0, np.inf),
            ("w", 0, 1),
            ("g", -1, 1),
            ("Reff", 0, np.inf),
        ):
            array = nc[field][:]
            if not np.isfinite(array).all() or np.any(array < lower) or np.any(array > upper):
                raise ValueError(f"Invalid {field}")
        phase = nc["pcoeff"][:]
        if phase.shape != (1, 39, len(names), len(frequency)) or not np.isfinite(phase).all():
            raise ValueError("Invalid packed scalar phase dimensions/values")
        if not np.allclose(phase[:, [0, 5, 12, 21]], 0.5, atol=0.005, rtol=0) or np.any(
            phase[:, 38] != 0
        ):
            raise ValueError("Invalid phase normalization or padding")
    return {"valid": True, "native_crtm_compatible": False, "species": names}
