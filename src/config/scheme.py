"""config / scheme domain implementation."""

from __future__ import annotations

import copy
import json
import math
import runpy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.optics.refractive_index import wavelength_to_um
from zju_scatt_interface.psd.models import SizeDistribution

SCHEME_SCHEMA_VERSION = "1.0"


def _positive(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return number


def _wavelengths(value: Any, unit: str) -> tuple[float, ...]:
    if isinstance(value, Mapping):
        minimum = _positive(value.get("min"), "wavelengths.min")
        maximum = _positive(value.get("max"), "wavelengths.max")
        step = _positive(value.get("step"), "wavelengths.step")
        if maximum < minimum:
            raise ValueError("wavelengths.max must be greater than or equal to wavelengths.min")
        count = int(math.floor((maximum - minimum) / step + 1e-12)) + 1
        values = [minimum + index * step for index in range(count)]
        if values[-1] < maximum - step * 1e-9:
            values.append(maximum)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        values = [_positive(item, "wavelength") for item in value]
    else:
        raise ValueError("wavelengths must be a list or an object with min, max, and step")
    if not values:
        raise ValueError("at least one wavelength is required")
    try:
        normalized = [wavelength_to_um(item, unit) for item in values]
    except ValueError as exc:
        raise ValueError("wavelength_unit must be 'nm', 'um', or 'cm-1'") from exc
    return tuple(sorted(set(normalized)))


def _infer_format(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return "hdf5" if suffix in {".h5", ".hdf", ".hdf5"} else "netcdf4"


@dataclass(frozen=True)
class SchemeOutput:
    """Declarative output path and Phase-8 storage controls."""

    path: str = "bulk_optical_scheme.nc"
    format: str = "netcdf4"
    compression: bool = True
    compression_level: int = 4
    shuffle: bool = True
    chunk_wavelength: Optional[int] = None
    atomic: bool = True

    def __post_init__(self) -> None:
        if not str(self.path).strip():
            raise ValueError("output.path cannot be empty")
        normalized = str(self.format).casefold()
        aliases = {
            "nc": "netcdf4",
            "netcdf": "netcdf4",
            "netcdf4": "netcdf4",
            "h5": "hdf5",
            "hdf": "hdf5",
            "hdf5": "hdf5",
        }
        if normalized not in aliases:
            raise ValueError("output.format must be 'netcdf4' or 'hdf5'")
        object.__setattr__(self, "format", aliases[normalized])
        if not 0 <= int(self.compression_level) <= 9:
            raise ValueError("output.compression_level must be between 0 and 9")
        if self.chunk_wavelength is not None and int(self.chunk_wavelength) <= 0:
            raise ValueError("output.chunk_wavelength must be positive")

    @classmethod
    def from_value(cls, value: object) -> "SchemeOutput":
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, Path)):
            path = str(value)
            return cls(path=path, format=_infer_format(path))
        if not isinstance(value, Mapping):
            raise ValueError("output must be a path string or an object")
        path = str(value.get("path", "bulk_optical_scheme.nc"))
        return cls(
            path=path,
            format=str(value.get("format", _infer_format(path))),
            compression=bool(value.get("compression", True)),
            compression_level=int(value.get("compression_level", 4)),
            shuffle=bool(value.get("shuffle", True)),
            chunk_wavelength=(
                int(value["chunk_wavelength"])
                if value.get("chunk_wavelength") is not None
                else None
            ),
            atomic=bool(value.get("atomic", True)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "format": self.format,
            "compression": self.compression,
            "compression_level": self.compression_level,
            "shuffle": self.shuffle,
            "chunk_wavelength": self.chunk_wavelength,
            "atomic": self.atomic,
        }


@dataclass(frozen=True)
class DatabaseRefractiveIndex:
    """Use database wavelength optics, optionally at an ice temperature."""

    temperature_k: Optional[float] = None

    def to_dict(self) -> dict[str, object]:
        if self.temperature_k is None:
            return {"mode": "database"}
        return {
            "mode": "database_temperature",
            "temperature_k": _positive(self.temperature_k, "temperature_k"),
        }


@dataclass(frozen=True)
class FixedRefractiveIndex:
    """Advanced native-grid refractive-index override."""

    real: float
    imaginary: float

    def to_dict(self) -> dict[str, object]:
        real = _positive(self.real, "refractive_index.real")
        imaginary = float(self.imaginary)
        if not math.isfinite(imaginary) or imaginary < 0:
            raise ValueError("refractive_index.imaginary must be finite and non-negative")
        return {"mode": "fixed", "real": real, "imaginary": imaginary}


@dataclass(frozen=True)
class TableRefractiveIndex:
    """External wavelength-to-index table for a native mr/mi grid database."""

    file: Union[str, Path]

    def to_dict(self) -> dict[str, object]:
        return {"mode": "table", "file": str(self.file)}


@dataclass(frozen=True)
class BlackCarbonRefractiveIndex:
    """Two-material native refractive indices for encapsulated black carbon."""

    black_carbon_real: float
    black_carbon_imaginary: float
    hygroscopic_real: float
    hygroscopic_imaginary: float

    def to_dict(self) -> dict[str, object]:
        black_carbon = FixedRefractiveIndex(
            self.black_carbon_real, self.black_carbon_imaginary
        ).to_dict()
        hygroscopic = FixedRefractiveIndex(
            self.hygroscopic_real, self.hygroscopic_imaginary
        ).to_dict()
        return {
            "mode": "fixed",
            "black_carbon": {
                "real": black_carbon["real"],
                "imaginary": black_carbon["imaginary"],
            },
            "hygroscopic": {
                "real": hygroscopic["real"],
                "imaginary": hygroscopic["imaginary"],
            },
        }


@dataclass(frozen=True)
class BlackCarbonRefractiveIndexTables:
    """External material tables used by the black-carbon wavelength wrapper."""

    black_carbon_file: Union[str, Path]
    hygroscopic_file: Union[str, Path]

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": "table",
            "black_carbon_file": str(self.black_carbon_file),
            "hygroscopic_file": str(self.hygroscopic_file),
        }


