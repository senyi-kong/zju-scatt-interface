"""Application-owned native schema, validation and serialization policies."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from zju_scatt_interface.access.registration import registration_required as _registration_required
from zju_scatt_interface.io.native import _increasing, _plain

_CRTM_COORDS = {
    "Frequency_MW": "n_MW_Frequencies",
    "Frequency_IR": "n_IR_Frequencies",
    "Reff_MW": "n_MW_Radii",
    "Reff_IR": "n_IR_Radii",
    "Temperature": "n_Temperatures",
    "Density": "n_Densities",
}
_CRTM_AXES = {
    "L_MW": ("n_Temperatures", "n_MW_Radii", "n_MW_Frequencies"),
    "S_MW": ("n_Densities", "n_MW_Radii", "n_MW_Frequencies"),
    "IR": ("n_IR_Densities", "n_IR_Radii", "n_IR_Frequencies"),
}


@_registration_required
def crtm_cloud_output_template(dimensions, *, binary=False, byte_order="little", version=1):
    """CRTM CloudCoeff release 3 (CRTM 2.4), NetCDF or sequential binary.

    n_Legendre_Terms is the stored dimension length (39 in the official table),
    NOT maximum degree. CRTM packs stream sets at offsets 0, 0, 5, 12, 21.
    Callers must supply that packing; ordinary consecutive moments are invalid.
    """
    variables = {}
    units = {
        "Frequency_MW": "GigaHertz (GHz)",
        "Frequency_IR": "Inverse centimetres (cm^-1)",
        "Reff_MW": "Microns (um)",
        "Reff_IR": "Microns (um)",
        "Temperature": "Kelvin (K)",
        "Density": "Kilograms per cubic metre (kg.m^-3)",
    }
    for name, dimension in _CRTM_COORDS.items():
        variables[name] = {
            "source": name,
            "dtype": "float64",
            "dimensions": [dimension],
            "attributes": {"units": units[name]},
        }
    for block, axes in _CRTM_AXES.items():
        for prefix in ("ke", "w", "g", "pcoeff"):
            name = f"{prefix}_{block}"
            dims = list(axes)
            if prefix == "pcoeff":
                dims = (["n_Phase_Elements"] if block != "IR" else []) + ["n_Legendre_Terms"] + dims
            variables[name] = {
                "source": name,
                "dtype": "float64",
                "dimensions": dims,
                "attributes": {
                    "units": "Metres squared per kilogram (m^2.kg^-1)" if prefix == "ke" else "N/A"
                },
            }
    return {
        "schema_version": 1,
        "model": "crtm-cloud-v3",
        "format": "crtm-binary" if binary else "netcdf3",
        "byte_order": byte_order,
        "dimensions": dict(dimensions),
        "attributes": {"Release": 3, "Version": version},
        "variables": variables,
    }


def _validate_crtm(arrays, template):
    import numpy as np

    dims = template["dimensions"]
    if template.get("format") not in {"netcdf3", "netcdf4", "crtm-binary"}:
        raise ValueError("CRTM CloudCoeff requires NetCDF or crtm-binary")
    if template["attributes"].get("Release") != 3:
        raise ValueError("only CRTM CloudCoeff Release=3 is supported")
    expected = crtm_cloud_output_template(dims)
    if set(arrays) != set(expected["variables"]):
        raise ValueError("CRTM requires all six coordinate and twelve optical variables")
    if dims["n_IR_Densities"] != dims["n_Densities"] + 1:
        raise ValueError("CRTM n_IR_Densities must equal n_Densities + 1")
    if dims["n_Legendre_Terms"] != 39:
        raise ValueError("CRTM release-3 stream-set packing requires 39 stored phase coefficients")
    for name, spec in expected["variables"].items():
        if template["variables"][name].get("dimensions") != spec["dimensions"]:
            raise ValueError(f"CRTM {name}: wrong dimension names/order")
        if arrays[name].dtype.kind != "f" or arrays[name].dtype.itemsize != 8:
            raise ValueError(f"CRTM {name}: requires float64")
    for name in _CRTM_COORDS:
        _increasing(arrays[name], name, positive=True)
    for block in _CRTM_AXES:
        if np.any(arrays[f"ke_{block}"] < 0):
            raise ValueError("CRTM mass extinction must be nonnegative")
        if np.any((arrays[f"w_{block}"] < 0) | (arrays[f"w_{block}"] > 1)):
            raise ValueError("CRTM single scattering albedo must be in [0, 1]")
        if np.any(np.abs(arrays[f"g_{block}"]) > 1):
            raise ValueError("CRTM asymmetry must be in [-1, 1]")


def _write_crtm_binary(path, arrays, template):
    import numpy as np

    order = template.get("byte_order", "little")
    if order not in {"little", "big"}:
        raise ValueError("byte_order must be little or big")
    endian = "<" if order == "little" else ">"
    dims = template["dimensions"]
    dim_names = [
        "n_MW_Frequencies",
        "n_MW_Radii",
        "n_IR_Frequencies",
        "n_IR_Radii",
        "n_Temperatures",
        "n_Densities",
        "n_Legendre_Terms",
        "n_Phase_Elements",
    ]
    sizes = [dims[k] - (1 if k == "n_Legendre_Terms" else 0) for k in dim_names]
    with open(path, "wb") as handle:

        def record(payload):
            marker = struct.pack(endian + "i", len(payload))
            handle.write(marker + payload + marker)

        record(struct.pack(endian + "i", 123456789))  # Binary_File_Utility endian sentinel.
        record(struct.pack(endian + "2i", 3, int(template["attributes"]["Version"])))
        record(struct.pack(endian + "8i", *sizes))
        for names in [list(_CRTM_COORDS)] + [
            [f"{p}_{b}" for p in ("ke", "w", "g", "pcoeff")] for b in _CRTM_AXES
        ]:
            # C-order disk axes are reversed Fortran axes: the byte order agrees.
            record(
                b"".join(
                    np.asarray(arrays[n], dtype=endian + "f8").tobytes(order="C") for n in names
                )
            )


def read_arrays(path):
    from netCDF4 import Dataset

    with Dataset(path) as handle:
        handle.set_auto_maskandscale(False)
        return {k: np.asarray(v[:]) for (k, v) in handle.variables.items()}


def reference_template(path):
    model = "crtm-cloud-v3"
    path = Path(path)
    result = {
        "schema_version": 1,
        "model": model,
        "attributes": {},
        "dimensions": {},
        "groups": {},
        "variables": {},
    }
    from netCDF4 import Dataset

    with Dataset(path) as handle:
        result["format"] = "netcdf3"
        result["attributes"] = {k: _plain(handle.getncattr(k)) for k in handle.ncattrs()}
        result["dimensions"] = {k: len(v) for (k, v) in handle.dimensions.items()}
        for name, var in handle.variables.items():
            result["variables"][name] = {
                "source": name,
                "dimensions": list(var.dimensions),
                "dtype": var.dtype.str,
                "attributes": {k: _plain(var.getncattr(k)) for k in var.ncattrs()},
            }
    return result


def bulk_fields(bulk, *, mass_concentration_kg_m3=None, number_density_m3=None):
    from zju_scatt_interface.io.applications.common import normalized_bulk_coefficients

    ext, sca, absorption = normalized_bulk_coefficients(bulk, mass_concentration_kg_m3)
    if bulk.asymmetry_factor is None:
        raise ValueError("CRTM requires asymmetry_factor")
    return {"ke": ext, "w": sca / ext if ext else 0.0, "g": float(bulk.asymmetry_factor)}
