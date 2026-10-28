"""Loading explicitly named scalar optical table columns."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

from zju_scatt_interface.errors import ScattError

BULK_COLUMN_ALIASES = {
    "size": (
        "size",
        "particle_size",
        "radius",
        "r",
        "diameter",
        "diam",
        "d",
    ),
    "number": (
        "number",
        "number_distribution",
        "number_density",
        "dndr",
        "dn_dr",
        "dndsize",
        "dn_dsize",
        "concentration",
        "number_concentration",
        "bin_number",
        "n",
    ),
    "extinction_cross_section": (
        "c_ext",
        "cext",
        "extinction_cross_section",
        "ext_cross_section",
        "cross_section_extinction",
    ),
    "scattering_cross_section": (
        "c_sca",
        "csca",
        "scattering_cross_section",
        "sca_cross_section",
        "cross_section_scattering",
    ),
    "absorption_cross_section": (
        "c_abs",
        "cabs",
        "absorption_cross_section",
        "abs_cross_section",
        "cross_section_absorption",
    ),
    "extinction_efficiency": ("q_ext", "qext", "extinction_efficiency"),
    "scattering_efficiency": ("q_sca", "qsca", "scattering_efficiency"),
    "absorption_efficiency": ("q_abs", "qabs", "absorption_efficiency"),
    "asymmetry_factor": ("g", "asymmetry_factor", "asymmetry", "asymmetry_parameter"),
}


def _normalize_table_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().casefold()).strip("_")


def _find_bulk_column(
    fieldnames: Sequence[str],
    aliases: Sequence[str],
    explicit: Optional[str],
    label: str,
    *,
    required: bool = False,
) -> Optional[str]:
    if explicit:
        if explicit in fieldnames:
            return explicit
        normalized_explicit = _normalize_table_column(explicit)
        for field in fieldnames:
            if _normalize_table_column(field) == normalized_explicit:
                return field
        raise ScattError(f"Column {explicit!r} for {label} was not found")
    normalized_aliases = {_normalize_table_column(alias) for alias in aliases}
    for field in fieldnames:
        if _normalize_table_column(field) in normalized_aliases:
            return field
    if required:
        raise ScattError(f"No {label} column found. Expected one of: {', '.join(aliases)}")
    return None


def _read_bulk_numeric_column(
    rows: Sequence[Mapping[str, str]],
    column: Optional[str],
    label: str,
    *,
    required: bool = False,
) -> Optional[list[float]]:
    from zju_scatt_interface.bulk.lowlevel import _finite_float

    if column is None:
        if required:
            raise ScattError(f"{label} column is required")
        return None
    values: list[float] = []
    for index, row in enumerate(rows, start=2):
        text = (row.get(column) or "").strip()
        if not text:
            raise ScattError(f"Missing {label} value in CSV row {index}")
        values.append(_finite_float(text, f"{label} in row {index}"))
    return values


def load_bulk_optics_table(
    path: Union[str, Path],
    *,
    size_column: Optional[str] = None,
    number_column: Optional[str] = None,
    extinction_column: Optional[str] = None,
    scattering_column: Optional[str] = None,
    absorption_column: Optional[str] = None,
    extinction_efficiency_column: Optional[str] = None,
    scattering_efficiency_column: Optional[str] = None,
    absorption_efficiency_column: Optional[str] = None,
    asymmetry_column: Optional[str] = None,
) -> tuple[dict[str, Optional[list[float]]], dict[str, Optional[str]]]:
    """Read a CSV table for ``integrate_bulk_optics``.

    The table must contain size and number-distribution columns. Optical
    columns are auto-detected from common aliases unless explicit names are
    supplied.
    """
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        raise ScattError(f"Could not read bulk input CSV {source}: {exc}") from exc
    if not fieldnames:
        raise ScattError("Bulk input CSV must have a header row")
    if not rows:
        raise ScattError("Bulk input CSV must contain at least one data row")

    columns = {
        "size": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["size"],
            size_column,
            "size",
            required=True,
        ),
        "number": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["number"],
            number_column,
            "number distribution",
            required=True,
        ),
        "extinction_cross_section": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["extinction_cross_section"],
            extinction_column,
            "extinction cross section",
        ),
        "scattering_cross_section": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["scattering_cross_section"],
            scattering_column,
            "scattering cross section",
        ),
        "absorption_cross_section": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["absorption_cross_section"],
            absorption_column,
            "absorption cross section",
        ),
        "extinction_efficiency": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["extinction_efficiency"],
            extinction_efficiency_column,
            "extinction efficiency",
        ),
        "scattering_efficiency": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["scattering_efficiency"],
            scattering_efficiency_column,
            "scattering efficiency",
        ),
        "absorption_efficiency": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["absorption_efficiency"],
            absorption_efficiency_column,
            "absorption efficiency",
        ),
        "asymmetry_factor": _find_bulk_column(
            fieldnames,
            BULK_COLUMN_ALIASES["asymmetry_factor"],
            asymmetry_column,
            "asymmetry factor",
        ),
    }
    table = {
        "sizes": _read_bulk_numeric_column(rows, columns["size"], "size", required=True),
        "number_distribution": _read_bulk_numeric_column(
            rows,
            columns["number"],
            "number distribution",
            required=True,
        ),
        "extinction_cross_section": _read_bulk_numeric_column(
            rows,
            columns["extinction_cross_section"],
            "extinction cross section",
        ),
        "scattering_cross_section": _read_bulk_numeric_column(
            rows,
            columns["scattering_cross_section"],
            "scattering cross section",
        ),
        "absorption_cross_section": _read_bulk_numeric_column(
            rows,
            columns["absorption_cross_section"],
            "absorption cross section",
        ),
        "extinction_efficiency": _read_bulk_numeric_column(
            rows,
            columns["extinction_efficiency"],
            "extinction efficiency",
        ),
        "scattering_efficiency": _read_bulk_numeric_column(
            rows,
            columns["scattering_efficiency"],
            "scattering efficiency",
        ),
        "absorption_efficiency": _read_bulk_numeric_column(
            rows,
            columns["absorption_efficiency"],
            "absorption efficiency",
        ),
        "asymmetry_factor": _read_bulk_numeric_column(
            rows,
            columns["asymmetry_factor"],
            "asymmetry factor",
        ),
    }
    return table, columns
