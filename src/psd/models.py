"""psd / models domain implementation."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple, Union

SIZE_DEFINITIONS = (
    "volume_equivalent_sphere_radius",
    "maximum_dimension_radius",
)
SIZE_UNITS = ("nm", "um")
INTEGRATION_MODE = "discrete_bin"


def _as_floats(values: object, label: str) -> Tuple[float, ...]:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ValueError("{} must be a one-dimensional array".format(label))
    result = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("{} must contain numeric values".format(label)) from exc
        if not math.isfinite(number):
            raise ValueError("{} must contain only finite values".format(label))
        result.append(number)
    if not result:
        raise ValueError("{} cannot be empty".format(label))
    return tuple(result)


def _normalize_size_unit(unit: object) -> str:
    normalized = str(unit).strip().lower().replace("μ", "u").replace("µ", "u")
    aliases = {
        "nm": "nm",
        "nanometer": "nm",
        "nanometre": "nm",
        "um": "um",
        "micrometer": "um",
        "micrometre": "um",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError("size_unit must be 'nm' or 'um'") from exc


def _normalize_size_definition(value: object) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "volume_equivalent_sphere_radius": "volume_equivalent_sphere_radius",
        "volume_equivalent_radius": "volume_equivalent_sphere_radius",
        "veq_radius": "volume_equivalent_sphere_radius",
        "maximum_dimension_radius": "maximum_dimension_radius",
        "maximum_dimension_half": "maximum_dimension_radius",
        "dmax_over_2": "maximum_dimension_radius",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(
            "size_definition must be 'volume_equivalent_sphere_radius' or "
            "'maximum_dimension_radius'"
        ) from exc


def _validate_dndr_unit(value: object) -> str:
    normalized = (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("**", "^")
        .replace("⁻", "-")
        .replace("³", "3")
    )
    if normalized not in {"cm-3", "cm^-3", "1/cm3", "cm^(-3)"}:
        raise ValueError(
            "dndr_unit is fixed to 'cm-3' (discrete concentration per represented bin)"
        )
    return "cm-3"


def _header(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("μ", "u")
        .replace("µ", "u")
        .replace("/", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _column(
    fields: Mapping[str, str],
    requested: Optional[str],
    aliases: Sequence[str],
    label: str,
) -> str:
    if requested:
        normalized = _header(requested)
        if normalized not in fields:
            raise ValueError("column {!r} does not exist".format(requested))
        return fields[normalized]
    for alias in aliases:
        normalized = _header(alias)
        if normalized in fields:
            return fields[normalized]
    raise ValueError("cannot identify the {} column".format(label))


def _spacing_ratio(size_um: Sequence[float]) -> float:
    if len(size_um) < 3:
        return 1.0
    log_steps = [math.log(size_um[index] / size_um[index - 1]) for index in range(1, len(size_um))]
    minimum = min(log_steps)
    return max(log_steps) / minimum if minimum > 0 else math.inf


def _bin_edges(centers: Sequence[float]) -> Tuple[float, ...]:
    if len(centers) < 2:
        raise ValueError("at least two size points are required to derive bin edges")
    middle = [0.5 * (centers[index - 1] + centers[index]) for index in range(1, len(centers))]
    first = max(0.0, centers[0] - 0.5 * (centers[1] - centers[0]))
    last = centers[-1] + 0.5 * (centers[-1] - centers[-2])
    return (first, *middle, last)


@dataclass(frozen=True)
class RemapReport:
    source_number_concentration_cm3: float
    output_number_concentration_cm3: float
    outside_number_concentration_cm3: float
    outside_fraction: float
    truncation_policy: str
    source_range_um: Tuple[float, float]
    target_range_um: Tuple[float, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_number_concentration_cm3": self.source_number_concentration_cm3,
            "output_number_concentration_cm3": self.output_number_concentration_cm3,
            "outside_number_concentration_cm3": self.outside_number_concentration_cm3,
            "outside_fraction": self.outside_fraction,
            "truncation_policy": self.truncation_policy,
            "source_range_um": list(self.source_range_um),
            "target_range_um": list(self.target_range_um),
        }


@dataclass(frozen=True, init=False)
class SizeDistribution:
    """Discrete per-bin particle concentrations on a physical radius grid.

    ``dndr`` retains the familiar user-facing name, but its fixed public unit is
    ``cm-3`` per represented bin. The explicit ``integration_mode`` records this
    convention and prevents accidental density-mode integration.
    """

    size_um: Tuple[float, ...]
    dndr_cm3: Tuple[float, ...]
    size_definition: str
    integration_mode: str
    source: str
    metadata: Mapping[str, object]
    validation_messages: Tuple[str, ...] = field(default_factory=tuple)

    def __init__(
        self,
        size: object,
        dndr: object,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        *,
        dndr_unit: str = "cm-3",
        integration_mode: str = INTEGRATION_MODE,
        source: str = "python_array",
        metadata: Optional[Mapping[str, object]] = None,
        gap_policy: str = "warn",
        maximum_log_spacing_ratio: float = 10.0,
    ) -> None:
        unit = _normalize_size_unit(size_unit)
        _validate_dndr_unit(dndr_unit)
        sizes = _as_floats(size, "size")
        concentrations = _as_floats(dndr, "dndr")
        if len(sizes) != len(concentrations):
            raise ValueError("size and dndr must have the same length")
        if unit == "nm":
            sizes = tuple(value / 1000.0 for value in sizes)
        if any(value <= 0 for value in sizes):
            raise ValueError("size values must be positive")
        if any(sizes[index] <= sizes[index - 1] for index in range(1, len(sizes))):
            raise ValueError("size values must be strictly increasing; duplicates are not allowed")
        if any(value < 0 for value in concentrations):
            raise ValueError("dndr values cannot be negative")
        if sum(concentrations) <= 0:
            raise ValueError("dndr must contain at least one positive concentration")
        normalized_mode = str(integration_mode).strip().lower()
        if normalized_mode in {"bin", "discrete", "discrete_bin_concentration"}:
            normalized_mode = INTEGRATION_MODE
        if normalized_mode != INTEGRATION_MODE:
            raise ValueError(
                "integration_mode must be 'discrete_bin'; dndr is stored in cm-3 "
                "per represented bin"
            )
        normalized_gap_policy = str(gap_policy).strip().lower()
        if normalized_gap_policy not in {"allow", "warn", "error"}:
            raise ValueError("gap_policy must be 'allow', 'warn', or 'error'")
        maximum_ratio = float(maximum_log_spacing_ratio)
        if not math.isfinite(maximum_ratio) or maximum_ratio < 1:
            raise ValueError("maximum_log_spacing_ratio must be finite and >= 1")
        messages = []
        ratio = _spacing_ratio(sizes)
        if ratio > maximum_ratio:
            message = (
                "size grid has a large logarithmic spacing gap (ratio {:.6g} > {:.6g})".format(
                    ratio, maximum_ratio
                )
            )
            if normalized_gap_policy == "error":
                raise ValueError(message)
            if normalized_gap_policy == "warn":
                messages.append(message)
        object.__setattr__(self, "size_um", sizes)
        object.__setattr__(self, "dndr_cm3", concentrations)
        object.__setattr__(
            self,
            "size_definition",
            _normalize_size_definition(size_definition),
        )
        object.__setattr__(self, "integration_mode", normalized_mode)
        object.__setattr__(self, "source", str(source))
        object.__setattr__(self, "metadata", dict(metadata or {}))
        object.__setattr__(self, "validation_messages", tuple(messages))

    @property
    def size(self) -> Tuple[float, ...]:
        return self.size_um

    @property
    def dndr(self) -> Tuple[float, ...]:
        return self.dndr_cm3

    @property
    def number_concentration_cm3(self) -> float:
        return sum(self.dndr_cm3)

    @property
    def size_range_um(self) -> Tuple[float, float]:
        return self.size_um[0], self.size_um[-1]

    def to_dict(self) -> dict[str, object]:
        return {
            "size": list(self.size_um),
            "dndr": list(self.dndr_cm3),
            "size_unit": "um",
            "dndr_unit": "cm-3",
            "size_definition": self.size_definition,
            "integration_mode": self.integration_mode,
            "source": self.source,
            "metadata": dict(self.metadata),
            "validation_messages": list(self.validation_messages),
            "number_concentration_cm3": self.number_concentration_cm3,
        }

    def to_csv(self, path: Union[str, Path]) -> Path:
        """Write physical radius centers and per-bin counts without normalization.

        The size_definition column distinguishes volume-equivalent and maximum-
        dimension radii. Counts are cm^-3 per bin, never a differential density.
        The file can be read back with SizeDistribution.from_file.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["radius_um", "number_per_bin_cm3", "size_definition"])
            writer.writerows(
                zip(self.size_um, self.dndr_cm3, [self.size_definition] * len(self.size_um))
            )
        return target

    def normalized(self, number_concentration_cm3: object) -> "SizeDistribution":
        target = float(number_concentration_cm3)
        if not math.isfinite(target) or target <= 0:
            raise ValueError("number_concentration_cm3 must be finite and positive")
        scale = target / self.number_concentration_cm3
        return SizeDistribution(
            self.size_um,
            [value * scale for value in self.dndr_cm3],
            "um",
            self.size_definition,
            source=self.source,
            metadata={
                **self.metadata,
                "normalized_from_cm3": self.number_concentration_cm3,
            },
            gap_policy="allow",
        )

    def remap(
        self,
        target_size: object,
        *,
        target_size_unit: str = "um",
        truncation_policy: str = "error",
        outside_tolerance: float = 1e-12,
    ) -> tuple["SizeDistribution", RemapReport]:
        """Conservatively distribute source-bin concentration over target bins."""

        target_values = _as_floats(target_size, "target_size")
        target = SizeDistribution(
            target_values,
            [1.0] * len(target_values),
            target_size_unit,
            self.size_definition,
            source="temporary_target_grid",
            gap_policy="allow",
        ).size_um
        policy = str(truncation_policy).strip().lower()
        if policy not in {"error", "truncate"}:
            raise ValueError("truncation_policy must be 'error' or 'truncate'")
        tolerance = float(outside_tolerance)
        if not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
            raise ValueError("outside_tolerance must be between 0 and 1")

        output = [0.0] * len(target)
        outside = 0.0
        if len(self.size_um) == 1:
            if len(target) == 1:
                if math.isclose(self.size_um[0], target[0]):
                    output[0] = self.dndr_cm3[0]
                else:
                    outside = self.dndr_cm3[0]
            else:
                edges = _bin_edges(target)
                index = next(
                    (
                        candidate
                        for candidate in range(len(target))
                        if edges[candidate] <= self.size_um[0] <= edges[candidate + 1]
                    ),
                    None,
                )
                if index is None:
                    outside = self.dndr_cm3[0]
                else:
                    output[index] = self.dndr_cm3[0]
        else:
            source_edges = _bin_edges(self.size_um)
            target_edges = _bin_edges(target) if len(target) > 1 else (0.0, math.inf)
            for source_index, concentration in enumerate(self.dndr_cm3):
                lower = source_edges[source_index]
                upper = source_edges[source_index + 1]
                width = upper - lower
                assigned = 0.0
                for target_index in range(len(target)):
                    overlap = max(
                        0.0,
                        min(upper, target_edges[target_index + 1])
                        - max(lower, target_edges[target_index]),
                    )
                    if overlap:
                        amount = concentration * overlap / width
                        output[target_index] += amount
                        assigned += amount
                outside += max(0.0, concentration - assigned)

        total = self.number_concentration_cm3
        outside_fraction = outside / total
        if outside_fraction > tolerance and policy == "error":
            raise ValueError(
                "{:.6%} of number concentration is outside the target size grid; "
                "use truncation_policy='truncate' explicitly to discard it".format(outside_fraction)
            )
        if sum(output) <= 0:
            raise ValueError("target grid has no overlap with the particle distribution")
        remapped = SizeDistribution(
            target,
            output,
            "um",
            self.size_definition,
            source="conservative_remap",
            metadata={
                **self.metadata,
                "remapped_from_source": self.source,
                "outside_fraction": outside_fraction,
                "truncation_policy": policy,
            },
            gap_policy="allow",
        )
        report = RemapReport(
            source_number_concentration_cm3=total,
            output_number_concentration_cm3=remapped.number_concentration_cm3,
            outside_number_concentration_cm3=outside,
            outside_fraction=outside_fraction,
            truncation_policy=policy,
            source_range_um=self.size_range_um,
            target_range_um=(target[0], target[-1]),
        )
        return remapped, report

    def convert_size_definition(
        self,
        target_definition: str,
        *,
        converter: Optional[Callable[[Tuple[float, ...]], Sequence[float]]] = None,
        geometry_source: Optional[str] = None,
    ) -> "SizeDistribution":
        target = _normalize_size_definition(target_definition)
        if target == self.size_definition:
            return self
        if converter is None or not geometry_source:
            raise ValueError(
                "changing size_definition requires a validated particle-specific "
                "converter and geometry_source"
            )
        converted = converter(self.size_um)
        return SizeDistribution(
            converted,
            self.dndr_cm3,
            "um",
            target,
            source=self.source,
            metadata={
                **self.metadata,
                "converted_from_size_definition": self.size_definition,
                "geometry_source": geometry_source,
            },
            gap_policy="allow",
        )

    @classmethod
    def from_callable(
        cls,
        size: object,
        function: Callable[[float], object],
        *,
        size_unit: str = "um",
        size_definition: str = "volume_equivalent_sphere_radius",
        source: Optional[str] = None,
        **kwargs: object,
    ) -> "SizeDistribution":
        sizes = _as_floats(size, "size")
        values = [function(value) for value in sizes]
        return cls(
            sizes,
            values,
            size_unit,
            size_definition,
            source=source or getattr(function, "__name__", "python_function"),
            **kwargs,
        )

    @classmethod
    def from_delimited(
        cls,
        path: Union[str, Path],
        *,
        size_column: Optional[str] = None,
        dndr_column: Optional[str] = None,
        size_unit: str = "um",
        size_definition: Optional[str] = None,
        delimiter: Optional[str] = None,
        **kwargs: object,
    ) -> "SizeDistribution":
        source = Path(path).expanduser()
        chosen_delimiter = delimiter or ("\t" if source.suffix.lower() == ".tsv" else ",")
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=chosen_delimiter)
            if not reader.fieldnames:
                raise ValueError("PSD table has no header")
            fields = {_header(name): name for name in reader.fieldnames}
            size_name = _column(
                fields,
                size_column,
                ("size", "size_um", "radius", "radius_um", "r"),
                "size",
            )
            dndr_name = _column(
                fields,
                dndr_column,
                ("dndr", "number_concentration", "concentration", "n", "number_per_bin_cm3"),
                "dndr",
            )
            size_values = []
            dndr_values = []
            definitions = set()
            for row_number, row in enumerate(reader, start=2):
                if "size_definition" in fields:
                    definitions.add(_normalize_size_definition(row[fields["size_definition"]]))
                try:
                    size_values.append(float(row[size_name]))
                    dndr_values.append(float(row[dndr_name]))
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid PSD value on row {}".format(row_number)) from exc
        if len(definitions) > 1:
            raise ValueError("PSD table mixes different size definitions")
        if definitions:
            recorded = next(iter(definitions))
            if (
                size_definition is not None
                and _normalize_size_definition(size_definition) != recorded
            ):
                raise ValueError("Explicit size_definition conflicts with the PSD table")
            size_definition = recorded
        return cls(
            size_values,
            dndr_values,
            size_unit,
            size_definition or "volume_equivalent_sphere_radius",
            source=str(source.resolve()),
            **kwargs,
        )

    @classmethod
    def from_netcdf(
        cls,
        path: Union[str, Path],
        *,
        size_variable: str = "size",
        dndr_variable: str = "dndr",
        size_unit: Optional[str] = None,
        size_definition: Optional[str] = None,
        dndr_unit: Optional[str] = None,
        **kwargs: object,
    ) -> "SizeDistribution":
        try:
            from netCDF4 import Dataset
        except ImportError as exc:
            raise RuntimeError(
                "NetCDF PSD input requires netCDF4; install zju-scatt-interface[netcdf]"
            ) from exc
        source = Path(path).expanduser()
        with Dataset(source, "r") as dataset:
            if size_variable not in dataset.variables:
                raise ValueError("NetCDF PSD has no variable {!r}".format(size_variable))
            if dndr_variable not in dataset.variables:
                raise ValueError("NetCDF PSD has no variable {!r}".format(dndr_variable))
            size_data = dataset.variables[size_variable]
            dndr_data = dataset.variables[dndr_variable]
            sizes = size_data[:]
            concentrations = dndr_data[:]
            unit = size_unit or getattr(size_data, "units", "um")
            concentration_unit = dndr_unit or getattr(dndr_data, "units", "cm-3")
            definition = size_definition or getattr(
                size_data,
                "size_definition",
                getattr(dataset, "size_definition", SIZE_DEFINITIONS[0]),
            )
        return cls(
            sizes,
            concentrations,
            unit,
            definition,
            dndr_unit=str(concentration_unit),
            source=str(source.resolve()),
            **kwargs,
        )

    @classmethod
    def from_hdf5(
        cls,
        path: Union[str, Path],
        *,
        size_dataset: str = "size",
        dndr_dataset: str = "dndr",
        size_unit: Optional[str] = None,
        size_definition: Optional[str] = None,
        dndr_unit: Optional[str] = None,
        **kwargs: object,
    ) -> "SizeDistribution":
        try:
            import h5py
        except ImportError as exc:
            raise RuntimeError(
                "HDF5 PSD input requires h5py; install zju-scatt-interface[netcdf]"
            ) from exc
        source = Path(path).expanduser()
        with h5py.File(source, "r") as handle:
            if size_dataset not in handle or dndr_dataset not in handle:
                raise ValueError(
                    "HDF5 PSD requires datasets {!r} and {!r}".format(size_dataset, dndr_dataset)
                )
            size_data = handle[size_dataset]
            sizes = size_data[...]
            concentrations = handle[dndr_dataset][...]
            unit = size_unit or size_data.attrs.get("units", "um")
            concentration_unit = dndr_unit or handle[dndr_dataset].attrs.get("units", "cm-3")
            definition = size_definition or size_data.attrs.get(
                "size_definition",
                handle.attrs.get("size_definition", SIZE_DEFINITIONS[0]),
            )
            if isinstance(unit, bytes):
                unit = unit.decode("utf-8")
            if isinstance(definition, bytes):
                definition = definition.decode("utf-8")
            if isinstance(concentration_unit, bytes):
                concentration_unit = concentration_unit.decode("utf-8")
        return cls(
            sizes,
            concentrations,
            str(unit),
            str(definition),
            dndr_unit=str(concentration_unit),
            source=str(source.resolve()),
            **kwargs,
        )

    @classmethod
    def from_file(
        cls,
        path: Union[str, Path],
        **kwargs: object,
    ) -> "SizeDistribution":
        source = Path(path).expanduser()
        suffix = source.suffix.lower()
        if suffix in {".csv", ".tsv"}:
            return cls.from_delimited(source, **kwargs)
        if suffix in {".nc", ".nc4", ".cdf"}:
            return cls.from_netcdf(source, **kwargs)
        if suffix in {".h5", ".hdf5", ".hdf"}:
            return cls.from_hdf5(source, **kwargs)
        raise ValueError(
            "unsupported PSD file extension {!r}; use CSV, TSV, NetCDF, or HDF5".format(suffix)
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, object],
        *,
        base_dir: Optional[Union[str, Path]] = None,
    ) -> "SizeDistribution":
        if value.get("type") == "lognormal":
            raise ValueError(
                "analytical PSD parameters are no longer scheme inputs; provide "
                "explicit size and dndr arrays, a PSD file, or construct "
                "SizeDistribution.from_callable() in Python"
            )
        size_definition = value.get(
            "size_definition",
            "volume_equivalent_sphere_radius",
        )
        size_unit = value.get("size_unit", "um")
        if value.get("file"):
            source = Path(str(value["file"])).expanduser()
            if not source.is_absolute() and base_dir is not None:
                source = Path(base_dir) / source
            kwargs = {
                "size_unit": str(size_unit),
                "size_definition": str(size_definition),
            }
            if source.suffix.lower() in {".csv", ".tsv"}:
                kwargs.update(
                    {
                        "size_column": value.get("size_column"),
                        "dndr_column": value.get("dndr_column"),
                    }
                )
            elif source.suffix.lower() in {".nc", ".nc4", ".cdf"}:
                kwargs.update(
                    {
                        "size_variable": str(value.get("size_variable", "size")),
                        "dndr_variable": str(value.get("dndr_variable", "dndr")),
                    }
                )
            else:
                kwargs.update(
                    {
                        "size_dataset": str(value.get("size_dataset", "size")),
                        "dndr_dataset": str(value.get("dndr_dataset", "dndr")),
                    }
                )
            return cls.from_file(source, **kwargs)
        size = value.get("size", value.get("sizes"))
        dndr = value.get("dndr", value.get("dNdr", value.get("values")))
        if size is None or dndr is None:
            raise ValueError("size_distribution requires inline size and dndr arrays or file")
        return cls(
            size,
            dndr,
            str(size_unit),
            str(size_definition),
            dndr_unit=str(value.get("dndr_unit", "cm-3")),
            integration_mode=str(value.get("integration_mode", INTEGRATION_MODE)),
            source=str(value.get("source", "inline_scheme")),
            metadata=(
                value.get("metadata") if isinstance(value.get("metadata"), Mapping) else None
            ),
        )
