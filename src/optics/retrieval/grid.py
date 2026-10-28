"""optics / retrieval / grid domain implementation."""

from __future__ import annotations

import math
import re
from pathlib import Path

from zju_scatt_interface.optics.refractive_index import resolve_grid_refractive_indices
from zju_scatt_interface.sources.adapters.boundaries import (
    FAMILY,
    database_type,
    refractive_index_scheme,
)

DEFAULT_INDEX_NOTICE = (
    "Since no refractive index was provided, the default refractive index scheme was used."
)
GRID_FAMILIES = ("super_spheroid", "encapsulated_fractal_aggregates_black_carbon")


def grid_family(obj):
    parts = obj.key.replace("\\", "/").split("/")
    return next((family for family in GRID_FAMILIES if family in parts), None)


def grid_coordinates(obj, family):
    from zju_scatt_interface.access.metadata import (
        NUMBER_PATTERN,
        extract_scatt_metadata,
    )

    if family == "super_spheroid":
        values = extract_scatt_metadata(obj.name)
        if "ref_real" not in values or "ref_imag" not in values:
            raise ValueError(f"Missing dust refractive-index metadata: {obj.key}")
        return {
            "refractive_index_real": values["ref_real"],
            "refractive_index_imaginary": values["ref_imag"],
        }
    match = re.search(
        rf"ref_bc_({NUMBER_PATTERN})_({NUMBER_PATTERN})_hygro_({NUMBER_PATTERN})_({NUMBER_PATTERN})",
        obj.name,
        re.I,
    )
    if not match:
        raise ValueError(f"Missing black-carbon/coating index metadata: {obj.key}")
    return dict(
        zip(
            (
                "black_carbon_refractive_index_real",
                "black_carbon_refractive_index_imaginary",
                "hygroscopic_refractive_index_real",
                "hygroscopic_refractive_index_imaginary",
            ),
            map(float, match.groups()),
        )
    )


def _series_key(obj, family):
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN

    pattern = (
        rf"ref_({NUMBER_PATTERN})_({NUMBER_PATTERN})"
        if family == "super_spheroid"
        else rf"ref_bc_({NUMBER_PATTERN})_({NUMBER_PATTERN})_hygro_({NUMBER_PATTERN})_({NUMBER_PATTERN})"
    )
    key = re.sub(pattern, "ref_GRID", obj.key, flags=re.I)
    # Processing level is a source preference, not an independent particle grid.
    return re.sub(r"(?i)(?<![\w.])L1(?:\.5)?(?=[_/])", "L_NATIVE", key)


def prefer_index_sources(objects, family):
    """Keep L1.5 over L1 at equal coordinates within the same shape/version."""
    preferred = {}
    for obj in sorted(objects, key=lambda item: item.key):
        coordinates = tuple(sorted(grid_coordinates(obj, family).items()))
        key = (_series_key(obj, family), coordinates)
        rank = int(bool(re.match(r"L1\.5_", obj.name, re.I)))
        previous = preferred.get(key)
        if previous is None or rank > previous[0]:
            preferred[key] = (rank, obj)
    return [item[1] for item in preferred.values()]


