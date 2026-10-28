"""Public exports for the optics domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "SingleParticleOptics": ("zju_scatt_interface.optics.models", "SingleParticleOptics"),
    "BulkOptics": ("zju_scatt_interface.optics.models", "BulkOptics"),
    "load_single": ("zju_scatt_interface.optics.loading", "load_single"),
    "OpticalNode": ("zju_scatt_interface.optics.interpolation", "OpticalNode"),
    "OpticalSourceRequest": ("zju_scatt_interface.optics.interpolation", "OpticalSourceRequest"),
    "InterpolatedOpticalProduct": (
        "zju_scatt_interface.optics.interpolation",
        "InterpolatedOpticalProduct",
    ),
    "InterpolationProvenance": (
        "zju_scatt_interface.optics.interpolation",
        "InterpolationProvenance",
    ),
    "InterpolationError": ("zju_scatt_interface.optics.interpolation", "InterpolationError"),
    "interpolate_nodes": ("zju_scatt_interface.optics.interpolation", "interpolate_nodes"),
    "interpolate_sources": ("zju_scatt_interface.optics.interpolation", "interpolate_sources"),
    "ComplexRefractiveIndex": (
        "zju_scatt_interface.optics.refractive_index",
        "ComplexRefractiveIndex",
    ),
    "RefractiveIndexTable": ("zju_scatt_interface.optics.refractive_index", "RefractiveIndexTable"),
    "default_refractive_index_paths": (
        "zju_scatt_interface.optics.refractive_index",
        "default_refractive_index_paths",
    ),
    "wavelength_to_um": ("zju_scatt_interface.optics.refractive_index", "wavelength_to_um"),
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
