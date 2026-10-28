"""Public exports for the config domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "Scheme": ("zju_scatt_interface.config.scheme", "Scheme"),
    "ParticleComponent": ("zju_scatt_interface.config.scheme", "ParticleComponent"),
    "IceComponent": ("zju_scatt_interface.config.scheme", "IceComponent"),
    "SeaSaltComponent": ("zju_scatt_interface.config.scheme", "SeaSaltComponent"),
    "DustComponent": ("zju_scatt_interface.config.scheme", "DustComponent"),
    "SuperSpheroidComponent": ("zju_scatt_interface.config.scheme", "SuperSpheroidComponent"),
    "BlackCarbonComponent": ("zju_scatt_interface.config.scheme", "BlackCarbonComponent"),
    "HygroscopicSphereComponent": (
        "zju_scatt_interface.config.scheme",
        "HygroscopicSphereComponent",
    ),
    "WaterCloudComponent": ("zju_scatt_interface.config.scheme", "WaterCloudComponent"),
    "SulfateComponent": ("zju_scatt_interface.config.scheme", "SulfateComponent"),
    "NitrateComponent": ("zju_scatt_interface.config.scheme", "NitrateComponent"),
    "OrganicCarbonComponent": ("zju_scatt_interface.config.scheme", "OrganicCarbonComponent"),
    "DatabaseRefractiveIndex": ("zju_scatt_interface.config.scheme", "DatabaseRefractiveIndex"),
    "FixedRefractiveIndex": ("zju_scatt_interface.config.scheme", "FixedRefractiveIndex"),
    "TableRefractiveIndex": ("zju_scatt_interface.config.scheme", "TableRefractiveIndex"),
    "BlackCarbonRefractiveIndex": (
        "zju_scatt_interface.config.scheme",
        "BlackCarbonRefractiveIndex",
    ),
    "BlackCarbonRefractiveIndexTables": (
        "zju_scatt_interface.config.scheme",
        "BlackCarbonRefractiveIndexTables",
    ),
    "SchemeOutput": ("zju_scatt_interface.config.scheme", "SchemeOutput"),
    "SCHEME_SCHEMA_VERSION": ("zju_scatt_interface.config.scheme", "SCHEME_SCHEMA_VERSION"),
    "load_scheme": ("zju_scatt_interface.config.scheme", "load_scheme"),
    "get_particle_profile": ("zju_scatt_interface.config.particles", "get_particle_profile"),
    "list_particle_profiles": ("zju_scatt_interface.config.particles", "list_particle_profiles"),
    "ParticleProfile": ("zju_scatt_interface.config.particles", "ParticleProfile"),
    "DataStructure": ("zju_scatt_interface.config.particles", "DataStructure"),
    "scheme_reference": ("zju_scatt_interface.config.reference", "scheme_reference"),
    "write_scheme_reference": ("zju_scatt_interface.config.reference", "write_scheme_reference"),
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
