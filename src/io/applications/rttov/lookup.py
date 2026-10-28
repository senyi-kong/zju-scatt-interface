"""io / applications / rttov / lookup domain implementation."""

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
from zju_scatt_interface.io.applications.rttov.v13 import AEROSOL_NAMES
from zju_scatt_interface.io.applications.rttov.v14 import (
    HYDROMETEOR_NAMES,
    TABLE_DIMS,
    _characters,
)

HUMID_FAMILIES = {
    "coated_super_spheroid_seasalt",
    "sphere_sulfate",
    "sphere_nitrate",
    "sphere_organic_carbon",
}
FIELDS = ("ext", "ssa", "asym", "bpr", "lcoef")


def _axis(values, name, lower=0, upper=math.inf):
    import numpy as np

    array = np.asarray(values, dtype=float)
    if (
        array.ndim != 1
        or not len(array)
        or not np.isfinite(array).all()
        or np.any(np.diff(array) <= 0)
        or np.any(array < lower)
        or np.any(array > upper)
    ):
        raise ValueError(f"{name} must be finite, increasing, unique and within [{lower}, {upper}]")
    return array


def _radius_psd(reference, radius, bounds, bins):
    """Fit the *realized* finite-grid M3/M2, retaining parent sigma/variance."""
    from zju_scatt_interface.psd.analytical import (
        gamma_psd,
        lognormal_psd,
        radius_moments,
    )

    if not bounds[0] < radius < bounds[1]:
        raise ValueError(f"Effective radius {radius} um is outside common size coverage {bounds}")
    kind = reference["type"]

    def make(parent):
        common = dict(
            number_concentration_cm3=1.0,
            radius_range_um=bounds,
            bins=bins,
            normalization="renormalize",
        )
        if kind == "lognormal":
            return lognormal_psd(parent, reference["sigma_g"], **common)
        return gamma_psd(parent, reference["effective_variance"], **common)

    # Center the search on the untruncated effective radius relation.
    guess = (
        radius / math.exp(2.5 * math.log(reference["sigma_g"]) ** 2)
        if kind == "lognormal"
        else radius
    )
    lo, hi = math.log(guess), math.log(guess)
    for _ in range(40):
        if radius_moments(make(math.exp(lo)))["realized_effective_radius_um"] <= radius:
            break
        lo -= 0.25
    else:
        raise ValueError("Cannot resolve target effective radius at lower PSD boundary")
    for _ in range(40):
        if radius_moments(make(math.exp(hi)))["realized_effective_radius_um"] >= radius:
            break
        hi += 0.25
    else:
        raise ValueError("Cannot resolve target effective radius at upper PSD boundary")
    for _ in range(55):
        midpoint = (lo + hi) / 2
        psd = make(math.exp(midpoint))
        realized = radius_moments(psd)["realized_effective_radius_um"]
        if abs(realized / radius - 1) < 1e-9:
            return psd
        if realized < radius:
            lo = midpoint
        else:
            hi = midpoint
    raise ValueError("Effective-radius PSD fit did not converge")


