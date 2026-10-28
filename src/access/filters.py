"""Validated filename/scientific filters, constraints and range parsing."""

from __future__ import annotations

import argparse
import fnmatch
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from zju_scatt_interface.access.models import (
    AnyNumericConstraint,
    AnyNumericTargetConstraint,
    NumericConstraint,
    NumericTargetConstraint,
    RemoteObject,
)
from zju_scatt_interface.errors import ScattError


@dataclass
class FilterSpec:
    """All filters are ANDed; repeated include globs are ORed."""

    include_globs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    contains: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    regexes: list[re.Pattern[str]] = field(default_factory=list)
    extensions: set[str] = field(default_factory=set)
    minimum_size: Optional[int] = None
    maximum_size: Optional[int] = None
    modified_after: Optional[datetime] = None
    modified_before: Optional[datetime] = None
    particle_types: list[str] = field(default_factory=list)
    numeric: list[NumericConstraint] = field(default_factory=list)
    numeric_targets: list[NumericTargetConstraint] = field(default_factory=list)
    any_numeric: list[AnyNumericConstraint] = field(default_factory=list)
    any_numeric_targets: list[AnyNumericTargetConstraint] = field(default_factory=list)
    custom_numeric: list[tuple[re.Pattern[str], float, float]] = field(default_factory=list)
    custom_numeric_targets: list[tuple[re.Pattern[str], tuple[float, ...], float]] = field(
        default_factory=list
    )
    shape_groups: list[list[tuple[re.Pattern[str], float, float]]] = field(default_factory=list)

    def matches(self, obj: RemoteObject) -> bool:
        from zju_scatt_interface.access.metadata import (
            extract_scatt_metadata,
            particle_type_matches,
        )

        key = obj.key
        name = obj.name
        lowered = key.lower()

        if self.include_globs and not any(
            fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(name, pattern)
            for pattern in self.include_globs
        ):
            return False
        if any(
            fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(name, pattern)
            for pattern in self.exclude_globs
        ):
            return False
        if any(value.lower() not in lowered for value in self.contains):
            return False
        if any(value.lower() in lowered for value in self.excludes):
            return False
        if any(pattern.search(key) is None for pattern in self.regexes):
            return False
        if self.extensions:
            extension = Path(name).suffix.lower().lstrip(".")
            if extension not in self.extensions:
                return False
        if self.minimum_size is not None and obj.size < self.minimum_size:
            return False
        if self.maximum_size is not None and obj.size > self.maximum_size:
            return False
        if self.modified_after or self.modified_before:
            modified = parse_datetime(obj.last_modified)
            if modified is None:
                return False
            if self.modified_after and modified < self.modified_after:
                return False
            if self.modified_before and modified > self.modified_before:
                return False

        if self.particle_types and not any(
            particle_type_matches(key, requested) for requested in self.particle_types
        ):
            return False

        metadata = extract_scatt_metadata(name)
        if self.shape_groups:
            from zju_scatt_interface.sources.shapes import matches_shapes

            if not matches_shapes(name, self.shape_groups):
                return False
        for constraint in self.numeric:
            value = metadata.get(constraint.name)
            if value is None or not constraint.minimum <= value <= constraint.maximum:
                return False
        for constraint in self.numeric_targets:
            value = metadata.get(constraint.name)
            if value is None or not any(
                abs(value - target) <= constraint.tolerance for target in constraint.targets
            ):
                return False
        for constraint in self.any_numeric:
            if not any(
                value is not None and constraint.minimum <= value <= constraint.maximum
                for value in (metadata.get(name) for name in constraint.names)
            ):
                return False
        for constraint in self.any_numeric_targets:
            if not any(
                value is not None
                and any(
                    abs(value - target) <= constraint.tolerance for target in constraint.targets
                )
                for value in (metadata.get(name) for name in constraint.names)
            ):
                return False
        for pattern, minimum, maximum in self.custom_numeric:
            match = pattern.search(key)
            if match is None:
                return False
            try:
                raw_value = match.group("value") if "value" in match.groupdict() else match.group(1)
                value = float(raw_value)
            except (IndexError, TypeError, ValueError):
                return False
            if not math.isfinite(value) or not minimum <= value <= maximum:
                return False
        for pattern, targets, tolerance in self.custom_numeric_targets:
            match = pattern.search(key)
            if match is None:
                return False
            try:
                raw_value = match.group("value") if "value" in match.groupdict() else match.group(1)
                value = float(raw_value)
            except (IndexError, TypeError, ValueError):
                return False
            if not math.isfinite(value) or not any(
                abs(value - target) <= tolerance for target in targets
            ):
                return False
        return True


def parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            result = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def parse_date_argument(value: str) -> datetime:
    result = parse_datetime(value)
    if result is None:
        raise argparse.ArgumentTypeError(
            "Expected an ISO date/time, for example 2026-04-20 or 2026-04-20T12:30:00Z"
        )
    return result


def parse_size(value: str) -> int:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgtpe]?i?b)?\s*", value, re.I)
    if not match:
        raise argparse.ArgumentTypeError("Use a size such as 500MB, 2GiB, or 1024")
    number = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    decimal = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    binary = {
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
        "PIB": 1024**5,
        "EIB": 1024**6,
    }
    multiplier = decimal.get(unit, binary.get(unit))
    if multiplier is None:
        raise argparse.ArgumentTypeError(f"Unsupported size unit: {unit}")
    return int(number * multiplier)


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(size) < 1024 or unit == "PiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def human_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def compile_filter(args: argparse.Namespace) -> FilterSpec:
    from zju_scatt_interface.access.metadata import (
        NUMBER_PATTERN,
        SIZE_METADATA_FIELDS,
        expand_string_list,
        particle_type_matches,
    )
    from zju_scatt_interface.access.models import (
        AnyNumericConstraint,
        AnyNumericTargetConstraint,
        NumericConstraint,
        NumericTargetConstraint,
    )
    from zju_scatt_interface.access.requests import (
        normalize_shape_targets,
        parse_float_targets,
        parse_optional_float,
        wavelength_range_values_to_um,
    )
    from zju_scatt_interface.sources.shapes import compile_shapes

    if getattr(args, "shapes", None) is not None and any(
        getattr(args, name, None)
        for name in ("param", "shape_target", "shape_targets", "n_range", "aspect_ratio")
    ):
        raise ScattError("Use shapes alone; it cannot be combined with legacy shape filters")
    shapes = getattr(args, "shapes", None)
    requested = expand_string_list(getattr(args, "particle_type", None) or [])
    if (
        shapes is not None
        and getattr(args, "api_mode", False)
        and (getattr(args, "target_wavelength", None) or getattr(args, "target_wavelengths", None))
        and getattr(args, "target_wavelength_mode", "interp") == "interp"
    ):
        from zju_scatt_interface.sources.selection import source_shapes

        shapes = source_shapes(shapes, requested)
    if (
        shapes is not None
        and getattr(args, "target_temperatures", None) is not None
        and requested
        and all(particle_type_matches("super_spheroid_ice", name) for name in requested)
    ):
        from zju_scatt_interface.optics.retrieval.ice import source_shapes

        shapes = source_shapes(shapes)
    spec = FilterSpec(
        shape_groups=compile_shapes(shapes),
        include_globs=list(getattr(args, "glob", None) or []),
        exclude_globs=list(getattr(args, "exclude_glob", None) or []),
        contains=list(getattr(args, "contains", None) or []),
        excludes=list(getattr(args, "exclude", None) or []),
        regexes=[
            re.compile(pattern, re.I if getattr(args, "ignore_case", False) else 0)
            for pattern in (getattr(args, "regex", None) or [])
        ],
        extensions={
            extension.lower().lstrip(".") for extension in (getattr(args, "extension", None) or [])
        },
        minimum_size=getattr(args, "min_size", None),
        maximum_size=getattr(args, "max_size", None),
        modified_after=getattr(args, "after", None),
        modified_before=getattr(args, "before", None),
        particle_types=expand_string_list(getattr(args, "particle_type", None) or []),
    )
    known_ranges = {
        "wavelength": "wavelength_um",
        "ref_real": "ref_real",
        "ref_imag": "ref_imag",
        "n_range": "n",
        "aspect_ratio": "aspect_ratio",
    }
    for argument_name, metadata_name in known_ranges.items():
        values = getattr(args, argument_name, None)
        if values:
            if argument_name == "wavelength":
                minimum, maximum = wavelength_range_values_to_um(
                    values,
                    getattr(args, "wavelength_unit", None),
                    "wavelength_range",
                )
            else:
                minimum, maximum = map(float, values)
            validate_range(minimum, maximum, argument_name)
            spec.numeric.append(NumericConstraint(metadata_name, minimum, maximum))

    if getattr(args, "command", None) != "retrieve":
        target_ranges = {
            "ref_real_target": ("ref_real", "ref_real_target"),
            "ref_imag_target": ("ref_imag", "ref_imag_target"),
        }
        for argument_name, (metadata_name, label) in target_ranges.items():
            targets = parse_float_targets(getattr(args, argument_name, None), label)
            if targets:
                tolerance = parse_optional_float(
                    getattr(args, f"{argument_name}_tolerance", None),
                    f"{label}_tolerance",
                )
                spec.numeric_targets.append(
                    NumericTargetConstraint(
                        metadata_name,
                        tuple(targets),
                        tolerance if tolerance is not None else 1e-9,
                    )
                )

    values = getattr(args, "size_range", None)
    if values:
        minimum, maximum = map(float, values)
        validate_range(minimum, maximum, "size_range")
        spec.any_numeric.append(
            AnyNumericConstraint("size_range", SIZE_METADATA_FIELDS, minimum, maximum)
        )
    if getattr(args, "command", None) != "retrieve":
        targets = parse_float_targets(getattr(args, "target_size", None), "target_size")
        if targets:
            tolerance = parse_optional_float(
                getattr(args, "target_size_tolerance", None),
                "target_size_tolerance",
            )
            spec.any_numeric_targets.append(
                AnyNumericTargetConstraint(
                    "target_size",
                    SIZE_METADATA_FIELDS,
                    tuple(targets),
                    tolerance if tolerance is not None else 1e-9,
                )
            )

    for name, minimum_text, maximum_text in getattr(args, "param", None) or []:
        minimum, maximum = float(minimum_text), float(maximum_text)
        validate_range(minimum, maximum, name)
        escaped = re.escape(name)
        pattern = re.compile(rf"(?:^|_){escaped}_(?P<value>{NUMBER_PATTERN})(?=_|\.|$)", re.I)
        spec.custom_numeric.append((pattern, minimum, maximum))
    for pattern_text, minimum_text, maximum_text in getattr(args, "value_regex", None) or []:
        minimum, maximum = float(minimum_text), float(maximum_text)
        validate_range(minimum, maximum, pattern_text)
        try:
            pattern = re.compile(pattern_text, re.I if getattr(args, "ignore_case", False) else 0)
        except re.error as exc:
            raise ScattError(f"Invalid value regex {pattern_text!r}: {exc}") from exc
        if pattern.groups < 1 and "value" not in pattern.groupindex:
            raise ScattError(
                f"Value regex {pattern_text!r} needs a capture group, e.g. temp_([0-9.]+)"
            )
        spec.custom_numeric.append((pattern, minimum, maximum))
    if getattr(args, "command", None) != "retrieve":
        tolerance = parse_optional_float(
            getattr(args, "shape_target_tolerance", None),
            "shape_target_tolerance",
        )
        for name, targets, item_tolerance in normalize_shape_targets(
            getattr(args, "shape_target", None)
        ):
            pattern = re.compile(
                rf"(?:^|_){re.escape(name)}_(?P<value>{NUMBER_PATTERN})(?=_|\.|$)",
                re.I,
            )
            spec.custom_numeric_targets.append(
                (
                    pattern,
                    tuple(targets),
                    item_tolerance
                    if item_tolerance is not None
                    else tolerance
                    if tolerance is not None
                    else 1e-9,
                )
            )
    return spec


def validate_range(minimum: float, maximum: float, label: str) -> None:
    if not (math.isfinite(minimum) and math.isfinite(maximum)):
        raise ScattError(f"Range for {label} must contain finite numbers")
    if minimum > maximum:
        raise ScattError(f"Range minimum exceeds maximum for {label}")
