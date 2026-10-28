"""plotting / single domain implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)


@dataclass(frozen=True)
class OpticalPlotStyle:
    """Shared inspection style; layouts must contain four/six panels respectively.

    Settings apply only while creating figures, leaving global rcParams unchanged.
    """

    font_family: str = "DejaVu Sans"
    font_size: float = 10
    line_width: float = 1.5
    scalar_layout: tuple = (2, 2)
    phase_layout: tuple = (2, 3)
    scalar_figsize: tuple = (10, 7)
    phase_figsize: tuple = (12, 6.6)
    colors: tuple = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#000000")
    line_styles: tuple = ("-", "--", "-.", ":")
    grid_alpha: float = 0.2

    def __post_init__(self):
        for layout, count in ((self.scalar_layout, 4), (self.phase_layout, 6)):
            if (
                len(layout) != 2
                or any(type(n) is not int or n <= 0 for n in layout)
                or layout[0] * layout[1] != count
            ):
                raise ValueError(f"Layout must contain exactly {count} panels")
        if (
            self.font_size <= 0
            or self.line_width <= 0
            or len(self.colors) < 6
            or not self.line_styles
        ):
            raise ValueError(
                "Use positive font/line sizes, at least six colors and nonempty line styles"
            )


def _inspection_title(metadata):
    parts = []
    for key, label, unit in (
        ("wavelength_um", "wavelength", " um"),
        ("temperature_k", "T", " K"),
        ("n", "n", ""),
        ("aspect_ratio", "asp", ""),
    ):
        value = metadata.get(key)
        if value is not None:
            parts.append(
                f"{label} = {value:g}{unit}"
                if isinstance(value, (int, float))
                else f"{label} = {value}{unit}"
            )
    return "Single-particle optics" + (" | " + ", ".join(parts) if parts else "")


def _plot_settings(style):
    return {
        "font.family": style.font_family,
        "font.size": style.font_size,
        "lines.linewidth": style.line_width,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.facecolor": "white",
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
    }


def _phase_figure(angles, curves, labels, *, style, title):
    """Shared six-panel native-phase display; missing elements remain empty."""
    import matplotlib.pyplot as plt
    import numpy as np

    with plt.rc_context(_plot_settings(style)):
        fig, axes = plt.subplots(
            *style.phase_layout, figsize=style.phase_figsize, layout="constrained", squeeze=False
        )
        elements = (
            ("p11", 1, "P11"),
            ("p12", -1, "-P12 / P11"),
            ("p22", 1, "P22 / P11"),
            ("p33", 1, "P33 / P11"),
            ("p44", 1, "P44 / P11"),
            ("p43", 1, "P43 / P11"),
        )
        for axis, (field, sign, label), letter in zip(axes.flat, elements, "abcdef"):
            for j, (curve, legend) in enumerate(zip(curves, labels)):
                if field not in curve or "p11" not in curve:
                    continue
                denominator = np.asarray(curve["p11"], dtype=float)
                numerator = sign * np.asarray(curve[field], dtype=float)
                y = (
                    np.where(numerator > 0, numerator, np.nan)
                    if field == "p11"
                    else np.divide(
                        numerator,
                        denominator,
                        out=np.full_like(numerator, np.nan),
                        where=denominator > 0,
                    )
                )
                axis.plot(
                    angles,
                    y,
                    color=style.colors[j % len(style.colors)],
                    ls=style.line_styles[j % len(style.line_styles)],
                    label=legend,
                )
            axis.set_xlim(0, 180)
            axis.set_xticks([0, 45, 90, 135, 180])
            axis.set_xlabel("Scattering angle (degree)")
            axis.set_ylabel(label)
            axis.set_title(f"({letter})", loc="left", fontweight="bold")
            axis.grid(True, alpha=style.grid_alpha)
            if field == "p11":
                axis.set_yscale("log")
            if axis.lines and field == "p11":
                axis.legend(fontsize=style.font_size * 0.8)
        fig.suptitle(title)
    return fig


@_registration_required
def plot_single_particle_optics(
    optics,
    *,
    output=None,
    phase_output=None,
    phase_radii_um=None,
    title=None,
    show=False,
    dpi=300,
    style=None,
):
    """Plot single-particle cross sections/efficiencies, SSA, g and phase ratios.

    optics is a loaded SingleParticleOptics. output/phase_output are optional
    PNG/PDF/SVG paths. Phase curves use nearest native sizes and label their
    actual radii, without size interpolation or phase renormalization.
    With no plot options, uses a standard four-panel size overview and six-panel
    phase overview. Missing scalar fields leave their panels empty; no scalar
    fields are derived. Optional OpticalPlotStyle controls fonts and arrangement.
    A report counts nonfinite/nonphysical values; log plots leave gaps at nonpositive
    samples. Returned figures remain open for customization/export by callers.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    from zju_scatt_interface.optics.models import SingleParticleOptics

    if not isinstance(optics, SingleParticleOptics):
        raise TypeError("Expected SingleParticleOptics; load a coordinate slice first")
    if phase_radii_um is not None and optics.size_unit != "um":
        raise ValueError("phase_radii_um requires physical radii in um")
    radii = np.asarray(optics.sizes, dtype=float)
    if (
        radii.ndim != 1
        or not len(radii)
        or not np.isfinite(radii).all()
        or np.any(radii <= 0)
        or np.any(np.diff(radii) <= 0)
    ):
        raise ValueError("Particle sizes must be finite, positive and strictly increasing")
    style = OpticalPlotStyle() if style is None else style
    if not isinstance(style, OpticalPlotStyle):
        raise TypeError("style must be an OpticalPlotStyle")
    colors = style.colors
    styles = style.line_styles
    report = {
        "size_count": len(radii),
        "size_range": [float(radii[0]), float(radii[-1])],
        "size_unit": optics.size_unit,
        "cross_section_unit": optics.cross_section_unit,
        "fields": {},
    }

    def values(field):
        data = getattr(optics, field)
        if data is None:
            return None
        array = np.asarray(data, dtype=float)
        if array.shape != radii.shape:
            raise ValueError(f"{field} does not match particle sizes")
        finite = array[np.isfinite(array)]
        report["fields"][field] = {
            "nonfinite": int(np.sum(~np.isfinite(array))),
            "negative": int(np.sum(array < 0)),
            "zero": int(np.sum(array == 0)),
            "minimum": float(finite.min()) if len(finite) else None,
            "maximum": float(finite.max()) if len(finite) else None,
        }
        return array

    fields = {
        key: values(key)
        for key in (
            "extinction_cross_section",
            "scattering_cross_section",
            "absorption_cross_section",
            "extinction_efficiency",
            "scattering_efficiency",
            "absorption_efficiency",
            "single_scattering_albedo",
            "asymmetry_factor",
        )
    }
    ext, sca, absorption = (
        fields[f"{name}_cross_section"] for name in ("extinction", "scattering", "absorption")
    )
    report["missing_fields"] = [key for key, value in fields.items() if value is None]
    report["ssa_source"] = (
        "loaded single_scattering_albedo"
        if fields["single_scattering_albedo"] is not None
        else None
    )
    closure = None
    if all(v is not None for v in (ext, sca, absorption)):
        closure = np.divide(
            ext - sca - absorption, ext, out=np.full_like(ext, np.nan), where=ext > 0
        )
        finite = closure[np.isfinite(closure)]
        report["maximum_relative_extinction_closure_error"] = (
            float(np.max(np.abs(finite))) if len(finite) else None
        )
    for field, low, high in (("single_scattering_albedo", 0, 1), ("asymmetry_factor", -1, 1)):
        array = fields[field]
        report[field + "_outside_physical_range"] = (
            int(np.sum((array < low) | (array > high))) if array is not None else None
        )
    phase = None
    indices = []
    if optics.phase_matrix is not None:
        phase = np.asarray(optics.phase_matrix, dtype=float)
        angles = np.asarray(optics.scattering_angles, dtype=float)
        if (
            angles.ndim != 1
            or len(angles) < 2
            or not np.isfinite(angles).all()
            or np.any(np.diff(angles) <= 0)
            or angles[0] != 0
            or angles[-1] != 180
            or phase.shape != (len(radii), len(angles), 4, 4)
        ):
            raise ValueError("Phase matrix must match size/angle grids spanning 0..180 degrees")
        targets = np.asarray(
            phase_radii_um
            if phase_radii_um is not None
            else np.geomspace(radii[0], radii[-1], 5)[1:-1],
            dtype=float,
        )
        if (
            targets.ndim != 1
            or not 1 <= len(targets) <= 6
            or not np.isfinite(targets).all()
            or np.any(targets < radii[0])
            or np.any(targets > radii[-1])
        ):
            raise ValueError("Choose 1..6 phase radii within the available size range")
        indices = list(dict.fromkeys(int(np.argmin(abs(np.log(radii / t)))) for t in targets))
        report["phase_nonfinite_values"] = int(np.sum(~np.isfinite(phase)))
        report["phase_requested_radii"] = targets.tolist()
        report["phase_angle_count"] = len(angles)
        report["phase_selection"] = []
        for i in indices:
            p11 = phase[i, :, 0, 0][::-1]
            mu = np.cos(np.deg2rad(angles))[::-1]
            half = float(np.sum(np.diff(mu) * (p11[1:] + p11[:-1]) / 4))
            report["phase_selection"].append(
                {
                    "index": i,
                    "actual_radius": float(radii[i]),
                    "P11_half_integral": half if np.isfinite(half) else None,
                }
            )
    elif phase_output is not None or phase_radii_um is not None:
        raise ValueError("Phase data were not loaded; use include_phase_matrix=True")
    settings = _plot_settings(style)
    with plt.rc_context(settings):
        fig, axes = plt.subplots(
            *style.scalar_layout, figsize=style.scalar_figsize, layout="constrained", squeeze=False
        )
        axes = axes.ravel()
        a = axes
        xlabel = (
            "Volume-equivalent radius"
            if optics.metadata.get("size_definition") == "volume_equivalent_sphere_radius"
            else "Particle size"
        ) + f" ({optics.size_unit})"
        for axis in a:
            axis.set_xscale("log")
            axis.set_xlabel(xlabel)
            axis.grid(True, alpha=style.grid_alpha)
            axis.set_xlim(radii[0] / 1.05, radii[-1] * 1.05)
        for i, (name, label) in enumerate(
            zip(("extinction", "scattering", "absorption"), ("Cext", "Csca", "Cabs"))
        ):
            array = fields[name + "_cross_section"]
            if array is not None:
                axes[0].plot(
                    radii,
                    np.where(array > 0, array, np.nan),
                    color=colors[i],
                    ls=styles[i % len(styles)],
                    label=label,
                )
        axes[0].set_yscale("log")
        axes[0].set_ylabel(f"Cross section ({optics.cross_section_unit})")
        if axes[0].lines:
            axes[0].legend()
        efficiencies = False
        for i, (name, label) in enumerate(
            zip(("extinction", "scattering", "absorption"), ("Qext", "Qsca", "Qabs"))
        ):
            array = fields[name + "_efficiency"]
            if array is not None:
                efficiencies = True
                axes[1].plot(radii, array, color=colors[i], ls=styles[i % len(styles)], label=label)
        axes[1].set_ylabel("Efficiency")
        if efficiencies:
            axes[1].legend()
        else:
            # An empty Matplotlib axis defaults to 0..1; do not imply a
            # physical efficiency bound when no efficiency data are available.
            axes[1].set_yticks([])
        for axis, field, label, low in (
            (axes[2], "single_scattering_albedo", "Single-scattering albedo", 0),
            (axes[3], "asymmetry_factor", "Asymmetry factor", -1),
        ):
            axis.set_ylim(low - 0.02, 1.02)
            array = fields[field]
            if array is not None:
                axis.plot(radii, array, color=colors[0])
                finite = array[np.isfinite(array)]
                axis.set_ylim(
                    min(low - 0.02, float(finite.min()) - 0.02) if len(finite) else low - 0.02,
                    max(1.02, float(finite.max()) + 0.02) if len(finite) else 1.02,
                )
            axis.set_ylabel(label)
        for label, axis in zip("abcd", axes):
            axis.set_title(f"({label})", loc="left", fontweight="bold")
        heading = title if title is not None else _inspection_title(optics.metadata)
        fig.suptitle(heading)
        phase_fig = None
        if phase is not None:
            elements = {
                "p11": (0, 0),
                "p12": (0, 1),
                "p22": (1, 1),
                "p33": (2, 2),
                "p44": (3, 3),
                "p43": (3, 2),
            }
            phase_fig = _phase_figure(
                angles,
                [
                    {name: phase[i, :, row, col] for name, (row, col) in elements.items()}
                    for i in indices
                ],
                [f"size = {radii[i]:.4g} {optics.size_unit}" for i in indices],
                style=style,
                title=heading + "\nNative phase elements (no renormalization)",
            )
        for figure, path in ((fig, output), (phase_fig, phase_output)):
            if figure is not None and path is not None:
                target = Path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                figure.savefig(target, dpi=dpi)
        if show:
            plt.show()
    return {"properties": fig, "phase": phase_fig, "inspection": report}


