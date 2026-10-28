"""Built-in database coordinate and refractive-index planning policies."""

from __future__ import annotations

import math
from itertools import product
from typing import Mapping, Sequence, Tuple

from zju_scatt_interface.config.particles import (
    DataStructure,
    get_particle_profile,
    normalize_parameter_name,
    validate_profile_parameters,
)
from zju_scatt_interface.config.scheme import ParticleComponent, Scheme
from zju_scatt_interface.optics.refractive_index import resolve_grid_refractive_indices


def _values(value: object) -> Tuple[object, ...]:
    if isinstance(value, Mapping):
        value = value.get("values", value.get("value"))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return () if value is None else (value,)


def _finite_values(value: object, label: str) -> Tuple[float, ...]:
    result = []
    for item in _values(value):
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("{} must contain finite values".format(label))
        result.append(number)
    return tuple(result)


def _retrieval_shapes(profile, component):
    """Select native geometry support for each requested ensemble member."""
    from zju_scatt_interface.sources.shapes import SHAPE_AXES

    base = {
        normalize_parameter_name(name): list(_finite_values(value, name))
        for name, value in component.shape_parameters.items()
        if normalize_parameter_name(name) in SHAPE_AXES
    }
    selections = []
    members = component.shape_ensemble or ({},)
    for member in members:
        values = dict(base)
        parameters = member.get("parameters", member)
        for name, value in parameters.items():
            canonical = normalize_parameter_name(name)
            if canonical in SHAPE_AXES:
                values[canonical] = [float(value)]
        names = list(values)
        joint_grid = (
            profile.particle_type == "super_spheroid"
            and set(names) == {"roundness", "aspect_ratio"}
        ) or (
            profile.particle_type == "encapsulated_fractal_aggregates_black_carbon"
            and set(names) == {"df"}
        )
        for combination in product(*(values[name] for name in names)):
            shape = {}
            for name, number in zip(names, combination):
                grid = profile.parameter(name).grid_values
                lower = [value for value in grid if value <= number]
                upper = [value for value in grid if value >= number]
                if joint_grid:
                    shape[name] = number
                elif grid and lower and upper and max(lower) != min(upper):
                    shape[name] = (max(lower), min(upper))
                else:
                    shape[name] = number
            if shape and shape not in selections:
                selections.append(shape)
    return selections or None


