"""Public exports for the psd domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "SizeDistribution": ("zju_scatt_interface.psd.models", "SizeDistribution"),
    "RemapReport": ("zju_scatt_interface.psd.models", "RemapReport"),
    "lognormal_psd": ("zju_scatt_interface.psd.analytical", "lognormal_psd"),
    "gamma_psd": ("zju_scatt_interface.psd.analytical", "gamma_psd"),
    "check_size_coverage": ("zju_scatt_interface.psd.coverage", "check_size_coverage"),
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
