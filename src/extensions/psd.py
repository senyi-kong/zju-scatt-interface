"""Named PSD constructors shared by configurable table workflows."""

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry


@dataclass(frozen=True)
class PSDContext:
    lower_um: float
    upper_um: float
    concentration_cm3: float = 1.0
    reference: bool = False
    conditional_reference: bool = False


@dataclass(frozen=True)
class PSDFactory:
    """create(config, context) validates its options and returns SizeDistribution."""

    create: Callable


_factories = NamedRegistry[PSDFactory]("PSD factory")
_lock = RLock()
_loaded = False


def _ensure_builtins():
    global _loaded
    with _lock:
        if not _loaded:
            from zju_scatt_interface.psd.factories import analytical_distribution

            for name in ("lognormal", "gamma"):
                _factories.register(name, PSDFactory(analytical_distribution))
            _loaded = True


def register_psd(name, factory: PSDFactory, *, aliases=()):
    _ensure_builtins()
    if not isinstance(factory, PSDFactory) or not callable(factory.create):
        raise ExtensionError("PSDFactory.create must be callable")
    return _factories.register(name, factory, aliases=aliases)


def create_psd(config, context: PSDContext):
    from zju_scatt_interface.psd.models import SizeDistribution

    _ensure_builtins()
    canonical = _factories.canonical_name(config["type"])
    factory = _factories.get(canonical)
    config = {**config, "type": canonical}
    result = factory.create(dict(config), context)
    if not isinstance(result, SizeDistribution):
        raise ExtensionError("A PSD factory must return SizeDistribution")
    return result


def has_psd(name):
    _ensure_builtins()
    return _factories.contains(name)
