"""io / applications / rttov / v14 domain implementation."""

from __future__ import annotations

import csv
import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.io.applications.common import AEROSOL_NAMES, HYDROMETEOR_NAMES
from zju_scatt_interface.io.applications.common import characters as _characters
from zju_scatt_interface.io.applications.common import input_spectrum as _input_spectrum
from zju_scatt_interface.io.native import scalar_phase_to_model

TABLE_DIMS = ("dim_id_4", "dim_id_3", "dim_id_2", "dim_id_1", "nwvn")


def _write_table(path, root_name, wavelengths, types, max_moments):
    import numpy as np
    from netCDF4 import Dataset

    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with Dataset(temporary, "w", format="NETCDF4") as nc:
            nc.title = "ZJU-SCATT custom RTTOV14 optical properties"
            table = nc.createGroup(root_name)
            for name, size in {
                "nchan": len(wavelengths),
                "nwvn": len(wavelengths),
                "nchan_pha": 0,
                "ntypes": len(types),
                "maxnmom_dim": max_moments + 1,
                "table_max_dim": 4,
                "date_dim": 3,
                "str_name_dim": 32,
                "str_readme_dim": 132,
                "readme_dim": 100,
            }.items():
                table.createDimension(name, size)

            def put(group, name, values, dtype="i4", dims=(), units=None):
                variable = group.createVariable(name, dtype, dims)
                variable[...] = values
                if units:
                    variable.units = units

            for name, value in {
                "version": 4,
                "id": 0,
                "maxnmom": max_moments,
                "has_asym": 1,
                "has_bpr": 1,
                "has_zef": 0,
            }.items():
                put(table, name, value)
            date = datetime.now(ZoneInfo("Asia/Shanghai"))
            put(table, "creation_date", [date.year, date.month, date.day], dims=("date_dim",))
            notes = [
                "ZJU-SCATT custom fixed-population thermal-IR optical properties.",
                "Monochromatic channel samples; gas coefficient channels must match in count/order.",
                "Aerosol profiles: mmr_aer=False, number concentration in cm^-3.",
                "Hydrometeor profiles: mmr_hydro=False, mass concentration in g m^-3.",
                "Fixed PSD/shape/RH/temperature assumptions are recorded in the external report.",
            ]
            put(
                table,
                "readme_opt_prop",
                _characters(notes + [""] * (100 - len(notes)), 132),
                "S1",
                ("readme_dim", "str_readme_dim"),
            )
            put(table, "names", _characters(list(types), 32), "S1", ("ntypes", "str_name_dim"))
            for name, item in types.items():
                group = table.createGroup(name)
                for dim in (
                    "dim_id_1",
                    "dim_id_2",
                    "dim_id_3",
                    "dim_id_4",
                    "nrelhum",
                    "ndeff",
                    "ntemperature",
                    "npartial_mass_density",
                ):
                    group.createDimension(dim, 1)
                put(group, "is_frozen", int(item["is_frozen"]))
                put(group, "confac", 0.0, "f8")
                for key, value in (
                    ("dim_type", [0] * 4),
                    ("dim_size", [1] * 4),
                    ("dim_interp", [0] * 4),
                ):
                    put(group, key, value, dims=("table_max_dim",))
                for key in ("ext", "ssa", "asym", "bpr"):
                    put(
                        group,
                        key,
                        np.asarray(item[key]).reshape(1, 1, 1, 1, -1),
                        "f4",
                        TABLE_DIMS,
                        units=(
                            "km-1 per particle cm-3"
                            if root_name == "aertable"
                            else "km-1 per g m-3"
                        )
                        if key == "ext"
                        else "1",
                    )
                put(group, "nmom", [max_moments] * len(wavelengths), dims=("nwvn",))
                put(
                    group,
                    "lcoef",
                    np.asarray(item["lcoef"]).reshape(
                        1, 1, 1, 1, len(wavelengths), max_moments + 1
                    ),
                    "f4",
                    TABLE_DIMS + ("maxnmom_dim",),
                )
        validate_rttov14_optical_table(temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()  # One explicitly named temporary file.


@_registration_required
def validate_rttov14_optical_table(path):
    """Validate the emitted fixed-population RTTOV14 version-4 subset."""
    import numpy as np
    from netCDF4 import Dataset, chartostring

    with Dataset(path) as nc:
        if len(nc.groups) != 1 or not set(nc.groups) <= {"aertable", "hydrotable"}:
            raise ValueError("Expected one aertable or hydrotable root group")
        table = next(iter(nc.groups.values()))
        if int(table["version"][...]) != 4 or int(table["id"][...]) != 0:
            raise ValueError("Expected version=4 and user table id=0")
        names = [str(s).strip() for s in chartostring(table["names"][:])]
        if len(names) != len(set(names)) or set(names) != set(table.groups):
            raise ValueError("Particle names/groups disagree or are truncated")
        channels = len(table.dimensions["nchan"])
        moments = int(table["maxnmom"][...])
        if channels <= 0 or len(table.dimensions["nwvn"]) != channels:
            raise ValueError("Expected one optical table per channel")
        for name in names:
            group = table[name]
            if list(group["dim_type"][:]) != [0] * 4 or list(group["dim_size"][:]) != [1] * 4:
                raise ValueError("Expected fixed-population singleton dimensions")
            for field in ("ext", "ssa", "asym", "bpr"):
                variable = group[field]
                values = variable[:]
                if variable.dimensions != TABLE_DIMS or values.shape != (1, 1, 1, 1, channels):
                    raise ValueError(f"Wrong Fortran/NetCDF axis order for {name}/{field}")
                if not np.isfinite(values).all():
                    raise ValueError(f"Nonfinite {field}")
                lower, upper = (
                    (0, np.inf) if field == "ext" else (-1, 1) if field == "asym" else (0, 1)
                )
                if np.any(values < lower) or np.any(values > upper):
                    raise ValueError(f"Invalid range for {field}")
            if (
                group["lcoef"].dimensions != TABLE_DIMS + ("maxnmom_dim",)
                or group["lcoef"].shape != (1, 1, 1, 1, channels, moments + 1)
                or not np.isfinite(group["lcoef"][:]).all()
                or list(group["nmom"][:]) != [moments] * channels
            ):
                raise ValueError("Invalid Legendre coefficient storage")
    return {
        "passed": True,
        "path": str(path),
        "species": names,
        "channels": channels,
        "schema_version": 4,
        "compiled_rttov_reader_tested": False,
    }


@_registration_required
def write_rttov14_bulk_tables(
    data,
    directory,
    *,
    max_moments=32,
    water_density_kg_m3=1000.0,
    ice_density_kg_m3=917.0,
    phase_normalization="preserve",
):
    """Write native RTTOV14 NetCDF aertable/hydrotable files for all eight types.

    data is a BulkTableResult, or its canonical bulk NetCDF path (with sibling
    report.json). PSD counts stay fixed. Model ext is km^-1 per particle/cm^3
    for aerosols and km^-1 per g/m^3 for clouds. Native version-4 user tables
    support full species names without reader renaming. They still require
    matching gas-coefficient channels and appropriate profile concentrations.
    """
    import numpy as np

    if (
        isinstance(max_moments, bool)
        or not isinstance(max_moments, int)
        or not 1 <= max_moments <= 255
    ):
        raise ValueError("max_moments must be an integer from 1 to 255")
    if phase_normalization not in {"preserve", "renormalize"}:
        raise ValueError("phase_normalization must be preserve or renormalize")
    if any(not math.isfinite(x) or x <= 0 for x in (water_density_kg_m3, ice_density_kg_m3)):
        raise ValueError("Cloud densities must be positive and finite")
    wavelengths, records, report = _input_spectrum(data)
    if not wavelengths or any(not math.isfinite(w) or w < 3 for w in wavelengths):
        raise ValueError("This exporter requires thermal-IR wavelengths >=3 um")
    if set(records) != set(AEROSOL_NAMES) | set(HYDROMETEOR_NAMES):
        raise ValueError("Expected all eight particle types")
    tables = {
        "aertable": dict.fromkeys(AEROSOL_NAMES.values()),
        "hydrotable": dict.fromkeys(HYDROMETEOR_NAMES.values()),
    }
    populations, phase_checks = {}, {}
    for family, spectrum in records.items():
        psd = report["species"][family]["psd"]
        number = float(psd["number_concentration_cm3"])
        if not math.isfinite(number) or number <= 0:
            raise ValueError("PSD number concentration must be positive")
        is_aerosol = family in AEROSOL_NAMES
        mass = None
        if not is_aerosol:
            density = water_density_kg_m3 if family == "sphere_water_cloud" else ice_density_kg_m3
            mass = (
                sum(n * (r * 1e-6) ** 3 for r, n in zip(psd["size"], psd["dndr"]))
                * (4 * math.pi / 3)
                * density
                * 1e9
            )
            if not math.isfinite(mass) or mass <= 0:
                raise ValueError("Cloud mass concentration must be positive")
        populations[family] = {"number_concentration_cm3": number, "mass_concentration_g_m3": mass}
        item = {
            "is_frozen": family == "super_spheroid_ice",
            "ext": [],
            "ssa": [],
            "asym": [],
            "bpr": [],
            "lcoef": [],
        }
        phase_checks[family] = []
        for wavelength, row in zip(wavelengths, spectrum):
            if not math.isclose(row["number"], number, rel_tol=1e-10):
                raise ValueError("Bulk and PSD number concentrations disagree")
            angles, phase = np.asarray(row["angles"]), np.asarray(row["p11"])
            mu, reverse = np.cos(np.deg2rad(angles))[::-1], phase[::-1]
            integral = float(np.sum(np.diff(mu) * (reverse[1:] + reverse[:-1]) / 4))
            if not math.isfinite(integral) or integral <= 0:
                raise ValueError("Invalid P11 half-integral")
            scale = 1 / integral if phase_normalization == "renormalize" else 1.0
            projected = scalar_phase_to_model(
                angles,
                phase * scale,
                model="rttov14",
                max_moments=max_moments,
                quadrature_points=max(512, 2 * max_moments + 1),
            )
            phase_checks[family].append(
                {
                    "wavelength_um": wavelength,
                    "input_half_integral": integral,
                    "applied_phase_scale": scale,
                }
            )
            item["ext"].append(row["ext"] * 1000 / (number if is_aerosol else mass))
            item["ssa"].append(row["ssa"])
            item["asym"].append(row["g"])
            item["bpr"].append(projected["BPR"])
            item["lcoef"].append(projected["LEGCOEF"])
        root = "aertable" if is_aerosol else "hydrotable"
        name = (AEROSOL_NAMES if is_aerosol else HYDROMETEOR_NAMES)[family]
        tables[root][name] = item
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    paths, validation = {}, {}
    for root, types in tables.items():
        path = output / f"rttov_{root}_zju_default.nc"
        _write_table(path, root, wavelengths, types, max_moments)
        paths[root] = str(path)
        validation[root] = validate_rttov14_optical_table(path)
    with (output / "channel_wavelengths.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["table_channel_index", "wavelength_um", "wavenumber_cm-1"])
        writer.writerows((i, w, 1e4 / w) for i, w in enumerate(wavelengths, 1))
    manifest = {
        "model": "RTTOV14",
        "table_version": 4,
        "user_table_id": 0,
        "bulk_source_file": str(Path(data).resolve()) if isinstance(data, (str, Path)) else None,
        "bulk_source_report": str(Path(data).resolve().with_name("report.json"))
        if isinstance(data, (str, Path))
        else None,
        "outputs": paths,
        "wavelengths_um": wavelengths,
        "aerosol_species": AEROSOL_NAMES,
        "hydrometeor_species": HYDROMETEOR_NAMES,
        "populations": populations,
        "particle_order": {root: list(types) for root, types in tables.items()},
        "profile_settings": {"mmr_aer": False, "mmr_hydro": False, "nhydro": 2},
        "aerosol_units": "ext: km^-1 per particle cm^-3; profiles: cm^-3; mass conversion unsupported (confac=0)",
        "hydrometeor_units": "ext: km^-1 per g m^-3; profiles: g m^-3",
        "schema_requires_reader_renaming": False,
        "population_axes": "Fixed PSD, shapes, RH and temperature; no interpolation axes in these model tables",
        "channel_requirement": "Monochromatic samples; match gas-coefficient channels/order, or compute sensor-response averages first",
        "water_density_kg_m3": water_density_kg_m3,
        "ice_density_kg_m3": ice_density_kg_m3,
        "phase_normalization": phase_normalization,
        "phase_checks": phase_checks,
        "max_moments": max_moments,
        "validation": validation,
        "radiance_simulation_tested": False,
    }
    (output / "rttov14_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
