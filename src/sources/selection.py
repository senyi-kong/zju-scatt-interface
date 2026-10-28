"""sources / selection domain implementation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from itertools import product
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    normalize_parameter_name,
)


def shape_targets(shapes, family):
    """Complete scalar shapes are interpolation targets; ranges retain raw semantics."""
    required = {"roundness", "aspect_ratio"} if family == "super_spheroid" else {"df"}
    values = [shapes] if isinstance(shapes, Mapping) else shapes or []
    targets = []
    for shape in values:
        normalized = {normalize_parameter_name(key): value for key, value in shape.items()}
        if set(normalized) != required or any(
            isinstance(value, tuple) for value in normalized.values()
        ):
            return []
        target = {key: float(value) for key, value in normalized.items()}
        if target not in targets:
            targets.append(target)
    return targets


def source_shapes(shapes, requested):
    """Defer complete target filtering until actual catalog coordinates are known."""
    from zju_scatt_interface.optics.retrieval.grid import GRID_FAMILIES

    if not requested or len(requested) != 1:
        return shapes
    profile = get_particle_profile(requested[0])
    if profile.particle_type not in GRID_FAMILIES:
        return shapes
    targets = shape_targets(shapes, profile.particle_type)
    if not targets:
        return shapes
    # Registered grids describe the database, but a catalog/version can omit
    # native nodes. Actual available nodes must determine the enclosing stencil.
    return None


@_registration_required
def select_shape_grid_sources(objects, family, points, targets):
    """Choose joint geometry/RI stencils, without mixing database revisions."""
    from zju_scatt_interface.access.metadata import (
        NUMBER_PATTERN,
        extract_scatt_metadata,
    )
    from zju_scatt_interface.optics.interpolation import OpticalNode, _select_neighbors
    from zju_scatt_interface.optics.retrieval.grid import (
        DEFAULT_INDEX_NOTICE,
        _series_key,
        grid_coordinates,
        prefer_index_sources,
    )

    groups = {}
    for obj in prefer_index_sources(objects, family):
        series = re.sub(rf"_(n|asp|df)_({NUMBER_PATTERN})", r"_\1_GRID", _series_key(obj, family))
        meta = extract_scatt_metadata(obj.name)
        geometry = (
            {"roundness": meta["n"], "aspect_ratio": meta["aspect_ratio"]}
            if family == "super_spheroid"
            else {"df": float(re.search(rf"_df_({NUMBER_PATTERN})_", obj.name).group(1))}
        )
        groups.setdefault(series, []).append((obj, {**grid_coordinates(obj, family), **geometry}))
    selected, resolutions = {}, []
    selected_series = set()
    required = False
    series_nodes = {
        series: [OpticalNode(coords, None, obj.key) for obj, coords in records]
        for series, records in groups.items()
    }
    for point in points:
        stencils = []
        for shape in targets:
            target = {**point.values, **shape}
            supported = []
            for series, records in sorted(groups.items()):
                nodes = series_nodes[series]
                # A complete local rectangle needs only its corner records.
                # Preserve the full-grid sparse fallback when any corner is absent.
                bounds = []
                for axis, value in target.items():
                    values = {node.coordinates[axis] for node in nodes}
                    lo = [x for x in values if x <= value]
                    hi = [x for x in values if x >= value]
                    if not lo or not hi:
                        break
                    bounds.append(tuple(sorted({max(lo), min(hi)})))
                compact = []
                if len(bounds) == len(target):
                    corners = set(product(*bounds))
                    compact = [
                        node
                        for node in nodes
                        if tuple(node.coordinates[axis] for axis in target) in corners
                    ]
                    if len(
                        {tuple(node.coordinates[axis] for axis in target) for node in compact}
                    ) != len(corners):
                        compact = []
                try:
                    method, chosen, weights, _, _ = _select_neighbors(
                        tuple(target), target, compact or nodes, sparse_power=2.0
                    )
                except ValueError:
                    continue
                # Sparse support must retain the coordinate brackets expected by adapters.
                for axis, value in target.items():
                    for lower in (True, False):

                        def side(node):
                            return (
                                node.coordinates[axis] <= value
                                if lower
                                else node.coordinates[axis] >= value
                            )

                        if not any(side(node) for node in chosen):
                            candidates = [node for node in nodes if side(node)]
                            if candidates:
                                chosen.append(
                                    min(
                                        candidates,
                                        key=lambda node: abs(node.coordinates[axis] - value),
                                    )
                                )
                keys = {node.source for node in chosen}
                supported.append((series, records, method, chosen, weights, keys))
            if len(supported) != 1:
                raise ValueError(
                    f"Expected one supported database series for {shape} and {dict(point.values)}, "
                    f"found {len(supported)}; restrict the catalog/version or check target coverage"
                )
            series, records, method, chosen, weights, keys = supported[0]
            selected_series.add(series)
            if len(selected_series) != 1:
                raise ValueError(
                    "Requested targets require different database series; mixing revisions is not allowed"
                )
            selected.update((obj.key, obj) for obj, _ in records if obj.key in keys)
            required = required or method != "exact"
            stencils.append(
                {
                    "series": series,
                    "target_shape_parameters": dict(shape),
                    "method": method,
                    "source_keys": sorted(keys),
                    "neighbors": [
                        {
                            "source": node.source,
                            "coordinates": dict(node.coordinates),
                            "weight": float(weight),
                        }
                        for node, weight in zip(chosen, weights)
                    ],
                }
            )
        default = point.input_mode == "wavelength_to_refractive_index"
        resolutions.append(
            {
                "particle_type": family,
                "wavelength_um": point.wavelength_um,
                "input_mode": point.input_mode,
                "used_default": default,
                "message": DEFAULT_INDEX_NOTICE
                if default
                else "Explicit refractive index was used.",
                "target_indices": dict(point.values),
                "table_sources": dict(point.sources),
                "table_relative_paths": {
                    name: Path(path)
                    .resolve()
                    .relative_to(Path(__file__).resolve().parents[1])
                    .as_posix()
                    for name, path in point.sources.items()
                }
                if default
                else {},
                "table_relative_path_base": "zju_scatt_interface package directory",
                "source_selection_methods": sorted({item["method"] for item in stencils}),
                "unsupported_series": [],
                "shape_stencils": stencils,
                "selected_index_nodes": [
                    dict(coords)
                    for obj, coords in (record for records in groups.values() for record in records)
                    if obj.key in {key for item in stencils for key in item["source_keys"]}
                ],
            }
        )
    return sorted(selected.values(), key=lambda obj: obj.key), tuple(resolutions), required
