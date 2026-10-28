"""Sea-salt wavelength/humidity adapter."""

from __future__ import annotations

from zju_scatt_interface.config.particles import (
    validate_profile_parameters,
)
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
)
from zju_scatt_interface.sources.adapters.wavelength import _WavelengthAdapter


class SeaSaltWavelengthAdapter(_WavelengthAdapter):
    particle_type = "coated_super_spheroid_seasalt"
    axes = ("wavelength", "relative_humidity", "humidity_branch")
    internal_axis = "relative_humidity"

    def _target(self, wavelength_um, parameters, tables):
        from zju_scatt_interface.sources.adapters.base import _finite

        if tables:
            raise AdapterError("Sea salt obtains refractive index from the database.")
        if "relative_humidity" not in parameters:
            raise AdapterError("Sea salt requires relative_humidity in unit 1.")
        rh = _finite(parameters["relative_humidity"], "relative_humidity")
        branch = parameters.get("humidity_branch")
        defaults = []
        if branch is None:
            branch = "deliquescence"
            defaults.append("humidity_branch=deliquescence")
        branch = str(branch).casefold()
        target = {
            "wavelength": wavelength_um,
            "relative_humidity": rh,
            "humidity_branch": branch,
        }
        validate_profile_parameters(self.particle_type, target)
        return target, "database", {}, defaults

    def _expand_internal(self, records):
        from zju_scatt_interface.sources.adapters.base import (
            _FileRecord,
            _read_coordinate,
        )

        result = []
        for record in records:
            for index, stored_rh in enumerate(_read_coordinate(record.path, "rh")):
                branch = "crystallization" if stored_rh < 0 else "deliquescence"
                result.append(
                    _FileRecord(
                        record.path,
                        {
                            **record.coordinates,
                            "relative_humidity": abs(stored_rh) / 100.0,
                            "humidity_branch": branch,
                        },
                        {"rh": index},
                    )
                )
        return result, [
            "source RH converted from percent to unit 1",
            "negative source RH mapped to humidity_branch=crystallization",
        ]
