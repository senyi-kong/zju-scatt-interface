"""ARTS fixed-population scattering tables and validation."""

from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.io.applications.common import (
    AEROSOL_NAMES,
    HYDROMETEOR_NAMES,
)
from zju_scatt_interface.io.applications.common import (
    input_spectrum as _input_spectrum,
)
from zju_scatt_interface.io.native import (
    arts_arrays_from_bulk,
    arts_output_template,
    read_native_optical_arrays,
    write_native_optical_output,
)


def _arts_solid_angle_integral(phase, angles):
    """ARTS 2.6 AngIntegrate_trapezoid: integrate Z11 sin(theta) in theta."""
    import numpy as np

    theta = np.deg2rad(angles)
    weighted = phase[:, :, :, 0, 0, 0, 0] * np.sin(theta)
    return np.pi * np.sum(np.diff(theta) * (weighted[:, :, 1:] + weighted[:, :, :-1]), axis=-1)


@_registration_required
def validate_arts_bulk_table(path, *, normalization_tolerance=0.01):
    """Validate the SSD tensor schema and integrated Z11 against Cext-Cabs.

    This checks the generated XML; it does not run an ARTS radiance solver.
    """
    import numpy as np

    from zju_scatt_interface.io.native import _validate_native

    arrays = read_native_optical_arrays(path, model="arts2")
    _validate_native(
        arrays,
        arts_output_template(len(arrays["f_grid"]), len(arrays["T_grid"]), len(arrays["za_grid"])),
    )
    for key, value in arrays.items():
        if not isinstance(value, str) and not np.isfinite(value).all():
            raise ValueError(f"ARTS {key} contains nonfinite values")
    integrated = _arts_solid_angle_integral(arrays["pha_mat_data"], arrays["za_grid"])
    scattering = (arrays["ext_mat_data"] - arrays["abs_vec_data"])[:, :, 0, 0, 0]
    if not np.allclose(integrated, scattering, rtol=normalization_tolerance, atol=1e-30):
        raise ValueError("ARTS integrated Z11 disagrees with extinction minus absorption")
    return {
        "valid": True,
        "frequency_count": len(arrays["f_grid"]),
        "temperature_grid_k": arrays["T_grid"].tolist(),
        "angle_count": len(arrays["za_grid"]),
        "native_arts_solver_tested": False,
    }


def _write_vector(path, values):
    root = ET.Element("arts", format="ascii", version="1")
    ET.SubElement(root, "Vector", nelem=str(len(values))).text = (
        "\n" + " ".join(format(float(v), ".17g") for v in values) + "\n"
    )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


