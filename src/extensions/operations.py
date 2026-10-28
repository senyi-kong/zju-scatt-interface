"""Registered public operations. Built-ins load once, before user registration."""

from threading import RLock

from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry, TypeRegistry

_operations = {
    name: TypeRegistry(name)
    for name in ("build", "plan", "validate", "plot", "write", "interpolate")
}
_plotters = NamedRegistry("plot kind")
_lock = RLock()
_loaded = False


def _ensure_builtins():
    global _loaded
    with _lock:
        if not _loaded:
            from zju_scatt_interface.extensions.builtins import install

            install(_operations, _plotters)
            _loaded = True


def register_operation(operation, product_type, handler):
    """Add a handler(value, **options); write handlers also receive path."""
    _ensure_builtins()
    if operation not in _operations:
        raise ExtensionError(f"Unknown operation {operation!r}")
    return _operations[operation].register(product_type, handler)


def dispatch(operation, value, *args, **options):
    _ensure_builtins()
    return _operations[operation](value, *args, **options)


def register_plotter(kind, handler):
    _ensure_builtins()
    if not callable(handler):
        raise ExtensionError("Plot handler must be callable")
    return _plotters.register(kind, handler)


def plot_with_kind(kind, value, **options):
    _ensure_builtins()
    return _plotters.get(kind)(value, **options)
