"""io / custom domain implementation."""

from __future__ import annotations

import json
import re
import runpy
from collections.abc import Mapping
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.io.native import _resolve_arrays, write_native_optical_output
from zju_scatt_interface.io.tables import _normalize_content

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNITS = {}
for category, pairs in {
    "length": {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "um": 1e-6, "nm": 1e-9},
    "inverse_length": {"m-1": 1.0, "km-1": 1e-3, "cm-1": 1e2},
    "number_density": {"m-3": 1.0, "cm-3": 1e6},
    "area": {"m2": 1.0, "cm2": 1e-4, "um2": 1e-12},
    "dimensionless": {"1": 1.0, "%": 0.01},
    "mass_density": {"kgm-3": 1.0, "gm-3": 1e-3},
    "temperature": {"K": 1.0},
    "angle": {"degree": 1.0, "rad": 180 / 3.141592653589793},
}.items():
    _UNITS.update({unit: (category, factor) for unit, factor in pairs.items()})


def _unit(unit):
    text = str(unit).replace(" ", "").replace("^", "").replace("µ", "u").replace("μ", "u")
    return {
        "": "1",
        "dimensionless": "1",
        "1/m": "m-1",
        "1/km": "km-1",
        "micrometer": "um",
        "micrometre": "um",
        "degrees": "degree",
        "deg": "degree",
        "kelvin": "K",
    }.get(text, text)


def _conversion(source, target):
    a, b = _unit(source), _unit(target)
    if a == b:
        return 1.0
    if a not in _UNITS or b not in _UNITS or _UNITS[a][0] != _UNITS[b][0]:
        raise ValueError(
            f"Unsupported unit conversion {source!r} -> {target!r}; prepare physical model fields explicitly"
        )
    return _UNITS[a][1] / _UNITS[b][1]


def _attrs(values):
    result = {}
    for key, value in values.items():
        if isinstance(value, bool):
            value = int(value)
        elif isinstance(value, (dict, list, tuple)):
            value = json.dumps(value)
        elif value is None:
            raise ValueError(f"Attribute {key!r} cannot be None")
        result[str(key)] = value
    return result


def _path(text, **values):
    name = str(text).format(**values)
    if name and any(not _NAME.fullmatch(part) for part in name.split("/")):
        raise ValueError(f"Invalid portable output name/path: {name!r}")
    return name


def _component(key, components):
    if key in components:
        return key
    from zju_scatt_interface.config.particles import get_particle_profile

    try:
        family = get_particle_profile(key).particle_type
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Unknown output species {key!r}") from exc
    found = [
        name
        for name, entry in components.items()
        if name == family or entry.get("attributes", {}).get("particle_type") == family
    ]
    if len(found) != 1:
        raise ValueError(
            f"Species {key!r} matches {len(found)} components; use an exact component name"
        )
    return found[0]


def _configuration(value):
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        if path.suffix.lower() == ".json":
            loaded = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() == ".py":
            loaded = runpy.run_path(str(path))
            loaded = {key: loaded[key] for key in ("output", "outputs") if key in loaded}
        else:
            raise ValueError("Custom output configuration must be Python or JSON")
        base = path.parent
    else:
        loaded, base = value, Path.cwd()
    if not isinstance(loaded, Mapping):
        raise TypeError("Output configuration must be a mapping or Python/JSON path")
    if "output" in loaded and "outputs" in loaded:
        raise ValueError("Specify output or outputs, not both")
    if "outputs" in loaded:
        specs = loaded["outputs"]
    else:
        specs = [loaded.get("output", loaded)]
    if not isinstance(specs, (list, tuple)) or not specs:
        raise ValueError("outputs must be a nonempty list of output specifications")
    return specs, base


