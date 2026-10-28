"""Ice wavelength/temperature/shape adapter."""

from __future__ import annotations

import zju_scatt_interface.access.metadata as _domain_access_metadata
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    validate_profile_parameters,
)
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
    DatabaseBoundaryError,
)
from zju_scatt_interface.sources.adapters.wavelength import _WavelengthAdapter


class IceWavelengthTemperatureAdapter(_WavelengthAdapter):
    particle_type = "super_spheroid_ice"
    axes = ("wavelength", "temperature", "roundness", "aspect_ratio")

    def _target(self, wavelength_um, parameters, tables):
        from zju_scatt_interface.sources.adapters.base import _finite

        if tables:
            raise AdapterError("Ice obtains refractive index from wavelength and temperature.")
        required = ("temperature", "roundness", "aspect_ratio")
        missing = [name for name in required if name not in parameters]
        if missing:
            raise AdapterError("Ice requires: " + ", ".join(missing))
        target = {
            "wavelength": wavelength_um,
            "temperature": _finite(parameters["temperature"], "temperature"),
            "roundness": _finite(parameters["roundness"], "roundness"),
            "aspect_ratio": _finite(parameters["aspect_ratio"], "aspect_ratio"),
        }
        temperature = target["temperature"]
        if temperature <= 0:
            raise AdapterError("Ice temperature must be greater than 0 K.")
        temperature_spec = get_particle_profile(self.particle_type).parameter("temperature")
        if not temperature_spec.minimum <= temperature <= temperature_spec.maximum:
            raise DatabaseBoundaryError(
                f"Ice temperature={temperature:g} K is outside database support "
                f"[{temperature_spec.minimum:g}, {temperature_spec.maximum:g}] K."
            )
        validate_profile_parameters(self.particle_type, target)
        return target, "database_temperature", {}, []

    def _file_coordinates(self, path):
        coordinates = super()._file_coordinates(path)
        metadata = _domain_access_metadata.extract_scatt_metadata(path.name)
        required = ("temperature_k", "n", "aspect_ratio")
        if any(name not in metadata for name in required):
            raise AdapterError("not an ice L1 filename")
        coordinates.update(
            {
                "temperature": metadata["temperature_k"],
                "roundness": metadata["n"],
                "aspect_ratio": metadata["aspect_ratio"],
            }
        )
        return coordinates


def interpolation_policy(values, nodes):
    from zju_scatt_interface.optics.interpolation import InterpolationError

    if "temperature" in values and float(values["temperature"]) <= 0:
        raise InterpolationError("Ice temperature must be greater than 0 K.")
    return IceWavelengthTemperatureAdapter.axes, True