@_registration_required
def plot_single_scattering(
    source, *, output_dir=None, wavelength_um=None, coordinate_indices=None, show=False, style=None
):
    """Load and inspect an obtained file (or SingleParticleOptics) in one call.

    Save standard PNG/PDF/SVG figures, size-series CSV and inspection JSON.
    File inputs default to a sibling <filename>_plots directory; loaded objects
    default to ./single_scattering_plots. No retrieval or interpolation occurs.
    Extra native dimensions require explicit coordinate_indices; RI-grid files
    without wavelength metadata require wavelength_um. Returned ``files`` maps
    output names to paths. Figures are closed after saving unless show=True.
    Use plot_single_particle_optics for live figures and advanced plot options.
    """
    import csv
    import json

    import matplotlib.pyplot as plt

    from zju_scatt_interface.optics.models import SingleParticleOptics

    if isinstance(source, SingleParticleOptics):
        optics = source
        default_directory = Path.cwd() / "single_scattering_plots"
        if wavelength_um is not None or coordinate_indices is not None:
            raise ValueError("Loading options apply to file inputs only")
    else:
        from zju_scatt_interface.optics.loading import load_single

        path = Path(source)
        optics = load_single(
            path,
            include_phase_matrix=True,
            wavelength_um=wavelength_um,
            coordinate_indices=coordinate_indices,
        )
        default_directory = path.with_name(path.stem + "_plots")
    directory = Path(output_dir) if output_dir is not None else default_directory
    figures = plot_single_particle_optics(optics, style=style)
    files = {}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for name, stem in (("properties", "size_properties"), ("phase", "phase_matrix")):
            figure = figures[name]
            if figure is not None:
                for extension in ("png", "pdf", "svg"):
                    target = directory / f"{stem}.{extension}"
                    with plt.rc_context(
                        {"pdf.fonttype": 42, "svg.fonttype": "none", "savefig.facecolor": "white"}
                    ):
                        figure.savefig(target, dpi=300)
                    files[f"{name}_{extension}"] = target
        fields = (
            "extinction_cross_section",
            "scattering_cross_section",
            "absorption_cross_section",
            "single_scattering_albedo",
            "asymmetry_factor",
            "extinction_efficiency",
            "scattering_efficiency",
            "absorption_efficiency",
        )
        columns = [getattr(optics, key) for key in fields]
        files["csv"] = directory / "size_properties.csv"
        with files["csv"].open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    f"size_{optics.size_unit}",
                    *[f"C{name}_{optics.cross_section_unit}" for name in ("ext", "sca", "abs")],
                    "ssa",
                    "g",
                    "Qext",
                    "Qsca",
                    "Qabs",
                ]
            )
            writer.writerows(
                [size] + [column[i] if column is not None else "" for column in columns]
                for i, size in enumerate(optics.sizes)
            )
        report = {"loader_metadata": optics.metadata, **figures["inspection"]}
        files["report"] = directory / "inspection.json"
        files["report"].write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        if show:
            plt.show()
    finally:
        if not show:
            for name in ("properties", "phase"):
                if figures[name] is not None:
                    plt.close(figures[name])
    return {"output_dir": directory, "files": files, "inspection": report}
