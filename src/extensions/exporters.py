"""Named application exporters using shared canonical scientific products."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from zju_scatt_interface.access.registration import registration_required
from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry


@dataclass(frozen=True)
class Exporter:
    """write(data, destination, **options), and optional validate(path, **options)."""

    write: Callable
    validate: Callable | None = None


_exporters = NamedRegistry[Exporter]("application exporter")
_loaded = False
_lock = RLock()


def _ensure_builtins():
    global _loaded
    with _lock:
        if not _loaded:
            from zju_scatt_interface.io.applications.arts.bulk import (
                validate_arts_bulk_table,
                write_arts_bulk_tables,
            )
            from zju_scatt_interface.io.applications.crtm.ir import (
                validate_crtm_ir_optical_table,
                write_crtm_ir_bulk_tables,
            )
            from zju_scatt_interface.io.applications.rttov.v13 import write_rttov13_bulk_tables
            from zju_scatt_interface.io.applications.rttov.v14 import (
                validate_rttov14_optical_table,
                write_rttov14_bulk_tables,
            )

            for name, writer, validator in (
                ("arts", write_arts_bulk_tables, validate_arts_bulk_table),
                ("crtm_ir", write_crtm_ir_bulk_tables, validate_crtm_ir_optical_table),
                ("rttov13", write_rttov13_bulk_tables, None),
                ("rttov14", write_rttov14_bulk_tables, validate_rttov14_optical_table),
            ):
                _exporters.register(name, Exporter(writer, validator))
            _loaded = True


def register_exporter(name, exporter: Exporter, *, aliases=()):
    _ensure_builtins()
    if not isinstance(exporter, Exporter) or not callable(exporter.write):
        raise ExtensionError("Exporter.write must be callable")
    if exporter.validate is not None and not callable(exporter.validate):
        raise ExtensionError("Exporter.validate must be callable")
    return _exporters.register(name, exporter, aliases=aliases)


@registration_required
def export(application, data, destination, **options):
    _ensure_builtins()
    return _exporters.get(application).write(data, destination, **options)


@registration_required
def validate_export(application, path, **options):
    _ensure_builtins()
    validator = _exporters.get(application).validate
    if validator is None:
        raise ExtensionError(f"No validator registered for {application!r}")
    return validator(path, **options)
