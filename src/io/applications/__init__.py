"""Public exports for the io.applications domain. Implementations live in its modules."""

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
    "validate_rttov14_optical_table": (
        "zju_scatt_interface.io.applications.rttov.v14",
        "validate_rttov14_optical_table",
    ),
    "build_rttov14_lookup_tables": (
        "zju_scatt_interface.io.applications.rttov.lookup",
        "build_rttov14_lookup_tables",
    ),
    "write_rttov14_lookup_slice": (
        "zju_scatt_interface.io.applications.rttov.lookup",
        "write_rttov14_lookup_slice",
    ),
    "validate_rttov14_lookup_table": (
        "zju_scatt_interface.io.applications.rttov.lookup",
        "validate_rttov14_lookup_table",
    ),
    "rename_rttov14_species": (
        "zju_scatt_interface.io.applications.rttov.names",
        "rename_rttov14_species",
    ),
    "write_arts_bulk_tables": (
        "zju_scatt_interface.io.applications.arts.bulk",
        "write_arts_bulk_tables",
    ),
    "validate_arts_bulk_table": (
        "zju_scatt_interface.io.applications.arts.bulk",
        "validate_arts_bulk_table",
    ),
    "write_crtm_ir_bulk_tables": (
        "zju_scatt_interface.io.applications.crtm.ir",
        "write_crtm_ir_bulk_tables",
    ),
    "validate_crtm_ir_optical_table": (
        "zju_scatt_interface.io.applications.crtm.ir",
        "validate_crtm_ir_optical_table",
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
