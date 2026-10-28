"""bulk / grid domain implementation."""

from __future__ import annotations

import math
import re
import runpy
from dataclasses import dataclass
from functools import reduce
from itertools import product
from operator import mul
from pathlib import Path
from typing import Any, Mapping, Sequence

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.bulk.models import PopulationResult
from zju_scatt_interface.bulk.workflow import (
    _component_calculation_inputs,
    compute_population,
)
from zju_scatt_interface.config.scheme import ParticleComponent

_DIMENSION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_WAVELENGTH_PARAMETERS = {"wavelength", "wavelength_um"}
_RESERVED_DIMENSIONS = {
    "size",
    "radius",
    "particle_size",
    "psd_size",
    "ensemble_member",
    "sca_angle",
    "beta_ext",
    "beta_sca",
    "beta_abs",
    "ssa",
    "g",
    "number_concentration",
}


@dataclass(frozen=True)
class BulkDimension:
    """One retained output axis and its explicit coordinate values."""

    name: str
    coordinates: tuple[float | str, ...]
    unit: str = "1"
    description: str = ""
    parameter: str | None = None

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not _DIMENSION_NAME.fullmatch(name):
            raise ValueError(
                "dimension name must start with a letter and contain only "
                "letters, numbers, and underscores"
            )
        if name in _RESERVED_DIMENSIONS:
            raise ValueError(f"dimension name {name!r} is reserved")
        values = tuple(self.coordinates)
        if not values:
            raise ValueError(f"dimension {name!r} requires coordinate values")
        normalized: list[float | str] = []
        for value in values:
            if isinstance(value, bool):
                raise ValueError(f"dimension {name!r} cannot contain booleans")
            if isinstance(value, (int, float)):
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError(f"dimension {name!r} coordinates must be finite")
                normalized.append(number)
            elif isinstance(value, str) and value:
                normalized.append(value)
            else:
                raise ValueError(f"dimension {name!r} coordinates must be numbers or strings")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"dimension {name!r} coordinates must be unique")
        parameter = str(self.parameter or name).strip()
        if not parameter:
            raise ValueError("dimension parameter cannot be empty")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "coordinates", tuple(normalized))
        object.__setattr__(self, "parameter", parameter)

    @property
    def size(self) -> int:
        return len(self.coordinates)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BulkDimension":
        coordinates = value.get("coordinates", value.get("values"))
        if not isinstance(coordinates, Sequence) or isinstance(coordinates, (str, bytes)):
            raise ValueError("dimension coordinates must be a list")
        declared_size = value.get("size")
        if declared_size is not None and int(declared_size) != len(coordinates):
            raise ValueError(
                f"dimension {value.get('name')!r} declares size {declared_size} "
                f"but provides {len(coordinates)} coordinates"
            )
        name = str(value.get("name", "")).strip()
        default_unit = (
            "um"
            if str(value.get("parameter", name)) in _WAVELENGTH_PARAMETERS
            else "K"
            if str(value.get("parameter", name)) in {"temperature", "temperature_k"}
            else "1"
        )
        return cls(
            name=name,
            coordinates=tuple(coordinates),
            unit=str(value.get("unit", default_unit)),
            description=str(value.get("description", "")),
            parameter=(str(value["parameter"]) if value.get("parameter") is not None else None),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "size": self.size,
            "coordinates": list(self.coordinates),
            "unit": self.unit,
            "description": self.description,
            "parameter": self.parameter,
        }