def _refractive_mapping(value: object) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        result = value.to_dict()
    elif isinstance(value, Mapping):
        result = dict(value)
    else:
        raise ValueError("refractive_index must be a mapping or typed index object")
    if not isinstance(result, Mapping):
        raise ValueError("refractive_index.to_dict() must return a mapping")
    return dict(result)


def _resolve_relative_path(value: object, base_dir: Optional[Path]) -> object:
    if not value or base_dir is None:
        return value
    path = Path(str(value)).expanduser()
    return str(path if path.is_absolute() else (base_dir / path).resolve())


@dataclass(frozen=True)
class ParticleComponent:
    """One independently named particle population in a bulk scheme."""

    name: str
    particle_type: str
    size_distribution: SizeDistribution
    refractive_index: Mapping[str, Any]
    shape_parameters: Mapping[str, Any] = field(default_factory=dict)
    shape_ensemble: tuple[Mapping[str, Any], ...] = ()
    source: Optional[str] = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("component name cannot be empty")
        if not str(self.particle_type).strip():
            raise ValueError("particle_type cannot be empty")
        if not isinstance(self.size_distribution, SizeDistribution):
            raise TypeError("size_distribution must be a SizeDistribution")
        if not isinstance(self.refractive_index, Mapping):
            raise TypeError("refractive_index must be a mapping")

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        index: int = 0,
        *,
        base_dir: Union[str, Path, None] = None,
    ) -> "ParticleComponent":
        name = str(value.get("name", "")).strip()
        particle_type = str(value.get("particle_type", "")).strip()
        if not name:
            raise ValueError(f"particles[{index}].name is required")
        if not particle_type:
            raise ValueError(f"particles[{index}].particle_type is required")
        distribution = value.get("size_distribution")
        if not isinstance(distribution, Mapping):
            raise ValueError(
                f"particles[{index}].size_distribution must contain size/dndr arrays or a file"
            )
        base = Path(base_dir).expanduser().resolve() if base_dir is not None else None
        parsed_distribution = SizeDistribution.from_mapping(
            distribution,
            base_dir=base,
        )
        refractive_index = value.get("refractive_index")
        if not isinstance(refractive_index, Mapping) or not refractive_index.get("mode"):
            raise ValueError(f"particles[{index}].refractive_index.mode is required")
        refractive = dict(refractive_index)
        refractive_mode = str(refractive["mode"]).casefold()
        if refractive_mode == "fixed":
            if "real" in refractive or "imaginary" in refractive:
                FixedRefractiveIndex(refractive.get("real"), refractive.get("imaginary")).to_dict()
            else:
                for material in ("black_carbon", "hygroscopic"):
                    material_index = refractive.get(material)
                    if not isinstance(material_index, Mapping):
                        raise ValueError(
                            f"particles[{index}].refractive_index.{material} "
                            "must contain real and imaginary"
                        )
                    FixedRefractiveIndex(
                        material_index.get("real"),
                        material_index.get("imaginary"),
                    ).to_dict()
        elif refractive_mode == "database_temperature":
            _positive(
                refractive.get("temperature_k"),
                f"particles[{index}].refractive_index.temperature_k",
            )
        elif refractive_mode == "table":
            if not refractive.get("file") and not (
                refractive.get("black_carbon_file") and refractive.get("hygroscopic_file")
            ):
                raise ValueError(
                    f"particles[{index}] table refractive_index requires file, or "
                    "black_carbon_file and hygroscopic_file"
                )
            for key in ("file", "black_carbon_file", "hygroscopic_file"):
                if refractive.get(key):
                    refractive[key] = _resolve_relative_path(refractive[key], base)
        elif refractive_mode != "database":
            raise ValueError(
                f"particles[{index}].refractive_index.mode must be database, fixed, "
                "table, or database_temperature"
            )
        shape = value.get("shape_parameters", {})
        if not isinstance(shape, Mapping):
            raise ValueError(f"particles[{index}].shape_parameters must be an object")
        ensemble_value = value.get("shape_ensemble", [])
        if isinstance(ensemble_value, Mapping):
            ensemble_value = ensemble_value.get("members", [])
        if not isinstance(ensemble_value, Sequence) or isinstance(ensemble_value, (str, bytes)):
            raise ValueError(f"particles[{index}].shape_ensemble must be a list of members")
        ensemble = tuple(dict(member) for member in ensemble_value if isinstance(member, Mapping))
        if len(ensemble) != len(ensemble_value):
            raise ValueError(f"particles[{index}].shape_ensemble members must be objects")
        if "mixing_fraction" in value:
            raise ValueError(
                f"particles[{index}].mixing_fraction is not supported; each "
                "particle component is calculated independently from its own "
                "size distribution"
            )
        source = value.get("source", value.get("source_path"))
        return cls(
            name=name,
            particle_type=particle_type,
            size_distribution=parsed_distribution,
            refractive_index=refractive,
            shape_parameters=dict(shape),
            shape_ensemble=ensemble,
            source=(str(_resolve_relative_path(source, base)) if source is not None else None),
        )

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        base_dir: Union[str, Path, None] = None,
    ) -> "ParticleComponent":
        return cls.from_mapping(value, base_dir=base_dir)

    def to_dict(self) -> dict[str, object]:
        result = {
            "name": self.name,
            "particle_type": self.particle_type,
            "size_distribution": self.size_distribution.to_dict(),
            "refractive_index": dict(self.refractive_index),
            "shape_parameters": dict(self.shape_parameters),
            "shape_ensemble": [dict(member) for member in self.shape_ensemble],
        }
        if self.source is not None:
            result["source"] = self.source
        return result


