"""config / particles domain implementation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Tuple

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)


class DataStructure(str, Enum):
    """How a particle family is organized in the L1 database."""

    GRID_BASED = "grid_based"
    WAVELENGTH_BASED = "wavelength_based"


class ParameterRole(str, Enum):
    """Whether a public coordinate may or must be supplied by a user."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    DERIVED = "derived"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ParameterSpec:
    """One canonical public coordinate and its scientific constraints."""

    name: str
    role: ParameterRole
    description: str
    unit: str = "1"
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Tuple[object, ...] = ()
    grid_values: Tuple[float, ...] = ()
    aliases: Tuple[str, ...] = ()
    source_variable: Optional[str] = None
    source_scale: float = 1.0
    multiple: bool = False

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["role"] = self.role.value
        return result


@dataclass(frozen=True)
class SourceSchema:
    """Minimum L1 schema needed for retrieval and bulk-optics calculations."""

    dataset_names: Tuple[str, ...]
    required_variables: Tuple[str, ...]
    required_optical_variables: Tuple[str, ...] = (
        "cext",
        "ssa",
        "g",
        "sca_angle",
        "p11",
        "p12",
        "p22",
        "p33",
        "p43",
        "p44",
    )
    accepted_data_major_versions: Tuple[int, ...] = (1,)


@dataclass(frozen=True)
class ParticleProfile:
    """Complete user-facing contract for one database particle family."""

    particle_type: str
    display_name: str
    aliases: Tuple[str, ...]
    database_directory: str
    data_structure: DataStructure
    parameters: Tuple[ParameterSpec, ...]
    native_size_variables: Tuple[str, ...]
    supported_size_definitions: Tuple[str, ...]
    default_size_definition: str
    source_schema: SourceSchema
    native_lookup_coordinates: Tuple[str, ...] = ()
    default_wrapper_input_mode: str = "native"
    forbidden_parameters: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    refractive_index_parameters: Tuple[str, ...] = ()

    def parameter(self, name: str) -> ParameterSpec:
        canonical = normalize_parameter_name(name)
        for item in self.parameters:
            if _normalize_label(name) in {_normalize_label(alias) for alias in item.aliases}:
                return item
        for item in self.parameters:
            if item.name == canonical:
                return item
        raise KeyError(
            "Unknown parameter {!r} for {}. Valid parameters: {}".format(
                name, self.particle_type, ", ".join(item.name for item in self.parameters)
            )
        )

    def to_dict(self) -> Dict[str, object]:
        result = {
            "particle_type": self.particle_type,
            "display_name": self.display_name,
            "aliases": list(self.aliases),
            "database_directory": self.database_directory,
            "data_structure": self.data_structure.value,
            "parameters": [item.to_dict() for item in self.parameters],
            "native_size_variables": list(self.native_size_variables),
            "supported_size_definitions": list(self.supported_size_definitions),
            "default_size_definition": self.default_size_definition,
            "source_schema": asdict(self.source_schema),
            "native_lookup_coordinates": list(self.native_lookup_coordinates),
            "default_wrapper_input_mode": self.default_wrapper_input_mode,
            "forbidden_parameters": list(self.forbidden_parameters),
            "notes": list(self.notes),
        }
        if self.data_structure == DataStructure.GRID_BASED:
            required = [p.name for p in self.parameters if p.role == ParameterRole.REQUIRED]
            indices = list(self.refractive_index_parameters)
            result["input_modes"] = {
                "wavelength_to_refractive_index": {
                    "required_inputs": required,
                    "description": "Resolve indices from external material tables; wavelength also supplies physical scaling.",
                },
                "explicit_refractive_index": {
                    "required_inputs": required + indices,
                    "description": "Supply the complete index set together to bypass material tables. Wavelength remains required for physical scaling.",
                },
            }
        return result


_WAVELENGTH = ParameterSpec(
    "wavelength",
    ParameterRole.REQUIRED,
    (
        "Incident wavelength; normalized to micrometres before wrapper resolution, "
        "native lookup, or physical-unit conversion as applicable."
    ),
    unit="um",
    aliases=("wl", "lambda"),
    source_variable="wavelength",
    multiple=True,
)


