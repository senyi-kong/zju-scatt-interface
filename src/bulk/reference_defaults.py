"""bulk / defaults domain implementation."""

from __future__ import annotations

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import get_particle_profile


@_registration_required
def builtin_defaults(particle_type, source_paths=None, *, preset="literature_v1"):
    """Return editable reference settings; these are not universal atmospheric PSDs.

    literature_v1 follows Bi et al. (2026), Table 2. reference_v1 retains the
    previous illustrative lognormal-only setup for reproducibility.
    Lognormal rg denotes volume-equivalent radius; gamma uses effective radius
    M3/M2 on that coordinate. N is normalized to 1 cm^-3.
    The caller must restrict the PSD to actual source coverage over its spectrum.
    Optional selected source_paths resolve BC vf to the nearest common native
    coordinate, rather than interpolating vf or assuming every release shares it.
    Humidity/temperature are supplied only to profiles exposing those axes.
    """
    profile = get_particle_profile(particle_type)
    family = profile.particle_type
    if preset not in {"literature_v1", "reference_v1"}:
        raise ValueError("preset must be literature_v1 or reference_v1")
    psds = {
        "super_spheroid": (0.5, 1.8),
        "encapsulated_fractal_aggregates_black_carbon": (0.08, 1.6),
        "coated_super_spheroid_seasalt": (0.3, 1.8),
        "super_spheroid_ice": (15.0, 1.5),
        "sphere_water_cloud": (6.0, 1.4),
        "sphere_sulfate": (0.08, 1.6),
        "sphere_nitrate": (0.1, 1.6),
        "sphere_organic_carbon": (0.08, 1.6),
    }
    rg, sigma = psds[family]
    parameters, shapes = {}, []
    retrieval = {}
    ri = "native wavelength-indexed optical constants"
    if family == "super_spheroid":
        aspects = [asp for asp in profile.parameter("aspect_ratio").grid_values if 0.5 <= asp <= 2]
        shapes = [
            {"parameters": {"ssph_n": 2.6, "ssph_asp": asp}, "weight": 1 / len(aspects)}
            for asp in aspects
        ]
        ri = "packaged default dust refractive-index table"
    elif family == "encapsulated_fractal_aggregates_black_carbon":
        parameters = {"df": 2.1, "vf": 0.3, "database_type": "wavelength", "ri_scheme": "v1.2.1"}
        retrieval = {
            "refractive_index_parameters": {
                "black_carbon": {"database_type": "wavelength", "ri_scheme": "v1.2.1"}
            }
        }
        ri = "native wavelength database with the default v1.2.1 black_carbon*_used and coating RI scheme"
    elif family == "super_spheroid_ice":
        parameters = {"temperature": 220.0}
        shapes = [
            {"parameters": {"ssph_n": n, "ssph_asp": asp}, "weight": 1 / 3}
            for n, asp in ((2.5, 1.75), (2.5, 2.0), (2.75, 2.0))
        ]
        retrieval = {"target_temperatures": [220.0]}
        ri = "native ice optical constants at 220 K"
    elif family == "coated_super_spheroid_seasalt":
        parameters = {"relative_humidity": 0.6, "humidity_branch": "crystallization"}
    elif family in {"sphere_sulfate", "sphere_nitrate", "sphere_organic_carbon"}:
        parameters = {"relative_humidity": 0.6}
    result = {
        "particle_type": family,
        "parameters": parameters,
        "shape_ensemble": shapes,
        "retrieval_parameters": retrieval,
        "refractive_index_assumption": ri,
        "psd": {
            "type": "lognormal",
            "rg_um": rg,
            "sigma_g": sigma,
            "number_concentration_cm3": 1.0,
            "size_definition": "volume_equivalent_sphere_radius",
            "interpretation": "Illustrative reference PSD, conditional on actual size coverage; not a measured climatology",
        },
        "shape_weight_interpretation": "equal number fractions over the listed discrete shapes",
        "vf_selection": "nearest common native vf to 0.3; ties choose the smaller value"
        if family.startswith("encapsulated_")
        else None,
    }
    if preset == "literature_v1":
        lognormal = {
            "super_spheroid": (0.5, 2.0),
            "encapsulated_fractal_aggregates_black_carbon": (0.1, 1.5),
            "coated_super_spheroid_seasalt": (0.1, 2.0),
            "sphere_sulfate": (0.07, 1.6),
            "sphere_nitrate": (0.07, 1.6),
            "sphere_organic_carbon": (0.02, 1.8),
        }
        if family in lognormal:
            rg, sigma = lognormal[family]
            result["psd"].update(rg_um=rg, sigma_g=sigma)
        else:
            radius, variance = (10.0, 1 / 3) if family == "sphere_water_cloud" else (30.0, 0.1)
            result["psd"] = {
                "type": "gamma",
                "effective_radius_um": radius,
                "effective_variance": variance,
                "number_concentration_cm3": 1.0,
                "size_definition": "volume_equivalent_sphere_radius",
            }
        result["psd"]["interpretation"] = (
            "Literature-based representative parent PSD, conditional on common source coverage; not a measured climatology"
        )
        notes = {
            "super_spheroid": "Representative rg=0.5 um selected from Table 2 dust size grid; not a mixture of all six sizes.",
            "encapsulated_fractal_aggregates_black_carbon": "Coated-BC row. Fresh BC alternative: rg=0.015 um, sigma_g=1.9; both coated rows use rg=0.1 um, sigma_g=1.5.",
            "coated_super_spheroid_seasalt": "Intermediate Table 2 size selected; alternatives rg=0.02 and 1 um, sigma_g=2.0. No implicit dry-to-wet size conversion.",
            "sphere_water_cloud": "Representative 10 um selected from Table 2 range 5..15 um; effective variance 1/3 is the article's value (exponential number PSD).",
            "super_spheroid_ice": "Representative 30 um selected from Table 2 grid 20..200 um in steps of 10; not a universal cirrus size. Effective radius is defined on volume-equivalent radius, not projected area.",
        }
        result["psd_reference"] = {
            "preset": preset,
            "doi": "10.1175/BAMS-D-25-0258.1",
            "location": "Table 2 and Eqs. (4)-(7), PDF pp. 10-11 (E1572-E1573)",
            "selection_note": notes.get(family, "Direct species parameter pair from Table 2."),
            "radius_basis": "physical volume-equivalent radius at selected native environmental coordinates; no extra hygroscopic growth factor is applied",
        }
    else:
        result["psd_reference"] = {
            "preset": preset,
            "selection_note": "Legacy illustrative lognormal PSD; not literature-calibrated.",
        }
    if family == "encapsulated_fractal_aggregates_black_carbon" and source_paths is not None:
        import math

        import numpy as np
        from netCDF4 import Dataset

        from zju_scatt_interface.sources.adapters.base import _expand_netcdf_paths

        common = None
        for path in _expand_netcdf_paths(source_paths):
            with Dataset(path) as ds:
                values = np.asarray(ds.variables["vf"][:], dtype=float).ravel()
            if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
                raise ValueError(f"Invalid native BC volume fractions: {path}")
            common = (
                values
                if common is None
                else np.array(
                    [
                        value
                        for value in common
                        if np.isclose(values, value, rtol=1e-7, atol=1e-8).any()
                    ]
                )
            )
        if common is None or not len(common):
            raise ValueError("Selected BC sources have no common native vf coordinate")
        distance = min(abs(float(value) - 0.3) for value in common)
        chosen = min(
            float(value)
            for value in common
            if math.isclose(abs(float(value) - 0.3), distance, rel_tol=1e-12, abs_tol=1e-12)
        )
        result["requested_vf"] = 0.3
        result["used_native_vf"] = chosen
        result["parameters"]["vf"] = chosen
    return result
