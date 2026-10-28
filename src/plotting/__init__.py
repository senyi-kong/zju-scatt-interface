"""Public exports for the plotting domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "OpticalPlotStyle": ("zju_scatt_interface.plotting.single", "OpticalPlotStyle"),
    "plot_single_particle_optics": (
        "zju_scatt_interface.plotting.single",
        "plot_single_particle_optics",
    ),
    "plot_single_scattering": ("zju_scatt_interface.plotting.single", "plot_single_scattering"),
    "plot_bulk_optics": ("zju_scatt_interface.plotting.bulk", "plot_bulk_optics"),
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