def _wavelength(minimum: float, maximum: float) -> ParameterSpec:
    return replace(_WAVELENGTH, minimum=minimum, maximum=maximum)


_GRID_WAVELENGTH = replace(
    _WAVELENGTH,
    source_variable=None,
    description=(
        "Physical calculation wavelength, not a native refractive-index-grid lookup coordinate. "
        "Required to convert xsize to radius and k^2 Cext to physical cross section. "
        "By default it also selects indices from external material tables; complete explicit "
        "indices bypass those tables. Must be finite and positive. Table mode is limited "
        "by table coverage (packaged defaults: 0.3-20 um); explicit mode is limited by "
        "available index/size coverage and any profile bounds."
    ),
)


_DERIVED_RI_REAL = ParameterSpec(
    "refractive_index_real",
    ParameterRole.DERIVED,
    "Real refractive index selected by wavelength (and temperature where applicable).",
    aliases=("mr", "n_real"),
    source_variable="mr",
)
_DERIVED_RI_IMAG = ParameterSpec(
    "refractive_index_imaginary",
    ParameterRole.DERIVED,
    "Imaginary refractive index selected by wavelength (and temperature where applicable).",
    aliases=("mi", "n_imag", "k"),
    source_variable="mi",
)
_ROUNDNESS = ParameterSpec(
    "roundness",
    ParameterRole.REQUIRED,
    "Super-spheroid roundness exponent; the L1 variable is ssph_n.",
    aliases=("n", "smoothness", "ssph_n"),
    source_variable="ssph_n",
    multiple=True,
)
_ASPECT_RATIO = ParameterSpec(
    "aspect_ratio",
    ParameterRole.REQUIRED,
    "Super-spheroid aspect ratio; the L1 variable is ssph_asp.",
    aliases=("alpha", "asp", "ar", "ssph_asp"),
    source_variable="ssph_asp",
    multiple=True,
)
_RH = ParameterSpec(
    "relative_humidity",
    ParameterRole.REQUIRED,
    "Dimensionless relative humidity. Source values are stored on a 0-99 scale.",
    minimum=0.0,
    maximum=0.99,
    aliases=("rh",),
    source_variable="rh",
    source_scale=100.0,
    multiple=True,
)

_PHASE_VARIABLES = (
    "cext",
    "ssa",
    "g",
    "sca_angle",
    "p11",
    "p12",
    "p22",
    "p33",
    "p43",
    "p44",
)


def _schema(dataset_name: str, required: Iterable[str]) -> SourceSchema:
    return SourceSchema(
        dataset_names=(dataset_name,),
        required_variables=tuple(required),
        required_optical_variables=_PHASE_VARIABLES,
    )


