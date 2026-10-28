"""Population, ensemble-member and multi-component dataset results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from zju_scatt_interface.bulk.quality import BulkConvergenceReport, BulkQualityReport
from zju_scatt_interface.optics.models import BulkOptics
from zju_scatt_interface.psd.models import RemapReport


@dataclass
class EnsembleMemberResult:
    parameters: dict[str, float | str]
    weight: float
    bulk: BulkOptics
    remap: RemapReport
    qa: BulkQualityReport
    convergence: BulkConvergenceReport
    interpolation_provenance: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "parameters": dict(self.parameters),
            "weight": self.weight,
            "bulk": self.bulk.to_dict(),
            "remap": self.remap.to_dict(),
            "qa": self.qa.to_dict(),
            "convergence": self.convergence.to_dict(),
            "interpolation_provenance": dict(self.interpolation_provenance),
        }


@dataclass
class PopulationResult:
    particle_type: str
    wavelength_um: float
    bulk: BulkOptics
    qa: BulkQualityReport
    members: tuple[EnsembleMemberResult, ...]
    ensemble: Mapping[str, object]
    uncertainty: Mapping[str, object] = field(default_factory=dict)

    def save(
        self,
        directory,
        *,
        component_name="bulk_optics",
        source_manifest=None,
        size_distribution=None,
        netcdf_path="bulk_optics.nc",
        title=None,
        include_members=False,
        l2_lognormal=False,
    ):
        """Save validated NetCDF, scalar/phase CSV and a JSON diagnostic report.

        An optional input PSD is saved unchanged. Diagnostic fields remain in
        JSON; NetCDF uses the existing bulk optical schema and member axis.
        include_members adds per-member CSV rows before the ensemble result.
        l2_lognormal explicitly exports normalized dust L2 files per member,
        requiring a lognormal size_distribution and recorded local sources.
        """
        from zju_scatt_interface.io.reports import save_bulk_calculation

        return save_bulk_calculation(
            self,
            directory,
            component_name=component_name,
            source_manifest=source_manifest,
            size_distribution=size_distribution,
            netcdf_path=netcdf_path,
            title=title,
            include_members=include_members,
            l2_lognormal=l2_lognormal,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "particle_type": self.particle_type,
            "wavelength_um": self.wavelength_um,
            "bulk": self.bulk.to_dict(),
            "qa": self.qa.to_dict(),
            "members": [member.to_dict() for member in self.members],
            "ensemble": dict(self.ensemble),
            "uncertainty": dict(self.uncertainty),
        }


@dataclass
class BulkDataset:
    name: str
    wavelengths_um: tuple[float, ...]
    components: Mapping[str, tuple[PopulationResult, ...]]
    mixture: tuple[BulkOptics, ...] | None = None
    dependency_plan: object | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "wavelengths_um": list(self.wavelengths_um),
            "components": {
                name: [result.to_dict() for result in results]
                for name, results in self.components.items()
            },
            "mixture": (
                [result.to_dict() for result in self.mixture] if self.mixture is not None else None
            ),
            "dependency_plan": (
                self.dependency_plan.to_dict()
                if self.dependency_plan is not None and hasattr(self.dependency_plan, "to_dict")
                else None
            ),
        }
