"""Public exports for the optics.retrieval domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "interpolate_downloaded_particle_series": (
        "zju_scatt_interface.optics.retrieval.workflow",
        "interpolate_downloaded_particle_series",
    ),
    "verify_native_schema": ("zju_scatt_interface.optics.retrieval.native", "verify_native_schema"),
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