_PROFILES = (
    ParticleProfile(
        particle_type="encapsulated_fractal_aggregates_black_carbon",
        display_name="Encapsulated fractal-aggregate black carbon",
        aliases=("black_carbon", "bc", "encapsulated_black_carbon"),
        database_directory="encapsulated_fractal_aggregates_black_carbon",
        data_structure=DataStructure.GRID_BASED,
        parameters=(
            ParameterSpec(
                "database_type",
                ParameterRole.OPTIONAL,
                "Independent BC database family; defaults to refractive_index_grid.",
                choices=("refractive_index_grid", "wavelength"),
            ),
            ParameterSpec(
                "ri_scheme",
                ParameterRole.OPTIONAL,
                "Built-in wavelength BC refractive-index scheme; defaults to v1.2.2.",
                choices=("v1.2.1", "v1.2.2"),
            ),
            replace(_GRID_WAVELENGTH, minimum=0.3, maximum=20.0),
            ParameterSpec(
                "black_carbon_refractive_index_real",
                ParameterRole.OPTIONAL,
                "Explicit BC real index; supply all four BC/coating index components together to bypass external tables.",
                minimum=1.50,
                maximum=3.63,
                grid_values=(1.55, 1.65, 1.75, 1.85, 1.95),
                aliases=("bc_mr", "mr_bc"),
                multiple=True,
            ),
            ParameterSpec(
                "black_carbon_refractive_index_imaginary",
                ParameterRole.OPTIONAL,
                "Explicit BC imaginary index; supply all four BC/coating index components together to bypass external tables.",
                minimum=0.45,
                maximum=2.86,
                grid_values=(0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85),
                aliases=("bc_mi", "mi_bc"),
                multiple=True,
            ),
            ParameterSpec(
                "hygroscopic_refractive_index_real",
                ParameterRole.OPTIONAL,
                "Explicit coating real index; supply all four BC/coating index components together to bypass external tables.",
                minimum=1.13,
                maximum=2.56,
                grid_values=(1.2, 1.25, 1.3, 1.35, 1.4, 1.45, 1.5, 1.55, 1.6),
                aliases=("hygro_mr", "mr_hygro"),
                multiple=True,
            ),
            ParameterSpec(
                "hygroscopic_refractive_index_imaginary",
                ParameterRole.OPTIONAL,
                "Explicit coating imaginary index; supply all four BC/coating index components together to bypass external tables.",
                minimum=0.0,
                maximum=0.37,
                grid_values=(0.0, 0.001, 0.005, 0.01, 0.05, 0.1),
                aliases=("hygro_mi", "mi_hygro"),
                multiple=True,
            ),
            ParameterSpec(
                "df",
                ParameterRole.REQUIRED,
                "Fractal dimension Df.",
                minimum=1.8,
                maximum=2.4,
                grid_values=(1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4),
                aliases=("Df", "fractal_dimension"),
                source_variable="Df",
                multiple=True,
            ),
            ParameterSpec(
                "vf",
                ParameterRole.REQUIRED,
                "Black-carbon volume fraction Vbc/(Vbc + Vhygro).",
                minimum=0.0,
                maximum=1.0,
                aliases=("Vf", "volume_fraction"),
                source_variable="vf",
                multiple=True,
            ),
        ),
        native_size_variables=("xsize_veq", "xsize_maxd"),
        supported_size_definitions=(
            "volume_equivalent_sphere_radius",
            "maximum_dimension_radius",
        ),
        default_size_definition="volume_equivalent_sphere_radius",
        source_schema=_schema(
            "encapsulated_fractal_aggregates_black_carbon",
            ("Df", "vf", "xsize_veq", "xsize_maxd"),
        ),
        native_lookup_coordinates=(
            "black_carbon_refractive_index_real",
            "black_carbon_refractive_index_imaginary",
            "hygroscopic_refractive_index_real",
            "hygroscopic_refractive_index_imaginary",
            "df",
            "vf",
            "xsize_veq",
            "xsize_maxd",
        ),
        default_wrapper_input_mode="wavelength_to_refractive_index",
        forbidden_parameters=(
            "temperature",
            "relative_humidity",
            "roundness",
            "aspect_ratio",
        ),
        notes=(
            "BC has independent refractive_index_grid and wavelength databases; select database_type explicitly for wavelength data.",
            "In grid mode wavelength controls scaling and RI table lookup. In wavelength mode it is a native coordinate, with ri_scheme v1.2.1 or v1.2.2.",
            "By default the interface resolves both material refractive indices from external wavelength-indexed tables.",
            "Advanced callers may supply all four refractive-index components explicitly instead.",
            "The source grid stores dimensionless size parameters; wavelength supplies physical scaling.",
            "Do not substitute an arithmetic relationship between the two nonspherical size definitions.",
        ),
    ),
    ParticleProfile(
        particle_type="super_spheroid",
        display_name="Generic super-spheroid (including mineral dust)",
        aliases=("dust", "generic_super_spheroid", "super_spheroid_dust"),
        database_directory="super_spheroid",
        data_structure=DataStructure.GRID_BASED,
        parameters=(
            _GRID_WAVELENGTH,
            ParameterSpec(
                "refractive_index_real",
                ParameterRole.OPTIONAL,
                "Explicit real index; supply both real and imaginary components together to bypass the external dust table.",
                aliases=("mr", "n_real"),
                source_variable="mr",
                minimum=0.8,
                maximum=2.0,
                multiple=True,
            ),
            ParameterSpec(
                "refractive_index_imaginary",
                ParameterRole.OPTIONAL,
                "Explicit imaginary index; supply both real and imaginary components together to bypass the external dust table.",
                aliases=("mi", "n_imag", "k"),
                source_variable="mi",
                minimum=1.0e-7,
                maximum=1.0,
                multiple=True,
            ),
            ParameterSpec(
                **{
                    **_ROUNDNESS.__dict__,
                    "minimum": 1.2,
                    "maximum": 3.0,
                    "grid_values": (1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0),
                }
            ),
            ParameterSpec(
                **{
                    **_ASPECT_RATIO.__dict__,
                    "minimum": 0.5,
                    "maximum": 2.0,
                    "grid_values": (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0),
                }
            ),
        ),
        native_size_variables=("xsize_veq", "xsize_maxd"),
        supported_size_definitions=(
            "volume_equivalent_sphere_radius",
            "maximum_dimension_radius",
        ),
        default_size_definition="volume_equivalent_sphere_radius",
        source_schema=_schema(
            "super_spheroid",
            ("mr", "mi", "ssph_n", "ssph_asp", "xsize_veq", "xsize_maxd"),
        ),
        native_lookup_coordinates=(
            "refractive_index_real",
            "refractive_index_imaginary",
            "roundness",
            "aspect_ratio",
            "xsize_veq",
            "xsize_maxd",
        ),
        default_wrapper_input_mode="wavelength_to_refractive_index",
        forbidden_parameters=("temperature", "relative_humidity", "df", "vf"),
        notes=(
            "Wavelength is a wrapper input for physical scaling and external refractive-index interpolation; it is not a native database lookup coordinate.",
            "The default interface resolves refractive index from an external wavelength-indexed table; advanced callers may provide both components explicitly.",
            "The default material table is mineral dust. For other materials, supply both refractive_index_real and refractive_index_imaginary, or a custom table.",
            "No fixed wavelength bounds are declared by this profile; default table coverage is 0.3-20 um with no extrapolation. Explicit indices still require a finite positive physical wavelength and available index/size coverage.",
            "Database refractive-index domains and size-parameter coverage vary by spectral grid.",
        ),
    ),
    ParticleProfile(
        particle_type="coated_super_spheroid_seasalt",
        display_name="Coated super-spheroid sea salt",
        aliases=("sea_salt", "seasalt", "coated_sea_salt"),
        database_directory="coated_super_spheroid_seasalt",
        data_structure=DataStructure.WAVELENGTH_BASED,
        parameters=(
            _wavelength(0.2, 40.0),
            _RH,
            ParameterSpec(
                "humidity_branch",
                ParameterRole.OPTIONAL,
                "Hygroscopic path used where crystallization and deliquescence states overlap.",
                choices=("deliquescence", "crystallization"),
                aliases=("rh_branch", "state"),
            ),
            _DERIVED_RI_REAL,
            _DERIVED_RI_IMAG,
        ),
        native_size_variables=("xsize_veq", "xsize_maxd"),
        supported_size_definitions=(
            "volume_equivalent_sphere_radius",
            "maximum_dimension_radius",
        ),
        default_size_definition="volume_equivalent_sphere_radius",
        source_schema=SourceSchema(
            dataset_names=("coated_super_spheroid_sea_salt",),
            required_variables=(
                "rh",
                "gf",
                "ve",
                "xsize_veq",
                "xsize_maxd",
            ),
            required_optical_variables=_PHASE_VARIABLES,
        ),
        native_lookup_coordinates=(
            "wavelength",
            "relative_humidity",
            "xsize_veq",
            "xsize_maxd",
        ),
        forbidden_parameters=(
            "temperature",
            "refractive_index_real",
            "refractive_index_imaginary",
            "roundness",
            "aspect_ratio",
            "df",
            "vf",
        ),
        notes=(
            "Public relative humidity is 0-1; the adapter converts it to the source scale.",
            "Negative source RH values encode the crystallization branch, not negative physical humidity.",
            "Refractive index and wet-particle geometry are database-derived.",
        ),
    ),
    ParticleProfile(
        particle_type="super_spheroid_ice",
        display_name="Super-spheroid ice crystal",
        aliases=("ice", "ice_crystal", "super_spheroid_ice_crystal"),
        database_directory="super_spheroid_ice",
        data_structure=DataStructure.WAVELENGTH_BASED,
        parameters=(
            _wavelength(0.3, 99.0),
            ParameterSpec(
                "temperature",
                ParameterRole.REQUIRED,
                "Ice refractive-index temperature.",
                unit="K",
                minimum=160.0,
                maximum=270.0,
                grid_values=(160.0, 220.0, 270.0),
                aliases=("temperature_k", "t"),
                source_variable="temperature",
                multiple=True,
            ),
            ParameterSpec(
                **{
                    **_ROUNDNESS.__dict__,
                    "minimum": 2.0,
                    "maximum": 3.0,
                    "grid_values": (2.0, 2.25, 2.5, 2.75, 3.0),
                }
            ),
            ParameterSpec(
                **{
                    **_ASPECT_RATIO.__dict__,
                    "minimum": 1.0,
                    "maximum": 2.5,
                    "grid_values": (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5),
                }
            ),
            _DERIVED_RI_REAL,
            _DERIVED_RI_IMAG,
        ),
        native_size_variables=("xsize_veq", "xsize_maxd"),
        supported_size_definitions=(
            "volume_equivalent_sphere_radius",
            "maximum_dimension_radius",
        ),
        default_size_definition="volume_equivalent_sphere_radius",
        source_schema=_schema(
            "super_spheroid_ice",
            (
                "wavelength",
                "temperature",
                "mr",
                "mi",
                "ssph_n",
                "ssph_asp",
                "xsize_veq",
                "xsize_maxd",
            ),
        ),
        native_lookup_coordinates=(
            "wavelength",
            "temperature",
            "roundness",
            "aspect_ratio",
            "xsize_veq",
            "xsize_maxd",
        ),
        forbidden_parameters=(
            "relative_humidity",
            "refractive_index_real",
            "refractive_index_imaginary",
            "df",
            "vf",
        ),
        notes=(
            "The user selects wavelength and temperature; the database supplies refractive index.",
            "Wavelength coverage and available size parameters must be checked jointly.",
        ),
    ),
)


