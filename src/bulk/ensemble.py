"""Explicit shape weights and physical combination of integrated populations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.optics.models import BulkOptics


@dataclass(frozen=True, init=False)
class WeightedValues:
    """Independent parameter values with validated, normalized weights."""

    values: tuple[float | str, ...]
    weights: tuple[float, ...]

    def __init__(self, values: Sequence[float | str], weights: Sequence[float]):
        value_tuple = tuple(values)
        weight_tuple = tuple(float(value) for value in weights)
        if not value_tuple:
            raise ValueError("WeightedValues requires at least one value")
        if len(value_tuple) != len(weight_tuple):
            raise ValueError("WeightedValues values and weights must have equal length")
        if any(not math.isfinite(value) or value < 0 for value in weight_tuple):
            raise ValueError("WeightedValues weights must be finite and non-negative")
        total = sum(weight_tuple)
        if total <= 0:
            raise ValueError("WeightedValues weights must have a positive sum")
        object.__setattr__(self, "values", value_tuple)
        object.__setattr__(self, "weights", tuple(value / total for value in weight_tuple))

    @classmethod
    def from_value(cls, value: object) -> "WeightedValues":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping) and "values" in value:
            return cls(value["values"], value.get("weights", []))
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            raise ValueError(
                "Multiple parameter values require explicit weights; use "
                "WeightedValues(values, weights)"
            )
        return cls([value], [1.0])

    def to_dict(self) -> dict[str, object]:
        return {"values": list(self.values), "weights": list(self.weights)}


@dataclass(frozen=True, init=False)
class WeightedShapeMember:
    """One correlated parameter/shape state and its population weight."""

    parameters: Mapping[str, float | str]
    weight: float

    def __init__(
        self,
        parameters: Mapping[str, float | str] | None = None,
        weight: float = 1.0,
        **coordinates: float | str,
    ):
        merged = dict(parameters or {})
        overlap = set(merged).intersection(coordinates)
        if overlap:
            raise ValueError(
                "WeightedShapeMember duplicate parameters: " + ", ".join(sorted(overlap))
            )
        merged.update(coordinates)
        if not merged:
            raise ValueError("WeightedShapeMember requires at least one parameter")
        numeric_weight = float(weight)
        if not math.isfinite(numeric_weight) or numeric_weight < 0:
            raise ValueError("WeightedShapeMember weight must be finite and non-negative")
        object.__setattr__(self, "parameters", merged)
        object.__setattr__(self, "weight", numeric_weight)

    def to_dict(self) -> dict[str, object]:
        return {"parameters": dict(self.parameters), "weight": self.weight}


@dataclass(frozen=True, init=False)
class WeightedShapeEnsemble:
    """Validated joint members whose weights sum to one."""

    members: tuple[WeightedShapeMember, ...]

    def __init__(self, members: Sequence[WeightedShapeMember | Mapping[str, object]]):
        parsed = []
        for member in members:
            if isinstance(member, WeightedShapeMember):
                parsed.append(member)
                continue
            if not isinstance(member, Mapping):
                raise ValueError("shape ensemble members must be mappings")
            values = dict(member)
            weight = values.pop("weight", 1.0)
            parameters = values.pop("parameters", None)
            if values and parameters:
                raise ValueError(
                    "shape member must use either parameters or direct coordinate keys"
                )
            parsed.append(
                WeightedShapeMember(
                    parameters if parameters is not None else values,
                    weight=float(weight),
                )
            )
        if not parsed:
            raise ValueError("WeightedShapeEnsemble requires at least one member")
        total = sum(member.weight for member in parsed)
        if total <= 0:
            raise ValueError("shape ensemble weights must have a positive sum")
        object.__setattr__(
            self,
            "members",
            tuple(
                WeightedShapeMember(member.parameters, member.weight / total) for member in parsed
            ),
        )

    @classmethod
    def from_shapes(cls, shapes, weights=None):
        """Build paired shape members, with equal weights when omitted."""
        shapes = tuple(shapes)
        weights = tuple(weights) if weights is not None else (1.0,) * len(shapes)
        if len(shapes) != len(weights):
            raise ValueError("shapes and weights must have equal length")
        return cls(
            [WeightedShapeMember(shape, weight=weight) for shape, weight in zip(shapes, weights)]
        )

    def to_dict(self) -> dict[str, object]:
        return {"members": [member.to_dict() for member in self.members]}


def _normalize_parameter_name(name: str) -> str:
    from zju_scatt_interface.config.particles import normalize_parameter_name

    return normalize_parameter_name(name)


def _ensemble_members(
    parameters: Mapping[str, object] | None,
    shape_ensemble: WeightedShapeEnsemble | Sequence[WeightedShapeMember] | None,
) -> tuple[list[tuple[dict[str, float | str], float]], dict[str, object]]:
    independent: list[tuple[str, WeightedValues]] = []
    for raw_name, value in (parameters or {}).items():
        name = _normalize_parameter_name(raw_name)
        independent.append((name, WeightedValues.from_value(value)))
    independent_names = {name for name, _ in independent}
    joint = (
        shape_ensemble
        if isinstance(shape_ensemble, WeightedShapeEnsemble)
        else WeightedShapeEnsemble(shape_ensemble)
        if shape_ensemble is not None
        else None
    )
    joint_members = (
        list(joint.members)
        if joint is not None
        else [WeightedShapeMember({"__no_joint_shape__": 0.0}, 1.0)]
    )
    result: list[tuple[dict[str, float | str], float]] = []
    choices = [list(zip(weighted.values, weighted.weights)) for _, weighted in independent]
    independent_products = list(product(*choices)) if choices else [()]
    for combination in independent_products:
        base = {name: value for (name, _), (value, _weight) in zip(independent, combination)}
        base_weight = math.prod(weight for _value, weight in combination) if combination else 1.0
        for member in joint_members:
            joint_parameters = {
                _normalize_parameter_name(name): value
                for name, value in member.parameters.items()
                if name != "__no_joint_shape__"
            }
            overlap = independent_names.intersection(joint_parameters)
            if overlap:
                raise ValueError(
                    "Parameters cannot be supplied both independently and in a joint "
                    "shape member: " + ", ".join(sorted(overlap))
                )
            result.append(({**base, **joint_parameters}, base_weight * member.weight))
    total = sum(weight for _parameters, weight in result)
    normalized = [(member_parameters, weight / total) for member_parameters, weight in result]
    provenance = {
        "member_count": len(normalized),
        "independent": {name: weighted.to_dict() for name, weighted in independent},
        "joint_shape_ensemble": joint.to_dict() if joint is not None else None,
        "weight_sum": sum(weight for _parameters, weight in normalized),
    }
    return normalized, provenance


def _nested_weighted_sum(values: Sequence[Any], weights: Sequence[float]) -> Any:
    first = values[0]
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        if any(len(value) != len(first) for value in values):
            raise ValueError("Ensemble phase matrices must have identical shapes")
        return [
            _nested_weighted_sum([value[index] for value in values], weights)
            for index in range(len(first))
        ]
    return sum(float(value) * weight for value, weight in zip(values, weights))


@_registration_required
def combine(
    results: Sequence[BulkOptics],
    weights: Sequence[float] | None = None,
    *,
    metadata: Mapping[str, object] | None = None,
) -> BulkOptics:
    """Combine extensive coefficients and re-derive all intensive properties."""
    from zju_scatt_interface.optics.models import BulkOptics

    if not results:
        raise ValueError("At least one bulk result is required")
    numeric_weights = (
        [1.0] * len(results) if weights is None else [float(value) for value in weights]
    )
    if len(numeric_weights) != len(results):
        raise ValueError("Bulk result and weight lengths must match")
    if any(not math.isfinite(value) or value < 0 for value in numeric_weights):
        raise ValueError("Bulk combination weights must be finite and non-negative")
    if sum(numeric_weights) <= 0:
        raise ValueError("Bulk combination weights must have a positive sum")

    def extensive(attribute: str) -> float | None:
        values = [getattr(result, attribute) for result in results]
        if all(value is None for value in values):
            return None
        if any(value is None for value in values):
            raise ValueError(f"Ensemble members inconsistently provide {attribute}")
        return sum(weight * float(value) for weight, value in zip(numeric_weights, values))

    beta_ext = extensive("extinction_coefficient")
    beta_sca = extensive("scattering_coefficient")
    beta_abs = extensive("absorption_coefficient")
    ssa = beta_sca / beta_ext if beta_ext not in (None, 0.0) and beta_sca is not None else None
    scattering_weights = [
        weight * float(result.scattering_coefficient or 0.0)
        for weight, result in zip(numeric_weights, results)
    ]
    g = None
    if beta_sca not in (None, 0.0) and any(
        result.asymmetry_factor is not None for result in results
    ):
        if any(result.asymmetry_factor is None for result in results):
            raise ValueError("Ensemble members inconsistently provide asymmetry_factor")
        g = (
            sum(
                weight * float(result.asymmetry_factor)
                for weight, result in zip(scattering_weights, results)
            )
            / beta_sca
        )
    phase = None
    phases = [result.phase_matrix for result in results]
    if any(value is not None for value in phases):
        if any(value is None for value in phases):
            raise ValueError("Ensemble members inconsistently provide phase_matrix")
        if beta_sca in (None, 0.0):
            phase = None
        else:
            phase = _nested_weighted_sum(phases, [value / beta_sca for value in scattering_weights])
    return BulkOptics(
        extinction_coefficient=beta_ext,
        scattering_coefficient=beta_sca,
        absorption_coefficient=beta_abs,
        single_scattering_albedo=ssa,
        asymmetry_factor=g,
        phase_matrix=phase,
        number_concentration=sum(
            weight * result.number_concentration for weight, result in zip(numeric_weights, results)
        ),
        size_count=max(result.size_count for result in results),
        metadata={
            "bulk_coefficient_unit": "m-1",
            "number_concentration_output_unit": "cm-3",
            "combination": "extensive_linear_intensive_rederived",
            **dict(metadata or {}),
        },
    )
