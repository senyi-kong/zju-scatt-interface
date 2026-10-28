"""Built-in particle bindings; the generic framework knows no family names."""

from functools import partial

_PROFILE_AXES: dict[str, tuple[str, ...]] = {
    "encapsulated_fractal_aggregates_black_carbon": (
        "black_carbon_refractive_index_real",
        "black_carbon_refractive_index_imaginary",
        "hygroscopic_refractive_index_real",
        "hygroscopic_refractive_index_imaginary",
        "df",
        "vf",
    ),
    "super_spheroid": (
        "refractive_index_real",
        "refractive_index_imaginary",
        "roundness",
        "aspect_ratio",
    ),
    "coated_super_spheroid_seasalt": ("wavelength", "relative_humidity"),
    "super_spheroid_ice": ("wavelength", "temperature", "roundness", "aspect_ratio"),
    "sphere_sulfate": ("wavelength", "relative_humidity"),
    "sphere_nitrate": ("wavelength", "relative_humidity"),
    "sphere_organic_carbon": ("wavelength", "relative_humidity"),
    "sphere_water_cloud": ("wavelength",),
}


def definitions():
    from zju_scatt_interface.bulk.reference_defaults import builtin_defaults
    from zju_scatt_interface.config.particles import _PROFILES
    from zju_scatt_interface.extensions.particles import ParticleDefinition
    from zju_scatt_interface.sources.adapters.black_carbon import BlackCarbonGridAdapter
    from zju_scatt_interface.sources.adapters.ice import IceWavelengthTemperatureAdapter
    from zju_scatt_interface.sources.adapters.inputs import calculation_inputs, table_settings
    from zju_scatt_interface.sources.adapters.planning import plan_component
    from zju_scatt_interface.sources.adapters.sea_salt import SeaSaltWavelengthAdapter
    from zju_scatt_interface.sources.adapters.spheres import (
        HygroscopicSphereAdapter,
        WaterCloudWavelengthAdapter,
    )
    from zju_scatt_interface.sources.adapters.super_spheroid import SuperSpheroidGridAdapter

    factories = {
        "encapsulated_fractal_aggregates_black_carbon": BlackCarbonGridAdapter,
        "super_spheroid": SuperSpheroidGridAdapter,
        "coated_super_spheroid_seasalt": SeaSaltWavelengthAdapter,
        "super_spheroid_ice": IceWavelengthTemperatureAdapter,
        "sphere_sulfate": partial(HygroscopicSphereAdapter, "sphere_sulfate"),
        "sphere_nitrate": partial(HygroscopicSphereAdapter, "sphere_nitrate"),
        "sphere_organic_carbon": partial(HygroscopicSphereAdapter, "sphere_organic_carbon"),
        "sphere_water_cloud": WaterCloudWavelengthAdapter,
    }
    from zju_scatt_interface.sources.adapters.black_carbon import interpolation_policy as bc_policy
    from zju_scatt_interface.sources.adapters.ice import interpolation_policy as ice_policy

    policies = {
        "encapsulated_fractal_aggregates_black_carbon": bc_policy,
        "super_spheroid_ice": ice_policy,
    }
    return tuple(
        ParticleDefinition(
            profile=profile,
            adapter_factory=factories[profile.particle_type],
            axes=_PROFILE_AXES[profile.particle_type],
            planner=plan_component,
            calculation_inputs=calculation_inputs,
            defaults=partial(builtin_defaults, profile.particle_type),
            interpolation_policy=policies.get(profile.particle_type),
            ensemble_axes={
                "super_spheroid": ("roundness", "aspect_ratio"),
                "super_spheroid_ice": ("roundness", "aspect_ratio"),
                "encapsulated_fractal_aggregates_black_carbon": ("df",),
            }.get(profile.particle_type, ()),
            table_settings=partial(table_settings, profile.particle_type),
        )
        for profile in _PROFILES
    )