def _write_grid(path, root_name, wavelengths, items, max_moments, *, master):
    import numpy as np
    from netCDF4 import Dataset

    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with Dataset(temporary, "w", format="NETCDF4") as nc:
            nc.title = (
                "ZJU-SCATT RTTOV14 multidimensional lookup"
                if master
                else "ZJU-SCATT RTTOV14 selected lookup slice"
            )
            nc.native_runtime_compatible = int(not master)
            nc.usage = (
                "Select aerosol radius and ice temperature before stock RTTOV14 use"
                if master
                else "RH-only aerosols; Deff-only hydrometeors"
            )
            nc.wavelengths_um = wavelengths
            table = nc.createGroup(root_name)
            for key, length in {
                "nchan": len(wavelengths),
                "nwvn": len(wavelengths),
                "nchan_pha": 0,
                "ntypes": len(items),
                "maxnmom_dim": max_moments + 1,
                "table_max_dim": 4,
                "date_dim": 3,
                "str_name_dim": 32,
                "str_readme_dim": 132,
                "readme_dim": 100,
            }.items():
                table.createDimension(key, length)

            def put(group, name, value, dims=(), dtype="i4", units=None):
                var = group.createVariable(name, dtype, dims)
                var[...] = value
                if units:
                    var.units = units

            for key, value in dict(
                version=4, id=0, maxnmom=max_moments, has_asym=1, has_bpr=1, has_zef=0
            ).items():
                put(table, key, value)
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            put(table, "creation_date", [now.year, now.month, now.day], ("date_dim",))
            notes = [
                nc.usage,
                "Deff=2*physical volume-equivalent PSD M3/M2 [um].",
                "Aerosol ext: km-1 per particle cm-3. Cloud ext: km-1 per g m-3.",
                "Reference PSDs conditional on common source coverage; see external manifest.",
            ]
            put(
                table,
                "readme_opt_prop",
                _characters(notes + [""] * (100 - len(notes)), 132),
                ("readme_dim", "str_readme_dim"),
                "S1",
            )
            put(table, "names", _characters(list(items), 32), ("ntypes", "str_name_dim"), "S1")
            for name, item in items.items():
                group = table.createGroup(name)
                axes = item["axes"]  # Native Fortran axis order; frequency comes first.
                dim_size = [len(values) for _, values in axes] + [1] * (4 - len(axes))
                dim_type = [{"relhum": 3, "deff": 4, "temperature": 1}[key] for key, _ in axes] + [
                    0
                ] * (4 - len(axes))
                for i, size in enumerate(dim_size, 1):
                    group.createDimension(f"dim_id_{i}", size)
                coordinate_lengths = {key: len(value) for key, value in axes}
                for dim, key in (
                    ("nrelhum", "relhum"),
                    ("ndeff", "deff"),
                    ("ntemperature", "temperature"),
                    ("npartial_mass_density", "mass_density"),
                ):
                    group.createDimension(dim, coordinate_lengths.get(key, 1))
                put(group, "is_frozen", int(item["is_frozen"]))
                put(group, "confac", 0.0, dtype="f8")
                put(group, "dim_type", dim_type, ("table_max_dim",))
                put(group, "dim_size", dim_size, ("table_max_dim",))
                put(group, "dim_interp", [1 if s > 1 else 0 for s in dim_size], ("table_max_dim",))
                for key, values in axes:
                    dim = {"relhum": "nrelhum", "deff": "ndeff", "temperature": "ntemperature"}[key]
                    put(
                        group,
                        key,
                        values,
                        (dim,),
                        "f8",
                        {"relhum": "%", "deff": "um", "temperature": "K"}[key],
                    )
                    if key == "temperature":
                        # Master uses explicit arbitrary T coordinates; runtime selection is mandatory.
                        put(group, "offset_temperature", float(values[0]) - 1, dtype="f8")
                if "deff" in coordinate_lengths:
                    put(
                        group,
                        "effective_radius",
                        next(v for k, v in axes if k == "deff") / 2,
                        ("ndeff",),
                        "f8",
                        "um",
                    )
                for key in FIELDS:
                    # item values: axes in Fortran order, wavelength, [moment].
                    values = np.asarray(item[key])
                    if key == "lcoef":
                        reshaped = values.reshape(*dim_size, len(wavelengths), max_moments + 1)
                        stored = reshaped.transpose(3, 2, 1, 0, 4, 5)
                    else:
                        reshaped = values.reshape(*dim_size, len(wavelengths))
                        stored = reshaped.transpose(3, 2, 1, 0, 4)
                    put(
                        group,
                        key,
                        stored,
                        TABLE_DIMS + (("maxnmom_dim",) if key == "lcoef" else ()),
                        "f4",
                        ("km-1 per particle cm-3" if root_name == "aertable" else "km-1 per g m-3")
                        if key == "ext"
                        else "1",
                    )
                put(group, "nmom", [max_moments] * len(wavelengths), ("nwvn",))
        validate_rttov14_lookup_table(temporary)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


