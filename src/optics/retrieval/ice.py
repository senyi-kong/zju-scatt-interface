"""optics / retrieval / ice domain implementation."""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Mapping
from itertools import product


def source_shapes(shapes):
    """Expand scalar ice geometry targets to native brackets for the scan."""
    from zju_scatt_interface.config.particles import (
        get_particle_profile,
        normalize_parameter_name,
    )
    from zju_scatt_interface.errors import ScattError

    if shapes is None:
        return None
    profile = get_particle_profile("ice")
    selections = []
    for shape in [shapes] if isinstance(shapes, Mapping) else shapes:
        selection = {}
        for name, value in shape.items():
            axis = normalize_parameter_name(name)
            if axis in {"roundness", "aspect_ratio"} and not isinstance(value, tuple):
                grid = profile.parameter(axis).grid_values
                lower, upper = [x for x in grid if x <= value], [x for x in grid if x >= value]
                if not lower or not upper:
                    raise ScattError(
                        f"Ice {axis}={value:g} outside shape support [{min(grid):g}, {max(grid):g}]; no extrapolation"
                    )
                selection[axis] = (max(lower), min(upper))
            else:
                selection[axis] = value
        selections.append(selection)
    return selections


def geometry_requests(shapes, native_geometries=None):
    from zju_scatt_interface.config.particles import (
        get_particle_profile,
        normalize_parameter_name,
    )

    if shapes is None:
        return None
    profile = get_particle_profile("ice")
    requests = []
    for shape in [shapes] if isinstance(shapes, Mapping) else shapes:
        values = {normalize_parameter_name(name): value for name, value in shape.items()}
        if "df" in values:
            continue
        axes = ("roundness", "aspect_ratio")
        native_pairs = (
            native_geometries
            if native_geometries is not None
            else [
                dict(zip(axes, pair))
                for pair in product(*(profile.parameter(axis).grid_values for axis in axes))
            ]
        )
        for native in native_pairs:
            request = {}
            for axis in axes:
                value = values.get(axis)
                if isinstance(value, tuple):
                    if not value[0] <= native[axis] <= value[1]:
                        break
                    request[axis] = native[axis]
                else:
                    request[axis] = native[axis] if value is None else float(value)
            if len(request) == 2 and request not in requests:
                requests.append(request)
    return requests


def geometry_records(records, request, coordinates):
    """Keep only the local shape brackets for this paired request."""
    from zju_scatt_interface.errors import ScattError

    selected = list(records)
    for axis, target in request.items():
        values = sorted({coordinates(record)[axis] for record in selected})
        lower, upper = [x for x in values if x <= target], [x for x in values if x >= target]
        if not lower or not upper:
            raise ScattError(f"Ice {axis}={target:g} has no source bracket; no shape extrapolation")
        bracket = {max(lower), min(upper)}
        selected = [record for record in selected if coordinates(record)[axis] in bracket]
    return selected


def series_key(obj, *, combine_geometry=False):
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN
    from zju_scatt_interface.sources.coordinates import object_series_key

    key = object_series_key(obj)
    key = re.sub(rf"_t_({NUMBER_PATTERN})k", "_t_TARGETk", key, flags=re.I)
    if combine_geometry:
        key = re.sub(rf"_(n|asp)_({NUMBER_PATTERN})", r"_\1_TARGET", key, flags=re.I)
    return re.sub(r"(?i)(?<![\w.])L1(?:\.5)?(?=[_/])", "L_NATIVE", key)


