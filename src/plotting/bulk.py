"""plotting / bulk domain implementation."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.plotting.single import (
    OpticalPlotStyle,
    _phase_figure,
    _plot_settings,
)

_SCALARS = {
    "beta_ext": ("extinction_coefficient",),
    "beta_sca": ("scattering_coefficient",),
    "beta_abs": ("absorption_coefficient",),
    "ssa": ("single_scattering_albedo",),
    "g": ("asymmetry_factor",),
    "number_concentration": (),
}
_PHASE = {"p11": (0, 0), "p12": (0, 1), "p22": (1, 1), "p33": (2, 2), "p44": (3, 3), "p43": (3, 2)}


def _bulk_content(source):
    from zju_scatt_interface.optics.models import BulkOptics

    if isinstance(source, BulkOptics):
        datasets = {}
        for field, aliases in _SCALARS.items():
            value = getattr(source, aliases[0] if aliases else field)
            if value is not None:
                unit = (
                    source.metadata.get(
                        "bulk_coefficient_unit",
                        source.metadata.get("extinction_coefficient_unit", "unknown"),
                    )
                    if field.startswith("beta_")
                    else source.metadata.get("number_concentration_output_unit", "unknown")
                    if field == "number_concentration"
                    else "1"
                )
                datasets[field] = {"data": value, "dimensions": [], "units": unit}
        if source.phase_matrix is not None:
            import numpy as np

            angles = source.metadata.get(
                "scattering_angles_degrees", source.metadata.get("scattering_angles")
            )
            phase = np.asarray(source.phase_matrix, dtype=float)
            if angles is None or phase.shape != (len(angles), 4, 4):
                raise ValueError(
                    "Bulk phase matrix requires matching scattering_angles_degrees metadata"
                )
            datasets["sca_angle"] = {"data": angles, "dimensions": ["sca_angle"], "units": "degree"}
            for field, (row, col) in _PHASE.items():
                datasets[field] = {
                    "data": phase[:, row, col],
                    "dimensions": ["sca_angle"],
                    "units": "1",
                }
        return {"datasets": {}, "components": {"bulk": {"datasets": datasets}}}
    from zju_scatt_interface.io.tables import _normalize_content

    return _normalize_content(source)


def _prepare_component(component, root):
    """Validate optical axes by their declared names, never infer them by length."""
    import numpy as np

    datasets = component.get("datasets", {})
    aliases = {name.lower(): name for name in datasets}
    fields = {}
    for canonical, alternatives in {**_SCALARS, **{name: () for name in _PHASE}}.items():
        found = next(
            (aliases[name] for name in (canonical, *alternatives) if name in aliases), None
        )
        if found is None:
            continue
        entry = datasets[found]
        data = np.asarray(entry["data"], dtype=float)
        dims = tuple(entry.get("dimensions", ()))
        if len(dims) != data.ndim or len(set(dims)) != len(dims) or any(n == 0 for n in data.shape):
            raise ValueError(f"{found}: missing/inconsistent dimension metadata or empty axis")
        fields[canonical] = {"data": data, "dimensions": dims, "units": entry.get("units", "1")}
    coordinates = {**root, **datasets}
    angle_key = next(
        (
            key
            for key in (
                "sca_angle",
                "scattering_angle",
                "scattering_angles",
                "scattering_angle_degrees",
            )
            if key in coordinates
        ),
        None,
    )
    angle_dim = None
    angles = None
    if any(name in fields for name in _PHASE):
        if angle_key is None:
            raise ValueError("Phase elements require a scattering-angle coordinate")
        entry = coordinates[angle_key]
        angles = np.asarray(entry["data"], dtype=float)
        dims = entry.get("dimensions", ())
        if (
            angles.ndim != 1
            or len(dims) != 1
            or len(angles) < 2
            or not np.isfinite(angles).all()
            or np.any(np.diff(angles) <= 0)
        ):
            raise ValueError(
                "Scattering angles must have one dimension and strictly increasing finite values"
            )
        unit = str(entry.get("units", "degree")).lower()
        if unit in ("rad", "radian", "radians"):
            angles = np.rad2deg(angles)
        elif unit not in ("degree", "degrees", "deg"):
            raise ValueError(f"Unsupported scattering-angle unit: {unit}")
        if angles[0] < 0 or angles[-1] > 180 + 1.0e-8:
            raise ValueError("Scattering angles must lie within 0..180 degrees")
        angle_dim = dims[0]
    sizes = {}
    for name, entry in fields.items():
        dims = entry["dimensions"]
        if name in _PHASE and angle_dim not in dims:
            raise ValueError(f"{name}: no scattering-angle dimension")
        if name in _SCALARS and angle_dim is not None and angle_dim in dims:
            raise ValueError(f"{name}: scalar property cannot depend on scattering angle")
        for dim, length in zip(dims, entry["data"].shape):
            if dim in sizes and sizes[dim] != length:
                raise ValueError(f"Conflicting length for dimension {dim}")
            sizes[dim] = length
    axes = {}
    for dim, length in sizes.items():
        if dim == angle_dim:
            if length != len(angles):
                raise ValueError("Phase element does not match the scattering-angle grid")
            continue
        entry = coordinates.get(dim)
        values = np.asarray(entry["data"]) if entry else np.arange(length)
        if values.shape != (length,):
            raise ValueError(
                f"Coordinate {dim} must be a one-dimensional vector of length {length}"
            )
        numeric = values.dtype.kind in "iuf"
        if numeric and not np.isfinite(values).all():
            raise ValueError(f"Nonfinite coordinate {dim}")
        physical = entry is not None and numeric and len(np.unique(values)) == length
        order = np.argsort(values, kind="stable") if physical else np.arange(length)
        axes[dim] = {
            "values": values,
            "x": values if physical else np.arange(length),
            "order": order,
            "units": entry.get("units", "1") if entry else "1",
            "index_axis": not physical,
        }
    return fields, axes, angle_dim, angles


def _slice(entry, varying, indices):
    """Keep one named dimension; select the same fixed state on all others."""
    return entry["data"][
        tuple(slice(None) if dim == varying else indices[dim] for dim in entry["dimensions"])
    ]


def _value_label(dim, axis, index):
    value = axis["values"][index]
    if hasattr(value, "item"):
        value = value.item()
    text = f"{value:.5g}" if isinstance(value, (int, float)) else str(value)
    unit = str(axis["units"])
    name = f"{dim}[{index}]" if axis["index_axis"] else dim
    return f"{name} = {text}" + (f" {unit}" if unit not in ("1", "") else "")


def _selection(axes, indices, exclude=None):
    return {
        dim: {"index": int(index), "label": _value_label(dim, axes[dim], index)}
        for dim, index in indices.items()
        if dim != exclude
    }


def _scalar_figure(fields, axes, varying, fixed, style, heading):
    import matplotlib.pyplot as plt
    import numpy as np

    with plt.rc_context(_plot_settings(style)):
        fig, paxes = plt.subplots(
            *style.scalar_layout, figsize=style.scalar_figsize, layout="constrained", squeeze=False
        )
        paxes = paxes.ravel()
        if varying is None:
            x = [0]
            order = None
            xlabel = "Bulk state"
        else:
            axis = axes[varying]
            order = axis["order"]
            x = axis["x"][order]
            xlabel = varying + (
                " index"
                if axis["index_axis"]
                else f" ({axis['units']})"
                if axis["units"] not in ("1", "")
                else ""
            )
        for i, (names, label) in enumerate(
            (
                (("beta_ext", "beta_sca", "beta_abs"), "Bulk coefficient"),
                (("ssa",), "Single-scattering albedo"),
                (("g",), "Asymmetry factor"),
                (("number_concentration",), "Number concentration"),
            )
        ):
            a = paxes[i]
            available = []
            for j, name in enumerate(names):
                entry = fields.get(name)
                if entry is None or (varying is not None and varying not in entry["dimensions"]):
                    continue
                y = np.atleast_1d(_slice(entry, varying, fixed))
                if order is not None:
                    y = y[order]
                a.plot(
                    x,
                    y,
                    color=style.colors[j],
                    ls=style.line_styles[j % len(style.line_styles)],
                    marker="o" if varying is None else None,
                    label=name,
                )
                available.append(entry["units"])
            units = set(available)
            if len(units) > 1:
                plt.close(fig)
                raise ValueError("Overlaid bulk coefficients require identical units")
            unit = available[0] if available else None
            a.set_ylabel(label + (f" ({unit})" if unit not in (None, "1", "") else ""))
            a.set_xlabel(xlabel)
            a.set_title(f"({chr(97 + i)})", loc="left", fontweight="bold")
            a.grid(True, alpha=style.grid_alpha)
            if (
                varying is not None
                and not axes[varying]["index_axis"]
                and any(token in varying.lower() for token in ("radius", "size", "diameter"))
                and np.all(np.asarray(x) > 0)
            ):
                a.set_xscale("log")
            if varying is None:
                a.set_xticks([0], ["state"])
            if i in (1, 2) and a.lines:
                values = np.concatenate(
                    [np.asarray(line.get_ydata(), dtype=float) for line in a.lines]
                )
                finite = values[np.isfinite(values)]
                lower = 0 if i == 1 else -1
                a.set_ylim(
                    min(lower - 0.02, float(finite.min()) - 0.02) if finite.size else lower - 0.02,
                    max(1.02, float(finite.max()) + 0.02) if finite.size else 1.02,
                )
            if len(a.lines) > 1:
                a.legend()
        fig.suptitle(heading)
    return fig


@_registration_required
def plot_bulk_optics(source, *, output_dir=None, show=False, style=None):
    """Inspect existing bulk NC/HDF5, canonical tables, grid results or BulkOptics.

    One scalar overview per non-singleton optical axis, and one six-panel phase
    figure per non-singleton phase axis. Phase curves select min/middle/max
    coordinate values (at most three). Other axes are fixed at their middle
    grid values, stated in titles and inspection.json. No averaging, integration,
    interpolation or phase renormalization is performed. PNG/PDF/SVG are saved
    automatically; returned figures are closed after export unless show=True.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    style = OpticalPlotStyle() if style is None else style
    if not isinstance(style, OpticalPlotStyle):
        raise TypeError("style must be an OpticalPlotStyle")
    content = _bulk_content(source)
    components = dict(content.get("components", {}))
    root = content.get("datasets", {})
    supported_names = (
        set(_SCALARS) | set(_PHASE) | {alias for aliases in _SCALARS.values() for alias in aliases}
    )
    if any(name.lower() in supported_names for name in root):
        components = {"root": {"datasets": root}, **components}
    # Validate every component before writing figures.
    prepared = {name: _prepare_component(component, root) for name, component in components.items()}
    prepared = {name: value for name, value in prepared.items() if value[0]}
    if not prepared:
        raise ValueError("No supported bulk coefficients, SSA, asymmetry or phase elements found")
    for component, (_, axes, _, _) in prepared.items():
        for name in (component, *axes):
            if name in (".", "..") or any(char in name for char in "/\\"):
                raise ValueError(
                    f"Unsupported path separator in component/dimension name: {name!r}"
                )
    if output_dir is None:
        output_dir = (
            Path(source).with_name(Path(source).stem + "_bulk_plots")
            if isinstance(source, (str, Path))
            else Path.cwd() / "bulk_optics_plots"
        )
    directory = Path(output_dir)
    report = {"components": {}}
    if content.get("path"):
        report["source_file"] = str(content["path"])
    figures = {}
    files = {}

    def save(figure, component, stem):
        key = f"{component}/{stem}"
        figures[key] = figure
        try:
            target_dir = directory / component
            target_dir.mkdir(parents=True, exist_ok=True)
            files[key] = {}
            for extension in ("png", "pdf", "svg"):
                target = target_dir / f"{stem}.{extension}"
                with plt.rc_context(_plot_settings(style)):
                    figure.savefig(target, dpi=300)
                files[key][extension] = target
        finally:
            if not show:
                plt.close(figure)

    try:
        for component, (fields, axes, angle_dim, angles) in prepared.items():
            fixed = {dim: int(axis["order"][len(axis["order"]) // 2]) for dim, axis in axes.items()}
            detail = {"fields": {}, "dimensions": {}, "scalar_plots": {}, "phase_plots": {}}
            detail["missing_fields"] = [name for name in (*_SCALARS, *_PHASE) if name not in fields]
            if angles is not None:
                detail["scattering_angle"] = {
                    "dimension": angle_dim,
                    "count": len(angles),
                    "range_degrees": [float(angles[0]), float(angles[-1])],
                }
            report["components"][component] = detail
            for name, entry in fields.items():
                a = entry["data"]
                finite = a[np.isfinite(a)]
                detail["fields"][name] = {
                    "dimensions": list(entry["dimensions"]),
                    "shape": list(a.shape),
                    "units": entry["units"],
                    "nonfinite": int(np.sum(~np.isfinite(a))),
                    "negative": int(np.sum(a < 0)),
                    "zero": int(np.sum(a == 0)),
                    "minimum": float(finite.min()) if finite.size else None,
                    "maximum": float(finite.max()) if finite.size else None,
                }
            for dim, axis in axes.items():
                detail["dimensions"][dim] = {
                    "count": len(axis["values"]),
                    "units": axis["units"],
                    "coordinate_source": "index" if axis["index_axis"] else "coordinate",
                }

            def heading(kind, varying):
                state = "; ".join(
                    value["label"]
                    for dim, value in _selection(axes, fixed, varying).items()
                    if any(
                        dim in entry["dimensions"]
                        for name, entry in fields.items()
                        if (name in _PHASE) == (kind == "Phase")
                    )
                )
                first = f"{component} | {kind}" + (f" | varying {varying}" if varying else "")
                return "\n".join(textwrap.wrap(first, width=95)) + (
                    "\n" + "\n".join(textwrap.wrap("Fixed: " + state, width=110)) if state else ""
                )

            scalar_axes = [
                dim
                for dim, axis in axes.items()
                if len(axis["values"]) > 1
                and any(dim in fields[name]["dimensions"] for name in _SCALARS if name in fields)
            ]
            if any(name in fields for name in _SCALARS):
                for dim in scalar_axes or [None]:
                    stem = f"scalar_{dim}" if dim else "scalar_state"
                    detail["scalar_plots"][stem] = {
                        "varying_dimension": dim,
                        "fixed": _selection(axes, fixed, dim),
                    }
                    save(
                        _scalar_figure(fields, axes, dim, fixed, style, heading("Scalars", dim)),
                        component,
                        stem,
                    )
            phase_axes = [
                dim
                for dim, axis in axes.items()
                if len(axis["values"]) > 1
                and any(dim in fields[name]["dimensions"] for name in _PHASE if name in fields)
            ]
            if any(name in fields for name in _PHASE):
                for dim in phase_axes or [None]:
                    indices = (
                        list(
                            dict.fromkeys(
                                int(axes[dim]["order"][i])
                                for i in (
                                    0,
                                    len(axes[dim]["values"]) // 2,
                                    len(axes[dim]["values"]) - 1,
                                )
                            )
                        )
                        if dim
                        else [None]
                    )
                    curves = []
                    labels = []
                    selections = []
                    for index in indices:
                        state = {**fixed, **({dim: index} if dim else {})}
                        curves.append(
                            {
                                name: _slice(entry, angle_dim, state)
                                for name, entry in fields.items()
                                if name in _PHASE
                            }
                        )
                        labels.append(_value_label(dim, axes[dim], index) if dim else "bulk state")
                        selections.append({"index": index, "label": labels[-1]})
                    stem = f"phase_{dim}" if dim else "phase_state"
                    detail["phase_plots"][stem] = {
                        "varying_dimension": dim,
                        "selected": selections,
                        "fixed": _selection(axes, fixed, dim),
                        "missing_elements": [name for name in _PHASE if name not in fields],
                    }
                    save(
                        _phase_figure(
                            angles, curves, labels, style=style, title=heading("Phase", dim)
                        ),
                        component,
                        stem,
                    )
        if show:
            plt.show()
    except Exception:
        for figure in figures.values():
            plt.close(figure)
        raise
    report_path = directory / "inspection.json"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return {
        "output_dir": directory,
        "files": files,
        "report_file": report_path,
        "inspection": report,
        "figures": figures,
    }
