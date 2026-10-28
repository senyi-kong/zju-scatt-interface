"""io / native domain implementation."""

from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)


def _plain(value):
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, (tuple, list)):
        return [_plain(x) for x in value]
    return value


@_registration_required
def load_native_output_template(path):
    """Read a declarative JSON template (no executable expressions)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


@_registration_required
def native_template_from_reference(path, *, model):
    from zju_scatt_interface.extensions.native import native_capability

    return native_capability(model, "template")(path)


@_registration_required
def read_native_optical_arrays(path, *, model):
    from zju_scatt_interface.extensions.native import native_capability

    return native_capability(model, "read")(path)


@_registration_required
def arts_output_template(n_frequency, n_temperature, n_angle):
    """Build an ARTS SSD template through its application implementation."""
    from zju_scatt_interface.io.applications.arts.native import (
        arts_output_template as implementation,
    )

    return implementation(n_frequency, n_temperature, n_angle)


def _resolve_arrays(data, template):
    import numpy as np

    if template.get("schema_version") != 1:
        raise ValueError("unsupported native template schema_version")
    allowed = {
        "schema_version",
        "model",
        "format",
        "attributes",
        "dimensions",
        "groups",
        "variables",
        "byte_order",
        "cloud_variant",
        "aerosol_variant",
        "group_dimensions",
    }
    if set(template) - allowed:
        raise ValueError(f"unknown native template keys: {sorted(set(template) - allowed)}")
    arrays = {}
    for name, spec in template["variables"].items():
        allowed_variable = {
            "source",
            "data",
            "shape",
            "dimensions",
            "dtype",
            "attributes",
            "compression",
            "transpose",
            "reshape",
            "scale",
            "offset",
        }
        if set(spec) - allowed_variable:
            raise ValueError(
                f"{name}: unknown variable keys {sorted(set(spec) - allowed_variable)}"
            )
        if ("data" in spec) == ("source" in spec):
            raise ValueError(f"{name}: specify exactly one of source or data")
        if "source" in spec and spec["source"] not in data:
            raise ValueError(f"{name}: missing source {spec['source']!r}")
        value = spec["data"] if "data" in spec else data[spec["source"]]
        if spec.get("dtype") == "string":
            arrays[name] = str(value)
            continue
        value = np.asarray(value)
        if value.dtype.kind == "c":
            raise ValueError(f"{name}: optical arrays must be real, not complex")
        if "transpose" in spec:
            value = value.transpose(spec["transpose"])
        if "scale" in spec or "offset" in spec:
            value = value * spec.get("scale", 1) + spec.get("offset", 0)
        if "reshape" in spec:
            value = value.reshape(spec["reshape"])
        shape = tuple(
            spec["shape"]
            if "shape" in spec
            else [template["dimensions"][d] for d in spec.get("dimensions", [])]
        )
        if value.shape != shape:
            raise ValueError(
                f"{name}: expected shape {shape}, got {value.shape}; no implicit broadcast"
            )
        dtype = np.dtype(spec.get("dtype", "float64"))
        if value.dtype.kind in "fciu":
            if not np.isfinite(value).all():
                raise ValueError(f"{name}: non-finite values")
            if dtype.kind in "iu":
                limits = np.iinfo(dtype)
                if (
                    np.any(value != np.floor(value))
                    or np.any(value < limits.min)
                    or np.any(value > limits.max)
                ):
                    raise ValueError(f"{name}: values cannot be represented as {dtype}")
        if dtype.kind == "S" and any(
            len(str(_plain(v)).encode()) > dtype.itemsize for v in value.flat
        ):
            raise ValueError(f"{name}: string would be truncated")
        arrays[name] = value.astype(dtype)
        if dtype.kind == "f" and not np.isfinite(arrays[name]).all():
            raise ValueError(f"{name}: overflow converting to {dtype}")
    return arrays


def _increasing(value, name, *, positive=False):
    import numpy as np

    if (
        value.ndim != 1
        or value.size == 0
        or not np.isfinite(value).all()
        or np.any(np.diff(value) <= 0)
    ):
        raise ValueError(f"{name}: requires a nonempty strictly increasing grid")
    if positive and np.any(value <= 0):
        raise ValueError(f"{name}: grid must be positive")


def _validate_native(arrays, template):
    from zju_scatt_interface.extensions.native import native_model

    return native_model(template.get("model")).validate(arrays, template)


@_registration_required
def write_native_optical_output(path, data, template, *, overwrite=False):
    """Write a validated native product atomically using a dict or JSON template.

    Variable specs support source/data, dtype, dimensions/shape, transpose,
    scale, offset, reshape and attributes. No interpolation, normalization or
    broadcasting is guessed. ``custom`` templates can define arbitrary HDF5
    groups or NetCDF dimensions; official presets enforce their model schema.
    """
    if isinstance(template, (str, Path)):
        template = load_native_output_template(template)
    template = copy.deepcopy(template)
    arrays = _resolve_arrays(data, template)
    _validate_native(arrays, template)
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _serialize(temporary, arrays, template)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()  # Only this explicitly named temporary file.
    return path


def _serialize(path, arrays, template):
    from zju_scatt_interface.extensions.native import serialize

    return serialize(path, arrays, template)


@_registration_required
def crtm_cloud_output_template(dimensions, *, binary=False, byte_order="little", version=1):
    """Build a CRTM cloud template through its application implementation."""
    from zju_scatt_interface.io.applications.crtm.native import (
        crtm_cloud_output_template as implementation,
    )

    return implementation(dimensions, binary=binary, byte_order=byte_order, version=version)


@_registration_required
def rttov13_aerosol_output_template(
    n_channels,
    species,
    *,
    max_moments=128,
    phase_angles=(),
    solar_channels=(),
    species_naming="rttov",
):
    """Build an RTTOV13 aerosol template through its application implementation."""
    from zju_scatt_interface.io.applications.rttov.native import (
        rttov13_aerosol_output_template as implementation,
    )

    return implementation(
        n_channels,
        species,
        max_moments=max_moments,
        phase_angles=phase_angles,
        solar_channels=solar_channels,
        species_naming=species_naming,
    )


@_registration_required
def arts_arrays_from_bulk(data, *, component, number_density_m3, temperature_k=None):
    """Convert canonical bulk data using the ARTS application policy."""
    from zju_scatt_interface.io.applications.arts.native import (
        arts_arrays_from_bulk as implementation,
    )

    return implementation(
        data, component=component, number_density_m3=number_density_m3, temperature_k=temperature_k
    )


@_registration_required
def bulk_model_fields(bulk, *, model, mass_concentration_kg_m3=None, number_density_m3=None):
    from zju_scatt_interface.extensions.native import native_capability

    return native_capability(model, "bulk_fields")(
        bulk, mass_concentration_kg_m3=mass_concentration_kg_m3, number_density_m3=number_density_m3
    )


@_registration_required
def scalar_phase_to_model(
    angles_degrees,
    p11,
    *,
    model,
    max_moments=128,
    quadrature_points=512,
    hemisphere_points=32,
    normalization_tolerance=0.01,
):
    """Project phase using the selected native model's registered convention."""
    from zju_scatt_interface.extensions.native import native_capability

    return native_capability(model, "phase")(
        angles_degrees,
        p11,
        max_moments=max_moments,
        quadrature_points=quadrature_points,
        hemisphere_points=hemisphere_points,
        normalization_tolerance=normalization_tolerance,
    )
