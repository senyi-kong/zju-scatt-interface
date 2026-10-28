"""sources / validation domain implementation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple, Union

from zju_scatt_interface.config.particles import ParticleProfile, get_particle_profile


@dataclass(frozen=True)
class VariableSummary:
    name: str
    dimensions: Tuple[str, ...]
    shape: Tuple[int, ...]
    dtype: str
    units: Optional[str]
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "dimensions": list(self.dimensions),
            "shape": list(self.shape),
            "dtype": self.dtype,
            "units": self.units,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class SourceInspection:
    path: Path
    particle_type: str
    dataset_name: str
    data_version: str
    valid: bool
    errors: Tuple[str, ...]
    variables: Mapping[str, VariableSummary]

    def to_dict(self) -> Dict[str, object]:
        return {
            "path": str(self.path),
            "particle_type": self.particle_type,
            "dataset_name": self.dataset_name,
            "data_version": self.data_version,
            "valid": self.valid,
            "errors": list(self.errors),
            "variables": {name: value.to_dict() for name, value in self.variables.items()},
        }


def _version_major(version: str) -> Optional[int]:
    match = re.search(r"(\d+)", version)
    return int(match.group(1)) if match else None


def _netcdf_path(path: Path) -> str:
    """Use Windows extended-length syntax before the 260-character boundary."""

    value = str(path.resolve())
    if os.name == "nt" and len(value) >= 248 and not value.startswith("\\\\?\\"):
        if value.startswith("\\\\"):
            return "\\\\?\\UNC\\" + value[2:]
        return "\\\\?\\" + value
    return value


def _finite_extent(variable: object) -> Tuple[Optional[float], Optional[float]]:
    # Coordinate arrays are small. Optical arrays are intentionally not read here.
    if getattr(variable, "ndim", 0) > 1 or getattr(variable, "size", 0) > 10000:
        return None, None
    try:
        values = variable[:]
        if hasattr(values, "compressed"):
            values = values.compressed()
        flat = values.reshape(-1)
        finite = [float(value) for value in flat if float("-inf") < float(value) < float("inf")]
        return (min(finite), max(finite)) if finite else (None, None)
    except (IndexError, TypeError, ValueError):
        try:
            value = float(variable.getValue())
            return value, value
        except (AttributeError, TypeError, ValueError):
            return None, None


def inspect_source_file(
    path: Union[str, Path],
    particle_type: Union[str, ParticleProfile],
) -> SourceInspection:
    """Validate an L1 file using root attributes and authoritative variable metadata."""

    try:
        from netCDF4 import Dataset
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError(
            "Source inspection requires the optional NetCDF dependencies. "
            "Install with: python -m pip install 'zju-scatt-interface[netcdf]'"
        ) from exc

    profile = (
        particle_type
        if isinstance(particle_type, ParticleProfile)
        else get_particle_profile(particle_type)
    )
    source_path = Path(path).expanduser()
    errors = []
    variables: Dict[str, VariableSummary] = {}
    with Dataset(_netcdf_path(source_path), "r") as dataset:
        dataset_name = str(getattr(dataset, "dataset_name", ""))
        data_version = str(getattr(dataset, "data_version", ""))
        if dataset_name not in profile.source_schema.dataset_names:
            errors.append(
                "dataset_name {!r} is not valid for {} (expected {})".format(
                    dataset_name,
                    profile.particle_type,
                    ", ".join(profile.source_schema.dataset_names),
                )
            )
        major = _version_major(data_version)
        if major not in profile.source_schema.accepted_data_major_versions:
            errors.append(
                "data_version {!r} has unsupported major version; accepted: {}".format(
                    data_version,
                    ", ".join(
                        str(value) for value in profile.source_schema.accepted_data_major_versions
                    ),
                )
            )
        required = set(profile.source_schema.required_variables)
        required.update(profile.source_schema.required_optical_variables)
        missing = sorted(required.difference(dataset.variables))
        if missing:
            errors.append("missing required variables: " + ", ".join(missing))
        for name, variable in dataset.variables.items():
            minimum, maximum = _finite_extent(variable) if name in required else (None, None)
            variables[name] = VariableSummary(
                name=name,
                dimensions=tuple(variable.dimensions),
                shape=tuple(variable.shape),
                dtype=str(variable.dtype),
                units=str(getattr(variable, "units", "")) or None,
                minimum=minimum,
                maximum=maximum,
            )
    return SourceInspection(
        path=source_path.resolve(),
        particle_type=profile.particle_type,
        dataset_name=dataset_name,
        data_version=data_version,
        valid=not errors,
        errors=tuple(errors),
        variables=variables,
    )
