"""sources / shapes domain implementation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from numbers import Real

from zju_scatt_interface.config.particles import (
    PARAMETER_ALIASES,
    normalize_parameter_name,
)
from zju_scatt_interface.errors import ScattError

SHAPE_AXES = {"roundness", "aspect_ratio", "df"}


def compile_shapes(shapes):
    """Compile a mapping or nonempty list of mappings to paired predicates.

    Scalars select exact coordinates; two-item tuples select inclusive ranges.
    Each mapping describes a combination, not independent per-axis targets.
    Only filename geometry is selected; internal vf/RH/size axes stay intact.
    """
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN

    if shapes is None:
        return []
    if isinstance(shapes, Mapping):
        shapes = [shapes]
    if not isinstance(shapes, list) or not shapes:
        raise ScattError("shapes must be a nonempty mapping or a nonempty list of mappings")
    groups = []
    for shape in shapes:
        if not isinstance(shape, Mapping) or not shape:
            raise ScattError("Each shapes entry must be a nonempty mapping")
        group = []
        seen = set()
        for name, value in shape.items():
            if not isinstance(name, str):
                raise ScattError("Shape parameter names must be strings")
            canonical = normalize_parameter_name(name)
            if canonical not in SHAPE_AXES:
                raise ScattError(
                    f"Unsupported shape parameter {name!r}; use roundness/n, aspect_ratio/asp or df"
                )
            if canonical in seen:
                raise ScattError(f"Duplicate aliases for shape parameter {canonical!r}")
            seen.add(canonical)
            bounds = value if isinstance(value, tuple) else (value, value)
            if len(bounds) != 2 or any(
                isinstance(item, bool) or not isinstance(item, Real) for item in bounds
            ):
                raise ScattError(
                    f"Shape parameter {name!r} requires a number or a two-number tuple (minimum, maximum)"
                )
            minimum, maximum = map(float, bounds)
            if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
                raise ScattError(
                    f"Shape parameter {name!r} requires finite, increasing range bounds"
                )
            tokens = {canonical} | {
                alias for alias, axis in PARAMETER_ALIASES.items() if axis == canonical
            }
            pattern = re.compile(
                rf"(?:^|_)(?:{'|'.join(re.escape(token) for token in sorted(tokens))})_({NUMBER_PATTERN})(?=_|\.|$)",
                re.I,
            )
            group.append((pattern, minimum, maximum))
        groups.append(group)
    return groups


def matches_shapes(filename, groups):
    """Match source filenames without creating cross-combinations of entries."""
    for group in groups:
        for pattern, minimum, maximum in group:
            match = pattern.search(filename)
            if match is None:
                break
            value = float(match.group(1))
            if not math.isfinite(value):
                break
            if minimum == maximum:
                if not math.isclose(value, minimum, rel_tol=0, abs_tol=1e-9):
                    break
            elif not minimum <= value <= maximum:
                break
        else:
            return True
    return not groups
