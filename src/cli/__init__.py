"""Public exports for the cli domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "main": ("zju_scatt_interface.cli.main", "main"),
    "validate_arguments": ("zju_scatt_interface.cli.main", "validate_arguments"),
    "build_parser": ("zju_scatt_interface.cli.parser", "build_parser"),
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