def _distribution(
    size_distribution: Optional[SizeDistribution],
    *,
    size: object,
    dndr: object,
    size_unit: str,
    size_definition: str,
) -> SizeDistribution:
    if size_distribution is not None:
        if size is not None or dndr is not None:
            raise ValueError("provide size_distribution or size/dndr arrays, not both")
        return size_distribution
    if size is None or dndr is None:
        raise ValueError("size and dndr arrays are required")
    return SizeDistribution(
        size,
        dndr,
        size_unit=size_unit,
        size_definition=size_definition,
    )


def _shape_values(**values: object) -> dict[str, object]:
    return {name: value for name, value in values.items() if value is not None}


def _source_value(value: Optional[Union[str, Path]]) -> Optional[str]:
    return str(Path(value).expanduser().resolve()) if value is not None else None


class IceComponent(ParticleComponent):
    """Typed super-spheroid ice component."""

    def __init__(
        self,
        name: str,
        *,
        temperature_k: float,
        size_distribution: Optional[SizeDistribution] = None,
        size: object = None,
        dndr: object = None,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        roundness: object = None,
        aspect_ratio: object = None,
        shape_ensemble: Sequence[Mapping[str, Any]] = (),
        source: Optional[Union[str, Path]] = None,
    ) -> None:
        super().__init__(
            name=name,
            particle_type="super_spheroid_ice",
            size_distribution=_distribution(
                size_distribution,
                size=size,
                dndr=dndr,
                size_unit=size_unit,
                size_definition=size_definition,
            ),
            refractive_index=DatabaseRefractiveIndex(temperature_k).to_dict(),
            shape_parameters=_shape_values(roundness=roundness, aspect_ratio=aspect_ratio),
            shape_ensemble=tuple(dict(member) for member in shape_ensemble),
            source=_source_value(source),
        )


