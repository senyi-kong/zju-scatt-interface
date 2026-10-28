"""Wavelength and numeric-coordinate source selection."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional, Sequence, Union

from zju_scatt_interface.access.models import (
    NumericSelectionProcessing,
    RemoteObject,
    WavelengthProcessing,
)
from zju_scatt_interface.errors import ScattError


def object_wavelength_um(obj: RemoteObject) -> Optional[float]:
    from zju_scatt_interface.access.metadata import extract_scatt_metadata

    return extract_scatt_metadata(obj.name).get("wavelength_um")


def object_refractive_point(obj: RemoteObject) -> Optional[tuple[float, float]]:
    from zju_scatt_interface.access.metadata import extract_scatt_metadata

    metadata = extract_scatt_metadata(obj.name)
    real = metadata.get("ref_real")
    imaginary = metadata.get("ref_imag")
    if real is None or imaginary is None:
        return None
    return real, imaginary


def object_series_key(obj: RemoteObject) -> str:
    from zju_scatt_interface.access.catalog import relative_remote_key
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN

    key = relative_remote_key(obj.key)
    key = re.sub(
        rf"wl_{NUMBER_PATTERN}(?:_(?:nm|um|mm|m))?",
        "wl_*",
        key,
        flags=re.I,
    )
    key = re.sub(
        rf"ref_{NUMBER_PATTERN}_{NUMBER_PATTERN}",
        "ref_*_*",
        key,
        flags=re.I,
    )
    key = re.sub(rf"water_{NUMBER_PATTERN}_{NUMBER_PATTERN}", "water_*_*", key, flags=re.I)
    return key


def object_numeric_value(obj: RemoteObject, names: Sequence[str]) -> Optional[float]:
    from zju_scatt_interface.access.metadata import (
        NUMBER_PATTERN,
        extract_scatt_metadata,
        finite_float,
    )

    metadata = extract_scatt_metadata(obj.name)
    for name in names:
        if name in metadata:
            return metadata[name]
    for name in names:
        match = re.search(
            rf"(?:^|_){re.escape(name)}_({NUMBER_PATTERN})(?=_|\.|$)",
            obj.name,
            re.I,
        )
        if match:
            value = finite_float(match.group(1))
            if value is not None:
                return value
    return None


def normalize_target_wavelengths(
    target_um: Optional[Union[float, Sequence[float]]],
) -> list[float]:
    if target_um is None:
        return []
    if isinstance(target_um, (int, float)):
        values = [float(target_um)]
    else:
        values = [float(value) for value in target_um]
    for value in values:
        if not math.isfinite(value):
            raise ScattError("Target wavelength must be finite")
        if value <= 0:
            raise ScattError("Target wavelength must be positive")
    unique: list[float] = []
    for value in values:
        if not any(abs(value - existing) <= 1e-12 for existing in unique):
            unique.append(value)
    return unique


def normalize_target_wavelength_mode(value: object) -> str:
    mode = str(value or "interp").strip().casefold()
    aliases = {
        "interpolate": "interp",
        "interpolation": "interp",
        "interp": "interp",
        "nearest": "nearest",
        "nearest_wavelength": "nearest",
    }
    if mode not in aliases:
        raise ScattError("target wavelength mode must be 'interp' or 'nearest'")
    return aliases[mode]


def normalize_target_refractive_points(
    real_targets: Optional[Sequence[float]],
    imag_targets: Optional[Sequence[float]],
    target_count: int,
) -> list[Optional[tuple[float, float]]]:
    real_values = list(real_targets or [])
    imag_values = list(imag_targets or [])
    if not real_values and not imag_values:
        return [None for _ in range(target_count)]
    if not real_values or not imag_values:
        return [None for _ in range(target_count)]
    if len(real_values) != len(imag_values):
        raise ScattError(
            "Refractive-index interpolation for target wavelengths requires "
            "matching real and imaginary target counts"
        )
    if len(real_values) == 1:
        point = (float(real_values[0]), float(imag_values[0]))
        return [point for _ in range(target_count)]
    if len(real_values) != target_count:
        raise ScattError("Refractive-index target count must be one or match target wavelengths")
    return [(float(real), float(imaginary)) for real, imaginary in zip(real_values, imag_values)]


def refractive_distance(
    left: tuple[float, float],
    right: tuple[float, float],
) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def estimate_target_refractive_point(
    values: Sequence[tuple[RemoteObject, float, tuple[float, float]]],
    target_um: float,
    tolerance_um: float,
) -> tuple[Optional[tuple[float, float]], str]:
    exact = [
        ref_point
        for _item, wavelength, ref_point in values
        if abs(wavelength - target_um) <= tolerance_um
    ]
    if exact:
        return exact[0], "exact wavelength refractive-index metadata"
    lower = [
        (wavelength, ref_point) for _item, wavelength, ref_point in values if wavelength < target_um
    ]
    upper = [
        (wavelength, ref_point) for _item, wavelength, ref_point in values if wavelength > target_um
    ]
    if lower and upper:
        lower_wavelength, lower_ref = max(lower, key=lambda item: item[0])
        upper_wavelength, upper_ref = min(upper, key=lambda item: item[0])
        fraction = (target_um - lower_wavelength) / (upper_wavelength - lower_wavelength)
        return (
            (
                lower_ref[0] + fraction * (upper_ref[0] - lower_ref[0]),
                lower_ref[1] + fraction * (upper_ref[1] - lower_ref[1]),
            ),
            ("target refractive index estimated from neighboring wavelength metadata"),
        )
    if values:
        _item, wavelength, ref_point = min(
            values,
            key=lambda item: abs(item[1] - target_um),
        )
        return (
            ref_point,
            f"nearest available wavelength metadata at {wavelength:g} um",
        )
    return None, "no refractive-index metadata available"


def select_for_single_target_wavelength(
    objects: Sequence[RemoteObject],
    target_um: float,
    *,
    tolerance_um: float = 1e-9,
    mode: str = "interp",
    target_refractive_point: Optional[tuple[float, float]] = None,
    interpolation_neighbors: int = 2,
) -> tuple[list[RemoteObject], WavelengthProcessing]:
    from zju_scatt_interface.access.models import WavelengthProcessing

    if tolerance_um < 0:
        raise ScattError("Target wavelength tolerance cannot be negative")
    mode = normalize_target_wavelength_mode(mode)
    if interpolation_neighbors < 1:
        raise ScattError("Interpolation neighbor count must be positive")

    with_wavelength = [
        (item, object_wavelength_um(item))
        for item in objects
        if object_wavelength_um(item) is not None
    ]
    exact = [
        item
        for item, wavelength in with_wavelength
        if wavelength is not None and abs(wavelength - target_um) <= tolerance_um
    ]
    if exact:
        selected = sorted(exact, key=lambda item: item.key)
        return selected, WavelengthProcessing(
            target_um=target_um,
            target_wavelengths_um=(target_um,),
            selected_wavelengths_um=tuple(
                sorted({round(object_wavelength_um(item) or target_um, 12) for item in selected})
            ),
            interpolation_required=False,
            interpolation_basis="none",
            selection_mode=mode,
            message=(
                f"Exact wavelength data found within {tolerance_um:g} um of "
                f"{target_um:g} um; no interpolation applied."
            ),
        )

    grouped: dict[str, list[tuple[RemoteObject, float, tuple[float, float]]]] = {}
    for item, wavelength in with_wavelength:
        ref_point = object_refractive_point(item)
        if wavelength is None or ref_point is None:
            continue
        grouped.setdefault(object_series_key(item), []).append((item, wavelength, ref_point))

    if mode == "nearest":
        selected_by_key: dict[str, RemoteObject] = {}
        selected_wavelengths: set[float] = set()
        selected_refs: set[tuple[float, float]] = set()
        for item, wavelength in with_wavelength:
            if wavelength is None:
                continue
            key = object_series_key(item)
            current = selected_by_key.get(key)
            if current is None:
                selected_by_key[key] = item
                continue
            current_wavelength = object_wavelength_um(current)
            if current_wavelength is None or abs(wavelength - target_um) < abs(
                current_wavelength - target_um
            ):
                selected_by_key[key] = item
        for item in selected_by_key.values():
            wavelength = object_wavelength_um(item)
            ref_point = object_refractive_point(item)
            if wavelength is not None:
                selected_wavelengths.add(round(wavelength, 12))
            if ref_point is not None:
                selected_refs.add((round(ref_point[0], 12), round(ref_point[1], 12)))
        if not selected_by_key:
            raise ScattError(f"No wavelength metadata found for {target_um:g} um")
        selected = sorted(selected_by_key.values(), key=lambda item: item.key)
        return selected, WavelengthProcessing(
            target_um=target_um,
            target_wavelengths_um=(target_um,),
            selected_wavelengths_um=tuple(sorted(selected_wavelengths)),
            selected_refractive_points=tuple(sorted(selected_refs)),
            selection_mode=mode,
            interpolation_required=False,
            interpolation_basis="nearest_wavelength",
            message=(
                f"No exact {target_um:g} um product was found; selected nearest "
                "available wavelength data for each matching series."
            ),
        )

    selected_by_key: dict[str, RemoteObject] = {}
    selected_wavelengths = set()
    selected_refs: set[tuple[float, float]] = set()
    target_refs: set[tuple[float, float]] = set()
    estimate_notes: set[str] = set()
    for group_values in grouped.values():
        wavelength_family = any(
            name in item.key
            for item, _, _ in group_values
            for name in (
                "super_spheroid_ice",
                "coated_super_spheroid_seasalt",
                "sphere_sulfate",
                "sphere_nitrate",
                "sphere_organic_carbon",
                "sphere_water_cloud",
            )
        )
        if wavelength_family and target_refractive_point is None:
            lower = [value for value in group_values if value[1] < target_um]
            upper = [value for value in group_values if value[1] > target_um]
            if not lower or not upper:
                raise ScattError(
                    f"No wavelength bracket for {target_um:g} um; extrapolation is not allowed"
                )
            for item, wavelength, ref_point in (
                max(lower, key=lambda value: value[1]),
                min(upper, key=lambda value: value[1]),
            ):
                selected_by_key[item.key] = item
                selected_wavelengths.add(round(wavelength, 12))
                selected_refs.add((round(ref_point[0], 12), round(ref_point[1], 12)))
            estimate_notes.add("wavelength_bracketing")
            continue
        target_point, note = (
            (target_refractive_point, "explicit target refractive-index parameters")
            if target_refractive_point is not None
            else estimate_target_refractive_point(group_values, target_um, tolerance_um)
        )
        estimate_notes.add(note)
        if target_point is None:
            continue
        target_refs.add((round(target_point[0], 12), round(target_point[1], 12)))
        ranked = sorted(
            group_values,
            key=lambda item: refractive_distance(item[2], target_point),
        )
        for item, wavelength, ref_point in ranked[:interpolation_neighbors]:
            selected_by_key[item.key] = item
            selected_wavelengths.add(round(wavelength, 12))
            selected_refs.add((round(ref_point[0], 12), round(ref_point[1], 12)))
    if not selected_by_key:
        raise ScattError(
            f"No refractive-index metadata found for target wavelength {target_um:g} um"
        )
    selected = sorted(selected_by_key.values(), key=lambda item: item.key)
    basis_note = "; ".join(sorted(estimate_notes))
    return selected, WavelengthProcessing(
        target_um=target_um,
        target_wavelengths_um=(target_um,),
        selected_wavelengths_um=tuple(sorted(selected_wavelengths)),
        target_refractive_points=tuple(sorted(target_refs)),
        selected_refractive_points=tuple(sorted(selected_refs)),
        selection_mode=mode,
        interpolation_required=True,
        interpolation_applied=False,
        interpolation_basis="wavelength"
        if estimate_notes == {"wavelength_bracketing"}
        else "refractive_index_nk",
        message=(
            f"No exact {target_um:g} um product was found; "
            + (
                "selected lower and upper wavelength source files."
                if estimate_notes == {"wavelength_bracketing"}
                else f"selected nearest source points in the two-dimensional refractive-index plane (n, k). Target n,k source: {basis_note}."
            )
        ),
    )


def select_for_target_wavelength(
    objects: Sequence[RemoteObject],
    target_um: Optional[Union[float, Sequence[float]]],
    *,
    tolerance_um: float = 1e-9,
    mode: str = "interp",
    target_refractive_points: Optional[Sequence[Optional[tuple[float, float]]]] = None,
    interpolation_neighbors: int = 2,
    refractive_index_parameters: Optional[Mapping[str, Mapping[str, Any]]] = None,
    shapes=None,
) -> tuple[list[RemoteObject], WavelengthProcessing]:
    from zju_scatt_interface.access.models import WavelengthProcessing

    targets = normalize_target_wavelengths(target_um)
    mode = normalize_target_wavelength_mode(mode)
    if not targets:
        wavelengths = sorted(
            {
                round(value, 12)
                for value in (object_wavelength_um(item) for item in objects)
                if value is not None
            }
        )
        return list(objects), WavelengthProcessing(
            selected_wavelengths_um=tuple(wavelengths),
            selection_mode=mode,
        )

    # Native dust/BC files are indexed by refractive index, not wavelength.
    # Resolve each requested wavelength through the packaged material tables,
    # then select the full source stencil separately for each particle family.
    from zju_scatt_interface.config.particles import get_particle_profile
    from zju_scatt_interface.optics.retrieval.grid import (
        GRID_FAMILIES,
        grid_family,
        select_grid_sources,
    )

    families = {grid_family(obj) for obj in objects} - {None}
    if families:
        if target_refractive_points is not None and len(target_refractive_points) != len(targets):
            raise ScattError("target_refractive_points must match target wavelengths")
        overrides = {
            get_particle_profile(name).particle_type: values
            for name, values in (refractive_index_parameters or {}).items()
        }
        selected = []
        resolutions = []
        required = False
        for family in GRID_FAMILIES:
            if family not in families:
                continue
            group = [obj for obj in objects if grid_family(obj) == family]
            parameters = overrides.get(family)
            if family == "super_spheroid" and target_refractive_points and parameters is None:
                # Preserve the legacy paired ref_real_targets/ref_imag_targets API.
                for wavelength, ref_point in zip(targets, target_refractive_points):
                    values = (
                        None
                        if ref_point is None
                        else {
                            "refractive_index_real": ref_point[0],
                            "refractive_index_imaginary": ref_point[1],
                        }
                    )
                    try:
                        nodes, details, needs_interp = select_grid_sources(
                            group,
                            family,
                            [wavelength],
                            parameters=values,
                            mode=mode,
                            shapes=shapes,
                        )
                    except ValueError as exc:
                        raise ScattError(f"{family}: {exc}") from exc
                    selected.extend(nodes)
                    resolutions.extend(details)
                    required = required or needs_interp
            else:
                try:
                    nodes, details, needs_interp = select_grid_sources(
                        group,
                        family,
                        targets,
                        parameters=parameters,
                        mode=mode,
                        shapes=shapes,
                    )
                except ValueError as exc:
                    raise ScattError(f"{family}: {exc}") from exc
                selected.extend(nodes)
                resolutions.extend(details)
                required = required or needs_interp
        native = [obj for obj in objects if grid_family(obj) is None]
        native_processing = WavelengthProcessing()
        if native:
            nodes, native_processing = select_for_target_wavelength(
                native,
                targets,
                tolerance_um=tolerance_um,
                mode=mode,
                target_refractive_points=target_refractive_points,
                interpolation_neighbors=interpolation_neighbors,
            )
            selected.extend(nodes)
        messages = [
            f"{item['particle_type']} at {item['wavelength_um']:g} um: {item['message']}"
            for item in resolutions
        ]
        for item in resolutions:
            if item["unsupported_series"]:
                messages.append(
                    f"{item['particle_type']}: {len(item['unsupported_series'])} source series "
                    "omitted because the requested indices are outside their coverage"
                )
        wavelength_bc = all(item.get("database_type") == "wavelength" for item in resolutions)
        messages.append("Native source files selected; optical interpolation has not been applied.")
        if native:
            messages.append(native_processing.message)
        return sorted(
            {obj.key: obj for obj in selected}.values(), key=lambda obj: obj.key
        ), WavelengthProcessing(
            target_um=targets[0] if len(targets) == 1 else None,
            target_wavelengths_um=tuple(targets),
            selected_wavelengths_um=native_processing.selected_wavelengths_um,
            target_refractive_points=native_processing.target_refractive_points,
            selected_refractive_points=native_processing.selected_refractive_points,
            selection_mode=mode,
            interpolation_required=required or native_processing.interpolation_required,
            interpolation_basis="wavelength"
            if wavelength_bc and not native
            else "refractive_index_grid",
            message="; ".join(messages),
            refractive_index_resolutions=tuple(resolutions),
        )

    selected_by_key: dict[str, RemoteObject] = {}
    selected_wavelengths: set[float] = set()
    selected_refs: set[tuple[float, float]] = set()
    target_refs: set[tuple[float, float]] = set()
    messages: list[str] = []
    interpolation_required = False
    interpolation_bases = set()
    target_ref_values = list(target_refractive_points or [None for _ in targets])
    if len(target_ref_values) != len(targets):
        raise ScattError("target_refractive_points must match target wavelengths")
    for target, target_ref in zip(targets, target_ref_values):
        selected, processing = select_for_single_target_wavelength(
            objects,
            target,
            tolerance_um=tolerance_um,
            mode=mode,
            target_refractive_point=target_ref,
            interpolation_neighbors=interpolation_neighbors,
        )
        selected_by_key.update((item.key, item) for item in selected)
        selected_wavelengths.update(processing.selected_wavelengths_um)
        selected_refs.update(processing.selected_refractive_points)
        target_refs.update(processing.target_refractive_points)
        interpolation_required = interpolation_required or processing.interpolation_required
        interpolation_bases.add(processing.interpolation_basis)
        messages.append(processing.message)

    return sorted(selected_by_key.values(), key=lambda item: item.key), WavelengthProcessing(
        target_um=targets[0] if len(targets) == 1 else None,
        target_wavelengths_um=tuple(targets),
        selected_wavelengths_um=tuple(sorted(selected_wavelengths)),
        target_refractive_points=tuple(sorted(target_refs)),
        selected_refractive_points=tuple(sorted(selected_refs)),
        selection_mode=mode,
        interpolation_required=interpolation_required,
        interpolation_applied=False,
        interpolation_basis=(
            (
                "wavelength"
                if interpolation_bases <= {"wavelength", "none"}
                else "refractive_index_nk"
            )
            if interpolation_required and mode == "interp"
            else "nearest_wavelength"
            if mode == "nearest"
            else "none"
        ),
        message="; ".join(messages),
    )


def select_for_numeric_targets(
    objects: Sequence[RemoteObject],
    targets: Optional[Sequence[float]],
    names: Sequence[str],
    label: str,
    *,
    tolerance: float = 1e-9,
) -> tuple[list[RemoteObject], NumericSelectionProcessing]:
    from zju_scatt_interface.access.models import (
        NumericSelectionProcessing,
    )

    if not targets:
        return list(objects), NumericSelectionProcessing(label=label)
    if tolerance < 0:
        raise ScattError(f"{label} target tolerance cannot be negative")
    for target in targets:
        if not math.isfinite(target):
            raise ScattError(f"{label} target must be finite")

    with_values = [
        (item, object_numeric_value(item, names))
        for item in objects
        if object_numeric_value(item, names) is not None
    ]
    selected_by_key: dict[str, RemoteObject] = {}
    selected_values: set[float] = set()
    messages: list[str] = []
    interpolation_required = False
    basis = "/".join(names)
    for target in targets:
        exact = [
            item
            for item, value in with_values
            if value is not None and abs(value - target) <= tolerance
        ]
        if exact:
            selected_by_key.update((item.key, item) for item in exact)
            selected_values.add(target)
            messages.append(
                f"Exact {label} data found within {tolerance:g} of {target:g}; no interpolation applied."
            )
            continue

        lower_values = [
            value for _item, value in with_values if value is not None and value < target
        ]
        upper_values = [
            value for _item, value in with_values if value is not None and value > target
        ]
        if not lower_values or not upper_values:
            raise ScattError(f"No exact match or bracketing {label} data found for {target:g}")
        lower = max(lower_values)
        upper = min(upper_values)
        selected = [
            item for item, value in with_values if value is not None and value in {lower, upper}
        ]
        selected_by_key.update((item.key, item) for item in selected)
        selected_values.update((lower, upper))
        interpolation_required = True
        messages.append(
            f"No exact {label} {target:g} product was found; selected bracketing values "
            f"{lower:g} and {upper:g} for interpolation provenance."
        )

    return sorted(selected_by_key.values(), key=lambda item: item.key), NumericSelectionProcessing(
        label=label,
        target_values=tuple(targets),
        selected_values=tuple(sorted(selected_values)),
        interpolation_required=interpolation_required,
        interpolation_applied=False,
        interpolation_basis=basis if interpolation_required else "none",
        message="; ".join(messages),
    )