def _compile(content, spec, base):
    import numpy as np

    allowed = {
        "format",
        "filename",
        "species",
        "species_names",
        "group",
        "dimensions",
        "coordinates",
        "variables",
        "attributes",
        "group_attributes",
        "compression",
    }
    if not isinstance(spec, Mapping) or set(spec) - allowed:
        raise ValueError(
            f"Unknown custom output options: {set(spec) - allowed if isinstance(spec, Mapping) else spec}"
        )
    fmt = {"hdf": "hdf5", "h5": "hdf5", "nc": "netcdf4", "netcdf": "netcdf4"}.get(
        spec.get("format"), spec.get("format")
    )
    if fmt not in {"hdf5", "netcdf4"}:
        raise ValueError("Custom output format must be hdf5 or netcdf4")
    if not spec.get("filename"):
        raise ValueError("Output filename is required")
    path = Path(spec["filename"]).expanduser()
    path = path if path.is_absolute() else base / path
    path = path.resolve()
    components = content["components"]
    selected = spec.get("species", list(components))
    if not isinstance(selected, (list, tuple)) or not selected:
        raise ValueError("species must be a nonempty list")
    selected = [_component(key, components) for key in selected]
    if len(set(selected)) != len(selected):
        raise ValueError("Duplicate selected species")
    aliases = {}
    for key, value in spec.get("species_names", {}).items():
        name = _component(key, components)
        if name in aliases:
            raise ValueError("Duplicate species aliases")
        aliases[name] = value
    names = {name: aliases.get(name, name) for name in selected}
    if any(
        not isinstance(value, str) or not _NAME.fullmatch(value) for value in names.values()
    ) or len(set(names.values())) != len(names):
        raise ValueError("Output species names must be unique portable identifiers")
    preferred = spec.get("dimensions", [])
    if not isinstance(preferred, (list, tuple)) or len(set(preferred)) != len(preferred):
        raise ValueError("dimensions must be an ordered list of unique source axis names")
    known_axes = {
        axis
        for component in selected
        for dataset in components[component]["datasets"].values()
        for axis in dataset.get("dimensions", [])
    }
    known_axes.update(
        axis
        for dataset in content.get("datasets", {}).values()
        for axis in dataset.get("dimensions", [])
    )
    if set(preferred) - known_axes:
        raise ValueError(f"Unknown preferred dimensions: {set(preferred) - known_axes}")
    variables = spec.get("variables")
    if not isinstance(variables, Mapping) or not variables:
        raise ValueError("A nonempty variables mapping is required")
    compression = spec.get("compression", 4)
    if (
        isinstance(compression, bool)
        or not isinstance(compression, int)
        or not 0 <= compression <= 9
    ):
        raise ValueError("compression must be an integer 0..9")
    template = {
        "schema_version": 1,
        "model": "custom",
        "format": fmt,
        "attributes": _attrs(spec.get("attributes", {})),
        "dimensions": {},
        "group_dimensions": {},
        "groups": {},
        "variables": {},
    }
    arrays = {}
    mappings = []

    def add(full, value, dims, units, attributes, dtype=None):
        value = np.asarray(value)
        if len(dims) != len(set(dims)):
            raise ValueError(f"Coordinate renaming collapses distinct dimensions for {full}")
        if set(attributes) & {"scale_factor", "add_offset", "_Unsigned"}:
            raise ValueError(
                "Packed-data attributes are unsupported; use explicit scale/offset and dtype"
            )
        if "units" in attributes and attributes["units"] != units:
            raise ValueError(f"Conflicting units attributes for {full}")
        if value.dtype.kind not in "iuf":
            raise ValueError(f"Custom optical variable {full} must be real numeric data")
        parent, _, _ = full.rpartition("/")
        target = (
            template["group_dimensions"].setdefault(parent, {})
            if parent
            else template["dimensions"]
        )
        for dim, length in zip(dims, value.shape):
            if length <= 0 or (dim in target and target[dim] != length):
                raise ValueError(f"Conflicting or empty dimension {parent}/{dim}")
            target[dim] = length
        attributes = {**_attrs(attributes), "units": units, "dimensions": json.dumps(dims)}
        if full in arrays:
            old = template["variables"][full]
            if (
                old["dimensions"] != dims
                or old["attributes"] != attributes
                or not np.array_equal(arrays[full], value)
            ):
                raise ValueError(
                    f"Conflicting output variable {full}; use separate species groups or names"
                )
            return
        arrays[full] = value
        template["variables"][full] = {
            "source": full,
            "shape": list(value.shape),
            "dimensions": dims,
            "dtype": dtype or ("float64" if value.dtype.kind == "f" else "int32"),
            "attributes": attributes,
            "compression": compression,
        }

    for component in selected:
        entry = components[component]
        datasets = {**content.get("datasets", {}), **entry["datasets"]}
        context = {"species": names[component], "component": component}
        group = _path(spec.get("group", "{species}"), **context)
        if group:
            attrs = {"source_component": component, **spec.get("group_attributes", {})}
            if group in template["groups"] and template["groups"][group] != _attrs(attrs):
                # A deliberately shared group has multiple source components.
                attrs.pop("source_component", None)
            template["groups"][group] = _attrs(attrs)
        coordinate_options = spec.get("coordinates", {})
        dimensions = {}

        def coordinate(axis):
            if axis in dimensions:
                return dimensions[axis]
            options = coordinate_options.get(axis, {})
            if not isinstance(options, Mapping) or set(options) - {
                "name",
                "source",
                "units",
                "dtype",
                "attributes",
            }:
                raise ValueError(f"Invalid coordinate options for {axis}")
            source = options.get("source", axis)
            if source not in datasets:
                raise ValueError(
                    f"Missing coordinate variable for {component}/{axis}; configure coordinates[{axis!r}].source"
                )
            record = datasets[source]
            if list(record.get("dimensions", [])) != [axis]:
                raise ValueError(f"Coordinate {source!r} must have dimensions [{axis!r}]")
            name = _path(options.get("name", axis), **context)
            if not name or "/" in name:
                raise ValueError("Coordinate names must be single identifiers")
            units = options.get("units", record.get("units", "1"))
            value = np.asarray(record["data"])
            factor = _conversion(record.get("units", "1"), units)
            if factor != 1.0:
                value = value * factor
            if value.ndim != 1:
                raise ValueError(f"Coordinate {axis} must be one-dimensional")
            full = f"{group}/{name}" if group else name
            add(full, value, [name], units, options.get("attributes", {}), options.get("dtype"))
            dimensions[axis] = (name, len(value))
            return dimensions[axis]

        for output_name, options in variables.items():
            options = {"source": options} if isinstance(options, str) else options
            if not isinstance(options, Mapping) or set(options) - {
                "source",
                "units",
                "dtype",
                "dimensions",
                "attributes",
                "scale",
                "offset",
            }:
                raise ValueError(f"Invalid variable options for {output_name}")
            source = options.get("source", output_name)
            if source not in datasets:
                raise ValueError(f"Missing optical variable {component}/{source}")
            record = datasets[source]
            original = list(record.get("dimensions", []))
            value = np.asarray(record["data"])
            if value.ndim != len(original) or len(set(original)) != len(original):
                raise ValueError(f"Invalid source dimensions for {component}/{source}")
            order = options.get(
                "dimensions",
                [a for a in preferred if a in original]
                + [a for a in original if a not in preferred],
            )
            if (
                not isinstance(order, (list, tuple))
                or len(order) != len(original)
                or set(order) != set(original)
            ):
                raise ValueError(
                    f"Variable dimensions must be a permutation of {original}; no broadcasting/squeezing is inferred"
                )
            for axis, length in zip(original, value.shape):
                if coordinate(axis)[1] != length:
                    raise ValueError(f"Coordinate length mismatch for {component}/{source}/{axis}")
            value = value.transpose([original.index(a) for a in order])
            units = options.get("units", record.get("units", "1"))
            attrs = options.get("attributes", {})
            if "units" in attrs and attrs["units"] != units:
                raise ValueError("Specify consistent units through the variable units option")
            factor = _conversion(record.get("units", "1"), units)
            if factor != 1.0:
                value = value * factor
            scale, offset = float(options.get("scale", 1)), float(options.get("offset", 0))
            if not np.isfinite([scale, offset]).all():
                raise ValueError("Scale and offset must be finite")
            if scale != 1.0 or offset != 0.0:
                value = value * scale + offset
            name = _path(output_name, **context)
            if not name or "/" in name:
                raise ValueError("Variable names must be single identifiers; use group for nesting")
            full = f"{group}/{name}" if group else name
            add(full, value, [coordinate(a)[0] for a in order], units, attrs, options.get("dtype"))
            mappings.append({"component": component, "variable": source, "output": full})
    # Validate every array and cast before opening or replacing any output file.
    expected = _resolve_arrays(arrays, template)
    return path, arrays, template, expected, mappings