@dataclass(frozen=True)
class SingleBulkScheme:
    """A retained multidimensional bulk-optics grid for one particle type."""

    name: str
    component: ParticleComponent
    dimensions: tuple[BulkDimension, ...]

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("single bulk scheme name cannot be empty")
        if not isinstance(self.component, ParticleComponent):
            raise TypeError("component must be a ParticleComponent")
        if not self.dimensions:
            raise ValueError("single bulk scheme requires at least one dimension")
        names = [dimension.name for dimension in self.dimensions]
        parameters = [str(dimension.parameter) for dimension in self.dimensions]
        if len(names) != len(set(names)):
            raise ValueError("bulk dimension names must be unique")
        if len(parameters) != len(set(parameters)):
            raise ValueError("bulk dimension parameters must be unique")
        wavelength_count = sum(parameter in _WAVELENGTH_PARAMETERS for parameter in parameters)
        if wavelength_count != 1:
            raise ValueError("single bulk scheme requires exactly one wavelength dimension")
        wavelength_dimension = next(
            dimension
            for dimension in self.dimensions
            if dimension.parameter in _WAVELENGTH_PARAMETERS
        )
        if wavelength_dimension.unit != "um":
            raise ValueError("wavelength dimension unit must be um")
        if any(
            not isinstance(value, float) or value <= 0.0
            for value in wavelength_dimension.coordinates
        ):
            raise ValueError("wavelength dimension coordinates must be positive numbers")

    @property
    def particle_type(self) -> str:
        return self.component.particle_type

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(dimension.size for dimension in self.dimensions)

    @property
    def point_count(self) -> int:
        return reduce(mul, self.shape, 1)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        index: int = 0,
        base_dir: str | Path | None = None,
    ) -> "SingleBulkScheme":
        dimensions_value = value.get("dimensions")
        if not isinstance(dimensions_value, Sequence) or isinstance(dimensions_value, (str, bytes)):
            raise ValueError(f"particles[{index}].dimensions must be a list")
        dimensions = tuple(
            BulkDimension.from_mapping(item)
            for item in dimensions_value
            if isinstance(item, Mapping)
        )
        if len(dimensions) != len(dimensions_value):
            raise ValueError(f"particles[{index}].dimensions entries must be objects")
        component_mapping = {key: item for key, item in value.items() if key != "dimensions"}
        component = ParticleComponent.from_mapping(
            component_mapping, index=index, base_dir=base_dir
        )
        return cls(component.name, component, dimensions)

    def to_dict(self) -> dict[str, object]:
        value = self.component.to_dict()
        value["dimensions"] = [dimension.to_dict() for dimension in self.dimensions]
        return value

    def build(self, source_paths: object = None, **kwargs: object) -> "BulkGrid":
        return build_grid(self, source_paths=source_paths, **kwargs)


@dataclass(frozen=True)
class BulkGrid:
    """Row-major calculation results over a ``SingleBulkScheme`` grid."""

    name: str
    particle_type: str
    dimensions: tuple[BulkDimension, ...]
    calculations: tuple[PopulationResult, ...]

    def __post_init__(self) -> None:
        expected = reduce(mul, (dimension.size for dimension in self.dimensions), 1)
        if len(self.calculations) != expected:
            raise ValueError(
                f"grid shape requires {expected} calculations, received {len(self.calculations)}"
            )
        if any(
            calculation.particle_type != self.particle_type for calculation in self.calculations
        ):
            raise ValueError("grid calculations must have one particle type")

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(dimension.size for dimension in self.dimensions)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "particle_type": self.particle_type,
            "dimensions": [dimension.to_dict() for dimension in self.dimensions],
            "shape": list(self.shape),
            "calculations": [value.to_dict() for value in self.calculations],
        }


@dataclass(frozen=True)
class MultiBulkScheme:
    """Multiple independent particle-type bulk grids."""

    name: str
    particles: tuple[SingleBulkScheme, ...]

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("multi bulk scheme name cannot be empty")
        if not self.particles:
            raise ValueError("multi bulk scheme requires particle grids")
        names = [particle.name for particle in self.particles]
        if len(names) != len(set(names)):
            raise ValueError("single bulk scheme names must be unique")

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        base_dir: str | Path | None = None,
    ) -> "MultiBulkScheme":
        particles_value = value.get("particles")
        if not isinstance(particles_value, Sequence) or isinstance(particles_value, (str, bytes)):
            raise ValueError("particles must be a list")
        particles = tuple(
            SingleBulkScheme.from_mapping(item, index=index, base_dir=base_dir)
            for index, item in enumerate(particles_value)
            if isinstance(item, Mapping)
        )
        if len(particles) != len(particles_value):
            raise ValueError("particles entries must be objects")
        return cls(str(value.get("name", "multidimensional_bulk_optics")), particles)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "particles": [particle.to_dict() for particle in self.particles],
        }

    def build(
        self,
        source_paths: Mapping[str, object] | object = None,
        **kwargs: object,
    ) -> "MultiBulkGrid":
        return build_grids(self, source_paths=source_paths, **kwargs)


