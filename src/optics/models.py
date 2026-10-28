"""optics / models domain implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union


@dataclass
class BulkOptics:
    """Size-distribution-integrated optical properties."""

    extinction_coefficient: Optional[float]
    scattering_coefficient: Optional[float]
    absorption_coefficient: Optional[float]
    single_scattering_albedo: Optional[float]
    asymmetry_factor: Optional[float]
    phase_matrix: Optional[Any] = None
    number_concentration: float = 0.0
    size_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "extinction_coefficient": self.extinction_coefficient,
            "scattering_coefficient": self.scattering_coefficient,
            "absorption_coefficient": self.absorption_coefficient,
            "single_scattering_albedo": self.single_scattering_albedo,
            "asymmetry_factor": self.asymmetry_factor,
            "phase_matrix": self.phase_matrix,
            "number_concentration": self.number_concentration,
            "size_count": self.size_count,
            "metadata": dict(self.metadata),
        }

    def write_json(
        self,
        path: Union[str, Path],
        *,
        indent: Optional[int] = 2,
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=indent) + "\n",
            encoding="utf-8",
        )
        return target


@dataclass
class SingleParticleOptics:
    """Single-particle optical arrays loaded from a ZJU-SCATT L1 file."""

    sizes: list[float]
    extinction_cross_section: Optional[list[float]] = None
    scattering_cross_section: Optional[list[float]] = None
    absorption_cross_section: Optional[list[float]] = None
    extinction_efficiency: Optional[list[float]] = None
    scattering_efficiency: Optional[list[float]] = None
    absorption_efficiency: Optional[list[float]] = None
    asymmetry_factor: Optional[list[float]] = None
    phase_matrix: Optional[Any] = None
    scattering_angles: Optional[list[float]] = None
    size_unit: str = "unknown"
    cross_section_unit: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    projected_area: Optional[list[float]] = None
    single_scattering_albedo: Optional[list[float]] = None