@_registration_required
def validate_rttov14_lookup_table(path):
    import numpy as np
    from netCDF4 import Dataset, chartostring

    with Dataset(path) as nc:
        table = next(iter(nc.groups.values()))
        if int(table["version"][...]) != 4 or int(table["id"][...]) != 0:
            raise ValueError("Expected RTTOV14 version-4 user table")
        names = [str(n).strip() for n in chartostring(table["names"][:])]
        if set(names) != set(table.groups) or len(names) != len(set(names)):
            raise ValueError("Lookup species names disagree")
        for name in names:
            group = table[name]
            sizes = list(map(int, group["dim_size"][:]))
            expected = tuple(sizes[::-1]) + (len(table.dimensions["nwvn"]),)
            for field in FIELDS:
                values = group[field][:]
                shape = expected + (
                    (len(table.dimensions["maxnmom_dim"]),) if field == "lcoef" else ()
                )
                if values.shape != shape or not np.isfinite(values).all():
                    raise ValueError(f"Invalid lookup dimensions/values: {name}/{field}")
                if group[field].dimensions != TABLE_DIMS + (
                    ("maxnmom_dim",) if field == "lcoef" else ()
                ):
                    raise ValueError("Incorrect Fortran/NetCDF dimension order")
                if field in {"ext", "ssa", "bpr", "asym"}:
                    low, high = (
                        (-1, 1) if field == "asym" else (0, np.inf) if field == "ext" else (0, 1)
                    )
                    if np.any(values < low) or np.any(values > high):
                        raise ValueError(f"Invalid physical range {field}")
            for axis, key in enumerate(group["dim_type"][:]):
                if key:
                    coordinate = {1: "temperature", 3: "relhum", 4: "deff"}[int(key)]
                    values = _axis(group[coordinate][:], coordinate)
                    if len(values) != sizes[axis]:
                        raise ValueError("Coordinate and optical dimensions disagree")
            if nc.native_runtime_compatible:
                codes = [int(k) for k, s in zip(group["dim_type"][:], sizes) if s > 1]
                if codes not in ([], [3] if table.name.strip("/") == "aertable" else [4]):
                    raise ValueError("Unsupported stock RTTOV14 runtime axes")
        return {
            "valid": True,
            "species": names,
            "native_runtime_compatible": bool(nc.native_runtime_compatible),
            "compiled_rttov_reader_tested": False,
        }


@_registration_required
def write_rttov14_lookup_slice(
    master_path, output_path, *, aerosol_effective_radii_um=None, ice_temperature_k=220.0
):
    """Select exact grid nodes into stock RH-only/Deff-only version-4 tables."""
    import numpy as np
    from netCDF4 import Dataset, chartostring

    master_path, output_path = Path(master_path), Path(output_path)
    if master_path.resolve() == output_path.resolve():
        raise ValueError("Slice output must differ from the master lookup file")
    validate_rttov14_lookup_table(master_path)
    items = {}

    def node(values, target):
        found = np.flatnonzero(np.isclose(values, target, rtol=1e-8, atol=1e-10))
        if len(found) != 1:
            raise ValueError(f"Selection {target} is not an exact lookup coordinate")
        return int(found[0])

    with Dataset(master_path) as nc:
        table = next(iter(nc.groups.values()))
        root = table.name.strip("/")
        names = [str(n).strip() for n in chartostring(table["names"][:])]
        name_map = json.loads(nc.species_name_map) if "species_name_map" in nc.ncattrs() else {}
        canonical_names = {value: key for key, value in name_map.items()}
        wavelengths = (
            np.atleast_1d(nc.getncattr("wavelengths_um"))
            if "wavelengths_um" in nc.ncattrs()
            else None
        )
        if wavelengths is None:
            raise ValueError("Master lookup lacks wavelength coordinates")
        for name in names:
            group = table[name]
            axes = []
            selectors = []
            for code in group["dim_type"][:]:
                if not code:
                    continue
                key = {1: "temperature", 3: "relhum", 4: "deff"}[int(code)]
                values = np.asarray(group[key][:])
                if root == "aertable" and key == "deff":
                    selection = aerosol_effective_radii_um or {}
                    selection_name = name if name in selection else canonical_names.get(name, name)
                    if selection_name not in selection:
                        raise ValueError(f"Specify an aerosol effective radius for {name}")
                    selectors.append(node(values, 2 * selection[selection_name]))
                elif key == "temperature":
                    selectors.append(node(values, ice_temperature_k))
                else:
                    selectors.append(slice(None))
                    axes.append((key, values))
            item = {"is_frozen": bool(group["is_frozen"][...]), "axes": axes}
            sizes = list(map(int, group["dim_size"][:]))
            for field in FIELDS:
                v = np.asarray(group[field][:])
                # Undo on-disk reversal, then remove the unused native dimensions.
                v = (
                    v.transpose(3, 2, 1, 0, 4, 5)
                    if field == "lcoef"
                    else v.transpose(3, 2, 1, 0, 4)
                )
                v = v.reshape(
                    *sizes[: len(selectors)],
                    len(wavelengths),
                    *(([v.shape[-1]]) if field == "lcoef" else []),
                )
                item[field] = v[tuple(selectors)]
            items[name] = item
        moments = int(table["maxnmom"][...])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_grid(output_path, root, wavelengths, items, moments, master=False)
    return validate_rttov14_lookup_table(output_path)