def _verify(path, template, expected):
    import numpy as np

    if template["format"] == "hdf5":
        import h5py

        with h5py.File(path) as handle:
            for name, array in expected.items():
                np.testing.assert_array_equal(handle[name][()], array)
                if (
                    handle[name].attrs["units"]
                    != template["variables"][name]["attributes"]["units"]
                ):
                    raise ValueError(f"Written unit mismatch for {name}")
    else:
        from netCDF4 import Dataset

        with Dataset(path) as handle:
            handle.set_auto_maskandscale(False)
            for name, array in expected.items():
                var = handle[name]
                np.testing.assert_array_equal(var[...], array)
                if (
                    list(var.dimensions) != template["variables"][name]["dimensions"]
                    or var.units != template["variables"][name]["attributes"]["units"]
                ):
                    raise ValueError(f"Written dimensions/units disagree for {name}")
    return {"valid": True, "path": str(path), "variables_checked": len(expected)}


@_registration_required
def export_bulk_optics(data, output, *, output_dir=None, overwrite=False):
    """Export a bulk result/canonical grid/file through Python/JSON layout config.

    output is a specification, {outputs:[...]}, or a .py/.json configuration
    containing output or outputs. Relative filenames resolve beside that file,
    or against output_dir when supplied. Each selected variable's actual axes
    are preserved; dimensions controls ordering, coordinates controls labels
    and units. Only known multiplicative unit conversions are automatic.
    Nonfinite optical arrays, lossy integer casts and missing coordinates fail.
    For physical model conversions, prepare model fields explicitly first.
    """
    source_path = Path(data).expanduser().resolve() if isinstance(data, (str, Path)) else None
    if hasattr(data, "scheme"):
        data = data.scheme
    content = _normalize_content(data)
    specs, base = _configuration(output)
    base = Path(output_dir).expanduser().resolve() if output_dir is not None else base
    plans = [_compile(content, spec, base) for spec in specs]
    paths = [p[0] for p in plans]
    if len(set(paths)) != len(paths):
        raise ValueError("Custom output filenames must be distinct")
    if source_path in paths:
        raise ValueError("Custom output must not overwrite the canonical source file")
    for path in paths:
        if path.exists() and not overwrite:
            raise FileExistsError(path)
    results = []
    for path, arrays, template, expected, mappings in plans:
        write_native_optical_output(path, arrays, template, overwrite=overwrite)
        results.append(
            {
                "path": str(path),
                "format": template["format"],
                "variables": mappings,
                "validation": _verify(path, template, expected),
            }
        )
    return {"outputs": [str(p) for p in paths], "results": results}
