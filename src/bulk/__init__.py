"""Public exports for the bulk domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "PopulationResult": ("zju_scatt_interface.bulk.models", "PopulationResult"),
    "BulkDataset": ("zju_scatt_interface.bulk.models", "BulkDataset"),
    "EnsembleMemberResult": ("zju_scatt_interface.bulk.models", "EnsembleMemberResult"),
    "WeightedShapeEnsemble": ("zju_scatt_interface.bulk.ensemble", "WeightedShapeEnsemble"),
    "WeightedShapeMember": ("zju_scatt_interface.bulk.ensemble", "WeightedShapeMember"),
    "WeightedValues": ("zju_scatt_interface.bulk.ensemble", "WeightedValues"),
    "combine": ("zju_scatt_interface.bulk.ensemble", "combine"),
    "integrate": ("zju_scatt_interface.bulk.integration", "integrate"),
    "integrate_arrays": ("zju_scatt_interface.bulk.integration", "integrate_arrays"),
    "compute_population": ("zju_scatt_interface.bulk.workflow", "compute_population"),
    "build_dataset": ("zju_scatt_interface.bulk.workflow", "build_dataset"),
    "BulkTableConfig": ("zju_scatt_interface.bulk.tables", "BulkTableConfig"),
    "BulkTableResult": ("zju_scatt_interface.bulk.tables", "BulkTableResult"),
    "build_table": ("zju_scatt_interface.bulk.tables", "build_table"),
    "load_table_config": ("zju_scatt_interface.bulk.tables", "load_table_config"),
    "resolve_bulk_settings": ("zju_scatt_interface.bulk.tables", "resolve_bulk_settings"),
    "BulkDimension": ("zju_scatt_interface.bulk.grid", "BulkDimension"),
    "SingleBulkScheme": ("zju_scatt_interface.bulk.grid", "SingleBulkScheme"),
    "MultiBulkScheme": ("zju_scatt_interface.bulk.grid", "MultiBulkScheme"),
    "BulkGrid": ("zju_scatt_interface.bulk.grid", "BulkGrid"),
    "MultiBulkGrid": ("zju_scatt_interface.bulk.grid", "MultiBulkGrid"),
    "build_grid": ("zju_scatt_interface.bulk.grid", "build_grid"),
    "build_grids": ("zju_scatt_interface.bulk.grid", "build_grids"),
    "load_grid_scheme": ("zju_scatt_interface.bulk.grid", "load_grid_scheme"),
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