class SeaSaltComponent(ParticleComponent):
    """Typed coated-super-spheroid sea-salt component."""

    def __init__(
        self,
        name: str,
        *,
        relative_humidity: object,
        humidity_branch: object = None,
        size_distribution: Optional[SizeDistribution] = None,
        size: object = None,
        dndr: object = None,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        shape_ensemble: Sequence[Mapping[str, Any]] = (),
        source: Optional[Union[str, Path]] = None,
    ) -> None:
        super().__init__(
            name=name,
            particle_type="coated_super_spheroid_seasalt",
            size_distribution=_distribution(
                size_distribution,
                size=size,
                dndr=dndr,
                size_unit=size_unit,
                size_definition=size_definition,
            ),
            refractive_index=DatabaseRefractiveIndex().to_dict(),
            shape_parameters=_shape_values(
                relative_humidity=relative_humidity,
                humidity_branch=humidity_branch,
            ),
            shape_ensemble=tuple(dict(member) for member in shape_ensemble),
            source=_source_value(source),
        )


class SuperSpheroidComponent(ParticleComponent):
    """Typed native mr/mi-grid super-spheroid component."""

    def __init__(
        self,
        name: str,
        *,
        refractive_index: object,
        roundness: object = None,
        aspect_ratio: object = None,
        size_distribution: Optional[SizeDistribution] = None,
        size: object = None,
        dndr: object = None,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        shape_ensemble: Sequence[Mapping[str, Any]] = (),
        source: Optional[Union[str, Path]] = None,
    ) -> None:
        super().__init__(
            name=name,
            particle_type="super_spheroid",
            size_distribution=_distribution(
                size_distribution,
                size=size,
                dndr=dndr,
                size_unit=size_unit,
                size_definition=size_definition,
            ),
            refractive_index=_refractive_mapping(refractive_index),
            shape_parameters=_shape_values(roundness=roundness, aspect_ratio=aspect_ratio),
            shape_ensemble=tuple(dict(member) for member in shape_ensemble),
            source=_source_value(source),
        )


class DustComponent(SuperSpheroidComponent):
    """Readable alias for a dust population using the super-spheroid database."""


