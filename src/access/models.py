"""Typed catalog, selection, transfer and retrieval records."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Optional, Union


@dataclass(frozen=True)
class RemoteObject:
    """Metadata returned by the OSS listing API."""

    key: str
    size: int = 0
    last_modified: str = ""
    etag: str = ""

    @property
    def name(self) -> str:
        return PurePosixPath(self.key).name

    @property
    def url(self) -> str:
        from zju_scatt_interface.access.catalog import object_url

        return object_url(self.key)


@dataclass(frozen=True)
class RemoteDirectory:
    """A virtual directory represented by an OSS common prefix."""

    key: str

    @property
    def name(self) -> str:
        return PurePosixPath(self.key.rstrip("/")).name


@dataclass(frozen=True)
class ListPage:
    objects: tuple[RemoteObject, ...]
    directories: tuple[RemoteDirectory, ...]
    truncated: bool
    next_marker: str


@dataclass
class ScanStats:
    pages: int = 0
    scanned: int = 0
    matched: int = 0
    bytes: int = 0


@dataclass(frozen=True)
class NumericConstraint:
    name: str
    minimum: float
    maximum: float


@dataclass(frozen=True)
class NumericTargetConstraint:
    name: str
    targets: tuple[float, ...]
    tolerance: float


@dataclass(frozen=True)
class AnyNumericConstraint:
    label: str
    names: tuple[str, ...]
    minimum: float
    maximum: float


@dataclass(frozen=True)
class AnyNumericTargetConstraint:
    label: str
    names: tuple[str, ...]
    targets: tuple[float, ...]
    tolerance: float


@dataclass(frozen=True)
class RegexConstraint:
    pattern: str
    minimum: float
    maximum: float


@dataclass(frozen=True)
class WavelengthProcessing:
    target_um: Optional[float] = None
    target_wavelengths_um: tuple[float, ...] = ()
    selected_wavelengths_um: tuple[float, ...] = ()
    target_refractive_points: tuple[tuple[float, float], ...] = ()
    selected_refractive_points: tuple[tuple[float, float], ...] = ()
    selection_mode: str = "interp"
    interpolation_required: bool = False
    interpolation_applied: bool = False
    interpolation_basis: str = "none"
    message: str = "No target wavelength interpolation requested."
    refractive_index_resolutions: tuple[dict, ...] = ()
    target_temperatures_k: tuple[float, ...] = ()


@dataclass(frozen=True)
class NumericSelectionProcessing:
    label: str
    target_values: tuple[float, ...] = ()
    selected_values: tuple[float, ...] = ()
    interpolation_required: bool = False
    interpolation_applied: bool = False
    interpolation_basis: str = "none"
    message: str = "No target value requested."


@dataclass(frozen=True)
class DownloadResult:
    obj: RemoteObject
    target: Path
    status: str
    message: str = ""


@dataclass
class RetrievalResult:
    """Result returned by the Python API retrieval helpers."""

    objects: list[RemoteObject]
    stats: ScanStats
    wavelength_processing: WavelengthProcessing
    target_processings: list[NumericSelectionProcessing] = field(default_factory=list)
    manifest_path: Optional[Path] = None
    operation_log_path: Optional[Path] = None
    download_results: list[DownloadResult] = field(default_factory=list)
    interpolated_products: list[Any] = field(default_factory=list)
    status_code: int = 0

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.objects)

    def write_manifest(self, path: Union[str, Path], format_name: Optional[str] = None) -> Path:
        from zju_scatt_interface.access.manifests import write_manifest

        target = Path(path)
        write_manifest(self.objects, target, format_name)
        self.manifest_path = target
        return target

    def raise_for_status(self, *, download=False, require_matches=False, require_products=False):
        """Validate completion centrally; permitted boundary NaNs are not failures."""
        from zju_scatt_interface.access.workflow import validate_retrieval_result

        validate_retrieval_result(
            self,
            download=download,
            require_matches=require_matches,
            require_products=require_products,
        )
        return self

    def to_dict(self):
        """Return the standard JSON-compatible source/product/processing report."""
        from zju_scatt_interface.access.workflow import retrieval_result_dict

        return retrieval_result_dict(self)

    def write_report(self, path):
        from zju_scatt_interface.access.workflow import _write_json

        return _write_json(path, self.to_dict())
