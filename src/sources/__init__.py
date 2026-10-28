"""Public exports for the sources domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "DependencyPlan": ("zju_scatt_interface.sources.planning", "DependencyPlan"),
    "WorkspaceLayout": ("zju_scatt_interface.sources.planning", "WorkspaceLayout"),
    "prepare_scheme_dependencies": (
        "zju_scatt_interface.sources.planning",
        "prepare_scheme_dependencies",
    ),
    "build_dependency_queries": (
        "zju_scatt_interface.sources.planning",
        "build_dependency_queries",
    ),
    "select_shape_grid_sources": (
        "zju_scatt_interface.sources.selection",
        "select_shape_grid_sources",
    ),
    "inspect_source_file": ("zju_scatt_interface.sources.validation", "inspect_source_file"),
    "SourceInspection": ("zju_scatt_interface.sources.validation", "SourceInspection"),
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
