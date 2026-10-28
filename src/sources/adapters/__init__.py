"""Public exports for the sources.adapters domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "get_particle_adapter": (
        "zju_scatt_interface.sources.adapters.registry",
        "get_particle_adapter",
    ),
    "resolve_particle_sources": (
        "zju_scatt_interface.sources.adapters.registry",
        "resolve_particle_sources",
    ),
    "resolve_plan_component_sources": (
        "zju_scatt_interface.sources.adapters.registry",
        "resolve_plan_component_sources",
    ),
    "interpolate_particle": (
        "zju_scatt_interface.sources.adapters.registry",
        "interpolate_particle",
    ),
    "AdapterResolution": ("zju_scatt_interface.sources.adapters.base", "AdapterResolution"),
    "AdapterProvenance": ("zju_scatt_interface.sources.adapters.base", "AdapterProvenance"),
    "AdapterSourceNode": ("zju_scatt_interface.sources.adapters.base", "AdapterSourceNode"),
    "ParticleAdapter": ("zju_scatt_interface.sources.adapters.base", "ParticleAdapter"),
    "AdapterError": ("zju_scatt_interface.sources.adapters.boundaries", "AdapterError"),
    "DatabaseBoundaryError": (
        "zju_scatt_interface.sources.adapters.boundaries",
        "DatabaseBoundaryError",
    ),
    "DatabaseBoundaryWarning": (
        "zju_scatt_interface.sources.adapters.boundaries",
        "DatabaseBoundaryWarning",
    ),
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    try:
        module, symbol = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module), symbol)
    globals()[name] = value
    return value