def plan_component(
    config: Scheme,
    component: ParticleComponent,
) -> tuple[dict[str, object], dict[str, object]]:
    profile = get_particle_profile(component.particle_type)
    coordinates: dict[str, object] = {
        "wavelength_um": list(config.wavelengths_um),
    }
    coordinate_values: dict[str, list[float]] = {}
    for raw_name, value in component.shape_parameters.items():
        name = normalize_parameter_name(raw_name)
        try:
            numbers = list(_finite_values(value, name))
        except (TypeError, ValueError):
            categorical = list(_values(value))
            if not categorical:
                raise ValueError("{} requires at least one value".format(name))
            coordinates[name] = categorical
        else:
            if numbers:
                coordinates[name] = numbers
                coordinate_values[name] = numbers
    for member in component.shape_ensemble:
        member_values = member.get("parameters", member)
        if not isinstance(member_values, Mapping):
            continue
        for raw_name, value in member_values.items():
            if raw_name == "weight":
                continue
            name = normalize_parameter_name(raw_name)
            number = float(value)
            coordinate_values.setdefault(name, [])
            if number not in coordinate_values[name]:
                coordinate_values[name].append(number)
            coordinates[name] = coordinate_values[name]

    refractive = component.refractive_index
    mode = str(refractive.get("mode", "")).casefold()
    retrieval: dict[str, object] = {
        "sources": [f"Single_opt/{profile.database_directory}/"],
        "particle_types": [profile.particle_type],
        "target_wavelengths": list(config.wavelengths_um),
        "shapes": _retrieval_shapes(profile, component),
        "target_wavelength_mode": (
            "interp" if config.interpolation == "linear" else config.interpolation
        ),
        "quiet": True,
        "download": False,
    }

    if profile.particle_type == "encapsulated_fractal_aggregates_black_carbon":
        kind = component.shape_parameters.get(
            "database_type", "wavelength" if mode == "database" else "refractive_index_grid"
        )
        scheme = component.shape_parameters.get("ri_scheme", "v1.2.1")
        if kind == "wavelength":
            if mode != "database":
                raise ValueError("Wavelength BC requires refractive_index.mode='database'")
            validate_profile_parameters(
                profile.particle_type,
                {
                    "wavelength": list(config.wavelengths_um),
                    **{
                        name: value
                        for name, value in coordinates.items()
                        if name != "wavelength_um"
                    },
                },
            )
            retrieval["refractive_index_parameters"] = {
                "black_carbon": {"database_type": kind, "ri_scheme": scheme}
            }
            coordinates["ri_scheme"] = [scheme]
            return coordinates, retrieval

    if profile.data_structure == DataStructure.WAVELENGTH_BASED:
        if mode == "fixed":
            raise ValueError(
                "{} is wavelength based; component {!r} must not supply a fixed "
                "refractive index. Use mode='database' or "
                "mode='database_temperature'.".format(
                    profile.particle_type,
                    component.name,
                )
            )
        retrieval["target_wavelengths"] = list(config.wavelengths_um)
        if profile.particle_type == "super_spheroid_ice":
            temperatures = _finite_values(
                refractive.get("temperature_k"),
                "temperature_k",
            ) or tuple(config.temperatures_k)
            if not temperatures:
                raise ValueError("ice component {!r} requires temperature_k".format(component.name))
            coordinates["temperature"] = list(temperatures)
            retrieval["target_temperatures"] = list(temperatures)
        validate_profile_parameters(
            profile.particle_type,
            {
                "wavelength": list(config.wavelengths_um),
                **{name: value for name, value in coordinates.items() if name != "wavelength_um"},
            },
        )
        return coordinates, retrieval

    if mode == "fixed":
        if profile.particle_type == "encapsulated_fractal_aggregates_black_carbon":
            bc = refractive.get("black_carbon", {})
            hygroscopic = refractive.get("hygroscopic", {})
            native_values = {
                "black_carbon_refractive_index_real": refractive.get(
                    "black_carbon_refractive_index_real",
                    bc.get("real") if isinstance(bc, Mapping) else None,
                ),
                "black_carbon_refractive_index_imaginary": refractive.get(
                    "black_carbon_refractive_index_imaginary",
                    bc.get("imaginary") if isinstance(bc, Mapping) else None,
                ),
                "hygroscopic_refractive_index_real": refractive.get(
                    "hygroscopic_refractive_index_real",
                    hygroscopic.get("real") if isinstance(hygroscopic, Mapping) else None,
                ),
                "hygroscopic_refractive_index_imaginary": refractive.get(
                    "hygroscopic_refractive_index_imaginary",
                    hygroscopic.get("imaginary") if isinstance(hygroscopic, Mapping) else None,
                ),
            }
            missing = [name for name, value in native_values.items() if value is None]
            if missing:
                raise ValueError(
                    "black-carbon fixed refractive index requires: " + ", ".join(missing)
                )
            for name, value in native_values.items():
                coordinates[name] = [float(value)]
            retrieval["refractive_index_parameters"] = {
                "black_carbon": {
                    "database_type": "refractive_index_grid",
                    **{name: float(value) for name, value in native_values.items()},
                }
            }
        else:
            real = float(refractive["real"])
            imaginary = float(refractive["imaginary"])
            coordinates["refractive_index_real"] = [real]
            coordinates["refractive_index_imaginary"] = [imaginary]
            retrieval["ref_real_targets"] = [real]
            retrieval["ref_imag_targets"] = [imaginary]
    elif mode in {"table", "database"}:
        tables = None
        if mode == "table" and profile.particle_type == "super_spheroid":
            tables = {"particle": refractive["file"]}
        elif mode == "table":
            try:
                tables = {
                    "black_carbon": refractive["black_carbon_file"],
                    "hygroscopic": refractive["hygroscopic_file"],
                }
            except KeyError as exc:
                raise ValueError(
                    "black-carbon table mode requires black_carbon_file and hygroscopic_file"
                ) from exc
        resolved = resolve_grid_refractive_indices(
            profile.particle_type,
            config.wavelengths_um,
            tables=tables,
        )
        if profile.particle_type == "encapsulated_fractal_aggregates_black_carbon":
            retrieval["refractive_index_parameters"] = {
                "black_carbon": {
                    "database_type": "refractive_index_grid",
                    **({"tables": tables} if tables else {}),
                }
            }
        native_names = sorted({name for point in resolved for name in point.values})
        for name in native_names:
            coordinates[name] = [point.values[name] for point in resolved]
        coordinates["refractive_index_sources"] = dict(resolved[0].sources)
        if profile.particle_type == "super_spheroid":
            retrieval["ref_real_targets"] = [
                point.values["refractive_index_real"] for point in resolved
            ]
            retrieval["ref_imag_targets"] = [
                point.values["refractive_index_imaginary"] for point in resolved
            ]
    else:
        raise ValueError(
            "{} component {!r} requires refractive_index.mode='fixed' or "
            "'table'; mode='database' uses the packaged default wavelength-to-index "
            "table.".format(profile.particle_type, component.name)
        )
    validate_profile_parameters(
        profile.particle_type,
        {
            "wavelength": list(config.wavelengths_um),
            **{
                name: value
                for name, value in coordinates.items()
                if name not in {"wavelength_um", "refractive_index_sources"}
            },
        },
    )
    return coordinates, retrieval
