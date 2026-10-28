"""Application-owned native schema, validation and serialization policies."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from zju_scatt_interface.access.registration import registration_required as _registration_required
from zju_scatt_interface.io.native import _increasing, _plain


@_registration_required
def rttov13_aerosol_output_template(
    n_channels,
    species,
    *,
    max_moments=128,
    phase_angles=(),
    solar_channels=(),
    species_naming="rttov",
):
    """Build a complete RTTOV13 SCAER template without a reference file.

    ``species`` maps four-character names to ``relative_humidity`` (percent)
    and ``confac`` ([particles cm^-3]/[g m^-3]). One species uses DATA, multiple
    species use uppercase named groups, as in RTTOV's writer. Required optical
    arrays are ABS/SCA/BPR, NMOM/LEGCOEF and (for solar channels) PHA, keyed by
    full dataset path. ABS/SCA must be per 1 particle/cm³, not raw bulk beta.
    BPR is the Chou backscattering parameter, not (1-g)/2.
    species_naming='descriptive' explicitly uses full lowercase names and
    sufficiently wide strings; this extension requires a modified RTTOV reader.
    """
    import numpy as np

    if species_naming not in {"rttov", "descriptive"}:
        raise ValueError("species_naming must be rttov or descriptive")
    if species_naming == "rttov":
        if not species or any(len(n) != 4 or not n.isascii() or not n.isalnum() for n in species):
            raise ValueError("species names must contain exactly four ASCII letters/digits")
    elif not species or any(
        not n
        or not n.isascii()
        or n != n.lower()
        or not n[0].isalpha()
        or not n.replace("_", "").isalnum()
        for n in species
    ):
        raise ValueError(
            "descriptive species names must use lowercase ASCII letters, digits and underscores"
        )
    if len({n.upper() for n in species}) != len(species):
        raise ValueError("species names must be unique ignoring case")
    variables = {}

    def add(name, shape, *, data=None, dtype="float64", units=None, bounds=True):
        attrs = {}
        if bounds:
            attrs.update(LBOUND=[1] * len(shape), UBOUND=list(shape[::-1]))
        if units:
            attrs["UNITS"] = units
        spec = {"shape": list(shape), "dtype": dtype, "attributes": attrs}
        spec.update({"source": name} if data is None else {"data": _plain(data)})
        variables[name] = spec

    root = "SCAER"
    for key, value in {
        "VERSION": 1,
        "ID": 2,
        "NCHAN": n_channels,
        "NTYPES": len(species),
        "MAXNMOM": max_moments,
        "NCHAN_PHA": len(solar_channels),
        "NPHANGLE": len(phase_angles),
    }.items():
        add(f"{root}/{key}", (1,), data=[value], dtype="int32", bounds=False)
    if len(species) > 1:
        width = 4 if species_naming == "rttov" else max(len(n) for n in species)
        add(root + "/NAMES", (len(species),), data=list(species), dtype=f"S{width}")
    if len(solar_channels):
        add(root + "/CHAN_PHA", (len(solar_channels),), data=solar_channels, dtype="int32")
        add(root + "/PHANGLE", (len(phase_angles),), data=phase_angles)
    for name, spec in species.items():
        group_name = name.upper() if species_naming == "rttov" else name
        base = root + "/" + (group_name if len(species) > 1 else "DATA")
        rh = np.asarray(spec["relative_humidity"])
        for key, value in {"NRELHUM": len(rh), "NDEFF": 1}.items():
            add(base + "/" + key, (1,), data=[value], dtype="int32", bounds=False)
        add(base + "/RELHUM", (len(rh),), data=rh, units="percent")
        add(base + "/DEFF", (1,), data=[0.0], units="microns")
        add(
            base + "/CONFAC",
            (1,),
            data=[spec["confac"]],
            units="[particle.cm^-3]/[g.m^-3]",
            bounds=False,
        )
        shape = (n_channels, 1, len(rh))
        for key in ("ABS", "SCA", "BPR"):
            add(base + "/" + key, shape, units="m-1" if key != "BPR" else None)
        add(base + "/NMOM", (n_channels, len(rh)), dtype="int32")
        add(base + "/LEGCOEF", shape + (max_moments + 1,))
        if len(solar_channels):
            add(base + "/PHA", (len(solar_channels), 1, len(rh), len(phase_angles)))
    template = {"schema_version": 1, "model": "rttov13", "format": "hdf5", "variables": variables}
    if species_naming == "descriptive":
        template["aerosol_variant"] = "descriptive"
    return template


def _validate_rttov(arrays, template):
    import numpy as np

    if template.get("format") != "hdf5":
        raise ValueError("RTTOV13 preset requires HDF5")
    roots = [k[:-8] for k in arrays if k.endswith("/VERSION")]
    if not roots or any(not (r == "SCAER" or r.startswith("SCCLD/")) for r in roots):
        raise ValueError("RTTOV13 requires SCAER or SCCLD optical-property groups")
    cloud_variant = template.get("cloud_variant", "standard")
    aerosol_variant = template.get("aerosol_variant", "standard")
    if aerosol_variant not in {"standard", "descriptive"}:
        raise ValueError("Unknown RTTOV13 aerosol layout variant")
    if cloud_variant not in {"standard", "zju_ice", "zju_clouds"}:
        raise ValueError("Unknown RTTOV13 cloud layout variant")
    ice_group = "ICE_CLOUD_BAUM" if cloud_variant == "standard" else "ICE_CLOUD_ZJU_SUPER_SPHEROID"
    water_group = "WATER_CLOUD_ZJU_GAMMA" if cloud_variant == "zju_clouds" else "WATER_CLOUD_DEFF"
    if any(r.startswith("SCCLD/") for r in roots) and set(roots) != {
        "SCCLD/" + ice_group,
        "SCCLD/" + water_group,
        "SCCLD/WATER_CLOUD_OPAC",
    }:
        raise ValueError("RTTOV13 cloud files require all three cloud optical-property groups")
    for root in roots:

        def scalar(name):
            a = arrays[f"{root}/{name}"]
            if a.shape != (1,) or a.dtype.kind != "i" or a.dtype.itemsize != 4:
                raise ValueError(f"RTTOV {root}/{name} requires a one-element int32 array")
            return int(a[0])

        if scalar("VERSION") != 1:
            raise ValueError("only RTTOV13 optical-property format VERSION=1 is supported")
        nc, ns, na, nm, nt = [
            scalar(k) for k in ("NCHAN", "NCHAN_PHA", "NPHANGLE", "MAXNMOM", "NTYPES")
        ]
        scalar("ID")
        if nc <= 0 or nt <= 0 or ns < 0 or ns > nc or nm < 0:
            raise ValueError("RTTOV invalid channel/type/moment counts")
        names = arrays.get(root + "/NAMES")
        if names is None:
            if nt != 1:
                raise ValueError("RTTOV multi-species group requires NAMES")
            species = ["DATA"]
        else:
            if names.shape != (nt,):
                raise ValueError("RTTOV NAMES count does not match NTYPES")
            species = [str(_plain(n)).strip() for n in names]
            if not (root == "SCAER" and aerosol_variant == "descriptive"):
                species = [n.upper() for n in species]
        if ns:
            channels = arrays[root + "/CHAN_PHA"]
            if (
                channels.shape != (ns,)
                or np.any(channels < 1)
                or np.any(channels > nc)
                or len(np.unique(channels)) != ns
            ):
                raise ValueError("RTTOV CHAN_PHA must contain unique 1-based channel indexes")
            angles = arrays[root + "/PHANGLE"]
            _increasing(angles, "PHANGLE")
            if angles.shape != (na,) or angles[0] != 0 or angles[-1] != 180:
                raise ValueError("RTTOV PHANGLE must span 0..180 degrees")
        for species_name in species:
            base = f"{root}/{species_name}"
            nr = int(arrays[base + "/NRELHUM"][0])
            nd = int(arrays[base + "/NDEFF"][0])
            if nr < 1 or nd < 1:
                raise ValueError("RTTOV requires nonempty RH and diameter grids")
            rh, deff = arrays[base + "/RELHUM"], arrays[base + "/DEFF"]
            _increasing(rh, "RELHUM")
            _increasing(deff, "DEFF")
            if (
                rh.shape != (nr,)
                or np.any((rh < 0) | (rh > 99))
                or deff.shape != (nd,)
                or np.any(deff < 0)
            ):
                raise ValueError("RTTOV invalid RELHUM/DEFF grids")
            expected = {
                "ABS": (nc, nd, nr),
                "SCA": (nc, nd, nr),
                "BPR": (nc, nd, nr),
                "CONFAC": (1,),
            }
            if nm:
                expected.update(LEGCOEF=(nc, nd, nr, nm + 1), NMOM=(nc, nr))
            if ns:
                expected["PHA"] = (ns, nd, nr, na)
            for key, shape in expected.items():
                a = arrays[base + "/" + key]
                if a.shape != shape:
                    raise ValueError(f"RTTOV {base}/{key}: expected {shape}, got {a.shape}")
            for key in ("ABS", "SCA", "CONFAC"):
                if np.any(arrays[base + "/" + key] < 0):
                    raise ValueError(f"RTTOV {key} must be nonnegative")
            if np.any((arrays[base + "/BPR"] < 0) | (arrays[base + "/BPR"] > 1)):
                raise ValueError("RTTOV BPR must be in [0, 1]")
            if nm and np.any((arrays[base + "/NMOM"] < 0) | (arrays[base + "/NMOM"] > nm)):
                raise ValueError("RTTOV NMOM exceeds MAXNMOM")
    for name, value in arrays.items():
        attrs = template["variables"][name].get("attributes", {})
        if "LBOUND" in attrs and "UBOUND" in attrs:
            extent = np.asarray(attrs["UBOUND"]) - np.asarray(attrs["LBOUND"]) + 1
            if tuple(extent[::-1]) != value.shape:
                raise ValueError(f"RTTOV {name}: Fortran bounds disagree with disk shape")


def read_arrays(path):
    import h5py

    result = {}
    with h5py.File(path) as handle:

        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                result[name] = obj[()]

        handle.visititems(visit)
    return result


def reference_template(path):
    model = "rttov13"
    path = Path(path)
    result = {
        "schema_version": 1,
        "model": model,
        "attributes": {},
        "dimensions": {},
        "groups": {},
        "variables": {},
    }
    import h5py

    result["format"] = "hdf5"
    with h5py.File(path) as handle:
        if "SCCLD/WATER_CLOUD_ZJU_GAMMA" in handle:
            result["cloud_variant"] = "zju_clouds"
        elif "SCCLD/ICE_CLOUD_ZJU_SUPER_SPHEROID" in handle:
            result["cloud_variant"] = "zju_ice"
        if "SCAER/NAMES" in handle:
            species_names = [str(_plain(n)).strip() for n in handle["SCAER/NAMES"][()]]
            if any((n != n.upper() for n in species_names)) and all(
                (n in handle["SCAER"] for n in species_names)
            ):
                result["aerosol_variant"] = "descriptive"
        result["attributes"] = {k: _plain(v) for (k, v) in handle.attrs.items()}

        def visit(name, obj):
            attrs = {k: _plain(v) for (k, v) in obj.attrs.items()}
            if isinstance(obj, h5py.Group):
                result["groups"][name] = attrs
            else:
                result["variables"][name] = {
                    "source": name,
                    "shape": list(obj.shape),
                    "dtype": obj.dtype.str,
                    "attributes": attrs,
                }

        handle.visititems(visit)
    return result


def bulk_fields(bulk, *, mass_concentration_kg_m3=None, number_density_m3=None):
    from zju_scatt_interface.io.applications.common import normalized_bulk_coefficients

    ext, sca, absorption = normalized_bulk_coefficients(bulk, number_density_m3)
    return {"ABS": absorption * 1e6, "SCA": sca * 1e6}


def encode_attribute(key, value):
    if isinstance(value, str):
        return np.bytes_(value)
    if key in {"LBOUND", "UBOUND"}:
        return np.asarray(value, dtype="int32")
    return value