class BlackCarbonComponent(ParticleComponent):
    """Typed encapsulated fractal-aggregate black-carbon component."""

    def __init__(
        self,
        name: str,
        *,
        df: object,
        vf: object,
        refractive_index: object,
        database_type: str = "refractive_index_grid",
        ri_scheme: Optional[str] = None,
        size_distribution: Optional[SizeDistribution] = None,
        size: object = None,
        dndr: object = None,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        shape_ensemble: Sequence[Mapping[str, Any]] = (),
        source: Optional[Union[str, Path]] = None,
    ) -> None:
        super().__init__(
            name=name,
            particle_type="encapsulated_fractal_aggregates_black_carbon",
            size_distribution=_distribution(
                size_distribution,
                size=size,
                dndr=dndr,
                size_unit=size_unit,
                size_definition=size_definition,
            ),
            refractive_index=_refractive_mapping(refractive_index),
            shape_parameters={
                "df": df,
                "vf": vf,
                "database_type": database_type,
                **({"ri_scheme": ri_scheme} if ri_scheme else {}),
            },
            shape_ensemble=tuple(dict(member) for member in shape_ensemble),
            source=_source_value(source),
        )


class HygroscopicSphereComponent(ParticleComponent):
    """Typed sulfate, nitrate, or organic-carbon sphere component."""

    _TYPES = {
        "sulfate": "sphere_sulfate",
        "nitrate": "sphere_nitrate",
        "organic_carbon": "sphere_organic_carbon",
    }

    def __init__(
        self,
        name: str,
        *,
        material: str,
        relative_humidity: object,
        size_distribution: Optional[SizeDistribution] = None,
        size: object = None,
        dndr: object = None,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        shape_ensemble: Sequence[Mapping[str, Any]] = (),
        source: Optional[Union[str, Path]] = None,
    ) -> None:
        key = str(material).casefold().replace("-", "_").replace(" ", "_")
        if key not in self._TYPES:
            raise ValueError("material must be sulfate, nitrate, or organic_carbon")
        super().__init__(
            name=name,
            particle_type=self._TYPES[key],
            size_distribution=_distribution(
                size_distribution,
                size=size,
                dndr=dndr,
                size_unit=size_unit,
                size_definition=size_definition,
            ),
            refractive_index=DatabaseRefractiveIndex().to_dict(),
            shape_parameters={"relative_humidity": relative_humidity},
            shape_ensemble=tuple(dict(member) for member in shape_ensemble),
            source=_source_value(source),
        )


class WaterCloudComponent(ParticleComponent):
    """Typed spherical liquid-water cloud component."""

    def __init__(
        self,
        name: str,
        *,
        size_distribution: Optional[SizeDistribution] = None,
        size: object = None,
        dndr: object = None,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        source: Optional[Union[str, Path]] = None,
    ) -> None:
        super().__init__(
            name=name,
            particle_type="sphere_water_cloud",
            size_distribution=_distribution(
                size_distribution,
                size=size,
                dndr=dndr,
                size_unit=size_unit,
                size_definition=size_definition,
            ),
            refractive_index=DatabaseRefractiveIndex().to_dict(),
            source=_source_value(source),
        )


class SulfateComponent(HygroscopicSphereComponent):
    """Typed sulfate sphere component."""

    def __init__(self, name: str, *, relative_humidity: object, **kwargs: object):
        super().__init__(
            name,
            material="sulfate",
            relative_humidity=relative_humidity,
            **kwargs,
        )


class NitrateComponent(HygroscopicSphereComponent):
    """Typed nitrate sphere component."""

    def __init__(self, name: str, *, relative_humidity: object, **kwargs: object):
        super().__init__(
            name,
            material="nitrate",
            relative_humidity=relative_humidity,
            **kwargs,
        )


class OrganicCarbonComponent(HygroscopicSphereComponent):
    """Typed organic-carbon sphere component."""

    def __init__(self, name: str, *, relative_humidity: object, **kwargs: object):
        super().__init__(
            name,
            material="organic_carbon",
            relative_humidity=relative_humidity,
            **kwargs,
        )


