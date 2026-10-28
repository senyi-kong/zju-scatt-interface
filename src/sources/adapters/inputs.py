"""Built-in refractive-index modes at the population calculation boundary."""

from __future__ import annotations


def calculation_inputs(
    component: object,
) -> tuple[dict[str, object], dict[str, object] | None]:
    parameters = dict(getattr(component, "shape_parameters", {}))
    refractive = dict(getattr(component, "refractive_index", {}))
    mode = str(refractive.get("mode", "")).casefold()
    particle_type = str(getattr(component, "particle_type"))
    from zju_scatt_interface.config.particles import get_particle_profile

    canonical = get_particle_profile(particle_type).particle_type
    tables: dict[str, object] | None = None
    if mode == "fixed":
        if canonical == "encapsulated_fractal_aggregates_black_carbon":
            bc = refractive.get("black_carbon", {})
            hygro = refractive.get("hygroscopic", {})
            parameters.update(
                {
                    "black_carbon_refractive_index_real": bc["real"],
                    "black_carbon_refractive_index_imaginary": bc["imaginary"],
                    "hygroscopic_refractive_index_real": hygro["real"],
                    "hygroscopic_refractive_index_imaginary": hygro["imaginary"],
                }
            )
        else:
            parameters.update(
                {
                    "refractive_index_real": refractive["real"],
                    "refractive_index_imaginary": refractive["imaginary"],
                }
            )
    elif mode == "table":
        if canonical == "encapsulated_fractal_aggregates_black_carbon":
            tables = {
                "black_carbon": refractive["black_carbon_file"],
                "hygroscopic": refractive["hygroscopic_file"],
            }
        else:
            tables = {"particle": refractive["file"]}
    elif mode == "database_temperature":
        parameters["temperature"] = refractive["temperature_k"]
    elif mode != "database":
        raise ValueError(
            f"Unsupported refractive-index mode {mode!r} for component "
            f"{getattr(component, 'name', '?')!r}"
        )
    return parameters, tables


def table_settings(family, parameters, shapes, refractive):
    if family == "super_spheroid_ice":
        if refractive.get("mode") != "database":
            raise ValueError(
                "Ice uses native temperature-dependent optical constants; specify temperature instead of refractive_index"
            )
        refractive = {
            "mode": "database_temperature",
            "temperature_k": parameters.pop("temperature"),
        }
    if (
        family == "encapsulated_fractal_aggregates_black_carbon"
        and refractive.get("mode") != "database"
    ):
        parameters["database_type"] = "refractive_index_grid"
        parameters.pop("ri_scheme", None)
    return parameters, shapes, refractive