def _sphere_profile(
    particle_type: str,
    display_name: str,
    aliases: Tuple[str, ...],
    *,
    relative_humidity: bool,
    wavelength_note: str,
) -> ParticleProfile:
    parameters = [_wavelength(0.3, 100.0) if not relative_humidity else _wavelength(0.2, 40.0)]
    required = ["xsize_veq"]
    if relative_humidity:
        parameters.append(_RH)
        required.extend(("rh", "gf", "xsize_maxd"))
    parameters.extend((_DERIVED_RI_REAL, _DERIVED_RI_IMAG))
    return ParticleProfile(
        particle_type=particle_type,
        display_name=display_name,
        aliases=aliases,
        database_directory=particle_type,
        data_structure=DataStructure.WAVELENGTH_BASED,
        parameters=tuple(parameters),
        native_size_variables=("xsize_veq", "xsize_maxd") if relative_humidity else ("xsize_veq",),
        supported_size_definitions=("volume_equivalent_sphere_radius",),
        default_size_definition="volume_equivalent_sphere_radius",
        source_schema=_schema(particle_type, required),
        native_lookup_coordinates=(
            ("wavelength", "relative_humidity", "xsize_veq", "xsize_maxd")
            if relative_humidity
            else ("wavelength", "xsize_veq")
        ),
        forbidden_parameters=(
            "temperature",
            "refractive_index_real",
            "refractive_index_imaginary",
            "roundness",
            "aspect_ratio",
            "df",
            "vf",
        )
        + (() if relative_humidity else ("relative_humidity",)),
        notes=(
            wavelength_note,
            "Refractive index is selected from the wavelength-indexed source product.",
        ),
    )