@_registration_required
def migrate_scheme_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate an unversioned/provisional mapping to schema 1.0."""

    result = copy.deepcopy(dict(value))
    version = str(result.get("schema_version", "0")).strip()
    if version not in {"", "0", "0.1", SCHEME_SCHEMA_VERSION}:
        raise ValueError(
            f"unsupported scheme schema_version {version!r}; "
            f"this interface supports {SCHEME_SCHEMA_VERSION}"
        )
    if "components" in result and "particles" not in result:
        result["particles"] = result.pop("components")
    if "wavelength" in result and "wavelengths" not in result:
        result["wavelengths"] = result.pop("wavelength")
    particles = result.get("particles", [])
    if isinstance(particles, Sequence) and not isinstance(particles, (str, bytes)):
        for particle in particles:
            if not isinstance(particle, dict):
                continue
            if "psd" in particle and "size_distribution" not in particle:
                particle["size_distribution"] = particle.pop("psd")
            distribution = particle.get("size_distribution")
            if isinstance(distribution, dict):
                if "r" in distribution and "size" not in distribution:
                    distribution["size"] = distribution.pop("r")
                if "dNdr" in distribution and "dndr" not in distribution:
                    distribution["dndr"] = distribution.pop("dNdr")
    result["schema_version"] = SCHEME_SCHEMA_VERSION
    return result


@dataclass(frozen=True)
class Scheme:
    """Complete typed request for a multi-particle optical scheme."""

    name: str
    wavelengths_um: tuple[float, ...]
    particles: tuple[ParticleComponent, ...]
    temperatures_k: tuple[float, ...] = ()
    interpolation: str = "linear"
    output: str = "bulk_optical_scheme.nc"
    schema_version: str = SCHEME_SCHEMA_VERSION
    output_settings: Optional[SchemeOutput] = None
    include_phase_matrix: bool = False
    scattering_angles_degrees: tuple[float, ...] = ()
    truncation_policy: str = "error"
    check_convergence: bool = True
    convergence_tolerance: float = 0.05
    strict_convergence: bool = False
    strict_qa: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != SCHEME_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEME_SCHEMA_VERSION!r}")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if not self.wavelengths_um:
            raise ValueError("at least one wavelength is required")
        if not self.particles:
            raise ValueError("at least one particle component is required")
        names = [particle.name for particle in self.particles]
        if len(names) != len(set(names)):
            raise ValueError("particle component names must be unique")
        if self.interpolation not in {"linear", "nearest"}:
            raise ValueError("interpolation must be 'linear' or 'nearest'")
        if self.truncation_policy not in {"error", "truncate"}:
            raise ValueError("truncation_policy must be 'error' or 'truncate'")
        if self.convergence_tolerance <= 0:
            raise ValueError("convergence_tolerance must be positive")
        settings = self.output_settings or SchemeOutput.from_value(self.output)
        object.__setattr__(self, "output_settings", settings)
        object.__setattr__(self, "output", settings.path)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        base_dir: Union[str, Path, None] = None,
    ) -> "Scheme":
        normalized = migrate_scheme_mapping(value)
        name = str(normalized.get("name", "bulk_optical_scheme")).strip()
        unit = str(normalized.get("wavelength_unit", "um")).strip().casefold()
        particles_value = normalized.get("particles")
        if not isinstance(particles_value, Sequence) or isinstance(particles_value, (str, bytes)):
            raise ValueError("particles must be a list")
        particles = tuple(
            ParticleComponent.from_mapping(item, index, base_dir=base_dir)
            for index, item in enumerate(particles_value)
            if isinstance(item, Mapping)
        )
        if len(particles) != len(particles_value):
            raise ValueError("every particle entry must be an object")
        temperatures_value = normalized.get("temperatures_k", [])
        if not isinstance(temperatures_value, Sequence) or isinstance(
            temperatures_value, (str, bytes)
        ):
            raise ValueError("temperatures_k must be a list")
        calculation = normalized.get("calculation", {})
        if not isinstance(calculation, Mapping):
            raise ValueError("calculation must be an object")
        if "include_mixture" in calculation or "include_mixture" in normalized:
            raise ValueError(
                "include_mixture is not supported in bulk_scheme; components are "
                "calculated and stored independently. Use combine_bulk_optics() "
                "explicitly for a custom aggregate."
            )
        angles = calculation.get(
            "scattering_angles_degrees",
            normalized.get("scattering_angles_degrees", []),
        )
        if not isinstance(angles, Sequence) or isinstance(angles, (str, bytes)):
            raise ValueError("scattering_angles_degrees must be a list")
        output_settings = SchemeOutput.from_value(
            normalized.get("output", "bulk_optical_scheme.nc")
        )
        return cls(
            name=name,
            wavelengths_um=_wavelengths(normalized.get("wavelengths"), unit),
            particles=particles,
            temperatures_k=tuple(_positive(item, "temperature") for item in temperatures_value),
            interpolation=str(normalized.get("interpolation", "linear")).casefold(),
            output=output_settings.path,
            schema_version=SCHEME_SCHEMA_VERSION,
            output_settings=output_settings,
            include_phase_matrix=bool(
                calculation.get(
                    "include_phase_matrix",
                    normalized.get("include_phase_matrix", False),
                )
            ),
            scattering_angles_degrees=tuple(float(item) for item in angles),
            truncation_policy=str(
                calculation.get(
                    "truncation_policy",
                    normalized.get("truncation_policy", "error"),
                )
            ).casefold(),
            check_convergence=bool(calculation.get("check_convergence", True)),
            convergence_tolerance=float(calculation.get("convergence_tolerance", 0.05)),
            strict_convergence=bool(calculation.get("strict_convergence", False)),
            strict_qa=bool(calculation.get("strict_qa", True)),
        )

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        base_dir: Union[str, Path, None] = None,
    ) -> "Scheme":
        return cls.from_mapping(value, base_dir=base_dir)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEME_SCHEMA_VERSION,
            "name": self.name,
            "wavelength_unit": "um",
            "wavelengths": list(self.wavelengths_um),
            "temperatures_k": list(self.temperatures_k),
            "interpolation": self.interpolation,
            "particles": [particle.to_dict() for particle in self.particles],
            "calculation": {
                "include_phase_matrix": self.include_phase_matrix,
                "scattering_angles_degrees": list(self.scattering_angles_degrees),
                "truncation_policy": self.truncation_policy,
                "check_convergence": self.check_convergence,
                "convergence_tolerance": self.convergence_tolerance,
                "strict_convergence": self.strict_convergence,
                "strict_qa": self.strict_qa,
            },
            "output": self.output_settings.to_dict(),
        }

    def write_json(self, path: Union[str, Path], *, indent: int = 2) -> Path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    def validate(self) -> tuple[object, ...]:
        """Validate particle-specific coordinates and return dependency queries."""

        from zju_scatt_interface.sources.planning import build_dependency_queries

        return build_dependency_queries(self)

    def plan(self, **kwargs: object) -> object:
        """Select source dependencies without downloading optical data."""

        from zju_scatt_interface.api import plan

        return plan(self, **kwargs)

    def build(self, **kwargs: object) -> object:
        """Build this scheme using the public workflow contract."""

        from zju_scatt_interface.api import build

        return build(self, **kwargs)


@_registration_required
def load_scheme(path: Union[str, Path]) -> Scheme:
    """Load and validate a JSON file or trusted Python dictionary script.

    Python files are executed and must define ``bulk_scheme`` (recommended),
    ``BULK_SCHEME``, or ``config`` as either a mapping or ``Scheme``.
    Only load Python scheme files that you trust.
    """

    source = Path(path).expanduser().resolve()
    if source.suffix.casefold() == ".py":
        namespace = runpy.run_path(str(source))
        value = next(
            (
                namespace[name]
                for name in ("bulk_scheme", "BULK_SCHEME", "config")
                if name in namespace
            ),
            None,
        )
        if isinstance(value, Scheme):
            return value
        if not isinstance(value, Mapping):
            raise ValueError(f"{source} must define bulk_scheme as a dictionary or Scheme")
        return Scheme.from_mapping(value, base_dir=source.parent)
    if source.suffix.casefold() != ".json":
        raise ValueError("scheme configuration must be a .py or .json file")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {source} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ValueError("the scheme configuration root must be a JSON object")
    return Scheme.from_mapping(value, base_dir=source.parent)
