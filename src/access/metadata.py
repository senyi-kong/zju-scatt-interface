"""Scientific metadata extraction and particle-label matching."""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional

SIZE_METADATA_FIELDS = (
    "size",
    "size_parameter",
    "radius",
    "diameter",
    "effective_radius",
    "reff",
)


NUMBER_PATTERN = r"(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|nan)"


def finite_float(value: str) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize_scatt_label(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold())
    return normalized.strip("_")


def expand_string_list(values: Iterable[object]) -> list[str]:
    if isinstance(values, (str, bytes)):
        values = [values]
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            result.extend(expand_string_list(value))
            continue
        for part in str(value).split(","):
            cleaned = part.strip()
            if cleaned:
                result.append(cleaned)
    return result


def particle_type_matches(key: str, requested: str) -> bool:
    # Known registry aliases must identify one family: a dust request must not
    # accidentally include sea salt or ice merely because their names contain
    # "super_spheroid". Keep substring matching for arbitrary legacy labels.
    from zju_scatt_interface.access.catalog import relative_remote_key
    from zju_scatt_interface.config.particles import (
        get_particle_profile,
        list_particle_profiles,
    )

    try:
        profile = get_particle_profile(requested)
    except ValueError:
        profile = None
    if profile is not None:
        parts = set(relative_remote_key(key).replace("\\", "/").split("/"))
        if any(item.database_directory in parts for item in list_particle_profiles()):
            return profile.database_directory in parts
        requested = profile.particle_type
    request = normalize_scatt_label(requested)
    if not request:
        return False
    haystack = normalize_scatt_label(relative_remote_key(key))
    compact_request = request.replace("_", "")
    compact_haystack = haystack.replace("_", "")
    return request in haystack or compact_request in compact_haystack


def extract_scatt_metadata(filename: str) -> dict[str, float]:
    """Extract common numeric fields encoded in ZJU-SCATT file names.

    Wavelengths are exposed as ``wavelength_um`` after unit normalization.
    Refractive index uses the first and second values after ``ref`` as its
    real and imaginary components.
    """
    result: dict[str, float] = {}

    wavelength = re.search(
        rf"(?:^|_)wl_({NUMBER_PATTERN})(?:_(nm|um|mm|m))?(?=_|\.|$)",
        filename,
        re.I,
    )
    if wavelength:
        value = finite_float(wavelength.group(1))
        if value is not None:
            unit = (wavelength.group(2) or "um").lower()
            factors = {"nm": 1e-3, "um": 1.0, "mm": 1e3, "m": 1e6}
            result["wavelength"] = value
            result["wavelength_um"] = value * factors[unit]

    refractive = re.search(
        rf"(?:^|_)ref_({NUMBER_PATTERN})_({NUMBER_PATTERN})(?=_|\.|$)",
        filename,
        re.I,
    )
    if refractive:
        real = finite_float(refractive.group(1))
        imaginary = finite_float(refractive.group(2))
        if real is not None:
            result["ref_real"] = real
        if imaginary is not None:
            result["ref_imag"] = imaginary

    temperature = re.search(
        rf"(?:^|_)t_({NUMBER_PATTERN})k(?=_|\.|$)",
        filename,
        re.I,
    )
    if temperature:
        value = finite_float(temperature.group(1))
        if value is not None:
            result["temperature_k"] = value

    leading_size = re.search(rf"(?:^|_)L({NUMBER_PATTERN})(?=_)", filename, re.I)
    if leading_size:
        value = finite_float(leading_size.group(1))
        if value is not None:
            result["size_parameter"] = value
            result["size"] = value

    aliases = {
        "n": "n",
        "asp": "aspect_ratio",
        "ar": "aspect_ratio",
        "roundness": "roundness",
        "reff": "reff",
        "r_eff": "reff",
        "effective_radius": "effective_radius",
        "veff": "veff",
        "size": "size",
        "x": "size_parameter",
        "radius": "radius",
        "rad": "radius",
        "r": "radius",
        "diam": "diameter",
        "diameter": "diameter",
        "d": "diameter",
    }
    for token, field_name in aliases.items():
        match = re.search(
            rf"(?:^|_){re.escape(token)}_({NUMBER_PATTERN})(?=_|\.|$)",
            filename,
            re.I,
        )
        if match:
            value = finite_float(match.group(1))
            if value is not None:
                result[field_name] = value
    return result
