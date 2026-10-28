"""Scientific request normalization and Python/JSON/CLI input resolution."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.endpoints import (
    ROOT_PREFIX,
)
from zju_scatt_interface.errors import ScattError

DEFAULT_RETRIEVE_MANIFEST = Path("zju_scatt_retrieval_manifest.csv")


DEFAULT_OPERATION_LOG = Path("zju_scatt_operation.log")


API_DATA_DIR = Path("zju_scatt_data")


def _api_sequence(values: Optional[Union[str, Sequence[Any]]]) -> Optional[list[Any]]:
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        return [values]
    try:
        return list(values)
    except TypeError:
        return [values]


def _api_range(values: Optional[Sequence[Any]]) -> Optional[list[Any]]:
    if values is None:
        return None
    if len(values) != 2:
        raise ScattError("Range values must contain exactly two items")
    return [values[0], values[1]]


def _api_client(
    client: Optional[ApiClient],
    *,
    timeout: float,
    retries: int,
    insecure: bool,
    quiet: bool,
) -> ApiClient:
    from zju_scatt_interface.access.client import ApiClient

    return client or ApiClient(
        timeout=timeout,
        retries=retries,
        insecure=insecure,
        show_tls_warning=not quiet,
    )


def make_retrieval_args(
    *,
    sources: Optional[Union[str, Sequence[str]]] = None,
    manifest: Optional[Union[str, Path]] = None,
    particle_types: Optional[Union[str, Sequence[str]]] = None,
    wavelength_range: Optional[Sequence[Any]] = None,
    wavelength_unit: str = "um",
    target_wavelengths: Optional[Union[Any, Sequence[Any]]] = None,
    target_temperatures: Optional[Union[Any, Sequence[Any]]] = None,
    target_wavelength_mode: str = "interp",
    target_tolerance_um: float = 1e-9,
    refractive_index_parameters: Optional[Mapping[str, Mapping[str, Any]]] = None,
    apply_interpolation: bool = True,
    interpolation_output_dir: Optional[Union[str, Path]] = None,
    interpolation_include_phase_matrix: bool = False,
    ref_real_range: Optional[Sequence[Any]] = None,
    ref_real_targets: Optional[Union[Any, Sequence[Any]]] = None,
    ref_real_tolerance: float = 1e-9,
    ref_imag_range: Optional[Sequence[Any]] = None,
    ref_imag_targets: Optional[Union[Any, Sequence[Any]]] = None,
    ref_imag_tolerance: float = 1e-12,
    size_range: Optional[Sequence[Any]] = None,
    target_sizes: Optional[Union[Any, Sequence[Any]]] = None,
    target_size_tolerance: float = 1e-9,
    shapes: Optional[Union[Mapping[str, Any], list[Mapping[str, Any]]]] = None,
    contains: Optional[Union[str, Sequence[str]]] = None,
    exclude: Optional[Union[str, Sequence[str]]] = None,
    glob: Optional[Union[str, Sequence[str]]] = None,
    exclude_glob: Optional[Union[str, Sequence[str]]] = None,
    regex: Optional[Union[str, Sequence[str]]] = None,
    ignore_case: bool = True,
    extension: Optional[Union[str, Sequence[str]]] = ("nc",),
    min_file_size: Optional[Union[int, str]] = None,
    max_file_size: Optional[Union[int, str]] = None,
    modified_after: Optional[Union[str, datetime]] = None,
    modified_before: Optional[Union[str, datetime]] = None,
    max_scan: Optional[int] = None,
    quiet: bool = True,
    download: bool = False,
    output_dir: Optional[Union[str, Path]] = None,
    workers: int = 4,
    max_files: Optional[int] = None,
    max_bytes: Optional[Union[int, str]] = None,
    flat: bool = False,
    overwrite: bool = False,
    resume: bool = True,
    verify_etag: bool = False,
    ignore_space: bool = False,
    no_progress: bool = True,
    session: Optional[str] = None,
    no_track: bool = False,
    display_limit: int = 200,
    urls: bool = False,
    manifest_output: Optional[Union[str, Path]] = None,
    operation_log: Optional[Union[str, Path]] = None,
    manifest_format: Optional[str] = None,
) -> argparse.Namespace:
    """Build an internal retrieval namespace from script-friendly arguments."""
    from zju_scatt_interface.sources.shapes import compile_shapes

    compile_shapes(shapes)  # Validate before opening a client or scanning sources.
    return argparse.Namespace(
        api_mode=True,
        shapes=shapes,
        target_temperatures=target_temperatures,
        refractive_index_parameters=refractive_index_parameters,
        config=None,
        source=_api_sequence(sources) or [],
        manifest=Path(manifest) if manifest is not None else None,
        glob=_api_sequence(glob),
        exclude_glob=_api_sequence(exclude_glob),
        contains=_api_sequence(contains),
        exclude=_api_sequence(exclude),
        regex=_api_sequence(regex),
        ignore_case=ignore_case,
        extension=_api_sequence(extension),
        min_size=min_file_size,
        max_size=max_file_size,
        after=modified_after,
        before=modified_before,
        particle_type=_api_sequence(particle_types),
        wavelength=_api_range(wavelength_range),
        wavelength_range=_api_range(wavelength_range),
        wavelength_unit=wavelength_unit,
        size_range=_api_range(size_range),
        target_size=_api_sequence(target_sizes),
        target_size_tolerance=target_size_tolerance,
        ref_real=_api_range(ref_real_range),
        ref_real_target=_api_sequence(ref_real_targets),
        ref_real_target_tolerance=ref_real_tolerance,
        ref_imag=_api_range(ref_imag_range),
        ref_imag_target=_api_sequence(ref_imag_targets),
        ref_imag_target_tolerance=ref_imag_tolerance,
        n_range=None,
        aspect_ratio=None,
        param=None,
        shape_target=None,
        shape_target_tolerance=1e-9,
        value_regex=None,
        max_scan=max_scan,
        quiet=quiet,
        download=download,
        output_dir=Path(output_dir) if output_dir is not None else API_DATA_DIR,
        workers=workers,
        max_files=max_files,
        max_bytes=max_bytes,
        flat=flat,
        overwrite=overwrite,
        no_resume=not resume,
        verify_etag=verify_etag,
        ignore_space=ignore_space,
        dry_run=False,
        no_progress=no_progress,
        yes=True,
        display_limit=display_limit,
        urls=urls,
        session=session,
        no_track=no_track,
        target_wavelength=(
            _api_sequence(target_wavelengths) if target_wavelengths is not None else None
        ),
        target_wavelength_mode=target_wavelength_mode,
        target_tolerance=target_tolerance_um,
        apply_interpolation=apply_interpolation,
        interpolation_output_dir=(
            Path(interpolation_output_dir) if interpolation_output_dir is not None else None
        ),
        interpolation_include_phase_matrix=interpolation_include_phase_matrix,
        manifest_output=Path(manifest_output) if manifest_output is not None else None,
        format=manifest_format,
        operation_log=Path(operation_log) if operation_log is not None else None,
    )


def retrieve_config_template() -> dict:
    return {
        "_description": (
            "Example ZJU-SCATT retrieval request. Delete keys you do not need; "
            "null leaves that option unset."
        ),
        "sources": ["Single_opt/"],
        "particle_types": ["super_spheroid_ice"],
        "wavelength_unit": "um",
        "wavelength_range": {"start_um": 0.40, "end_um": 0.80},
        "target_wavelengths": [],
        "target_wavelength_mode": "interp",
        "target_tolerance_um": 1e-9,
        "refractive_index": {
            "real": {"min": 1.30, "max": 1.50, "targets": []},
            "imag": {"min": 0.0, "max": 1e-6, "targets": []},
        },
        "size_range": {"min": None, "max": None},
        "target_size": [],
        "shape": {
            "n": {"min": None, "max": None},
            "aspect_ratio": {"min": None, "max": None},
            "parameters": [{"name": "roundness", "min": None, "max": None}],
            "targets": [{"name": "roundness", "values": [], "tolerance": None}],
        },
        "extensions": ["nc"],
        "contains": [],
        "exclude": [],
        "glob": [],
        "exclude_glob": [],
        "regex": [],
        "ignore_case": True,
        "min_file_size": None,
        "max_file_size": None,
        "modified_after": None,
        "modified_before": None,
        "custom_parameters": [
            {"name": "reff", "min": None, "max": None},
            {"name": "veff", "min": None, "max": None},
        ],
        "manifest_output": "zju_scatt_retrieval_manifest.csv",
        "manifest_format": "csv",
        "operation_log": "zju_scatt_operation.log",
        "download": True,
        "output_dir": "zju_scatt_data",
        "workers": 4,
        "max_files": None,
        "max_bytes": None,
        "flat": False,
        "overwrite": False,
        "resume": True,
        "verify_etag": False,
        "ignore_space": False,
        "dry_run": False,
        "yes": False,
        "display_limit": 200,
        "urls": False,
        "session": None,
        "no_track": False,
        "max_scan": None,
        "quiet": False,
    }


def write_retrieve_config_template(path: Path, *, overwrite: bool = False) -> None:
    path = path.expanduser()
    if path.exists() and not overwrite:
        raise ScattError(f"Config template already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(retrieve_config_template(), stream, indent=2)
        stream.write("\n")


def load_retrieve_config(path: Optional[Path]) -> dict:
    if path is None:
        return {}
    path = path.expanduser()
    if not path.exists():
        raise ScattError(f"Retrieval config does not exist: {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ScattError(f"Invalid JSON retrieval config: {path}") from exc
    if not isinstance(data, dict):
        raise ScattError("Retrieval config must be a JSON object")
    return data


def config_get(config: dict, *keys: str) -> object:
    for key in keys:
        current: object = config
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current is not None:
            return current
    return None


def parse_optional_float(value: object, label: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ScattError(f"{label} must be a number") from exc
    if not math.isfinite(result):
        raise ScattError(f"{label} must be finite")
    return result


def normalize_wavelength_unit(value: object) -> str:
    if value is None or value == "":
        return "um"
    cleaned = (
        str(value)
        .strip()
        .casefold()
        .replace("\u00b5", "u")
        .replace("\u03bc", "u")
        .replace("\u207b", "-")
        .replace("\u00b9", "1")
        .replace(" ", "")
    )
    aliases = {
        "um": "um",
        "micron": "um",
        "microns": "um",
        "micrometer": "um",
        "micrometers": "um",
        "micrometre": "um",
        "micrometres": "um",
        "nm": "nm",
        "nanometer": "nm",
        "nanometers": "nm",
        "nanometre": "nm",
        "nanometres": "nm",
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "millimetre": "mm",
        "millimetres": "mm",
        "m": "m",
        "meter": "m",
        "meters": "m",
        "metre": "m",
        "metres": "m",
        "cm-1": "cm-1",
        "cm^-1": "cm-1",
        "1/cm": "cm-1",
        "wavenumber": "cm-1",
        "wavenumbers": "cm-1",
    }
    try:
        return aliases[cleaned]
    except KeyError as exc:
        raise ScattError("Unsupported wavelength unit. Use um, nm, mm, m, or cm-1.") from exc


def wavelength_value_to_um(value: float, unit: str, label: str) -> float:
    if not math.isfinite(value):
        raise ScattError(f"{label} must be finite")
    if value <= 0:
        raise ScattError(f"{label} must be positive")
    unit = normalize_wavelength_unit(unit)
    factors = {"nm": 1e-3, "um": 1.0, "mm": 1e3, "m": 1e6}
    if unit == "cm-1":
        return 10000.0 / value
    return value * factors[unit]


def wavelength_range_values_to_um(
    values: Sequence[object], unit: object, label: str
) -> list[float]:
    if len(values) != 2:
        raise ScattError(f"{label} needs exactly two values")
    normalized_unit = normalize_wavelength_unit(unit)
    converted = [
        parse_wavelength_quantity(values[0], normalized_unit, f"{label} minimum"),
        parse_wavelength_quantity(values[1], normalized_unit, f"{label} maximum"),
    ]
    minimum, maximum = min(converted), max(converted)
    epsilon = max(abs(minimum), abs(maximum), 1.0) * 1e-9
    return [minimum - epsilon, maximum + epsilon]


def parse_wavelength_quantity(value: object, default_unit: str, label: str) -> float:
    from zju_scatt_interface.access.metadata import NUMBER_PATTERN

    if isinstance(value, (int, float)):
        return wavelength_value_to_um(float(value), default_unit, label)
    text = str(value).strip()
    match = re.fullmatch(
        rf"({NUMBER_PATTERN})\s*([A-Za-z/\^\-0-9\u00b5\u03bc\u207b\u00b9]+)?",
        text,
    )
    if not match:
        raise ScattError(f"{label} must be a wavelength value, e.g. 0.55 or 10000cm-1")
    unit = match.group(2) or default_unit
    numeric = parse_optional_float(match.group(1), label)
    if numeric is None:
        raise ScattError(f"{label} must be a number")
    return wavelength_value_to_um(numeric, unit, label)


def parse_float_targets(values: object, label: str) -> Optional[list[float]]:
    if values is None or values == "":
        return None
    if isinstance(values, (str, bytes)):
        raw_values = [part for part in re.split(r"[\s,]+", str(values).strip()) if part]
    elif isinstance(values, (list, tuple)):
        raw_values = list(values)
    else:
        raw_values = [values]
    result = [
        parse_optional_float(value, f"{label}[{index}]")
        for index, value in enumerate(raw_values, 1)
    ]
    return [value for value in result if value is not None]


def parse_range_config(value: object, label: str) -> Optional[list[float]]:
    from zju_scatt_interface.access.filters import validate_range

    if value is None or value == "":
        return None
    if isinstance(value, dict):
        minimum = config_get(
            value,
            "min",
            "minimum",
            "start",
            "start_um",
            "lower",
        )
        maximum = config_get(
            value,
            "max",
            "maximum",
            "end",
            "end_um",
            "upper",
        )
        if minimum is None and maximum is None:
            return None
        if minimum is None or maximum is None:
            raise ScattError(f"{label} needs both minimum and maximum")
        result = [
            parse_optional_float(minimum, f"{label} minimum"),
            parse_optional_float(maximum, f"{label} maximum"),
        ]
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        result = [
            parse_optional_float(value[0], f"{label} minimum"),
            parse_optional_float(value[1], f"{label} maximum"),
        ]
    elif isinstance(value, str):
        parts = [part for part in re.split(r"[\s,:]+", value.strip()) if part]
        if len(parts) != 2:
            raise ScattError(f"{label} range must contain two numbers")
        result = [
            parse_optional_float(parts[0], f"{label} minimum"),
            parse_optional_float(parts[1], f"{label} maximum"),
        ]
    else:
        raise ScattError(f"{label} range must be an object, list, or string")
    if result[0] is None or result[1] is None:
        return None
    validate_range(result[0], result[1], label)
    return [result[0], result[1]]


def parse_size_config(value: object, label: str) -> Optional[int]:
    from zju_scatt_interface.access.filters import parse_size

    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        result = int(value)
        if result < 0:
            raise ScattError(f"{label} cannot be negative")
        return result
    return parse_size(str(value))


def parse_bool_config(value: object, label: str) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    raise ScattError(f"{label} must be true or false")


def cli_or_config(args: argparse.Namespace, config: dict, attr: str, *keys: str, default=None):
    value = getattr(args, attr, None)
    if value is not None:
        return value
    configured = config_get(config, *keys)
    return default if configured is None else configured


def configured_custom_parameters(args: argparse.Namespace, config: dict) -> list[list[str]]:
    values = getattr(args, "param", None)
    if values is not None:
        return values
    configured = config_get(
        config,
        "custom_parameters",
        "parameters",
        "param",
        "shape.parameters",
        "shape.params",
    )
    if configured is None:
        return []
    result: list[list[str]] = []
    if not isinstance(configured, list):
        raise ScattError("custom_parameters must be a list")
    for item in configured:
        if not isinstance(item, dict):
            raise ScattError("Each custom parameter must be an object")
        name = item.get("name")
        range_values = parse_range_config(item, f"custom parameter {name or ''}".strip())
        if not name or range_values is None:
            continue
        result.append([str(name), str(range_values[0]), str(range_values[1])])
    return result


def normalize_shape_targets(value: object) -> list[tuple[str, list[float], Optional[float]]]:
    if value is None or value == "":
        return []
    items = value if isinstance(value, list) else [value]
    result: list[tuple[str, list[float], Optional[float]]] = []
    for item in items:
        tolerance: Optional[float] = None
        if isinstance(item, dict):
            name = item.get("name")
            raw_values = config_get(item, "values", "value", "target", "targets")
            tolerance = parse_optional_float(item.get("tolerance"), "shape_target_tolerance")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name = item[0]
            raw_values = list(item[1:])
        else:
            raise ScattError("Shape targets must be NAME VALUE... or objects with name/values")
        if not name:
            raise ScattError("Shape target requires a parameter name")
        targets = parse_float_targets(raw_values, f"shape_target {name}") or []
        if not targets:
            continue
        result.append((str(name), targets, tolerance))
    return result


def wavelength_range_from_config_or_cli(
    args: argparse.Namespace, config: dict
) -> Optional[list[float]]:
    cli_target = getattr(args, "target_wavelength", None)
    cli_range = getattr(args, "wavelength_range", None)
    if cli_range is None:
        cli_range = getattr(args, "wavelength", None)
    if cli_target is not None:
        return None
    if cli_range is not None:
        return list(map(float, cli_range))

    configured_target = config_get(
        config,
        "target_wavelengths",
        "target_wavelength",
        "target_wavelength_um",
    )
    if configured_target is not None:
        return None
    configured_range = parse_range_config(
        config_get(config, "wavelength_range", "wavelength"),
        "wavelength_range",
    )
    if configured_range is not None:
        return configured_range
    return None


def configured_target_wavelength_values(config: dict) -> object:
    configured = config_get(
        config,
        "target_wavelengths",
        "target_wavelength",
        "target_wavelength_um",
    )
    if isinstance(configured, dict):
        return config_get(configured, "values", "value", "wavelengths", "wavelength")
    return configured


def configured_target_wavelength_mode(args: argparse.Namespace, config: dict) -> str:
    from zju_scatt_interface.sources.coordinates import normalize_target_wavelength_mode

    configured_target = config_get(
        config,
        "target_wavelength",
        "target_wavelengths",
        "target_wavelength_um",
    )
    nested_mode = configured_target.get("mode") if isinstance(configured_target, dict) else None
    value = cli_or_config(
        args,
        config,
        "target_wavelength_mode",
        "target_wavelength_mode",
        "target_wavelength.mode",
        "target_wavelengths.mode",
        "target_interpolation",
        default=nested_mode or "interp",
    )
    return normalize_target_wavelength_mode(value)


def configured_wavelength_unit(args: argparse.Namespace, config: dict) -> str:
    value = cli_or_config(
        args,
        config,
        "wavelength_unit",
        "wavelength_unit",
        default="um",
    )
    return normalize_wavelength_unit(value)


def parse_target_wavelengths(
    args: argparse.Namespace, config: dict, wavelength_unit: str
) -> Optional[list[float]]:
    raw_values = getattr(args, "target_wavelength", None)
    if raw_values is None:
        raw_values = configured_target_wavelength_values(config)
    if raw_values is None or raw_values == "":
        return None
    if isinstance(raw_values, dict):
        raw_values = config_get(raw_values, "values", "value", "wavelengths", "wavelength")
    if raw_values is None or raw_values == "":
        return None
    if isinstance(raw_values, (str, bytes)):
        text = str(raw_values).strip()
        try:
            return [parse_wavelength_quantity(text, wavelength_unit, "target_wavelength[1]")]
        except ScattError:
            values = [part for part in re.split(r"[\s,]+", text) if part]
    elif isinstance(raw_values, (list, tuple)):
        values = list(raw_values)
    else:
        values = [raw_values]
    targets = [
        parse_wavelength_quantity(value, wavelength_unit, f"target_wavelength[{index}]")
        for index, value in enumerate(values, 1)
    ]
    return targets


def build_retrieve_runtime_args(args: argparse.Namespace) -> tuple[argparse.Namespace, dict]:
    from zju_scatt_interface.access.metadata import expand_string_list
    from zju_scatt_interface.errors import ScattError
    from zju_scatt_interface.sources.coordinates import normalize_target_wavelengths

    config = load_retrieve_config(getattr(args, "config", None))
    wavelength_unit = configured_wavelength_unit(args, config)
    target_wavelength_mode = configured_target_wavelength_mode(args, config)
    wavelength = wavelength_range_from_config_or_cli(args, config)
    target = parse_target_wavelengths(args, config, wavelength_unit)
    target = normalize_target_wavelengths(target)
    if target and wavelength is not None:
        raise ScattError("Use either --wavelength-range or --target-wavelength, not both")
    default_manifest_output = (
        None if getattr(args, "api_mode", False) else DEFAULT_RETRIEVE_MANIFEST
    )
    default_operation_log = None if getattr(args, "api_mode", False) else DEFAULT_OPERATION_LOG

    sources = getattr(args, "source", None)
    if sources:
        source_values = list(sources)
    else:
        source_values = expand_string_list([config_get(config, "sources", "source") or ROOT_PREFIX])
    if not source_values:
        source_values = [ROOT_PREFIX]

    extensions = getattr(args, "extension", None)
    if extensions is None:
        extensions = expand_string_list([config_get(config, "extensions", "extension") or "nc"])

    ignore_case = cli_or_config(args, config, "ignore_case", "ignore_case", default=False)
    no_progress = cli_or_config(args, config, "no_progress", "no_progress", default=False)
    no_track = cli_or_config(args, config, "no_track", "no_track", default=False)
    quiet = cli_or_config(args, config, "quiet", "quiet", default=False)
    dry_run = cli_or_config(args, config, "dry_run", "dry_run", default=False)
    yes = cli_or_config(args, config, "yes", "yes", default=False)
    flat = cli_or_config(args, config, "flat", "flat", default=False)
    overwrite = cli_or_config(args, config, "overwrite", "overwrite", default=False)
    verify_etag = cli_or_config(args, config, "verify_etag", "verify_etag", default=False)
    ignore_space = cli_or_config(args, config, "ignore_space", "ignore_space", default=False)
    if getattr(args, "no_resume", None):
        resume = False
    else:
        resume = cli_or_config(args, config, "resume", "resume", default=True)
    download_enabled = cli_or_config(args, config, "download", "download", default=True)
    manifest_value = cli_or_config(
        args,
        config,
        "manifest",
        "manifest",
        "manifest_input",
        default=None,
    )
    manifest_path = Path(manifest_value).expanduser() if manifest_value is not None else None

    runtime = argparse.Namespace(
        command="retrieve",
        source=source_values,
        manifest=manifest_path,
        glob=cli_or_config(args, config, "glob", "glob", default=None),
        exclude_glob=cli_or_config(args, config, "exclude_glob", "exclude_glob", default=None),
        contains=cli_or_config(args, config, "contains", "contains", default=None),
        exclude=cli_or_config(args, config, "exclude", "exclude", default=None),
        regex=cli_or_config(args, config, "regex", "regex", default=None),
        ignore_case=bool(parse_bool_config(ignore_case, "ignore_case")),
        extension=extensions,
        min_size=parse_size_config(
            cli_or_config(args, config, "min_size", "min_file_size", "min_size"),
            "min_file_size",
        ),
        max_size=parse_size_config(
            cli_or_config(args, config, "max_size", "max_file_size", "max_size"),
            "max_file_size",
        ),
        after=parse_config_date(
            cli_or_config(args, config, "after", "modified_after", "after"),
            "modified_after",
        ),
        before=parse_config_date(
            cli_or_config(args, config, "before", "modified_before", "before"),
            "modified_before",
        ),
        wavelength=wavelength,
        wavelength_unit=wavelength_unit,
        ref_real=parse_range_config(
            cli_or_config(args, config, "ref_real", "refractive_index.real", "ref_real"),
            "ref_real",
        ),
        ref_real_target=parse_float_targets(
            cli_or_config(
                args,
                config,
                "ref_real_target",
                "refractive_index.real.target",
                "refractive_index.real.targets",
                "ref_real_target",
            ),
            "ref_real_target",
        ),
        ref_real_target_tolerance=parse_optional_float(
            cli_or_config(
                args,
                config,
                "ref_real_target_tolerance",
                "refractive_index.real.tolerance",
                default=1e-9,
            ),
            "ref_real_target_tolerance",
        ),
        ref_imag=parse_range_config(
            cli_or_config(args, config, "ref_imag", "refractive_index.imag", "ref_imag"),
            "ref_imag",
        ),
        ref_imag_target=parse_float_targets(
            cli_or_config(
                args,
                config,
                "ref_imag_target",
                "refractive_index.imag.target",
                "refractive_index.imag.targets",
                "ref_imag_target",
            ),
            "ref_imag_target",
        ),
        ref_imag_target_tolerance=parse_optional_float(
            cli_or_config(
                args,
                config,
                "ref_imag_target_tolerance",
                "refractive_index.imag.tolerance",
                default=1e-12,
            ),
            "ref_imag_target_tolerance",
        ),
        n_range=parse_range_config(
            cli_or_config(args, config, "n_range", "shape.n", "n_range"),
            "n_range",
        ),
        aspect_ratio=parse_range_config(
            cli_or_config(args, config, "aspect_ratio", "shape.aspect_ratio", "aspect_ratio"),
            "aspect_ratio",
        ),
        size_range=parse_range_config(
            cli_or_config(args, config, "size_range", "size_range"),
            "size_range",
        ),
        target_size=parse_float_targets(
            cli_or_config(
                args,
                config,
                "target_size",
                "target_size",
                "size_target",
            ),
            "target_size",
        ),
        target_size_tolerance=parse_optional_float(
            cli_or_config(
                args,
                config,
                "target_size_tolerance",
                "size_tolerance",
                default=1e-9,
            ),
            "target_size_tolerance",
        ),
        shape_targets=normalize_shape_targets(
            cli_or_config(
                args,
                config,
                "shape_target",
                "shape.targets",
                "shape_target",
                default=None,
            )
        ),
        shape_target_tolerance=parse_optional_float(
            cli_or_config(
                args,
                config,
                "shape_target_tolerance",
                "shape.target_tolerance",
                default=1e-9,
            ),
            "shape_target_tolerance",
        ),
        particle_type=cli_or_config(
            args,
            config,
            "particle_type",
            "particle_types",
            "particle_type",
            default=None,
        ),
        param=configured_custom_parameters(args, config),
        shapes=cli_or_config(args, config, "shapes", "shapes"),
        value_regex=cli_or_config(args, config, "value_regex", "value_regex", default=None),
        max_scan=optional_int(
            cli_or_config(args, config, "max_scan", "max_scan", default=None),
            "max_scan",
        ),
        quiet=bool(parse_bool_config(quiet, "quiet")),
        output_dir=Path(
            cli_or_config(args, config, "output_dir", "output_dir", default="zju_scatt_data")
        ),
        workers=int(cli_or_config(args, config, "workers", "workers", default=4)),
        max_files=optional_int(
            cli_or_config(args, config, "max_files", "max_files"),
            "max_files",
        ),
        max_bytes=parse_size_config(
            cli_or_config(args, config, "max_bytes", "max_bytes"),
            "max_bytes",
        ),
        flat=bool(parse_bool_config(flat, "flat")),
        overwrite=bool(parse_bool_config(overwrite, "overwrite")),
        no_resume=not bool(parse_bool_config(resume, "resume")),
        verify_etag=bool(parse_bool_config(verify_etag, "verify_etag")),
        ignore_space=bool(parse_bool_config(ignore_space, "ignore_space")),
        dry_run=bool(parse_bool_config(dry_run, "dry_run")),
        no_progress=bool(parse_bool_config(no_progress, "no_progress")),
        yes=bool(parse_bool_config(yes, "yes")),
        display_limit=int(
            cli_or_config(args, config, "display_limit", "display_limit", default=200)
        ),
        urls=bool(
            parse_bool_config(cli_or_config(args, config, "urls", "urls", default=False), "urls")
        ),
        session=cli_or_config(args, config, "session", "session", default=None),
        no_track=bool(parse_bool_config(no_track, "no_track")),
        target_wavelengths=target or [],
        target_wavelength_mode=target_wavelength_mode,
        target_tolerance=parse_optional_float(
            cli_or_config(
                args,
                config,
                "target_tolerance",
                "target_tolerance_um",
                "target_tolerance",
                default=1e-9,
            ),
            "target_tolerance_um",
        ),
        apply_interpolation=bool(
            parse_bool_config(
                cli_or_config(
                    args, config, "apply_interpolation", "apply_interpolation", default=True
                ),
                "apply_interpolation",
            )
        ),
        interpolation_include_phase_matrix=bool(
            parse_bool_config(
                cli_or_config(
                    args,
                    config,
                    "interpolation_include_phase_matrix",
                    "interpolation_include_phase_matrix",
                    default=False,
                ),
                "interpolation_include_phase_matrix",
            )
        ),
        interpolation_output_dir=(
            Path(
                cli_or_config(args, config, "interpolation_output_dir", "interpolation_output_dir")
            )
            if cli_or_config(args, config, "interpolation_output_dir", "interpolation_output_dir")
            is not None
            else None
        ),
        refractive_index_parameters=cli_or_config(
            args, config, "refractive_index_parameters", "refractive_index_parameters"
        ),
        target_temperatures=cli_or_config(
            args, config, "target_temperatures", "ice.target_temperatures"
        ),
        download=bool(parse_bool_config(download_enabled, "download")),
        manifest_output=Path(
            cli_or_config(
                args,
                config,
                "manifest_output",
                "manifest_output",
                default=default_manifest_output,
            )
        )
        if cli_or_config(
            args,
            config,
            "manifest_output",
            "manifest_output",
            default=default_manifest_output,
        )
        is not None
        else None,
        format=cli_or_config(args, config, "format", "manifest_format", "format", default=None),
        operation_log=Path(
            cli_or_config(
                args,
                config,
                "operation_log",
                "operation_log",
                default=default_operation_log,
            )
        )
        if cli_or_config(
            args,
            config,
            "operation_log",
            "operation_log",
            default=default_operation_log,
        )
        is not None
        else None,
    )
    return runtime, config


def optional_int(value: object, label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ScattError(f"{label} must be an integer") from exc
    if result < 0:
        raise ScattError(f"{label} cannot be negative")
    return result


def parse_config_date(value: object, label: str) -> Optional[datetime]:
    from zju_scatt_interface.access.filters import parse_date_argument

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return parse_date_argument(str(value))
    except argparse.ArgumentTypeError as exc:
        raise ScattError(f"Invalid {label}: {value}") from exc
