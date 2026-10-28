"""Small explicit registries; registration never replaces an existing implementation."""

from __future__ import annotations

from functools import singledispatch
from threading import RLock
from typing import Generic, TypeVar

T = TypeVar("T")


class ExtensionError(ValueError):
    """An extension has an invalid contract or conflicts with another extension."""


class NamedRegistry(Generic[T]):
    """Atomic registration of a canonical name and aliases, in insertion order."""

    def __init__(self, category):
        self.category = category
        self._entries = {}
        self._aliases = {}
        self._lock = RLock()

    @staticmethod
    def normalize(name):
        if not isinstance(name, str) or not name.strip():
            raise ExtensionError("Extension names must be nonempty strings")
        return name.strip().casefold().replace("-", "_").replace(" ", "_")

    def register(self, name, implementation: T, *, aliases=()):
        if isinstance(aliases, (str, bytes)):
            raise ExtensionError("aliases must be a sequence of names, not a string")
        key = self.normalize(name)
        keys = {self.normalize(item) for item in (name, *aliases)}
        with self._lock:
            conflicts = keys.intersection(self._aliases)
            if conflicts:
                raise ExtensionError(f"Duplicate {self.category}: {', '.join(sorted(conflicts))}")
            self._entries[key] = implementation
            self._aliases.update({alias: key for alias in keys})
        return implementation

    def get(self, name) -> T:
        key = self.normalize(name)
        with self._lock:
            try:
                return self._entries[self._aliases[key]]
            except KeyError:
                raise ExtensionError(f"Unknown {self.category} {name!r}") from None

    def items(self):
        with self._lock:
            return tuple(self._entries.items())

    def contains(self, name):
        with self._lock:
            return self.normalize(name) in self._aliases

    def canonical_name(self, name):
        self.get(name)
        with self._lock:
            return self._aliases[self.normalize(name)]


class TypeRegistry:
    """Type dispatch with deterministic MRO and rejection of ambiguous virtual bases."""

    def __init__(self, category):
        self.category = category
        self._handlers = {}
        self._dispatch = singledispatch(self._unsupported)
        self._lock = RLock()

    def _unsupported(self, value, *args, **kwargs):
        raise TypeError(f"Unsupported {self.category} product: {type(value).__name__}")

    def register(self, product_type, handler):
        if not isinstance(product_type, type) or not callable(handler):
            raise ExtensionError("A type handler requires a class and a callable")
        with self._lock:
            if product_type in self._handlers:
                raise ExtensionError(
                    f"Duplicate {self.category} handler for {product_type.__name__}"
                )
            self._dispatch.register(product_type, handler)
            self._handlers[product_type] = handler
        return handler

    def resolve(self, value):
        with self._lock:
            try:
                return self._dispatch.dispatch(type(value))
            except RuntimeError as exc:
                raise ExtensionError(
                    f"Ambiguous {self.category} handlers for {type(value).__name__}"
                ) from exc

    def __call__(self, value, *args, **kwargs):
        return self.resolve(value)(value, *args, **kwargs)
