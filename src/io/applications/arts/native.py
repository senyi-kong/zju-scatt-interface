"""Application-owned native schema, validation and serialization policies."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from zju_scatt_interface.access.registration import registration_required as _registration_required
from zju_scatt_interface.io.native import _increasing

_ARTS_NAMES = (
    "ptype",
    "description",
    "f_grid",
    "T_grid",
    "za_grid",
    "aa_grid",
    "pha_mat_data",
    "ext_mat_data",
    "abs_vec_data",
)
_TENSOR_AXES = ("nlibraries", "nvitrines", "nshelves", "nbooks", "npages", "nrows", "ncols")


@_registration_required
def arts_output_template(n_frequency, n_temperature, n_angle):
    """ARTS 2.x SSD version 3, totally random orientation, six phase elements."""
    shapes = [
        (n_frequency,),
        (n_temperature,),
        (n_angle,),
        (0,),
        (n_frequency, n_temperature, n_angle, 1, 1, 1, 6),
        (n_frequency, n_temperature, 1, 1, 1),
        (n_frequency, n_temperature, 1, 1, 1),
    ]
    variables = {
        name: {"source": name, "shape": list(shape), "dtype": "float64"}
        for name, shape in zip(_ARTS_NAMES[2:], shapes)
    }
    variables["ptype"] = {"data": "totally_random", "dtype": "string"}
    variables["description"] = {"data": "ZJU-SCATT optical properties", "dtype": "string"}
    variables["aa_grid"]["data"] = []
    del variables["aa_grid"]["source"]
    return {"schema_version": 1, "model": "arts2", "format": "arts-xml", "variables": variables}


@_registration_required
def arts_arrays_from_bulk(data, *, component, number_density_m3, temperature_k=None):
    """Convert canonical bulk results to per-particle ARTS arrays.

    Bulk beta is m^-1, number density is m^-3; extinction/absorption become m².
    Canonical P integrates to 4π: Z = P * beta_sca / (4π * number_density).
    Z34 = -P43 * beta_sca / (4π * number_density). Only wavelength and
    temperature dimensions are accepted; select size/species grids beforehand.
    """
    import numpy as np

    from zju_scatt_interface.io.tables import bulk_output_records

    records = [
        r for r in bulk_output_records(data, include_phase=True) if r["component"] == component
    ]
    if not records:
        raise ValueError(f"no canonical records for component {component!r}")
    frequencies = sorted({299792458.0 / (float(r["wavelength_um"]) * 1e-6) for r in records})
    temperatures = (
        sorted({float(r.get("temperature", temperature_k)) for r in records})
        if (temperature_k is not None or all("temperature" in r for r in records))
        else []
    )
    if not temperatures:
        raise ValueError(
            "temperature_k is required when the canonical product has no temperature axis"
        )
    angles = sorted({float(r["sca_angle"]) for r in records})
    shape = (len(frequencies), len(temperatures))
    density = np.broadcast_to(np.asarray(number_density_m3, dtype=float), shape)
    if not np.isfinite(density).all() or np.any(density <= 0):
        raise ValueError("number_density_m3 must be finite and positive")
    phase = np.empty(shape + (len(angles), 1, 1, 1, 6))
    ext, absorption = np.empty(shape + (1, 1, 1)), np.empty(shape + (1, 1, 1))
    seen = set()
    for r in records:
        i = frequencies.index(299792458.0 / (float(r["wavelength_um"]) * 1e-6))
        j = temperatures.index(float(r.get("temperature", temperature_k)))
        k = angles.index(float(r["sca_angle"]))
        if (i, j, k) in seen:
            raise ValueError(
                "select extra canonical dimensions before ARTS export; duplicate grid point"
            )
        seen.add((i, j, k))
        ext[i, j, 0, 0, 0] = float(r["beta_ext"]) / density[i, j]
        absorption[i, j, 0, 0, 0] = float(r["beta_abs"]) / density[i, j]
        for m, name in enumerate(("p11", "p12", "p22", "p33", "p43", "p44")):
            if name not in r:
                raise ValueError(f"ARTS requires all six phase elements; missing {name}")
            phase[i, j, k, 0, 0, 0, m] = (
                float(r[name])
                * (-1 if name == "p43" else 1)
                * float(r["beta_sca"])
                / (4 * np.pi * density[i, j])
            )
    if len(seen) != len(frequencies) * len(temperatures) * len(angles):
        raise ValueError("ARTS requires a complete rectangular frequency/temperature/angle grid")
    return {
        "f_grid": np.asarray(frequencies),
        "T_grid": np.asarray(temperatures),
        "za_grid": np.asarray(angles),
        "aa_grid": np.array([]),
        "ptype": "totally_random",
        "description": f"ZJU-SCATT {component}",
        "pha_mat_data": phase,
        "ext_mat_data": ext,
        "abs_vec_data": absorption,
    }


def read_arrays(path):
    root = ET.parse(path).getroot()
    if root.tag != "arts" or root.get("format") != "ascii":
        raise ValueError("requires an ASCII ARTS XML file")
    node = root.find("SingleScatteringData")
    if node is None or node.get("version") != "3" or len(node) != 9:
        raise ValueError("requires one version-3 SingleScatteringData object")
    result = {}
    for name, item in zip(_ARTS_NAMES, node):
        if item.tag == "String":
            result[name] = (item.text or "").strip().strip('"')
        else:
            axes = ("nelem",) if item.tag == "Vector" else _TENSOR_AXES[-int(item.tag[6:]) :]
            shape = tuple((int(item.attrib[k]) for k in axes))
            result[name] = np.fromstring((item.text or "").strip(), sep=" ").reshape(shape)
    return result


def reference_template(path):
    path = Path(path)
    arrays = read_arrays(path)
    result = arts_output_template(
        arrays["f_grid"].size, arrays["T_grid"].size, arrays["za_grid"].size
    )
    for name in ("ptype", "description"):
        result["variables"][name]["data"] = arrays[name]
    return result


def validate_arrays(arrays, template):
    if template.get("format") != "arts-xml":
        raise ValueError("ARTS preset requires arts-xml format")
    if set(arrays) != set(_ARTS_NAMES) or arrays["ptype"] != "totally_random":
        raise ValueError("ARTS preset requires the nine SSD fields and totally_random orientation")
    for name in ("f_grid", "T_grid", "za_grid"):
        _increasing(arrays[name], name, positive=name != "za_grid")
    if arrays["za_grid"][0] != 0 or arrays["za_grid"][-1] != 180:
        raise ValueError("ARTS za_grid must span 0 to 180 degrees")
    expected = arts_output_template(
        len(arrays["f_grid"]), len(arrays["T_grid"]), len(arrays["za_grid"])
    )
    for name in _ARTS_NAMES[2:]:
        if arrays[name].shape != tuple(expected["variables"][name]["shape"]):
            raise ValueError(f"ARTS {name}: invalid tensor dimensions")
    if np.any(arrays["abs_vec_data"] < 0) or np.any(
        arrays["ext_mat_data"] < arrays["abs_vec_data"]
    ):
        raise ValueError("ARTS requires 0 <= absorption <= extinction")
    if np.any(arrays["pha_mat_data"][..., 0] < 0):
        raise ValueError("ARTS Z11 must be nonnegative")


def serialize_xml(path, arrays, template):
    root = ET.Element("arts", format="ascii", version="1")
    node = ET.SubElement(root, "SingleScatteringData", version="3")
    for name in _ARTS_NAMES:
        value = arrays[name]
        if isinstance(value, str):
            if '"' in value:
                raise ValueError("ARTS strings cannot contain embedded double quotes")
            ET.SubElement(node, "String").text = f'"{value}"'
        else:
            axes = ("nelem",) if value.ndim == 1 else _TENSOR_AXES[-value.ndim :]
            tag = "Vector" if value.ndim == 1 else f"Tensor{value.ndim}"
            item = ET.SubElement(node, tag, dict(zip(axes, map(str, value.shape))))
            item.text = "\n" + " ".join((format(float(x), ".17g") for x in value.flat)) + "\n"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def bulk_fields(bulk, *, mass_concentration_kg_m3=None, number_density_m3=None):
    from zju_scatt_interface.io.applications.common import normalized_bulk_coefficients

    ext, sca, absorption = normalized_bulk_coefficients(bulk, number_density_m3)
    return {"ext_mat_data": ext, "abs_vec_data": absorption, "phase_scale": sca / (4 * math.pi)}
