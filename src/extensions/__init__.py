"""Explicit extension contracts, registered during application startup.

Import extension modules explicitly before loading configurations or building a CLI.
No module scanning, filesystem execution, or automatic third-party imports occur.
"""

from importlib import import_module

CONTRACT_VERSION = 1
_EXPORTS = {
    "ExtensionError": "registry",
    "ParticleDefinition": "particles",
    "register_particle": "particles",
    "get_particle_definition": "particles",
    "register_operation": "operations",
    "register_plotter": "operations",
    "PSDFactory": "psd",
    "PSDContext": "psd",
    "create_psd": "psd",
    "register_psd": "psd",
    "Exporter": "exporters",
    "register_exporter": "exporters",
    "export": "exporters",
    "validate_export": "exporters",
    "Command": "commands",
    "register_command": "commands",
    "NativeModel": "native",
    "register_native_model": "native",
    "register_serializer": "native",
}
__all__ = ["CONTRACT_VERSION", *_EXPORTS]


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    globals()[name] = value
    return value