_PROFILES += (
    _sphere_profile(
        "sphere_sulfate",
        "Spherical sulfate",
        ("sulfate",),
        relative_humidity=True,
        wavelength_note="Relative humidity controls hygroscopic growth.",
    ),
    _sphere_profile(
        "sphere_nitrate",
        "Spherical nitrate",
        ("nitrate",),
        relative_humidity=True,
        wavelength_note="Relative humidity controls hygroscopic growth.",
    ),
    _sphere_profile(
        "sphere_organic_carbon",
        "Spherical organic carbon",
        ("organic_carbon", "oc"),
        relative_humidity=True,
        wavelength_note="Relative humidity controls hygroscopic growth.",
    ),
    _sphere_profile(
        "sphere_water_cloud",
        "Spherical liquid-water cloud",
        ("water_cloud", "liquid_water_cloud"),
        relative_humidity=False,
        wavelength_note="The liquid-water refractive index is wavelength dependent.",
    ),
)


PARAMETER_ALIASES: Mapping[str, str] = {
    "df": "df",
    "fractal_dimension": "df",
    "vf": "vf",
    "volume_fraction": "vf",
    "n": "roundness",
    "smoothness": "roundness",
    "ssph_n": "roundness",
    "alpha": "aspect_ratio",
    "asp": "aspect_ratio",
    "ar": "aspect_ratio",
    "ssph_asp": "aspect_ratio",
    "rh": "relative_humidity",
    "relative_humidity": "relative_humidity",
    "temperature_k": "temperature",
    "t": "temperature",
    "wl": "wavelength",
    "lambda": "wavelength",
    "mr": "refractive_index_real",
    "n_real": "refractive_index_real",
    "mi": "refractive_index_imaginary",
    "n_imag": "refractive_index_imaginary",
    "k": "refractive_index_imaginary",
    "bc_mr": "black_carbon_refractive_index_real",
    "mr_bc": "black_carbon_refractive_index_real",
    "bc_mi": "black_carbon_refractive_index_imaginary",
    "mi_bc": "black_carbon_refractive_index_imaginary",
    "hygro_mr": "hygroscopic_refractive_index_real",
    "mr_hygro": "hygroscopic_refractive_index_real",
    "hygro_mi": "hygroscopic_refractive_index_imaginary",
    "mi_hygro": "hygroscopic_refractive_index_imaginary",
}

