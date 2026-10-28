"""Common wavelength-based adapter behavior."""

from __future__ import annotations

import zju_scatt_interface.access.metadata as _domain_access_metadata
from zju_scatt_interface.sources.adapters.base import ParticleAdapter
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
)


class _WavelengthAdapter(ParticleAdapter):
    def _file_coordinates(self, path):
        metadata = _domain_access_metadata.extract_scatt_metadata(path.name)
        if "wavelength_um" not in metadata:
            raise AdapterError("filename does not contain wavelength")
        return {"wavelength": metadata["wavelength_um"]}