@_registration_required
def build_rttov14_lookup_tables(
    *,
    wavelengths,
    source_paths,
    effective_radii_um,
    relative_humidity_percent,
    ice_temperatures_k,
    output_dir,
    bins=160,
    max_moments=32,
    sea_salt_branch="deliquescence",
    overrides=None,
    progress=print,
):
    """Compute all eight default-shape populations on covered physical-radius grids.

    Names in source_paths are family names; radius mapping uses full output names.
    BC vf stays fixed (nearest native default unless explicitly supplied);
    BC has no RH dimension. overrides accepts family/alias-keyed shape settings
    using the same shapes API as compute_bulk_table; BC also accepts df/vf.
    Analytical PSDs are explicitly normalized to N=1 cm^-3 on common coverage.
    Parent scale is fitted so the actual discrete M3/M2 equals each requested
    effective radius. Parent sigma_g/effective_variance remain the preset values.
    """
    import numpy as np

    from zju_scatt_interface.bulk.defaults import default_bulk_assumptions
    from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble, combine
    from zju_scatt_interface.bulk.integration import integrate
    from zju_scatt_interface.bulk.quality import validate_bulk_optics
    from zju_scatt_interface.bulk.tables import _settings, check_spectral_size_coverage
    from zju_scatt_interface.config.particles import (
        get_particle_profile,
        normalize_parameter_name,
    )
    from zju_scatt_interface.io.native import scalar_phase_to_model
    from zju_scatt_interface.sources.adapters.registry import get_particle_adapter

    wl = _axis(wavelengths, "wavelengths", 3)
    rh = _axis(relative_humidity_percent, "relative_humidity_percent", 0, 99)
    temperatures = _axis(ice_temperatures_k, "ice_temperatures_k", 160, 270)
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 3:
        raise ValueError("bins must be an integer >=3")
    if (
        not isinstance(max_moments, int)
        or isinstance(max_moments, bool)
        or not 1 <= max_moments <= 255
    ):
        raise ValueError("max_moments must be an integer 1..255")
    if sea_salt_branch not in {"deliquescence", "crystallization"}:
        raise ValueError("Unknown sea-salt branch")
    names = {**AEROSOL_NAMES, **HYDROMETEOR_NAMES}
    shape_overrides = {}
    for key, value in (overrides or {}).items():
        family = get_particle_profile(key).particle_type
        if family in shape_overrides:
            raise ValueError(f"Duplicate shape overrides for {family}")
        allowed = (
            {"shapes", "df", "vf"}
            if family == "encapsulated_fractal_aggregates_black_carbon"
            else {"shapes"}
        )
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError(f"Lookup overrides for {family} accept only {sorted(allowed)}")
        shape_overrides[family] = value
    if set(source_paths) != set(names) or set(effective_radii_um) != set(names.values()):
        raise ValueError("Supply all eight source families and all eight effective-radius grids")
    prepared = {}
    for family, name in names.items():
        radii = _axis(effective_radii_um[name], f"{name} effective radii", 1e-12)
        paths = [Path(p) for p in source_paths[family]]
        if not paths or any(not p.is_file() for p in paths):
            raise ValueError(f"Missing native sources for {name}")
        override = shape_overrides.get(family, {})
        defaults, base, shapes, _, _ = _settings(family, override)
        if name == "black_carbon" and not any(
            normalize_parameter_name(k) == "vf" for k in override
        ):
            base["vf"] = default_bulk_assumptions(family, source_paths=paths)["used_native_vf"]
        if family in HUMID_FAMILIES:
            states = [{"relative_humidity": float(h) / 100} for h in rh]
            if name == "sea_salt":
                base["humidity_branch"] = sea_salt_branch
        elif name == "ice_cloud_zju_super_spheroid":
            states = [{"temperature": float(t)} for t in temperatures]
        else:
            states = [{}]
        ensemble = WeightedShapeEnsemble(shapes) if shapes else None
        if progress:
            progress(
                f"Checking common size coverage: {name}, {len(states)} environmental states",
                flush=True,
            )
        cover = [
            check_spectral_size_coverage(
                family, paths, wl, parameters={**base, **state}, shape_ensemble=ensemble
            )["common_source_radius_um"]
            for state in states
        ]
        bounds = [max(b[0] for b in cover), min(b[1] for b in cover)]
        psds = [_radius_psd(defaults["psd"], float(r), bounds, bins) for r in radii]
        prepared[family] = (name, paths, defaults, base, states, shapes, bounds, radii, psds)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    tables = {"aertable": {}, "hydrotable": {}}
    populations = {}
    for family, (
        name,
        paths,
        defaults,
        base,
        states,
        shapes,
        bounds,
        radii,
        psds,
    ) in prepared.items():
        humid = family in HUMID_FAMILIES
        icy = family == "super_spheroid_ice"
        axes = (
            [("relhum", rh), ("deff", 2 * radii)]
            if humid
            else [("deff", 2 * radii), ("temperature", temperatures)]
            if icy
            else [("deff", 2 * radii)]
        )
        sizes = tuple(len(v) for _, v in axes)
        item = {"is_frozen": icy, "axes": axes}
        for field in FIELDS:
            item[field] = np.empty(
                sizes + (len(wl),) + ((max_moments + 1,) if field == "lcoef" else ())
            )
        # Integrate each shape separately at identical physical radii, then combine.
        members = shapes or [{"parameters": {}, "weight": 1.0}]
        density = 917.0 if icy else 1000.0
        mass = [
            sum(n * (r * 1e-6) ** 3 for r, n in zip(p.size_um, p.dndr_cm3))
            * 4
            * np.pi
            / 3
            * density
            * 1e9
            for p in psds
        ]
        phase_scales = []
        selected_sources = []
        for state_index, state in enumerate(states):
            for windex, wavelength in enumerate(wl):
                if progress:
                    progress(
                        f"Computing {name}: state {state_index + 1}/{len(states)}, wavelength {wavelength:g} um",
                        flush=True,
                    )
                bulks = [[] for _ in psds]
                for member in members:
                    resolution = get_particle_adapter(family).resolve(
                        paths,
                        wavelength=float(wavelength),
                        parameters={**base, **state, **member["parameters"]},
                        include_phase_matrix=True,
                        size_definition="volume_equivalent_sphere_radius",
                    )
                    product = resolution.interpolate(
                        target_size_um=psds[0].size_um,
                        target_angles_degrees=list(range(181)),
                        phase_normalization="preserve",
                    )
                    selected_sources.append(
                        {
                            "environment": state,
                            "wavelength_um": float(wavelength),
                            "shape": member["parameters"],
                            "selection": resolution.provenance.to_dict(),
                        }
                    )
                    for i, psd in enumerate(psds):
                        bulk, _ = integrate(
                            product.optics,
                            psd,
                            database_size_definition="volume_equivalent_sphere_radius",
                        )
                        bulks[i].append(bulk)
                for rindex, results in enumerate(bulks):
                    bulk = combine(results, [m["weight"] for m in members])
                    qa = validate_bulk_optics(bulk)
                    if not qa.passed:
                        raise ValueError(f"Bulk lookup QA failed for {name}: {qa.errors}")
                    phase = np.asarray(bulk.phase_matrix)[:, 0, 0]
                    mu = np.cos(np.deg2rad(np.arange(181)))[::-1]
                    half = float(np.sum(np.diff(mu) * (phase[::-1][1:] + phase[::-1][:-1]) / 4))
                    if not math.isfinite(half) or half <= 0:
                        raise ValueError("Invalid phase integral")
                    projected = scalar_phase_to_model(
                        np.arange(181), phase / half, model="rttov14", max_moments=max_moments
                    )
                    index = (
                        (state_index, rindex)
                        if humid
                        else (rindex, state_index)
                        if icy
                        else (rindex,)
                    ) + (windex,)
                    values = {
                        "ext": bulk.extinction_coefficient
                        * 1000
                        / (1.0 if family in AEROSOL_NAMES else mass[rindex]),
                        "ssa": bulk.single_scattering_albedo,
                        "asym": bulk.asymmetry_factor,
                        "bpr": projected["BPR"],
                        "lcoef": projected["LEGCOEF"],
                    }
                    for field, value in values.items():
                        item[field][index] = value
                    phase_scales.append(1 / half)
        tables["aertable" if family in AEROSOL_NAMES else "hydrotable"][name] = item
        fixed = {
            k: v
            for k, v in base.items()
            if not (humid and k == "relative_humidity") and not (icy and k == "temperature")
        }
        populations[name] = {
            "family": family,
            "fixed_parameters": fixed,
            "shape_ensemble": shapes,
            "environmental_states": states,
            "common_radius_bounds_um": bounds,
            "psds": [p.to_dict() for p in psds],
            "parent_distribution": defaults["psd"],
            "phase_scale_range": [min(phase_scales), max(phase_scales)],
            "refractive_index_assumption": defaults["refractive_index_assumption"],
            "optical_source_selection": selected_sources,
            "source_paths": [str(p) for p in paths],
        }
        if family == "coated_super_spheroid_seasalt":
            populations[name]["source_coordinate_note"] = (
                "Reader recovers any all-one native xsize_veq placeholders using the native xsize_maxd * ve identity; source files unchanged"
            )
    outputs = {}
    validations = {}
    for root, items in tables.items():
        path = output / f"rttov_{root}_zju_lookup.nc"
        _write_grid(path, root, wl, items, max_moments, master=True)
        outputs[root] = str(path)
        validations[root] = validate_rttov14_lookup_table(path)
    manifest = {
        "outputs": outputs,
        "wavelengths_um": wl.tolist(),
        "relative_humidity_percent": rh.tolist(),
        "ice_temperatures_k": temperatures.tolist(),
        "populations": populations,
        "validation": validations,
        "native_runtime_compatible": False,
        "black_carbon": "fixed vf (explicit or nearest native default); no RH axis",
        "shape_overrides": shape_overrides,
        "size_convention": "physical volume-equivalent PSD M3/M2; deff=2*effective_radius",
        "sea_salt_branch": sea_salt_branch,
        "radiance_simulation_tested": False,
    }
    (output / "rttov14_lookup_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    with (output / "channel_wavelengths.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["channel_index", "wavelength_um", "wavenumber_cm-1"])
        writer.writerows((i + 1, w, 1e4 / w) for i, w in enumerate(wl))
    return manifest