_GRID_REFRACTIVE_GROUPS: Mapping[str, Tuple[str, ...]] = {
    "encapsulated_fractal_aggregates_black_carbon": (
        "black_carbon_refractive_index_real",
        "black_carbon_refractive_index_imaginary",
        "hygroscopic_refractive_index_real",
        "hygroscopic_refractive_index_imaginary",
    ),
    "super_spheroid": (
        "refractive_index_real",
        "refractive_index_imaginary",
    ),
}


def _normalize_label(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").replace(" ", "_").split("_"))


def normalize_parameter_name(name: str) -> str:
    """Return the lowercase canonical name for a known scientific alias."""

    normalized = _normalize_label(name)
    return PARAMETER_ALIASES.get(normalized, normalized)


def validate_profile_parameters(
    particle_type: str,
    parameters: Mapping[str, object],
    *,
    require_all: bool = True,
) -> Dict[str, object]:
    """Normalize and validate already-unit-normalized profile coordinates.

    Unit-bearing values must be converted at the scheme boundary before this
    function is called. This validator deliberately runs without database access.
    """

    profile = get_particle_profile(particle_type)
    specs = {item.name: item for item in profile.parameters}
    forbidden = {normalize_parameter_name(name) for name in profile.forbidden_parameters}
    normalized: Dict[str, object] = {}
    for raw_name, value in parameters.items():
        try:
            name = profile.parameter(raw_name).name
        except KeyError:
            name = normalize_parameter_name(raw_name)
        if name in normalized:
            raise ValueError(
                "Parameter {!r} was supplied more than once through aliases".format(name)
            )
        if name in forbidden:
            raise ValueError(
                "{} does not permit user input {!r}".format(profile.particle_type, name)
            )
        spec = specs.get(name)
        if spec is None:
            raise ValueError(
                "Unknown parameter {!r} for {}. Allowed user inputs: {}".format(
                    raw_name,
                    profile.particle_type,
                    ", ".join(
                        item.name
                        for item in profile.parameters
                        if item.role in (ParameterRole.REQUIRED, ParameterRole.OPTIONAL)
                    ),
                )
            )
        if spec.role in (ParameterRole.DERIVED, ParameterRole.FORBIDDEN):
            raise ValueError(
                "{} is {} for {} and cannot be supplied by the user".format(
                    name, spec.role.value, profile.particle_type
                )
            )
        values = (
            list(value)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
            else [value]
        )
        if len(values) > 1 and not spec.multiple:
            raise ValueError("{} accepts one value, not a sequence".format(name))
        for item in values:
            if spec.choices and item not in spec.choices:
                raise ValueError(
                    "{} must be one of: {}".format(
                        name, ", ".join(str(choice) for choice in spec.choices)
                    )
                )
            if spec.minimum is not None or spec.maximum is not None:
                try:
                    number = float(item)
                except (TypeError, ValueError) as exc:
                    raise ValueError("{} must be numeric".format(name)) from exc
                if not math.isfinite(number):
                    raise ValueError("{} must be finite".format(name))
                if spec.minimum is not None and number < spec.minimum:
                    raise ValueError("{} must be >= {}".format(name, spec.minimum))
                if spec.maximum is not None and number > spec.maximum:
                    raise ValueError("{} must be <= {}".format(name, spec.maximum))
        normalized[name] = value
    refractive_group = profile.refractive_index_parameters
    supplied_refractive = [name for name in refractive_group if name in normalized]
    if supplied_refractive and len(supplied_refractive) != len(refractive_group):
        missing_refractive = [name for name in refractive_group if name not in normalized]
        raise ValueError(
            "Explicit refractive-index override for {} must provide the complete "
            "native coordinate set; missing: {}".format(
                profile.particle_type,
                ", ".join(missing_refractive),
            )
        )
    if require_all:
        missing = [
            item.name
            for item in profile.parameters
            if item.role == ParameterRole.REQUIRED and item.name not in normalized
        ]
        if missing:
            raise ValueError(
                "Missing required parameters for {}: {}".format(
                    profile.particle_type, ", ".join(missing)
                )
            )
    return normalized


def grid_refractive_input_mode(
    particle_type: str,
    parameters: Mapping[str, object],
) -> str:
    """Classify a grid profile as external-table or explicit-index input."""

    profile = get_particle_profile(particle_type)
    group = profile.refractive_index_parameters or None
    if group is None:
        raise ValueError("{} is not a refractive-index-grid profile".format(profile.particle_type))
    supplied = {normalize_parameter_name(name) for name in parameters}
    present = [name for name in group if name in supplied]
    if not present:
        return "wavelength_to_refractive_index"
    if len(present) != len(group):
        missing = [name for name in group if name not in supplied]
        raise ValueError(
            "Incomplete explicit refractive-index override; missing: " + ", ".join(missing)
        )
    return "explicit_refractive_index"


# Built-in metadata remains declarative; extensions supply the same profile contract.
_PROFILES = tuple(
    replace(
        profile, refractive_index_parameters=_GRID_REFRACTIVE_GROUPS.get(profile.particle_type, ())
    )
    for profile in _PROFILES
)


@_registration_required
def list_particle_profiles() -> Tuple[ParticleProfile, ...]:
    from zju_scatt_interface.extensions.particles import particle_definitions

    return tuple(definition.profile for definition in particle_definitions())


@_registration_required
def get_particle_profile(particle_type: str) -> ParticleProfile:
    from zju_scatt_interface.extensions.particles import get_particle_definition

    try:
        return get_particle_definition(particle_type).profile
    except ValueError as exc:
        raise ValueError(
            f"Unknown particle type {particle_type!r}. Available particle types: "
            + ", ".join(profile.particle_type for profile in list_particle_profiles())
        ) from exc