def select_grid_sources(
    objects, family, wavelengths, *, parameters=None, mode="interp", shapes=None
):
    """Use the existing optical interpolator's source stencil for each shape series."""
    from zju_scatt_interface.config.particles import validate_profile_parameters
    from zju_scatt_interface.optics.interpolation import (
        OpticalNode,
        _axis_transform,
        _normalized_distances,
        _select_neighbors,
    )

    parameters = dict(parameters or {})
    tables = parameters.pop("tables", None)
    kind = parameters.pop("database_type", None)
    scheme = parameters.pop("ri_scheme", None)
    if family == FAMILY:
        if kind is None:
            # Explicit indices retain raw-grid semantics; otherwise prefer the
            # wavelength database calculated using the chosen material scheme.
            kind = (
                "refractive_index_grid"
                if parameters or tables
                else (
                    "wavelength"
                    if any(database_type(obj.name) == "wavelength" for obj in objects)
                    else "refractive_index_grid"
                )
            )
        if kind not in {"refractive_index_grid", "wavelength"}:
            raise ValueError("database_type must be refractive_index_grid or wavelength")
        objects = [obj for obj in objects if database_type(obj.name) == kind]
        if kind == "wavelength":
            from zju_scatt_interface.sources.shapes import (
                compile_shapes,
                matches_shapes,
            )

            predicates = compile_shapes(shapes)
            objects = [obj for obj in objects if matches_shapes(obj.name, predicates)]
            if parameters or tables:
                raise ValueError(
                    "Wavelength BC uses built-in indices; supply database_type and ri_scheme only"
                )
            scheme = scheme or "v1.2.1"
            if scheme not in {"v1.2.1", "v1.2.2"}:
                raise ValueError("ri_scheme must be v1.2.1 or v1.2.2")
            objects = [obj for obj in objects if refractive_index_scheme(obj.name) == scheme]
            return _select_bc_wavelength_sources(objects, wavelengths, scheme, mode)
    if parameters:
        validate_profile_parameters(family, parameters, require_all=False)
    points = resolve_grid_refractive_indices(
        family, wavelengths, parameters=parameters, tables=tables, ri_scheme=scheme or "v1.2.1"
    )
    from zju_scatt_interface.sources.selection import (
        select_shape_grid_sources,
        shape_targets,
    )

    targets = shape_targets(shapes, family)
    if targets and mode == "interp":
        return select_shape_grid_sources(objects, family, points, targets)
    groups = {}
    for obj in prefer_index_sources(objects, family):
        groups.setdefault(_series_key(obj, family), []).append((obj, grid_coordinates(obj, family)))
    selected = {}
    resolutions = []
    interpolation_required = False
    for point in points:
        axes = tuple(point.values)
        selected_coordinates = set()
        methods = set()
        skipped = []
        for series, records in groups.items():
            # Selection reads coordinates only; optics are loaded later by adapters.
            nodes = [OpticalNode(coords, None, obj.key) for obj, coords in records]
            try:
                method, chosen, _, _, _ = _select_neighbors(
                    axes,
                    point.values,
                    nodes,
                    sparse_power=2.0,
                )
            except ValueError as exc:
                skipped.append({"series": series, "reason": str(exc)})
                continue
            # Sparse nearest nodes alone can lose axis coverage. Include support
            # nodes so subsequent interpolation of the downloaded stencil remains
            # inside the source domain as well.
            if mode != "nearest":
                for axis in axes:
                    for lower in (True, False):
                        supported = any(
                            node.coordinates[axis] <= point.values[axis]
                            if lower
                            else node.coordinates[axis] >= point.values[axis]
                            for node in chosen
                        )
                        if not supported:
                            candidates = [
                                node
                                for node in nodes
                                if (
                                    node.coordinates[axis] <= point.values[axis]
                                    if lower
                                    else node.coordinates[axis] >= point.values[axis]
                                )
                            ]
                            chosen.append(
                                min(
                                    candidates,
                                    key=lambda node: abs(
                                        node.coordinates[axis] - point.values[axis]
                                    ),
                                )
                            )
            if mode == "nearest" and method != "exact":
                transforms = {
                    axis: _axis_transform(axis, (node.coordinates[axis] for node in nodes))[0]
                    for axis in axes
                }
                distances = _normalized_distances(axes, point.values, nodes, nodes, transforms)
                chosen = [min(zip(distances, nodes), key=lambda item: item[0])[1]]
                method = "nearest_refractive_index"
            methods.add(method)
            found = {tuple(node.coordinates[axis] for axis in axes) for node in chosen}
            chosen_keys = {node.source for node in chosen}
            selected.update((obj.key, obj) for obj, _ in records if obj.key in chosen_keys)
            selected_coordinates.update(found)
            interpolation_required = interpolation_required or any(
                not math.isclose(value, point.values[axis], rel_tol=1e-9, abs_tol=1e-12)
                for corner in found
                for axis, value in zip(axes, corner)
            )
        if not selected_coordinates:
            reason = skipped[0]["reason"] if skipped else "No native source series available."
            raise ValueError(f"No supported source series for {point.wavelength_um:g} um: {reason}")
        is_default = point.input_mode == "wavelength_to_refractive_index"
        table_relative_paths = (
            {
                name: Path(source)
                .resolve()
                .relative_to(Path(__file__).resolve().parents[2])
                .as_posix()
                for name, source in point.sources.items()
            }
            if is_default
            else {}
        )
        resolutions.append(
            {
                "particle_type": family,
                "wavelength_um": point.wavelength_um,
                "input_mode": point.input_mode,
                "used_default": is_default,
                "message": DEFAULT_INDEX_NOTICE
                if is_default
                else "Explicit refractive index was used.",
                "target_indices": dict(point.values),
                "table_sources": dict(point.sources),
                "table_relative_paths": table_relative_paths,
                "table_relative_path_base": "zju_scatt_interface package directory",
                "source_selection_methods": sorted(methods),
                "unsupported_series": skipped,
                "selected_index_nodes": [
                    dict(zip(axes, values)) for values in sorted(selected_coordinates)
                ],
            }
        )
    return (
        sorted(selected.values(), key=lambda obj: obj.key),
        tuple(resolutions),
        interpolation_required,
    )


