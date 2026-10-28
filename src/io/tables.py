"""io / tables domain implementation."""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Union

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.bulk.grid import BulkGrid, MultiBulkGrid
from zju_scatt_interface.bulk.models import BulkDataset
from zju_scatt_interface.io.canonical import (
    build_bulk_output_schema,
    build_multidimensional_bulk_output_schema,
    read,
)

RecordTransform = Callable[[dict[str, object]], Mapping[str, object]]
RecordFilter = Callable[[Mapping[str, object]], bool]
ValueTransform = Callable[[object, Mapping[str, object]], object]

_PHASE_FIELDS = frozenset({"sca_angle", "p11", "p12", "p22", "p33", "p43", "p44"})
_FIELD_ALIASES = {
    "wavelength_um": "wavelength",
    "extinction_coefficient": "beta_ext",
    "scattering_coefficient": "beta_sca",
    "absorption_coefficient": "beta_abs",
    "single_scattering_albedo": "ssa",
    "asymmetry_factor": "g",
    "scattering_angle_degrees": "sca_angle",
}
_MISSING = object()


@dataclass(frozen=True)
class OpticalTableColumn:
    """One output column selected from a canonical optical record."""

    field: str
    name: Optional[str] = None
    unit: str = ""
    format: Optional[str] = None
    scale: float = 1.0
    offset: float = 0.0
    transform: Optional[ValueTransform] = None

    def __post_init__(self) -> None:
        if not str(self.field).strip():
            raise ValueError("table column field cannot be empty")
        if not math.isfinite(float(self.scale)) or not math.isfinite(float(self.offset)):
            raise ValueError("table column scale and offset must be finite")
        if self.transform is not None and not callable(self.transform):
            raise TypeError("table column transform must be callable")

    @property
    def output_name(self) -> str:
        return self.name or self.field

    @classmethod
    def from_value(cls, value: object) -> "OpticalTableColumn":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value)
        if not isinstance(value, Mapping):
            raise TypeError("each table column must be a field name or mapping")
        allowed = {"field", "name", "unit", "format", "scale", "offset", "transform"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown table-column keys: {', '.join(unknown)}")
        if "field" not in value:
            raise ValueError("each table column mapping requires 'field'")
        return cls(**dict(value))


@dataclass(frozen=True)
class OpticalTableFormat:
    """Complete, versionable specification for a rendered optical table."""

    name: str
    columns: tuple[OpticalTableColumn, ...]
    delimiter: str = " "
    header_lines: tuple[str, ...] = ()
    include_column_header: bool = True
    include_unit_header: bool = False
    comment_prefix: str = "# "
    row_template: Optional[str] = None
    missing_value: str = "nan"
    strict_fields: bool = True
    line_ending: str = "\n"
    layout: str = "combined"
    filename_template: str = "{stem}_{component}{suffix}"
    record_transform: Optional[RecordTransform] = None
    record_filter: Optional[RecordFilter] = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValueError("table format name cannot be empty")
        if not self.columns:
            raise ValueError("table format requires at least one column")
        output_names = [column.output_name for column in self.columns]
        if len(output_names) != len(set(output_names)):
            raise ValueError("table column output names must be unique")
        if self.layout not in {"combined", "per_component"}:
            raise ValueError("layout must be 'combined' or 'per_component'")
        if self.line_ending not in {"\n", "\r\n"}:
            raise ValueError("line_ending must be '\\n' or '\\r\\n'")
        if self.record_transform is not None and not callable(self.record_transform):
            raise TypeError("record_transform must be callable")
        if self.record_filter is not None and not callable(self.record_filter):
            raise TypeError("record_filter must be callable")
        if self.layout == "per_component" and "{component}" not in self.filename_template:
            raise ValueError("per_component filename_template must contain {component}")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "OpticalTableFormat":
        allowed = {
            "name",
            "columns",
            "delimiter",
            "header_lines",
            "include_column_header",
            "include_unit_header",
            "comment_prefix",
            "row_template",
            "missing_value",
            "strict_fields",
            "line_ending",
            "layout",
            "filename_template",
            "record_transform",
            "record_filter",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown optical-table format keys: {', '.join(unknown)}")
        if "name" not in value or "columns" not in value:
            raise ValueError("table format requires 'name' and 'columns'")
        parameters = dict(value)
        columns = parameters["columns"]
        if isinstance(columns, (str, bytes)) or not isinstance(columns, Sequence):
            raise TypeError("table format columns must be a sequence")
        parameters["columns"] = tuple(OpticalTableColumn.from_value(item) for item in columns)
        parameters["header_lines"] = tuple(parameters.get("header_lines", ()))
        return cls(**parameters)


FormatInput = Union[OpticalTableFormat, Mapping[str, object], str, Path]
DataInput = Union[
    BulkDataset,
    BulkGrid,
    MultiBulkGrid,
    Mapping[str, object],
    str,
    Path,
]


@_registration_required
def load_optical_table_format(path: Union[str, Path]) -> OpticalTableFormat:
    """Load a JSON specification or a trusted Python specification script."""

    source = Path(path).expanduser().resolve()
    if source.suffix.lower() == ".json":
        content = json.loads(source.read_text(encoding="utf-8"))
    elif source.suffix.lower() == ".py":
        module_name = f"_zju_scatt_table_format_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, source)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load Python table format {source}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        content = next(
            (
                getattr(module, name)
                for name in ("optical_table_format", "OPTICAL_TABLE_FORMAT", "format_spec")
                if hasattr(module, name)
            ),
            None,
        )
        if content is None:
            raise ValueError(
                "Python format script must define optical_table_format, "
                "OPTICAL_TABLE_FORMAT, or format_spec"
            )
    else:
        raise ValueError("table format must be a .json or .py file")
    return _normalize_format(content)


def _normalize_format(value: FormatInput) -> OpticalTableFormat:
    if isinstance(value, OpticalTableFormat):
        return value
    if isinstance(value, (str, Path)):
        return load_optical_table_format(value)
    if isinstance(value, Mapping):
        return OpticalTableFormat.from_mapping(value)
    raise TypeError("format_spec must be an OpticalTableFormat, mapping, JSON, or Python file")


def _normalize_content(data: DataInput) -> Mapping[str, object]:
    if isinstance(data, BulkDataset):
        return build_bulk_output_schema(data)
    if isinstance(data, (BulkGrid, MultiBulkGrid)):
        return build_multidimensional_bulk_output_schema(data)
    if isinstance(data, (str, Path)):
        return read(data)
    if isinstance(data, Mapping):
        if "components" not in data:
            raise ValueError("canonical output mapping requires 'components'")
        return data
    raise TypeError("data must be a bulk result, canonical mapping, or NC/HDF5 output path")


def _nested_value(data: object, indices: Sequence[int]) -> object:
    value = data
    for index in indices:
        value = value[index]  # type: ignore[index]
    if hasattr(value, "item"):
        value = value.item()
    return value


def _attribute_list(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = [item.strip() for item in value.split(",") if item.strip()]
        value = decoded
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else []


def _component_dimensions(component: Mapping[str, object]) -> tuple[str, ...]:
    attributes = component.get("attributes", {})
    if isinstance(attributes, Mapping):
        declared = _attribute_list(attributes.get("dimension_names"))
        if declared:
            return tuple(declared)
    datasets = component.get("datasets", {})
    if not isinstance(datasets, Mapping) or "beta_ext" not in datasets:
        raise ValueError("component is missing canonical beta_ext data")
    beta_ext = datasets["beta_ext"]
    if not isinstance(beta_ext, Mapping):
        raise ValueError("component beta_ext dataset is invalid")
    return tuple(str(item) for item in beta_ext.get("dimensions", ()))


def _coordinate_values(
    dimension: str,
    component_datasets: Mapping[str, object],
    root_datasets: Mapping[str, object],
) -> Sequence[object]:
    candidate = component_datasets.get(dimension, root_datasets.get(dimension))
    if not isinstance(candidate, Mapping) or "data" not in candidate:
        raise ValueError(f"missing coordinate dataset for dimension {dimension!r}")
    values = candidate["data"]
    if isinstance(values, (str, bytes)) or not hasattr(values, "__len__"):
        raise ValueError(f"coordinate dataset {dimension!r} is not one-dimensional")
    return values  # type: ignore[return-value]


def _canonical_field(field: str) -> str:
    return _FIELD_ALIASES.get(field, field)


def _requested_phase(format_spec: OpticalTableFormat) -> bool:
    return any(_canonical_field(column.field) in _PHASE_FIELDS for column in format_spec.columns)


def _records_for_component(
    name: str,
    component: Mapping[str, object],
    root_datasets: Mapping[str, object],
    include_phase: bool,
) -> list[dict[str, object]]:
    datasets = component.get("datasets", {})
    attributes = component.get("attributes", {})
    if not isinstance(datasets, Mapping) or not isinstance(attributes, Mapping):
        raise ValueError(f"component {name!r} has an invalid canonical structure")
    dimensions = _component_dimensions(component)
    coordinates = {
        dimension: _coordinate_values(dimension, datasets, root_datasets)
        for dimension in dimensions
    }
    shapes = tuple(len(coordinates[dimension]) for dimension in dimensions)
    grid_datasets = {
        dataset_name: dataset
        for dataset_name, dataset in datasets.items()
        if isinstance(dataset, Mapping) and tuple(dataset.get("dimensions", ())) == dimensions
    }
    wavelength_dimension = str(attributes.get("wavelength_dimension", "wavelength"))
    records: list[dict[str, object]] = []
    for flat_index, indices in enumerate(itertools.product(*(range(size) for size in shapes))):
        record: dict[str, object] = {
            "component": name,
            "particle_type": attributes.get("particle_type", ""),
            "flat_index": flat_index,
        }
        for dimension, index in zip(dimensions, indices):
            record[dimension] = coordinates[dimension][index]
        for dataset_name, dataset in grid_datasets.items():
            record[dataset_name] = _nested_value(dataset["data"], indices)
        if wavelength_dimension in record:
            record["wavelength"] = record[wavelength_dimension]
            record["wavelength_um"] = record[wavelength_dimension]
        for alias, canonical in _FIELD_ALIASES.items():
            if canonical in record:
                record[alias] = record[canonical]
        if not include_phase:
            records.append(record)
            continue
        angle_dataset = datasets.get("sca_angle")
        if not isinstance(angle_dataset, Mapping):
            raise ValueError(f"component {name!r} has no phase-matrix angle data")
        angles = angle_dataset.get("data", ())
        for angle_index, angle in enumerate(angles):
            phase_record = dict(record)
            phase_record["sca_angle"] = angle
            phase_record["scattering_angle_degrees"] = angle
            for field in _PHASE_FIELDS - {"sca_angle"}:
                dataset = datasets.get(field)
                if isinstance(dataset, Mapping):
                    phase_record[field] = _nested_value(dataset["data"], (*indices, angle_index))
            records.append(phase_record)
    return records


@_registration_required
def bulk_output_records(
    data: DataInput,
    *,
    include_phase: bool = False,
) -> list[dict[str, object]]:
    """Flatten canonical bulk output into model-independent optical records."""

    content = _normalize_content(data)
    root_datasets = content.get("datasets", {})
    components = content.get("components", {})
    if not isinstance(root_datasets, Mapping) or not isinstance(components, Mapping):
        raise ValueError("canonical output has invalid datasets or components")
    records: list[dict[str, object]] = []
    for name, component in components.items():
        if not isinstance(component, Mapping):
            raise ValueError(f"component {name!r} is invalid")
        records.extend(_records_for_component(str(name), component, root_datasets, include_phase))
    return records


def _column_value(
    column: OpticalTableColumn,
    record: Mapping[str, object],
    *,
    strict: bool,
) -> object:
    canonical = _canonical_field(column.field)
    value = record.get(column.field, record.get(canonical, _MISSING))
    if value is _MISSING:
        if strict:
            raise ValueError(
                f"field {column.field!r} is unavailable for component {record.get('component')!r}"
            )
        return None
    if column.transform is not None:
        return column.transform(value, record)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) * float(column.scale) + float(column.offset)
    if column.scale != 1.0 or column.offset != 0.0:
        raise TypeError(f"cannot apply scale/offset to nonnumeric field {column.field!r}")
    return value


def _formatted_value(value: object, column: OpticalTableColumn, missing: str) -> str:
    if value is None:
        return missing
    if isinstance(value, float) and math.isnan(value):
        return missing
    return format(value, column.format or "")


def _safe_component(value: object) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    if not safe:
        raise ValueError("component name cannot produce a safe output filename")
    return safe


def _render_table(
    records: Sequence[Mapping[str, object]],
    format_spec: OpticalTableFormat,
    *,
    component: str,
) -> str:
    transformed: list[Mapping[str, object]] = []
    for original in records:
        record: Mapping[str, object] = original
        if format_spec.record_transform is not None:
            record = dict(format_spec.record_transform(dict(original)))
        if format_spec.record_filter is None or format_spec.record_filter(record):
            transformed.append(record)
    context = {
        "format_name": format_spec.name,
        "component": component,
        "record_count": len(transformed),
        "column_count": len(format_spec.columns),
        "column_names": format_spec.delimiter.join(
            column.output_name for column in format_spec.columns
        ),
        "column_units": format_spec.delimiter.join(
            column.unit or "1" for column in format_spec.columns
        ),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    lines = [
        format_spec.comment_prefix + template.format_map(context)
        for template in format_spec.header_lines
    ]
    if format_spec.include_column_header:
        lines.append(
            format_spec.comment_prefix
            + format_spec.delimiter.join(column.output_name for column in format_spec.columns)
        )
    if format_spec.include_unit_header:
        lines.append(
            format_spec.comment_prefix
            + format_spec.delimiter.join(column.unit or "1" for column in format_spec.columns)
        )
    for record in transformed:
        values = {
            column.output_name: _column_value(column, record, strict=format_spec.strict_fields)
            for column in format_spec.columns
        }
        if format_spec.row_template is not None:
            try:
                lines.append(format_spec.row_template.format_map(values))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"could not render row_template: {exc}") from exc
        else:
            lines.append(
                format_spec.delimiter.join(
                    _formatted_value(values[column.output_name], column, format_spec.missing_value)
                    for column in format_spec.columns
                )
            )
    return format_spec.line_ending.join(lines) + format_spec.line_ending


def _write_text_atomic(path: Path, content: str, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding=encoding, newline="")
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


@_registration_required
def write_formatted_optical_output(
    path: Union[str, Path],
    data: DataInput,
    format_spec: FormatInput,
    *,
    encoding: str = "utf-8",
) -> Union[Path, tuple[Path, ...]]:
    """Render bulk optics to a user-defined text table, atomically."""

    destination = Path(path).expanduser().resolve()
    specification = _normalize_format(format_spec)
    records = bulk_output_records(data, include_phase=_requested_phase(specification))
    if specification.layout == "combined":
        _write_text_atomic(
            destination,
            _render_table(records, specification, component="all"),
            encoding,
        )
        return destination
    written: list[Path] = []
    components = list(dict.fromkeys(str(record["component"]) for record in records))
    targets: list[tuple[str, Path]] = []
    for component in components:
        safe_component = _safe_component(component)
        filename = specification.filename_template.format(
            stem=destination.stem,
            suffix=destination.suffix,
            component=safe_component,
        )
        if Path(filename).name != filename:
            raise ValueError("filename_template must produce a filename, not a path")
        component_path = destination.with_name(filename)
        targets.append((component, component_path))
    if len({path for _, path in targets}) != len(targets):
        raise ValueError("filename_template produces duplicate component output paths")
    for component, component_path in targets:
        component_records = [record for record in records if str(record["component"]) == component]
        _write_text_atomic(
            component_path,
            _render_table(component_records, specification, component=component),
            encoding,
        )
        written.append(component_path)
    return tuple(written)
