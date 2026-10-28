"""optics / refractive_index domain implementation."""

from __future__ import annotations

import csv
import math
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple, Union

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    grid_refractive_input_mode,
    normalize_parameter_name,
)

_DEFAULT_TABLE_RELATIVE_PATHS = {
    "super_spheroid": {
        "particle": Path("Dust_refractive_index_statistics.csv"),
    },
    "encapsulated_fractal_aggregates_black_carbon": {
        "black_carbon": Path("Black_carbon_refractive_index_used_v1.2.1.csv"),
        "hygroscopic": Path("Hygroscopic_material_for_black_carbon_refractive_index_used.csv"),
    },
    "coated_super_spheroid_seasalt": {
        "particle": Path("Sea_salt_refractive_index_statistics.csv"),
    },
    "super_spheroid_ice": {
        "particle": Path("Ice_refractive_index_statistics_extend100um.csv"),
    },
}


@_registration_required
def wavelength_to_um(value: object, unit: str = "um") -> float:
    """Convert one wavelength or wavenumber to the internal micrometre unit."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("wavelength must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError("wavelength must be finite and positive")
    normalized = (
        unit.strip().lower().replace("µ", "u").replace("μ", "u").replace("−", "-").replace("^", "")
    )
    aliases = {
        "nm": "nm",
        "um": "um",
        "micrometer": "um",
        "micrometre": "um",
        "cm-1": "cm-1",
        "cm1": "cm-1",
        "1/cm": "cm-1",
        "wavenumber": "cm-1",
    }
    try:
        canonical = aliases[normalized]
    except KeyError as exc:
        raise ValueError("wavelength unit must be 'nm', 'um', or 'cm-1'") from exc
    if canonical == "nm":
        return number / 1000.0
    if canonical == "cm-1":
        return 10000.0 / number
    return number


@dataclass(frozen=True)
class ComplexRefractiveIndex:
    real: float
    imaginary: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.real) or not math.isfinite(self.imaginary):
            raise ValueError("refractive-index components must be finite")
        if self.real <= 0:
            raise ValueError("real refractive index must be positive")
        if self.imaginary < 0:
            raise ValueError("imaginary refractive index cannot be negative")


@dataclass(frozen=True)
class RefractiveIndexTable:
    """A validated wavelength-indexed external refractive-index table."""

    wavelength_um: Tuple[float, ...]
    real: Tuple[float, ...]
    imaginary: Tuple[float, ...]
    source: str = "in_memory"

    def __post_init__(self) -> None:
        length = len(self.wavelength_um)
        if length < 2:
            raise ValueError("a refractive-index table requires at least two rows")
        if len(self.real) != length or len(self.imaginary) != length:
            raise ValueError("wavelength, real, and imaginary arrays must have equal length")
        previous = -math.inf
        for wavelength, real, imaginary in zip(self.wavelength_um, self.real, self.imaginary):
            if not math.isfinite(wavelength) or wavelength <= 0:
                raise ValueError("table wavelengths must be finite and positive")
            if wavelength <= previous:
                raise ValueError("table wavelengths must be strictly increasing")
            ComplexRefractiveIndex(float(real), float(imaginary))
            previous = wavelength

    @property
    def minimum_wavelength_um(self) -> float:
        return self.wavelength_um[0]

    @property
    def maximum_wavelength_um(self) -> float:
        return self.wavelength_um[-1]

    def interpolate(
        self,
        wavelength_um: object,
        *,
        extrapolate: bool = False,
    ) -> ComplexRefractiveIndex:
        """Linearly interpolate real and imaginary components in wavelength."""

        target = wavelength_to_um(wavelength_um, "um")
        if not extrapolate and not (
            self.minimum_wavelength_um <= target <= self.maximum_wavelength_um
        ):
            from zju_scatt_interface.sources.adapters.boundaries import (
                DatabaseBoundaryError,
            )

            raise DatabaseBoundaryError(
                "wavelength {} um is outside refractive-index table coverage {}..{} um".format(
                    target,
                    self.minimum_wavelength_um,
                    self.maximum_wavelength_um,
                )
            )
        upper = bisect_left(self.wavelength_um, target)
        if upper < len(self.wavelength_um) and self.wavelength_um[upper] == target:
            return ComplexRefractiveIndex(self.real[upper], self.imaginary[upper])
        if upper == 0:
            lower, upper = 0, 1
        elif upper == len(self.wavelength_um):
            lower, upper = len(self.wavelength_um) - 2, len(self.wavelength_um) - 1
        else:
            lower = upper - 1
        fraction = (target - self.wavelength_um[lower]) / (
            self.wavelength_um[upper] - self.wavelength_um[lower]
        )
        return ComplexRefractiveIndex(
            self.real[lower] + fraction * (self.real[upper] - self.real[lower]),
            self.imaginary[lower] + fraction * (self.imaginary[upper] - self.imaginary[lower]),
        )

    @classmethod
    def from_csv(
        cls,
        path: Union[str, Path],
        *,
        wavelength_unit: Optional[str] = None,
        wavelength_column: Optional[str] = None,
        real_column: Optional[str] = None,
        imaginary_column: Optional[str] = None,
    ) -> "RefractiveIndexTable":
        source = Path(path).expanduser()
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ValueError("refractive-index CSV has no header")
            field_index = {_normalize_header(name): name for name in reader.fieldnames}
            wavelength_name, detected_unit = _resolve_wavelength_column(
                field_index,
                wavelength_column,
                wavelength_unit,
            )
            real_name = _resolve_column(
                field_index,
                real_column,
                ("refractive_index_real", "real", "mr", "n", "n_mean"),
                "real refractive index",
            )
            imaginary_name = _resolve_column(
                field_index,
                imaginary_column,
                (
                    "refractive_index_imaginary",
                    "imaginary",
                    "imag",
                    "mi",
                    "k",
                    "k_mean",
                ),
                "imaginary refractive index",
            )
            rows = []
            for row_number, row in enumerate(reader, start=2):
                try:
                    wavelength = wavelength_to_um(row[wavelength_name], detected_unit)
                    index = ComplexRefractiveIndex(
                        float(row[real_name]),
                        float(row[imaginary_name]),
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "invalid refractive-index value on CSV row {}".format(row_number)
                    ) from exc
                rows.append((wavelength, index.real, index.imaginary))
        rows.sort(key=lambda item: item[0])
        return cls(
            wavelength_um=tuple(row[0] for row in rows),
            real=tuple(row[1] for row in rows),
            imaginary=tuple(row[2] for row in rows),
            source=str(source.resolve()),
        )


def _normalize_header(value: str) -> str:
    normalized = (
        value.strip()
        .lower()
        .replace("µ", "u")
        .replace("μ", "u")
        .replace("−", "-")
        .replace("^", "")
        .replace("(", "_")
        .replace(")", "")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .strip("_")
    )
    return "_".join(part for part in normalized.split("_") if part)


def _resolve_column(
    fields: Mapping[str, str],
    requested: Optional[str],
    aliases: Sequence[str],
    label: str,
) -> str:
    if requested is not None:
        key = _normalize_header(requested)
        if key not in fields:
            raise ValueError("CSV column {!r} does not exist".format(requested))
        return fields[key]
    for alias in aliases:
        key = _normalize_header(alias)
        if key in fields:
            return fields[key]
    raise ValueError("cannot identify {} column".format(label))


def _resolve_wavelength_column(
    fields: Mapping[str, str],
    requested: Optional[str],
    requested_unit: Optional[str],
) -> Tuple[str, str]:
    if requested is not None:
        name = _resolve_column(fields, requested, (), "wavelength")
        return name, requested_unit or "um"
    candidates = (
        ("wavelength_um", "um"),
        ("wavelength_in_micrometers", "um"),
        ("wavelength_in_micrometres", "um"),
        ("wavelength_nm", "nm"),
        ("wavenumber_cm_1", "cm-1"),
        ("wavenumber", requested_unit or "cm-1"),
        ("wavelength", requested_unit or "um"),
        ("wl", requested_unit or "um"),
    )
    for alias, unit in candidates:
        key = _normalize_header(alias)
        if key in fields:
            return fields[key], unit
    raise ValueError("cannot identify wavelength or wavenumber column")


@dataclass(frozen=True)
class ResolvedGridRefractiveIndex:
    particle_type: str
    # Explicit dimensionless-grid planning does not require a physical wavelength.
    wavelength_um: Optional[float]
    values: Mapping[str, float]
    input_mode: str
    sources: Mapping[str, str]


@_registration_required
def default_refractive_index_paths(
    particle_type: str, *, ri_scheme: str = "v1.2.1"
) -> Mapping[str, Path]:
    """Return canonical packaged refractive-index tables for a particle profile.

    Grid profiles use these tables automatically when a complete native-index
    override is not supplied. Wavelength-resolved ice and sea-salt profiles
    expose their reference tables here for reproducible inspection and reuse.
    """

    profile = get_particle_profile(particle_type)
    try:
        relative_paths = _DEFAULT_TABLE_RELATIVE_PATHS[profile.particle_type]
    except KeyError as exc:
        raise ValueError(
            "{} has no packaged refractive-index table".format(profile.particle_type)
        ) from exc
    if profile.particle_type == "encapsulated_fractal_aggregates_black_carbon":
        if ri_scheme not in {"v1.2.1", "v1.2.2"}:
            raise ValueError("ri_scheme must be v1.2.1 or v1.2.2")
        relative_paths = {
            **relative_paths,
            "black_carbon": Path(f"Black_carbon_refractive_index_used_{ri_scheme}.csv"),
        }
    root = Path(__file__).resolve().parents[1] / "data" / "refractive_index"
    return {name: root / path for name, path in relative_paths.items()}


def _as_table(value: Union[str, Path, RefractiveIndexTable]) -> RefractiveIndexTable:
    return (
        value if isinstance(value, RefractiveIndexTable) else RefractiveIndexTable.from_csv(value)
    )


@_registration_required
def resolve_grid_refractive_indices(
    particle_type: str,
    wavelengths: Sequence[object],
    *,
    wavelength_unit: str = "um",
    ri_scheme: str = "v1.2.1",
    parameters: Optional[Mapping[str, object]] = None,
    tables: Optional[Mapping[str, Union[str, Path, RefractiveIndexTable]]] = None,
) -> Tuple[ResolvedGridRefractiveIndex, ...]:
    """Resolve wrapper wavelengths to the native refractive-index grid coordinates."""

    profile = get_particle_profile(particle_type)
    supplied = {normalize_parameter_name(name): value for name, value in (parameters or {}).items()}
    mode = grid_refractive_input_mode(profile.particle_type, supplied)
    wavelengths_um = tuple(wavelength_to_um(value, wavelength_unit) for value in wavelengths)
    if not wavelengths_um:
        raise ValueError("at least one wavelength is required")

    if mode == "explicit_refractive_index":
        if profile.particle_type == "super_spheroid":
            values = {
                "refractive_index_real": float(supplied["refractive_index_real"]),
                "refractive_index_imaginary": float(supplied["refractive_index_imaginary"]),
            }
            ComplexRefractiveIndex(
                values["refractive_index_real"],
                values["refractive_index_imaginary"],
            )
        else:
            values = {
                name: float(supplied[name])
                for name in (
                    "black_carbon_refractive_index_real",
                    "black_carbon_refractive_index_imaginary",
                    "hygroscopic_refractive_index_real",
                    "hygroscopic_refractive_index_imaginary",
                )
            }
            ComplexRefractiveIndex(
                values["black_carbon_refractive_index_real"],
                values["black_carbon_refractive_index_imaginary"],
            )
            ComplexRefractiveIndex(
                values["hygroscopic_refractive_index_real"],
                values["hygroscopic_refractive_index_imaginary"],
            )
        return tuple(
            ResolvedGridRefractiveIndex(
                particle_type=profile.particle_type,
                wavelength_um=wavelength,
                values=values,
                input_mode=mode,
                sources={"refractive_index": "explicit_user_override"},
            )
            for wavelength in wavelengths_um
        )

    table_values = dict(tables or {})
    default_paths = default_refractive_index_paths(profile.particle_type, ri_scheme=ri_scheme)
    for name, path in default_paths.items():
        if name not in table_values and path.is_file():
            table_values[name] = path
    required_tables = tuple(default_paths)
    missing = [name for name in required_tables if name not in table_values]
    if missing:
        expected = ", ".join("{}={}".format(name, default_paths[name]) for name in missing)
        raise ValueError(
            "Default refractive-index assets are not installed for {}. Provide "
            "tables for: {}. Expected CSV columns are wavelength plus real/mr and "
            "imaginary/mi. Packaged paths: {}.".format(
                profile.particle_type,
                ", ".join(missing),
                expected,
            )
        )
    resolved_tables = {name: _as_table(table_values[name]) for name in required_tables}
    results = []
    for wavelength in wavelengths_um:
        if profile.particle_type == "super_spheroid":
            index = resolved_tables["particle"].interpolate(wavelength)
            values = {
                "refractive_index_real": index.real,
                "refractive_index_imaginary": index.imaginary,
            }
        else:
            bc = resolved_tables["black_carbon"].interpolate(wavelength)
            hygro = resolved_tables["hygroscopic"].interpolate(wavelength)
            values = {
                "black_carbon_refractive_index_real": bc.real,
                "black_carbon_refractive_index_imaginary": bc.imaginary,
                "hygroscopic_refractive_index_real": hygro.real,
                "hygroscopic_refractive_index_imaginary": hygro.imaginary,
            }
        results.append(
            ResolvedGridRefractiveIndex(
                particle_type=profile.particle_type,
                wavelength_um=wavelength,
                values=values,
                input_mode=mode,
                sources={name: table.source for name, table in resolved_tables.items()},
            )
        )
    return tuple(results)