@_registration_required
def write_arts_bulk_tables(
    data, output_dir, *, reference_temperature_k=273.15, phase_normalization="error"
):
    """Write ARTS 2.x version-3 SSD XML, one effective element per fixed PSD.

    Cross sections are population beta divided by number density in m^-3.
    The matching ARTS pnd_field must contain total population number density,
    not another PSD integration. RH, shape and size mixture remain fixed.
    Actual configured particle temperature (e.g. ice 220 K) takes precedence;
    reference_temperature_k labels species without a temperature model only.
    Optional angular renormalization scales all six phase elements together;
    it never changes PSD counts or extinction/absorption.
    """
    import numpy as np

    if phase_normalization not in {"error", "renormalize"}:
        raise ValueError("phase_normalization must be error or renormalize")
    if not math.isfinite(reference_temperature_k) or reference_temperature_k <= 0:
        raise ValueError("reference_temperature_k must be finite and positive")
    wavelengths, records, report = _input_spectrum(data)
    wl = np.asarray(wavelengths, dtype=float)
    if (
        wl.ndim != 1
        or not len(wl)
        or not np.isfinite(wl).all()
        or np.any(wl <= 0)
        or len(set(wl)) != len(wl)
    ):
        raise ValueError("Wavelengths must be positive, finite and unique")
    names = {**AEROSOL_NAMES, **HYDROMETEOR_NAMES}
    if set(records) - set(names):
        raise ValueError("Unsupported ARTS particle family")
    selected = [f for f in names if f in records]
    order = np.argsort(299792458 / (wl * 1e-6))
    frequencies = 299792458 / (wl[order] * 1e-6)
    canonical = data if isinstance(data, (str, Path)) else data.scheme
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    root = ET.Element("arts", format="ascii", version="1")
    collection = ET.SubElement(
        root, "Array", type="ArrayOfSingleScatteringData", nelem=str(len(selected))
    )
    outputs, populations, validations, phase_checks = {}, {}, {}, {}
    number_densities = []
    for family in selected:
        name, entry = names[family], report["species"][family]
        number = float(entry["psd"]["number_concentration_cm3"]) * 1e6
        if not math.isfinite(number) or number <= 0:
            raise ValueError("Population number density must be finite and positive")
        if any(
            not math.isclose(float(r["number"]) * 1e6, number, rel_tol=1e-8)
            for r in records[family]
        ):
            raise ValueError("Bulk spectrum and PSD report disagree on number concentration")
        temperature = float(
            entry["effective_parameters"].get("temperature", reference_temperature_k)
        )
        if not math.isfinite(temperature) or temperature <= 0:
            raise ValueError("Particle temperature must be finite and positive")
        arrays = arts_arrays_from_bulk(
            canonical, component=family, number_density_m3=number, temperature_k=temperature
        )
        if len(arrays["T_grid"]) != 1 or not np.allclose(arrays["T_grid"], [temperature]):
            raise ValueError("Expected a single fixed temperature matching the population report")
        phase = arrays["pha_mat_data"]
        integrated = _arts_solid_angle_integral(phase, arrays["za_grid"])
        scattering = (arrays["ext_mat_data"] - arrays["abs_vec_data"])[:, :, 0, 0, 0]
        if np.any(scattering < 0) or not np.isfinite(integrated).all():
            raise ValueError("Invalid scattering cross section or phase integral")
        # Zero scattering must have a zero phase matrix; normalization is then irrelevant.
        if np.any((scattering == 0) & (np.max(np.abs(phase), axis=(2, 3, 4, 5, 6)) != 0)):
            raise ValueError("Zero scattering requires a zero phase matrix")
        if np.any((scattering > 0) & (integrated <= 0)):
            raise ValueError("Positive scattering requires a positive Z11 integral")
        ratio = np.divide(
            integrated, scattering, out=np.ones_like(integrated), where=scattering > 0
        )
        scale = 1 / ratio if phase_normalization == "renormalize" else np.ones_like(ratio)
        if phase_normalization == "error" and np.any(np.abs(ratio - 1) > 0.01):
            raise ValueError("P11 is not normalized; enable explicit angular renormalization")
        arrays["pha_mat_data"] = phase * scale[:, :, None, None, None, None, None]
        description = (
            f"ZJU-SCATT {name}; fixed PSD and shape mixture; per-particle ensemble mean; "
            f"reference population N={number:.17g} m-3; RH and particle temperature fixed. "
            "Use total population number density in pnd_field; do not integrate PSD again."
        )
        template = arts_output_template(len(arrays["f_grid"]), 1, len(arrays["za_grid"]))
        template["variables"]["description"]["data"] = description
        path = directory / f"{name}.xml"
        write_native_optical_output(path, arrays, template, overwrite=True)
        validations[name] = validate_arts_bulk_table(path)
        child = ET.SubElement(collection, "Array", type="SingleScatteringData", nelem="1")
        child.append(ET.parse(path).getroot().find("SingleScatteringData"))
        outputs[name] = str(path)
        populations[name] = {
            "family": family,
            "number_density_m3": number,
            "temperature_grid_k": [temperature],
            "temperature_mode": (
                "fixed configured particle temperature"
                if "temperature" in entry["effective_parameters"]
                else "reference label only; no temperature dependence supplied"
            ),
        }
        phase_checks[name] = {
            "input_integral_over_scattering": ratio[:, 0].tolist(),
            "applied_phase_scale": scale[:, 0].tolist(),
        }
        number_densities.append(number)
    combined = directory / "scat_data.xml"
    ET.ElementTree(root).write(combined, encoding="utf-8", xml_declaration=True)
    outputs["scat_data"] = str(combined)
    for name, values in (("f_grid", frequencies), ("number_density_m3", number_densities)):
        path = directory / f"{name}.xml"
        _write_vector(path, values)
        outputs[name] = str(path)
    mapping = directory / "wavelength_mapping.csv"
    with mapping.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["table_index_1based", "requested_index_1based", "wavelength_um", "frequency_hz"]
        )
        writer.writerows((i + 1, int(j) + 1, wl[j], frequencies[i]) for i, j in enumerate(order))
    outputs["wavelength_mapping"] = str(mapping)
    manifest_path = directory / "arts_manifest.json"
    outputs["manifest"] = str(manifest_path)
    manifest = {
        "format": "ARTS 2.x SingleScatteringData version 3 ASCII XML",
        "species_order": [names[f] for f in selected],
        "requested_wavelengths_um": list(wavelengths),
        "frequency_grid_hz": frequencies.tolist(),
        "outputs": outputs,
        "populations": populations,
        "phase_normalization": phase_normalization,
        "phase_checks": phase_checks,
        "validation": validations,
        "usage": "One fixed-PSD effective scattering element per species; pnd_field in particles/m3. No second PSD integration.",
        "source_report": report,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
