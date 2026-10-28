"""optics / retrieval / native domain implementation."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from zju_scatt_interface.io.paths import filesystem_path
from zju_scatt_interface.optics.interpolation import (
    InterpolationError,
    OpticalNode,
    _create_native_variable,
    _native_phase_variable_stores_ratio,
    _select_neighbors,
)

PHASE_NAMES = {"p11", "p12", "p22", "p33", "p43", "p44"}


def _values(variable):
    return np.asarray(np.ma.filled(variable[:].astype(float), np.nan), dtype=float)


def _same(left, right):
    a, b = np.asarray(left), np.asarray(right)
    if np.issubdtype(a.dtype, np.number) and np.issubdtype(b.dtype, np.number):
        return np.array_equal(a, b, equal_nan=True)
    return np.array_equal(a, b)


def _attributes_equal(left, right):
    return set(left.ncattrs()) == set(right.ncattrs()) and all(
        _same(left.getncattr(name), right.getncattr(name)) for name in left.ncattrs()
    )


def verify_native_schema(path, template_path):
    """Check complete dimensions, variables, dtypes and variable attributes."""
    from netCDF4 import Dataset

    with (
        Dataset(str(filesystem_path(path))) as output,
        Dataset(str(filesystem_path(template_path))) as template,
    ):
        if output.data_model != template.data_model:
            return False
        if set(output.dimensions) != set(template.dimensions):
            return False
        if any(
            len(output.dimensions[name]) != len(dim)
            or output.dimensions[name].isunlimited() != dim.isunlimited()
            for name, dim in template.dimensions.items()
        ):
            return False
        if set(output.variables) != set(template.variables):
            return False
        return all(
            output.variables[name].dimensions == variable.dimensions
            and output.variables[name].dtype == variable.dtype
            and _attributes_equal(output.variables[name], variable)
            for name, variable in template.variables.items()
        )


def _blend(arrays, weights, *, positive=False):
    """Parameter interpolation in native units; non-finite support stays invalid."""
    stacked = np.stack(arrays)
    w = np.asarray(weights).reshape((-1,) + (1,) * (stacked.ndim - 1))
    linear = np.sum(w * stacked, axis=0)
    if not positive:
        return linear
    valid_log = np.all(stacked > 0, axis=0)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        logarithmic = np.exp(np.sum(w * np.log(stacked), axis=0))
    return np.where(valid_log, logarithmic, linear)


def _resample(values, source, target, axis, *, logarithmic_values=False):
    """Linear native-coordinate alignment, with NaN outside source support."""
    source, target = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    if source.shape == target.shape and np.allclose(source, target, rtol=1e-10, atol=1e-12):
        return values
    if source.ndim != 1 or len(source) < 2 or np.any(np.diff(source) <= 0):
        raise InterpolationError("Native alignment requires a strictly increasing 1-D coordinate")
    moved = np.moveaxis(values, axis, 0)
    columns = moved.reshape(len(source), -1)
    aligned = np.empty((len(target), columns.shape[1]))
    for i, column in enumerate(columns.T):
        if logarithmic_values and np.all(column > 0):
            with np.errstate(invalid="ignore"):
                aligned[:, i] = np.exp(
                    np.interp(target, source, np.log(column), left=np.nan, right=np.nan)
                )
        else:
            aligned[:, i] = np.interp(target, source, column, left=np.nan, right=np.nan)
    return np.moveaxis(aligned.reshape((len(target),) + moved.shape[1:]), 0, axis)


def _native_filename(template, family, wavelength, indices, date, temperature=None, shapes=None):
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN

    stem = template.stem
    source_level = re.match(r"L[0-3](?:\.5)?", stem)
    level = source_level.group() if source_level else "L1"
    stem = re.sub(r"^L[0-3](?:\.5)?_", "L1.5_", stem)
    wavelength_token = "wl_nan" if wavelength is None else f"wl_{wavelength:.3f}_um"
    stem, count = re.subn(
        r"_wl_(?:nan|[0-9.eE+\-]+)(?:_um)?_ref_", f"_{wavelength_token}_ref_", stem, count=1
    )
    if count != 1:
        raise InterpolationError(
            f"Cannot construct a native wavelength filename from {template.name}"
        )
    if family == "super_spheroid":
        text = f"ref_{indices['refractive_index_real']:.3e}_{indices['refractive_index_imaginary']:.3e}"
        stem = re.sub(rf"ref_({NUMBER_PATTERN})_({NUMBER_PATTERN})", text, stem, count=1)
    elif family == "encapsulated_fractal_aggregates_black_carbon":
        text = (
            f"ref_bc_{indices['black_carbon_refractive_index_real']:.3e}_"
            f"{indices['black_carbon_refractive_index_imaginary']:.3e}_hygro_"
            f"{indices['hygroscopic_refractive_index_real']:.3e}_"
            f"{indices['hygroscopic_refractive_index_imaginary']:.3e}"
        )
        stem = re.sub(
            rf"ref_bc_({NUMBER_PATTERN})_({NUMBER_PATTERN})_hygro_({NUMBER_PATTERN})_({NUMBER_PATTERN})",
            text,
            stem,
            count=1,
        )
    else:
        stem = re.sub(
            rf"ref_({NUMBER_PATTERN})_({NUMBER_PATTERN})",
            f"ref_{indices['refractive_index_real']:.3e}_{indices['refractive_index_imaginary']:.3e}",
            stem,
            count=1,
        )
        if "water_refractive_index_real" in indices:
            stem = re.sub(
                rf"water_({NUMBER_PATTERN})_({NUMBER_PATTERN})",
                f"water_{indices['water_refractive_index_real']:.3e}_{indices['water_refractive_index_imaginary']:.3e}",
                stem,
                count=1,
            )
    if temperature is not None:
        stem = re.sub(rf"_t_({NUMBER_PATTERN})k", f"_t_{temperature:g}k", stem, count=1)
    for axis, value in (shapes or {}).items():
        token = {"roundness": "n", "aspect_ratio": "asp", "df": "df"}[axis]
        text = f"{value:.2f}" if axis == "df" else f"{value:.3f}"
        stem = re.sub(rf"_{token}_({NUMBER_PATTERN})", f"_{token}_{text}", stem, count=1)
    comment = f"interp_from_{level.lower().replace('.', 'p')}"
    stem, replaced = re.subn(r"_v([0-9.]+)_\d{8}$", rf"_{comment}_v\1_{date}", stem)
    if not replaced:
        stem = f"{stem}_{comment}_v1.0_{date}"
    return stem + ".nc"


def write_native_source_product(
    records, family, wavelength, resolution, destination, *, overwrite=False
):
    """Interpolate a native source series without changing its variable schema."""
    from netCDF4 import Dataset

    records = sorted(records, key=lambda record: str(record["path"]))
    is_grid = records[0]["is_grid"]
    if wavelength is None and not is_grid:
        raise InterpolationError("Only native refractive-index grids can omit wavelength")
    target = dict(resolution["target_indices"]) if is_grid else {"wavelength": wavelength}
    temperature = resolution.get("target_temperature_k")
    if temperature is not None:
        target["temperature"] = float(temperature)
    shape_parameters = resolution.get("target_shape_parameters", {})
    target.update(shape_parameters)
    axes = tuple(target)
    nodes = [
        OpticalNode({name: record["coordinates"][name] for name in axes}, None, str(record["path"]))
        for record in records
    ]
    selection_target = dict(target)
    if "selection_temperature_k" in resolution:
        selection_target["temperature"] = resolution["selection_temperature_k"]
    method, chosen, weights, distances, transforms = _select_neighbors(
        axes, selection_target, nodes, sparse_power=2.0
    )
    by_path = {str(record["path"]): record for record in records}
    selected = [by_path[node.source] for node in chosen]
    # Zero-weight corners should not propagate their NaNs into an exact-axis target.
    active = [
        (record, weight, distance)
        for record, weight, distance in zip(selected, weights, distances)
        if weight > 0
    ]
    selected, weights, distances = map(list, zip(*active))
    now = datetime.now(timezone.utc)
    date = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    with ExitStack() as stack:
        datasets = [
            stack.enter_context(Dataset(str(filesystem_path(record["path"]))))
            for record in selected
        ]
        first = datasets[0]
        size_name = "xsize_maxd" if "xsize_maxd" in first.variables else "xsize_veq"
        size_dimension = first.variables[size_name].dimensions[0]
        grids = [_values(dataset.variables[size_name]) for dataset in datasets]
        if any(grid.ndim != 1 or np.any(np.diff(grid) <= 0) for grid in grids):
            raise InterpolationError("Native source size coordinates must be increasing and 1-D")
        low, high = max(grid[0] for grid in grids), min(grid[-1] for grid in grids)
        if low > high:
            raise InterpolationError("Native sources have no common size support")
        candidates = [
            i for i, grid in enumerate(grids) if grid[0] >= low - 1e-10 and grid[-1] <= high + 1e-10
        ]
        template_index = max(
            candidates or range(len(grids)),
            key=lambda i: int(np.count_nonzero((grids[i] >= low) & (grids[i] <= high))),
        )
        template, template_record = datasets[template_index], selected[template_index]
        template_path = template_record["path"]
        target_grid = grids[template_index]
        for dataset in datasets:
            if set(dataset.variables) != set(template.variables) or set(dataset.dimensions) != set(
                template.dimensions
            ):
                raise InterpolationError("Sources in one series have different native schemas")
            for name, variable in template.variables.items():
                other = dataset.variables[name]
                if (
                    variable.dimensions != other.dimensions
                    or variable.dtype != other.dtype
                    or not _attributes_equal(variable, other)
                ):
                    raise InterpolationError(f"Native definitions differ for {name}")
            for name, dim in template.dimensions.items():
                if name not in {size_dimension, "sca_angle"} and len(
                    dataset.dimensions[name]
                ) != len(dim):
                    raise InterpolationError(f"Internal native dimension differs: {name}")

        def aligned(dataset, name, values=None, *, phase_positive=False):
            variable = dataset.variables[name]
            array = _values(variable) if values is None else values
            if "sca_angle" in variable.dimensions:
                array = _resample(
                    array,
                    _values(dataset.variables["sca_angle"]),
                    _values(template.variables["sca_angle"]),
                    variable.dimensions.index("sca_angle"),
                    logarithmic_values=phase_positive,
                )
            if size_dimension in variable.dimensions:
                array = _resample(
                    array,
                    _values(dataset.variables[size_name]),
                    target_grid,
                    variable.dimensions.index(size_dimension),
                )
            return array

        arrays_ext = [aligned(dataset, "cext") for dataset in datasets]
        arrays_sca = [
            aligned(
                dataset,
                "cext",
                _values(dataset.variables["cext"]) * _values(dataset.variables["ssa"]),
            )
            for dataset in datasets
        ]
        cext = _blend(arrays_ext, weights, positive=True)
        csca = _blend(arrays_sca, weights, positive=True)
        ssa = np.divide(csca, cext, out=np.full_like(cext, np.nan), where=cext > 0)
        ssa = np.clip(ssa, 0, 1)
        area = None
        if "proj_area" in template.variables:
            area = _blend(
                [aligned(dataset, "proj_area") for dataset in datasets], weights, positive=True
            )
        elif "qext" in template.variables:
            areas = []
            for dataset in datasets:
                ext, qext = _values(dataset.variables["cext"]), _values(dataset.variables["qext"])
                areas.append(
                    aligned(
                        dataset,
                        "cext",
                        np.divide(ext, qext, out=np.full_like(ext, np.nan), where=qext > 0),
                    )
                )
            area = _blend(areas, weights, positive=True)

        # RI lives in variables for dust, in filenames for BC/sea salt. Preserve
        # the original variable set and record all resolved values in attributes.
        indices = dict(resolution.get("target_indices", {}))
        if not indices:
            from zju_scatt_interface.optics.retrieval.grid import grid_coordinates

            if family == "encapsulated_fractal_aggregates_black_carbon":
                coordinates = [grid_coordinates(record["obj"], family) for record in selected]
                indices = {
                    name: float(np.dot(weights, [point[name] for point in coordinates]))
                    for name in coordinates[0]
                }
            else:
                from zju_scatt_interface.access.metadata import (
                    NUMBER_PATTERN,
                    extract_scatt_metadata,
                )

                metadata = [extract_scatt_metadata(record["obj"].name) for record in selected]
                indices = {
                    "refractive_index_real": float(
                        np.dot(weights, [point["ref_real"] for point in metadata])
                    ),
                    "refractive_index_imaginary": float(
                        np.dot(weights, [point["ref_imag"] for point in metadata])
                    ),
                }
                water = [
                    re.search(rf"water_({NUMBER_PATTERN})_({NUMBER_PATTERN})", record["obj"].name)
                    for record in selected
                ]
                if all(water):
                    indices.update(
                        water_refractive_index_real=float(
                            np.dot(weights, [float(match.group(1)) for match in water])
                        ),
                        water_refractive_index_imaginary=float(
                            np.dot(weights, [float(match.group(2)) for match in water])
                        ),
                    )

        fingerprint_data = {
            "writer": "native_schema_v2",
            "family": family,
            "wavelength": wavelength,
            "target": target,
            "ri_inputs": {
                "indices": indices,
                "table_sources": resolution.get("table_sources", {}),
                "database_type": resolution.get("database_type"),
                "ri_scheme": resolution.get("ri_scheme"),
            },
            "template": str(template_path),
            "sources": [
                (
                    str(record["path"]),
                    filesystem_path(record["path"]).stat().st_size,
                    filesystem_path(record["path"]).stat().st_mtime_ns,
                    weight,
                )
                for record, weight in zip(selected, weights)
            ],
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True).encode()
        ).hexdigest()
        output = (
            Path(destination)
            / family
            / _native_filename(
                template_path, family, wavelength, indices, date, temperature, shape_parameters
            )
        )
        local_output = filesystem_path(output)
        if local_output.exists() and not overwrite:
            with Dataset(str(local_output)) as cached:
                matching = getattr(cached, "retrieval_request_fingerprint", None) == fingerprint
                provenance = json.loads(getattr(cached, "interpolation_provenance_json", "{}"))
            if not matching or not verify_native_schema(output, template_path):
                raise InterpolationError(
                    f"Existing native filename has different inputs or schema; choose another output directory or overwrite explicitly: {output}"
                )
            return local_output, "skipped", provenance, tuple(record["path"] for record in selected)

        provenance = {
            "method": method,
            "particle_type": family,
            "target_wavelength_um": wavelength,
            "target_coordinates": target,
            "status": "out_of_database_bounds"
            if resolution.get("out_of_bounds")
            else "interpolated",
            "warnings": [resolution["out_of_bounds"]] if resolution.get("out_of_bounds") else [],
            "target_indices": indices,
            "axis_transforms": transforms,
            "native_schema_preserved": True,
            "template_source": str(template_path),
            "source_data_level": getattr(template, "data_level", "L1"),
            "size_alignment": "linear_in_native_x; source-exterior values remain NaN",
            "common_native_size_support": [float(low), float(high)],
            "template_size_points_outside_common_support": int(
                np.count_nonzero((target_grid < low) | (target_grid > high))
            ),
            "native_cross_section_convention": "dimensionless cext and proj_area, scaled by k^2",
            "scalar_method": "log_cext_and_csca; derive_ssa_qext; no dimensional conversion",
            "phase_method": "linear_parameter_p11_and_pij_over_p11; preserve_source_representation; log_positive_angle_alignment",
            "refractive_index_resolution": resolution,
            "neighbors": [
                {
                    "source": str(record["path"]),
                    "coordinates": record["coordinates"],
                    "weight": weight,
                    "normalized_distance": distance,
                }
                for record, weight, distance in zip(selected, weights, distances)
            ],
        }
        local_output.parent.mkdir(parents=True, exist_ok=True)
        temporary = local_output.with_name(local_output.name + ".part")
        with Dataset(str(temporary), "w", format=template.data_model) as destination_file:
            for name, dimension in template.dimensions.items():
                destination_file.createDimension(
                    name, None if dimension.isunlimited() else len(dimension)
                )
            destination_file.setncatts(
                {name: template.getncattr(name) for name in template.ncattrs()}
            )
            for name, variable in template.variables.items():
                _create_native_variable(destination_file, name, variable)
            p11 = None
            if "p11" in template.variables:
                p11 = _blend(
                    [aligned(dataset, "p11", phase_positive=True) for dataset in datasets], weights
                )
            for name, definition in template.variables.items():
                if name == "cext":
                    value = cext
                elif name == "ssa":
                    value = ssa
                elif name == "proj_area":
                    value = area
                elif name == "qext" and area is not None:
                    value = np.divide(cext, area, out=np.full_like(cext, np.nan), where=area > 0)
                elif name == "p11":
                    value = p11
                elif name in PHASE_NAMES:
                    ratios = []
                    for dataset in datasets:
                        raw = _values(dataset.variables[name])
                        if not _native_phase_variable_stores_ratio(dataset.variables[name]):
                            basis = _values(dataset.variables["p11"])
                            raw = np.divide(
                                raw, basis, out=np.full_like(raw, np.nan), where=basis != 0
                            )
                        ratios.append(aligned(dataset, name, raw))
                    value = _blend(ratios, weights)
                    if not _native_phase_variable_stores_ratio(definition):
                        value = value * p11
                elif name == "wavelength":
                    value = np.full(definition.shape, np.nan if wavelength is None else wavelength)
                elif name == "temperature" and temperature is not None:
                    value = np.full(definition.shape, temperature)
                elif (
                    name in {"ssph_n", "ssph_asp", "Df", "df"}
                    and {"ssph_n": "roundness", "ssph_asp": "aspect_ratio", "Df": "df", "df": "df"}[
                        name
                    ]
                    in shape_parameters
                ):
                    value = np.full(
                        definition.shape,
                        shape_parameters[
                            {
                                "ssph_n": "roundness",
                                "ssph_asp": "aspect_ratio",
                                "Df": "df",
                                "df": "df",
                            }[name]
                        ],
                    )
                elif name in {"mr", "mi"} and "refractive_index_real" in indices:
                    value = np.full(
                        definition.shape,
                        indices[
                            "refractive_index_real"
                            if name == "mr"
                            else "refractive_index_imaginary"
                        ],
                    )
                elif name in {"xsize_maxd", "xsize_veq", "sca_angle"}:
                    value = definition[:]
                elif size_dimension in definition.dimensions:
                    value = _blend([aligned(dataset, name) for dataset in datasets], weights)
                else:
                    value = definition[:]
                    if not all(_same(value, dataset.variables[name][:]) for dataset in datasets):
                        raise InterpolationError(
                            f"Fixed native coordinate {name} differs across sources"
                        )
                if resolution.get("out_of_bounds") and name in PHASE_NAMES | {
                    "cext",
                    "ssa",
                    "g",
                    "qext",
                    "proj_area",
                    "mr",
                    "mi",
                    "csca",
                    "cabs",
                    "qsca",
                    "qabs",
                }:
                    value = np.full(definition.shape, np.nan)
                destination_file.variables[name][...] = value
            prior_processing = str(getattr(template, "processing_type", "")).strip()
            processing = "refractive_index_interpolation" if is_grid else "wavelength_interpolation"
            if temperature is not None:
                processing = "wavelength_temperature_interpolation"
            if shape_parameters:
                processing = (
                    "refractive_index_shape_interpolation"
                    if is_grid
                    else "wavelength_temperature_shape_interpolation"
                )
            destination_file.setncatts(
                {
                    "data_level": "L1.5",
                    "creation_date": now.isoformat().replace("+00:00", "Z"),
                    "source_creation_date": str(getattr(template, "creation_date", "")),
                    "source_data_level": str(getattr(template, "data_level", "L1")),
                    "processing_type": ", ".join(filter(None, [prior_processing, processing])),
                    "derived_by": "zju_scatt_interface",
                    "target_refractive_indices_json": json.dumps(indices, sort_keys=True),
                    "interpolation_method": method,
                    "interpolation_provenance_json": json.dumps(provenance, sort_keys=True),
                    "retrieval_request_fingerprint": fingerprint,
                }
            )
            if wavelength is not None:
                destination_file.setncattr("target_wavelength_um", wavelength)
            if temperature is not None:
                destination_file.setncattr("target_temperature_k", float(temperature))
            if shape_parameters:
                destination_file.setncattr(
                    "target_shape_parameters_json", json.dumps(shape_parameters, sort_keys=True)
                )
            if resolution.get("out_of_bounds"):
                destination_file.setncattr("retrieval_status", "out_of_database_bounds")
                destination_file.setncattr("boundary_notice", resolution["out_of_bounds"])
        if not verify_native_schema(temporary, template_path):
            raise InterpolationError("Derived file does not preserve the complete native schema")
        temporary.replace(local_output)
    return local_output, "created", provenance, tuple(record["path"] for record in selected)
