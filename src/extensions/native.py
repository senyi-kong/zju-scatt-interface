"""Native model policies and independent serialization backends."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry


@dataclass(frozen=True)
class NativeModel:
    """Version-1 native template operations; unsupported capabilities stay explicit.

    validate(arrays, template) is required. Optional callbacks are read(path),
    template(path), bulk_fields(bulk, **options), phase(angles, p11, **options),
    and attribute(key, value) for backend-specific attribute representation.
    """

    validate: Callable
    read: Callable | None = None
    template: Callable | None = None
    bulk_fields: Callable | None = None
    phase: Callable | None = None
    attribute: Callable | None = None


_models = NamedRegistry[NativeModel]("native model")
_serializers = NamedRegistry("native serializer")
_loaded = False
_lock = RLock()


def _ensure_builtins():
    global _loaded
    with _lock:
        if not _loaded:
            from zju_scatt_interface.io.native_bindings import install

            install(_models, _serializers)
            _loaded = True


def register_native_model(name, model: NativeModel, *, aliases=()):
    _ensure_builtins()
    if not isinstance(model, NativeModel) or not callable(model.validate):
        raise ExtensionError("NativeModel.validate must be callable")
    for field in (model.read, model.template, model.bulk_fields, model.phase, model.attribute):
        if field is not None and not callable(field):
            raise ExtensionError("Native model capabilities must be callable")
    return _models.register(name, model, aliases=aliases)


def native_model(name):
    _ensure_builtins()
    return _models.get(name)


def native_capability(name, capability):
    callback = getattr(native_model(name), capability)
    if callback is None:
        raise ExtensionError(f"Native model {name!r} does not support {capability}")
    return callback


def register_serializer(name, serialize, *, aliases=()):
    """serialize(temporary_path, arrays, template) writes exactly that file."""
    _ensure_builtins()
    if not callable(serialize):
        raise ExtensionError("A serializer must be callable")
    return _serializers.register(name, serialize, aliases=aliases)


def serialize(path, arrays, template):
    _ensure_builtins()
    return _serializers.get(template["format"])(path, arrays, template)
