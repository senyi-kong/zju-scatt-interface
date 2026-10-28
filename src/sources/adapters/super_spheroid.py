"""Super-spheroid dust native-index adapter."""

from __future__ import annotations

import zju_scatt_interface.access.metadata as _domain_access_metadata
from zju_scatt_interface.config.particles import (
    validate_profile_parameters,
)
from zju_scatt_interface.optics.refractive_index import (
    resolve_grid_refractive_indices,
)
from zju_scatt_interface.sources.adapters.base import ParticleAdapter
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
)


class SuperSpheroidGridAdapter(ParticleAdapter):
    particle_type = "super_spheroid"
    axes = (
        "refractive_index_real",
        "refractive_index_imaginary",
        "roundness",
        "aspect_ratio",
    )

    def _target(self, wavelength_um, parameters, tables):
        from zju_scatt_interface.sources.adapters.base import _finite

        for name in ("roundness", "aspect_ratio"):
            if name not in parameters:
                raise AdapterError(f"Super-spheroid requires {name}.")
        resolved = resolve_grid_refractive_indices(
            self.particle_type,
            [wavelength_um],
            parameters=parameters,
            tables=tables,
        )[0]
        target = {
            **{name: float(value) for name, value in resolved.values.items()},
            "roundness": _finite(parameters["roundness"], "roundness"),
            "aspect_ratio": _finite(parameters["aspect_ratio"], "aspect_ratio"),
        }
        validate_profile_parameters(self.particle_type, {"wavelength": wavelength_um, **target})
        return target, resolved.input_mode, dict(resolved.sources), []

    def _file_coordinates(self, path):
        if "super_spheroid_ice" in path.name.casefold():
            raise AdapterError("ice uses the wavelength-temperature adapter")
        metadata = _domain_access_metadata.extract_scatt_metadata(path.name)
        required = ("ref_real", "ref_imag", "n", "aspect_ratio")
        if any(name not in metadata for name in required):
            raise AdapterError("not a super-spheroid grid filename")
        return {
            "refractive_index_real": metadata["ref_real"],
            "refractive_index_imaginary": metadata["ref_imag"],
            "roundness": metadata["n"],
            "aspect_ratio": metadata["aspect_ratio"],
        }
