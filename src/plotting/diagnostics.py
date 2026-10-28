"""plotting / diagnostics domain implementation."""

from __future__ import annotations

import math
from pathlib import Path, PurePosixPath
from typing import Any, Optional, Sequence, Union

from zju_scatt_interface.errors import ScattError
from zju_scatt_interface.optics.models import BulkOptics

BULK_PLOT_FIELDS = {
    "extinction": ("extinction_coefficient", "Extinction"),
    "scattering": ("scattering_coefficient", "Scattering"),
    "absorption": ("absorption_coefficient", "Absorption"),
    "ssa": ("single_scattering_albedo", "Single-scattering albedo"),
    "single_scattering_albedo": (
        "single_scattering_albedo",
        "Single-scattering albedo",
    ),
    "g": ("asymmetry_factor", "Asymmetry factor g"),
    "asymmetry_factor": ("asymmetry_factor", "Asymmetry factor g"),
}


def _bulk_result_list(
    results: Union[BulkOptics, Sequence[BulkOptics]],
) -> list[BulkOptics]:
    from zju_scatt_interface.optics.models import BulkOptics

    if isinstance(results, BulkOptics):
        return [results]
    result_list = list(results)
    if not result_list:
        raise ScattError("At least one BulkOptics is required for plotting")
    for result in result_list:
        if not isinstance(result, BulkOptics):
            raise ScattError("plot_optical_properties expects BulkOptics values")
    return result_list


def _bulk_plot_labels(results: Sequence[BulkOptics]) -> list[str]:
    labels: list[str] = []
    for index, result in enumerate(results, start=1):
        metadata = result.metadata
        label = (
            metadata.get("particle_type")
            or metadata.get("label")
            or metadata.get("source_file")
            or f"case {index}"
        )
        labels.append(PurePosixPath(str(label)).name)
    return labels