@dataclass(frozen=True)
class MultiBulkGrid:
    """Independent multidimensional grids for multiple particle types."""

    name: str
    components: Mapping[str, BulkGrid]

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("multi bulk grid result requires components")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "components": {name: value.to_dict() for name, value in self.components.items()},
        }


@_registration_required
def build_grid(
    scheme: SingleBulkScheme,
    *,
    source_paths: object = None,
    include_phase_matrix: bool = False,
    target_angles_degrees: Sequence[float] | None = None,
    phase_normalization: str = "preserve",
    truncation_policy: str = "error",
    check_convergence: bool = True,
    convergence_tolerance: float = 0.05,
    strict_convergence: bool = False,
    strict_qa: bool = True,
) -> BulkGrid:
    """Expand one declared grid and calculate every coordinate combination."""

    if not isinstance(scheme, SingleBulkScheme):
        raise TypeError("scheme must be a SingleBulkScheme")
    sources = source_paths if source_paths is not None else scheme.component.source
    if sources is None:
        raise ValueError(
            f"single bulk scheme {scheme.name!r} requires source_paths or component.source"
        )
    base_parameters, tables = _component_calculation_inputs(scheme.component)
    shape_ensemble = (
        tuple(scheme.component.shape_ensemble) if scheme.component.shape_ensemble else None
    )
    calculations: list[PopulationResult] = []
    for coordinate_values in product(*(dimension.coordinates for dimension in scheme.dimensions)):
        point = {
            str(dimension.parameter): value
            for dimension, value in zip(scheme.dimensions, coordinate_values)
        }
        wavelength_key = next(name for name in point if name in _WAVELENGTH_PARAMETERS)
        wavelength = point.pop(wavelength_key)
        parameters = {**base_parameters, **point}
        calculations.append(
            compute_population(
                scheme.component.particle_type,
                sources,
                scheme.component.size_distribution,
                wavelength=wavelength,
                parameters=parameters,
                shape_ensemble=shape_ensemble,
                refractive_index_tables=tables,
                size_definition=scheme.component.size_distribution.size_definition,
                truncation_policy=truncation_policy,
                include_phase_matrix=include_phase_matrix,
                target_angles_degrees=target_angles_degrees,
                phase_normalization=phase_normalization,
                check_convergence=check_convergence,
                convergence_tolerance=convergence_tolerance,
                strict_convergence=strict_convergence,
                strict_qa=strict_qa,
            )
        )
    return BulkGrid(
        scheme.name,
        scheme.component.particle_type,
        scheme.dimensions,
        tuple(calculations),
    )


@_registration_required
def build_grids(
    scheme: MultiBulkScheme,
    *,
    source_paths: Mapping[str, object] | object = None,
    **kwargs: object,
) -> MultiBulkGrid:
    """Build every particle grid independently without cross-particle mixing."""

    if not isinstance(scheme, MultiBulkScheme):
        raise TypeError("scheme must be a MultiBulkScheme")
    components: dict[str, BulkGrid] = {}
    for particle in scheme.particles:
        if isinstance(source_paths, Mapping):
            sources = source_paths.get(particle.name, source_paths.get(particle.particle_type))
        else:
            sources = source_paths
        components[particle.name] = build_grid(particle, source_paths=sources, **kwargs)
    return MultiBulkGrid(scheme.name, components)


@_registration_required
def load_grid_scheme(path: str | Path) -> MultiBulkScheme:
    """Load a trusted Python script defining ``multi_bulk_scheme``."""

    source = Path(path).expanduser().resolve()
    if source.suffix.casefold() != ".py":
        raise ValueError("multidimensional bulk scheme must be a Python .py file")
    namespace = runpy.run_path(str(source))
    value = next(
        (
            namespace[name]
            for name in ("multi_bulk_scheme", "MULTI_BULK_SCHEME")
            if name in namespace
        ),
        None,
    )
    if isinstance(value, MultiBulkScheme):
        return value
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{source} must define multi_bulk_scheme as a dictionary or MultiBulkScheme"
        )
    return MultiBulkScheme.from_mapping(value, base_dir=source.parent)
