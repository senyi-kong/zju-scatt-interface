"""Hygroscopic aerosol and water-cloud adapters."""

from __future__ import annotations

from zju_scatt_interface.config.particles import (
    get_particle_profile,
    validate_profile_parameters,
)
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
)
from zju_scatt_interface.sources.adapters.wavelength import _WavelengthAdapter


class HygroscopicSphereAdapter(_WavelengthAdapter):
    axes = ("wavelength", "relative_humidity")
    internal_axis = "relative_humidity"

    def __init__(self, particle_type: str):
        profile = get_particle_profile(particle_type)
        if profile.particle_type not in {
            "sphere_sulfate",
            "sphere_nitrate",
            "sphere_organic_carbon",
        }:
            raise AdapterError(f"{particle_type!r} is not a hygroscopic sphere profile.")
        self.particle_type = profile.particle_type

    def _target(self, wavelength_um, parameters, tables):
        from zju_scatt_interface.config.particles import validate_profile_parameters
        from zju_scatt_interface.sources.adapters.base import _finite

        if tables:
            raise AdapterError(f"{self.particle_type} obtains refractive index from the database.")
        if "relative_humidity" not in parameters:
            raise AdapterError(f"{self.particle_type} requires relative_humidity.")
        target = {
            "wavelength": wavelength_um,
            "relative_humidity": _finite(parameters["relative_humidity"], "relative_humidity"),
        }
        validate_profile_parameters(self.particle_type, target)
        return target, "database", {}, []

    def _expand_internal(self, records):
        from zju_scatt_interface.sources.adapters.base import (
            _FileRecord,
            _read_coordinate,
        )

        result = []
        for record in records:
            for index, rh_percent in enumerate(_read_coordinate(record.path, "rh")):
                result.append(
                    _FileRecord(
                        record.path,
                        {**record.coordinates, "relative_humidity": rh_percent / 100.0},
                        {"rh": index},
                    )
                )
        return result, ["source RH converted from percent to unit 1"]


class WaterCloudWavelengthAdapter(_WavelengthAdapter):
    particle_type = "sphere_water_cloud"
    axes = ("wavelength",)

    def _target(self, wavelength_um, parameters, tables):
        if tables:
            raise AdapterError("Water cloud obtains refractive index from the database.")
        if parameters:
            raise AdapterError(
                "Water-cloud lookup accepts wavelength only; no shape, RH, "
                "temperature, or refractive-index parameters are permitted."
            )
        target = {"wavelength": wavelength_um}
        validate_profile_parameters(self.particle_type, target)
        return target, "database", {}, []
