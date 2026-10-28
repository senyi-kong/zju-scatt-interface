"""One registration binds a particle's scientific metadata and workflow behavior."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry


@dataclass(frozen=True)
class ParticleDefinition:
    """Version-1 particle contract; callbacks use the existing optical/PSD units.

    planner(scheme, component) returns (coordinates, retrieval_parameters).
    calculation_inputs(component) returns (parameters, refractive_index_tables).
    adapter_factory() returns a ParticleAdapter; axes use canonical parameter names.
    defaults(source_paths, preset=...) is optional: absent defaults are an error,
    never an assumed atmospheric population.
    """

    profile: object
    adapter_factory: Callable
    axes: tuple[str, ...]
    planner: Callable
    calculation_inputs: Callable
    defaults: Callable | None = None
    interpolation_policy: Callable | None = None
    downloaded_interpolator: Callable | None = None
    ensemble_axes: tuple[str, ...] = ()
    table_settings: Callable | None = None


_particles = NamedRegistry[ParticleDefinition]("particle")
_lock = RLock()
_loaded = False


def _ensure_builtins():
    global _loaded
    with _lock:
        if not _loaded:
            from zju_scatt_interface.sources.adapters.builtins import definitions

            for definition in definitions():
                _add(definition)
            _loaded = True


def _add(definition):
    from zju_scatt_interface.config.particles import ParticleProfile

    if not isinstance(definition, ParticleDefinition) or not isinstance(
        definition.profile, ParticleProfile
    ):
        raise ExtensionError("ParticleDefinition requires a ParticleProfile")
    if not isinstance(definition.axes, tuple) or len(set(definition.axes)) != len(definition.axes):
        raise ExtensionError("Particle axes must be a tuple of unique names")
    if any(not isinstance(axis, str) or not axis for axis in definition.axes):
        raise ExtensionError("Particle axes must be nonempty strings")
    names = {parameter.name for parameter in definition.profile.parameters}
    if not set(definition.axes).issubset(names):
        raise ExtensionError("Particle axes must be declared in the profile")
    for callback in (definition.adapter_factory, definition.planner, definition.calculation_inputs):
        if not callable(callback):
            raise ExtensionError(
                "Particle factory, planner and calculation_inputs must be callable"
            )
    for callback in (
        definition.defaults,
        definition.interpolation_policy,
        definition.downloaded_interpolator,
        definition.table_settings,
    ):
        if callback is not None and not callable(callback):
            raise ExtensionError("Optional particle capabilities must be callable")
    if not set(definition.ensemble_axes).issubset(names):
        raise ExtensionError("Ensemble axes must be declared in the profile")
    profile = definition.profile
    return _particles.register(profile.particle_type, definition, aliases=profile.aliases)


def register_particle(definition: ParticleDefinition):
    """Register before use; aliases cannot shadow built-ins or other extensions."""
    _ensure_builtins()
    return _add(definition)


def get_particle_definition(name):
    _ensure_builtins()
    return _particles.get(name)


def particle_definitions():
    _ensure_builtins()
    return tuple(value for _, value in _particles.items())
