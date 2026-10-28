"""config / reference domain implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    list_particle_profiles,
)
from zju_scatt_interface.config.scheme import SCHEME_SCHEMA_VERSION

TYPED_COMPONENTS = {
    "encapsulated_fractal_aggregates_black_carbon": "BlackCarbonComponent",
    "super_spheroid": "DustComponent or SuperSpheroidComponent",
    "coated_super_spheroid_seasalt": "SeaSaltComponent",
    "super_spheroid_ice": "IceComponent",
    "sphere_sulfate": "SulfateComponent",
    "sphere_nitrate": "NitrateComponent",
    "sphere_organic_carbon": "OrganicCarbonComponent",
    "sphere_water_cloud": "WaterCloudComponent",
}


@_registration_required
def scheme_reference(particle_type: Optional[str] = None) -> dict[str, object]:
    """Return the authoritative GPT/user-facing schema and command contract."""

    profiles = (
        [get_particle_profile(particle_type)]
        if particle_type is not None
        else list(list_particle_profiles())
    )
    return {
        "reference_name": "zju_scatt_scheme_and_command_reference",
        "schema_version": SCHEME_SCHEMA_VERSION,
        "safety_rules": [
            "Never invent a particle_type or parameter.",
            "Never supply derived refractive index for wavelength-based profiles.",
            "For grid-based profiles, wavelength is a wrapper coordinate; the native "
            "database lookup remains refractive-index based.",
            "Never execute Python from JSON. Pass only evaluated size/dndr arrays.",
            "Never extrapolate outside a documented coordinate range.",
            "Never expose registration/session tokens in schemes, reports, or chat.",
        ],
        "units": {
            "wavelength_input": ["nm", "um", "cm-1"],
            "wavelength_normalized": "um",
            "wavenumber_conversion": "wavelength_um = 10000 / wavenumber_cm-1",
            "size_input": ["nm", "um"],
            "size_normalized": "um",
            "dndr": "cm-3 per represented size bin",
            "bulk_coefficient": "m-1",
            "relative_humidity": "1 (fraction 0..1, never percent)",
            "phase_matrix": "1",
            "scattering_angle": "degree",
            "temperature": "K",
        },
        "size_definitions": {
            "volume_equivalent_sphere_radius": (
                "radius of the sphere having the same particle volume"
            ),
            "maximum_dimension_radius": ("one half of the particle geometric maximum dimension"),
            "default": "volume_equivalent_sphere_radius",
            "conversion_rule": ("conversion requires a verified particle-specific geometry"),
        },
        "scheme_shape": {
            "required": ["schema_version", "name", "wavelengths", "particles"],
            "root_fields": {
                "schema_version": {"type": "string", "const": "1.0"},
                "name": {"type": "string"},
                "wavelength_unit": {
                    "type": "string",
                    "enum": ["nm", "um", "cm-1"],
                    "default": "um",
                },
                "wavelengths": {
                    "one_of": [
                        {"type": "array", "items": "positive number"},
                        {
                            "type": "object",
                            "required": ["min", "max", "step"],
                        },
                    ]
                },
                "particles": {
                    "type": "array",
                    "items": {
                        "required": [
                            "name",
                            "particle_type",
                            "size_distribution",
                            "refractive_index",
                        ]
                    },
                },
                "calculation": {
                    "fields": [
                        "include_phase_matrix",
                        "scattering_angles_degrees",
                        "truncation_policy",
                        "check_convergence",
                        "convergence_tolerance",
                        "strict_convergence",
                        "strict_qa",
                    ]
                },
                "output": {
                    "fields": [
                        "path",
                        "format",
                        "compression",
                        "compression_level",
                        "shuffle",
                        "chunk_wavelength",
                        "atomic",
                    ],
                    "format_enum": ["netcdf4", "hdf5"],
                },
            },
            "size_distribution": {
                "inline_required": ["size", "dndr"],
                "file_alternative": "file plus variable/column names",
                "size_unit_enum": ["nm", "um"],
                "size_definition_enum": [
                    "volume_equivalent_sphere_radius",
                    "maximum_dimension_radius",
                ],
                "dndr_unit_const": "cm-3",
                "integration_mode_const": "discrete_bin",
            },
            "weighted_value": {
                "required": ["values", "weights"],
                "rules": [
                    "equal lengths",
                    "finite non-negative weights",
                    "positive weight sum",
                    "weights are normalized by the interface",
                ],
            },
        },
        "commands": {
            "register": "zju-scatt register",
            "describe_all": "zju-scatt describe --json",
            "describe_one": "zju-scatt describe PARTICLE_TYPE --json",
            "validate": "zju-scatt bulk-opt validate SCHEME.json --report validate.json",
            "plan": (
                "zju-scatt bulk-opt plan SCHEME.json --workspace zju_scatt_data --report plan.json"
            ),
            "plan_dry_run": ("zju-scatt bulk-opt plan SCHEME.json --dry-run --json"),
            "build_netcdf": (
                "zju-scatt bulk-opt build SCHEME.json --format netcdf4 --report build.json"
            ),
            "build_hdf5": (
                "zju-scatt bulk-opt build SCHEME.json --format hdf5 --report build.json"
            ),
            "build_offline": ("zju-scatt bulk-opt build SCHEME.json --offline --resume"),
            "local_source": ("zju-scatt bulk-opt build SCHEME.json --source COMPONENT=PATH"),
        },
        "particle_profiles": [
            {
                **profile.to_dict(),
                "typed_component": TYPED_COMPONENTS.get(profile.particle_type, "ParticleComponent"),
            }
            for profile in profiles
        ],
    }


@_registration_required
def write_scheme_reference(
    path: Union[str, Path],
    *,
    particle_type: Optional[str] = None,
) -> Path:
    """Write the machine-readable reference as deterministic JSON."""

    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            scheme_reference(particle_type),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return target