def _select_bc_wavelength_sources(objects, wavelengths, scheme, mode):
    from zju_scatt_interface.access.metadata import extract_scatt_metadata

    groups = {}
    for obj in objects:
        df = re.search(r"_df_([\d.]+)_", obj.name)
        groups.setdefault(df.group(1) if df else "unknown", []).append(obj)
    if not groups:
        raise ValueError(f"No wavelength BC files for {scheme}")
    selected = {}
    resolutions = []
    required = False
    for wavelength in wavelengths:
        skipped = []
        for series, records in groups.items():
            pairs = [(extract_scatt_metadata(obj.name)["wavelength_um"], obj) for obj in records]
            lo = [pair for pair in pairs if pair[0] <= wavelength]
            hi = [pair for pair in pairs if pair[0] >= wavelength]
            if not lo or not hi:
                skipped.append(
                    {
                        "series": series,
                        "reason": f"wavelength={wavelength:g} outside source support",
                    }
                )
                continue
            bracket = [max(lo, key=lambda p: p[0]), min(hi, key=lambda p: p[0])]
            if mode == "nearest":
                bracket = [min(bracket, key=lambda p: abs(p[0] - wavelength))]
            selected.update((obj.key, obj) for _, obj in bracket)
            required = required or any(wl != wavelength for wl, _ in bracket)
        if len(skipped) == len(groups):
            raise ValueError(f"BC wavelength={wavelength:g} um outside {scheme} database support")
        point = resolve_grid_refractive_indices(FAMILY, [wavelength], ri_scheme=scheme)[0]
        package_dir = Path(__file__).resolve().parents[2]
        resolutions.append(
            {
                "particle_type": FAMILY,
                "wavelength_um": wavelength,
                "database_type": "wavelength",
                "ri_scheme": scheme,
                "message": DEFAULT_INDEX_NOTICE + f" Wavelength BC database, RI scheme {scheme}.",
                "used_default": True,
                "unsupported_series": skipped,
                "input_mode": "wavelength_to_refractive_index",
                "target_indices": dict(point.values),
                "table_sources": dict(point.sources),
                "table_relative_paths": {
                    name: Path(path).resolve().relative_to(package_dir).as_posix()
                    for name, path in point.sources.items()
                },
                "table_relative_path_base": "zju_scatt_interface package directory",
                "source_selection_methods": ["wavelength_bracketing"],
                "selected_index_nodes": [],
            }
        )
    return sorted(selected.values(), key=lambda obj: obj.key), tuple(resolutions), required
