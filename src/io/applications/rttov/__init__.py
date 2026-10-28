"""Public exports for the io.applications.rttov domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "write_rttov13_bulk_tables": (
        "zju_scatt_interface.io.applications.rttov.v13",
        "write_rttov13_bulk_tables",
    ),
    "write_rttov14_bulk_tables": (
        "zju_scatt_interface.io.applications.rttov.v14",
        "write_rttov14_bulk_tables",
    ),
    "build_rttov14_lookup_tables": (
        "zju_scatt_interface.io.applications.rttov.lookup",
        "build_rttov14_lookup_tables",
    ),
    "write_rttov14_lookup_slice": (
        "zju_scatt_interface.io.applications.rttov.lookup",
        "write_rttov14_lookup_slice",
    ),
    "rename_rttov14_species": (
        "zju_scatt_interface.io.applications.rttov.names",
        "rename_rttov14_species",
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
