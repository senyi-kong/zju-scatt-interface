"""Public exports for the io domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "write": ("zju_scatt_interface.io.products", "write"),
    "read": ("zju_scatt_interface.io.canonical", "read"),
    "validate_file": ("zju_scatt_interface.io.canonical", "validate_file"),
    "OutputOptions": ("zju_scatt_interface.io.canonical", "OutputOptions"),
    "OutputValidationReport": ("zju_scatt_interface.io.canonical", "OutputValidationReport"),
    "OpticalTableColumn": ("zju_scatt_interface.io.tables", "OpticalTableColumn"),
    "OpticalTableFormat": ("zju_scatt_interface.io.tables", "OpticalTableFormat"),
    "write_formatted_optical_output": (
        "zju_scatt_interface.io.tables",
        "write_formatted_optical_output",
    ),
    "load_optical_table_format": ("zju_scatt_interface.io.tables", "load_optical_table_format"),
    "export_bulk_optics": ("zju_scatt_interface.io.custom", "export_bulk_optics"),
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