def plot_optical_properties(
    results: Union[BulkOptics, Sequence[BulkOptics]],
    *,
    x: Optional[Sequence[Any]] = None,
    labels: Optional[Sequence[str]] = None,
    include: Sequence[str] = (
        "extinction",
        "scattering",
        "absorption",
        "ssa",
        "g",
    ),
    output: Optional[Union[str, Path]] = None,
    title: Optional[str] = None,
    x_label: Optional[str] = None,
    coefficient_label: str = "Bulk coefficient",
    show: bool = False,
    close: bool = False,
    dpi: int = 150,
) -> Any:
    """Plot bulk optical properties from one or more ZJU-SCATT calculations.

    Matplotlib is imported only when this function is called. Install
    ``matplotlib`` or the optional package extra before using plotting.
    """
    result_list = _bulk_result_list(results)
    field_specs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name in include:
        key = name.casefold()
        if key not in BULK_PLOT_FIELDS:
            raise ScattError(f"Unknown plot property {name!r}")
        attribute, label = BULK_PLOT_FIELDS[key]
        if attribute not in seen:
            field_specs.append((key, attribute, label))
            seen.add(attribute)
    if not field_specs:
        raise ScattError("At least one plot property must be requested")

    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ScattError(
            "Plotting requires matplotlib. Install it with "
            "`python -m pip install matplotlib` or `python -m pip install zju-scatt[plot]`."
        ) from exc

    if x is None:
        x_values = list(range(len(result_list)))
        tick_labels = list(labels) if labels is not None else _bulk_plot_labels(result_list)
        x_axis_label = x_label or "Case"
    else:
        x_values = list(x)
        if len(x_values) != len(result_list):
            raise ScattError("x must have the same length as results")
        tick_labels = list(labels) if labels is not None else None
        x_axis_label = x_label or "Value"
    if labels is not None and len(labels) != len(result_list):
        raise ScattError("labels must have the same length as results")
    if len(result_list) == 1 and x is None:
        tick_labels = None
        x_axis_label = x_label or "Optical property"

    coefficient_specs = [
        spec
        for spec in field_specs
        if spec[1]
        in {
            "extinction_coefficient",
            "scattering_coefficient",
            "absorption_coefficient",
        }
    ]
    dimensionless_specs = [
        spec for spec in field_specs if spec[1] in {"single_scattering_albedo", "asymmetry_factor"}
    ]
    panels: list[tuple[str, list[tuple[str, str, str]]]] = []
    if coefficient_specs:
        panels.append((coefficient_label, coefficient_specs))
    if dimensionless_specs:
        panels.append(("Dimensionless", dimensionless_specs))

    fig_height = 3.2 * len(panels)
    fig, axes = plt.subplots(len(panels), 1, figsize=(8.0, fig_height), squeeze=False)
    axes_list = [row[0] for row in axes]
    for axis, (ylabel, specs) in zip(axes_list, panels):
        for _key, attribute, label in specs:
            values = [
                getattr(result, attribute) if getattr(result, attribute) is not None else math.nan
                for result in result_list
            ]
            if len(result_list) == 1:
                axis.bar(label, values[0])
            else:
                axis.plot(x_values, values, marker="o", linewidth=1.8, label=label)
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.25)
        if len(result_list) > 1 and len(specs) > 1:
            axis.legend()
    axes_list[-1].set_xlabel(x_axis_label)
    if tick_labels is not None:
        axes_list[-1].set_xticks(x_values)
        axes_list[-1].set_xticklabels(tick_labels, rotation=30, ha="right")
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    if output is not None:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(target, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    if close:
        plt.close(fig)
    return fig


def plot_bulk_wavelength_series(
    results: Sequence[BulkOptics],
    *,
    output: Optional[Union[str, Path]] = None,
    phase_angle: float = 180.0,
    phase_row: int = 0,
    phase_column: int = 0,
    title: Optional[str] = None,
    show: bool = False,
    close: bool = False,
    dpi: int = 150,
) -> Any:
    """Plot absorption and a bulk phase-matrix element against wavelength."""
    from zju_scatt_interface.bulk.lowlevel import bulk_phase_matrix_element

    result_list = list(results)
    if not result_list:
        raise ScattError("At least one BulkOptics is required for plotting")
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ScattError(
            "Plotting requires matplotlib. Install it with "
            "`python -m pip install matplotlib` or `python -m pip install zju-scatt[plot]`."
        ) from exc

    rows: list[tuple[float, Optional[float], float, Optional[float]]] = []
    for result in result_list:
        wavelength = result.metadata.get("wavelength_um")
        if wavelength is None:
            raise ScattError("Each result must include metadata['wavelength_um']")
        p_value, matched_angle = bulk_phase_matrix_element(
            result,
            angle=phase_angle,
            row=phase_row,
            column=phase_column,
        )
        rows.append(
            (
                float(wavelength),
                result.absorption_coefficient,
                p_value,
                matched_angle,
            )
        )
    rows.sort(key=lambda item: item[0])
    wavelengths = [item[0] for item in rows]
    absorptions = [item[1] if item[1] is not None else math.nan for item in rows]
    phase_values = [item[2] for item in rows]
    matched_angles = [item[3] for item in rows if item[3] is not None]
    angle_label = (
        f"{sum(matched_angles) / len(matched_angles):.3g} deg"
        if matched_angles
        else f"{phase_angle:g} deg"
    )

    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.4), sharex=True)
    axes[0].plot(wavelengths, absorptions, marker="o", linewidth=1.8)
    axes[0].set_ylabel("Absorption coefficient")
    axes[0].grid(True, alpha=0.25)
    axes[1].plot(wavelengths, phase_values, marker="o", linewidth=1.8)
    axes[1].set_xlabel("Wavelength (um)")
    axes[1].set_ylabel(f"P{phase_row + 1}{phase_column + 1} ({angle_label})")
    axes[1].grid(True, alpha=0.25)
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    if output is not None:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(target, dpi=dpi, bbox_inches="tight")
    if show:
        plt.show()
    if close:
        plt.close(fig)
    return fig