def select_sources(objects, temperatures, wavelengths, *, shapes=None):
    from zju_scatt_interface.access.metadata import extract_scatt_metadata
    from zju_scatt_interface.errors import ScattError
    from zju_scatt_interface.sources.coordinates import select_for_target_wavelength

    native_geometries = [
        {
            "roundness": extract_scatt_metadata(obj.name)["n"],
            "aspect_ratio": extract_scatt_metadata(obj.name)["aspect_ratio"],
        }
        for obj in objects
    ]
    requests = geometry_requests(shapes, native_geometries)
    if requests is not None:

        def coords(obj):
            meta = extract_scatt_metadata(obj.name)
            return {"roundness": meta["n"], "aspect_ratio": meta["aspect_ratio"]}

        selected = {}
        required = False
        for request in requests:
            candidates = geometry_records(objects, request, coords)
            nodes, needs_interp = select_sources(candidates, temperatures, wavelengths)
            selected.update((obj.key, obj) for obj in nodes)
            required |= needs_interp or any(coords(obj) != request for obj in nodes)
        return sorted(selected.values(), key=lambda obj: obj.key), required
    groups = {}
    for obj in objects:
        groups.setdefault(series_key(obj), []).append(obj)
    selected = {}
    required = False
    for records in groups.values():
        available = sorted({extract_scatt_metadata(obj.name)["temperature_k"] for obj in records})
        for temperature in temperatures:
            lo, hi = max(160.0, available[0]), min(270.0, available[-1])
            bounded = min(max(temperature, lo), hi)
            bracket = {
                max(t for t in available if t <= bounded),
                min(t for t in available if t >= bounded),
            }
            required |= temperature not in available or not lo <= temperature <= hi
            for native_temperature in bracket:
                candidates = [
                    obj
                    for obj in records
                    if extract_scatt_metadata(obj.name)["temperature_k"] == native_temperature
                ]
                # Prefer the higher processing level at duplicate coordinates.
                preferred = {}
                for obj in sorted(candidates, key=lambda item: item.key):
                    key = re.sub(r"L1(?:\.5)?_", "L_NATIVE_", obj.key)
                    previous = preferred.get(key)
                    if previous is None or obj.name.startswith("L1.5_"):
                        preferred[key] = obj
                nodes, info = select_for_target_wavelength(list(preferred.values()), wavelengths)
                if not nodes:
                    raise ScattError(
                        "No ice wavelength support for the requested temperature/shape."
                    )
                required |= info.interpolation_required
                selected.update((obj.key, obj) for obj in nodes)
    return sorted(selected.values(), key=lambda obj: obj.key), required


def write_products(
    sources, wavelengths, temperatures, destination, *, overwrite=False, shapes=None
):
    from zju_scatt_interface.access.metadata import extract_scatt_metadata
    from zju_scatt_interface.optics.interpolation import InterpolatedFileResult
    from zju_scatt_interface.optics.retrieval.native import write_native_source_product
    from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryWarning

    sources = list(sources)
    native_geometries = [
        {
            "roundness": extract_scatt_metadata(obj.name)["n"],
            "aspect_ratio": extract_scatt_metadata(obj.name)["aspect_ratio"],
        }
        for obj, _ in sources
        if "super_spheroid_ice" in obj.key.split("/")
    ]
    requests = geometry_requests(shapes, native_geometries)
    groups = {}
    for obj, path in sources:
        if "super_spheroid_ice" not in obj.key.split("/"):
            continue
        meta = extract_scatt_metadata(obj.name)
        groups.setdefault(series_key(obj, combine_geometry=requests is not None), []).append(
            {
                "obj": obj,
                "path": path,
                "is_grid": False,
                "coordinates": {
                    "wavelength": meta["wavelength_um"],
                    "temperature": meta["temperature_k"],
                    "roundness": meta["n"],
                    "aspect_ratio": meta["aspect_ratio"],
                },
            }
        )
    products = []
    work = []
    for records in groups.values():
        for request in requests if requests is not None else [None]:
            chosen = (
                geometry_records(records, request, lambda item: item["coordinates"])
                if request
                else records
            )
            work.append((chosen, request))
    for records, request in work:
        available = [record["coordinates"]["temperature"] for record in records]
        lo, hi = max(160.0, min(available)), min(270.0, max(available))
        for temperature in temperatures:
            for wavelength in wavelengths:
                if any(
                    math.isclose(record["coordinates"]["temperature"], temperature)
                    and math.isclose(record["coordinates"]["wavelength"], wavelength)
                    and (
                        request is None
                        or all(
                            math.isclose(record["coordinates"][axis], value)
                            for axis, value in request.items()
                        )
                    )
                    for record in records
                ):
                    continue
                resolution = {"target_temperature_k": temperature}
                if request:
                    varying = {
                        axis: value
                        for axis, value in request.items()
                        if len({record["coordinates"][axis] for record in records}) > 1
                    }
                    if varying:
                        resolution["target_shape_parameters"] = varying
                if not lo <= temperature <= hi:
                    reason = f"Ice temperature={temperature:g} K outside available support [{lo:g}, {hi:g}] K; optical values are NaN."
                    warnings.warn(reason, DatabaseBoundaryWarning, stacklevel=2)
                    resolution.update(
                        out_of_bounds=reason, selection_temperature_k=min(max(temperature, lo), hi)
                    )
                path, status, provenance, paths = write_native_source_product(
                    records,
                    "super_spheroid_ice",
                    wavelength,
                    resolution,
                    destination,
                    overwrite=overwrite,
                )
                meta = extract_scatt_metadata(records[0]["obj"].name)
                products.append(
                    InterpolatedFileResult(
                        path,
                        "super_spheroid_ice",
                        wavelength,
                        {
                            "temperature": temperature,
                            **(
                                request
                                or {"roundness": meta["n"], "aspect_ratio": meta["aspect_ratio"]}
                            ),
                        },
                        paths,
                        status,
                        provenance,
                    )
                )
    return products
