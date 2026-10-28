"""One-population and complete scheme calculation workflows."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping, Sequence

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble, WeightedShapeMember
from zju_scatt_interface.bulk.models import BulkDataset, PopulationResult
from zju_scatt_interface.optics.models import BulkOptics
from zju_scatt_interface.psd.models import SizeDistribution
from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryError


@_registration_required
def compute_population(
    particle_type: str,
    source_paths: str | Path | Sequence[str | Path],
    size_distribution: SizeDistribution,
    *,
    wavelength: object,
    wavelength_unit: str = "um",
    parameters: Mapping[str, object] | None = None,
    shape_ensemble: WeightedShapeEnsemble | Sequence[WeightedShapeMember] | None = None,
    refractive_index_tables: Mapping[str, object] | None = None,
    size_definition: str | None = None,
    truncation_policy: str = "error",
    include_phase_matrix: bool = False,
    target_angles_degrees: Sequence[float] | None = None,
    phase_normalization: str = "preserve",
    check_convergence: bool = True,
    convergence_tolerance: float = 0.05,
    strict_convergence: bool = False,
    qa_tolerance: float = 1.0e-8,
    strict_qa: bool = True,
    uncertainty_metadata: Mapping[str, object] | None = None,
) -> PopulationResult:
    """Calculate bulk optics for one particle profile and optional shape ensemble.

    Automatically check physical size/PSD coverage across all positive-weight
    members. Error mode rejects uncovered PSD mass. Explicit truncate mode
    uses one shared integration grid and population for every member, without
    concentration renormalization. The report is in bulk.metadata['size_coverage'].
    """
    from zju_scatt_interface.bulk.ensemble import (
        _ensemble_members,
        combine,
    )
    from zju_scatt_interface.bulk.integration import integrate
    from zju_scatt_interface.bulk.models import EnsembleMemberResult, PopulationResult
    from zju_scatt_interface.bulk.quality import (
        BulkConvergenceReport,
        BulkQualityReport,
        _convergence_check,
        validate_bulk_optics,
    )
    from zju_scatt_interface.optics.refractive_index import wavelength_to_um
    from zju_scatt_interface.sources.adapters.registry import get_particle_adapter

    convergence_limit = float(convergence_tolerance)
    if not math.isfinite(convergence_limit) or convergence_limit <= 0:
        raise ValueError("convergence_tolerance must be finite and positive")
    wavelength_um = wavelength_to_um(wavelength, wavelength_unit)
    ensemble_members, ensemble_provenance = _ensemble_members(parameters, shape_ensemble)
    adapter = get_particle_adapter(particle_type)
    member_results: list[EnsembleMemberResult] = []
    common_angles = (
        list(map(float, target_angles_degrees)) if target_angles_degrees is not None else None
    )
    coverage = None
    working_distribution = size_distribution
    common_size_grid = None
    for member_parameters, weight in ensemble_members:
        if weight == 0:
            continue
        try:
            resolution = adapter.resolve(
                source_paths,
                wavelength=wavelength_um,
                parameters=member_parameters,
                refractive_index_tables=refractive_index_tables,
                size_definition=size_definition or size_distribution.size_definition,
                include_phase_matrix=include_phase_matrix,
            )
            if coverage is None:
                from zju_scatt_interface.psd.coverage import check_size_coverage

                coverage = check_size_coverage(
                    particle_type,
                    source_paths,
                    size_distribution,
                    wavelength=wavelength_um,
                    parameters=parameters,
                    shape_ensemble=shape_ensemble,
                    refractive_index_tables=refractive_index_tables,
                    size_definition=size_definition,
                    truncation_policy=truncation_policy,
                )
                common_size_grid = coverage.get("common_integration_grid_um")
                if common_size_grid is not None:
                    working_distribution, _ = size_distribution.remap(
                        common_size_grid, truncation_policy="truncate"
                    )
            product = resolution.interpolate(
                target_size_um=common_size_grid,
                target_angles_degrees=common_angles,
                phase_normalization=phase_normalization,
            )
        except DatabaseBoundaryError as exc:
            import warnings

            from zju_scatt_interface.sources.adapters.boundaries import (
                DatabaseBoundaryWarning,
            )

            message = f"{exc} Bulk optical values returned as NaN; no extrapolation applied."
            warnings.warn(message, DatabaseBoundaryWarning, stacklevel=2)
            invalid = BulkOptics(
                *([float("nan")] * 5),
                phase_matrix=(
                    [
                        [[float("nan")] * 4 for _ in range(4)]
                        for _ in (common_angles or [float("nan")])
                    ]
                    if include_phase_matrix
                    else None
                ),
                metadata={
                    "status": "out_of_database_bounds",
                    "warnings": [message],
                    "parameters": dict(member_parameters),
                    "wavelength_um": wavelength_um,
                },
            )
            return PopulationResult(
                adapter.particle_type,
                wavelength_um,
                invalid,
                BulkQualityReport(
                    False, {"database_bounds": False}, {}, warnings=(message,), errors=(str(exc),)
                ),
                tuple(member_results),
                ensemble_provenance,
                dict(uncertainty_metadata or {}),
            )
        if include_phase_matrix and common_angles is None:
            common_angles = list(product.optics.scattering_angles or [])
        bulk, remap = integrate(
            product.optics,
            working_distribution,
            database_size_definition=(size_definition or size_distribution.size_definition),
            truncation_policy=truncation_policy,
        )
        bulk.metadata.update(
            {
                "particle_type": product.particle_type,
                "size_coverage": coverage,
                "wavelength_um": wavelength_um,
                "parameters": dict(member_parameters),
                "scattering_angles_degrees": list(product.optics.scattering_angles or []),
                "interpolation_provenance": product.provenance.to_dict(),
            }
        )
        qa = validate_bulk_optics(
            bulk,
            scattering_angles=product.optics.scattering_angles,
            tolerance=qa_tolerance,
        )
        convergence = (
            _convergence_check(
                product.optics,
                working_distribution,
                bulk,
                database_size_definition=(size_definition or size_distribution.size_definition),
                truncation_policy=truncation_policy,
                tolerance=convergence_limit,
            )
            if check_convergence
            else BulkConvergenceReport(
                checked=False,
                passed=True,
                tolerance=convergence_limit,
                full_size_count=len(product.optics.sizes),
                coarse_size_count=0,
                relative_errors={},
                message="Convergence check disabled by caller.",
            )
        )
        if strict_qa and not qa.passed:
            raise ValueError("Bulk physical QA failed: " + "; ".join(qa.errors))
        if strict_convergence and not convergence.passed:
            raise ValueError(
                "Bulk convergence check failed: "
                + ", ".join(
                    f"{name}={value:.6g}" for name, value in convergence.relative_errors.items()
                )
            )
        member_results.append(
            EnsembleMemberResult(
                parameters=dict(member_parameters),
                weight=weight,
                bulk=bulk,
                remap=remap,
                qa=qa,
                convergence=convergence,
                interpolation_provenance=product.provenance.to_dict(),
            )
        )
    combined = combine(
        [member.bulk for member in member_results],
        [member.weight for member in member_results],
        metadata={
            "particle_type": adapter.particle_type,
            "size_coverage": coverage,
            "wavelength_um": wavelength_um,
            "ensemble": ensemble_provenance,
            "uncertainty": dict(uncertainty_metadata or {}),
            "scattering_angles_degrees": common_angles or [],
        },
    )
    combined.single_scattering_albedo = (
        combined.scattering_coefficient / combined.extinction_coefficient
        if combined.extinction_coefficient not in (None, 0.0)
        and combined.scattering_coefficient is not None
        else None
    )
    combined_qa = validate_bulk_optics(
        combined,
        scattering_angles=common_angles,
        tolerance=qa_tolerance,
    )
    if strict_qa and not combined_qa.passed:
        raise ValueError("Ensemble bulk physical QA failed: " + "; ".join(combined_qa.errors))
    return PopulationResult(
        particle_type=adapter.particle_type,
        wavelength_um=wavelength_um,
        bulk=combined,
        qa=combined_qa,
        members=tuple(member_results),
        ensemble=ensemble_provenance,
        uncertainty=dict(uncertainty_metadata or {}),
    )


def _component_calculation_inputs(component):
    from zju_scatt_interface.extensions.particles import get_particle_definition

    return get_particle_definition(component.particle_type).calculation_inputs(component)


@_registration_required
def build_dataset(
    config: object,
    *,
    source_paths: Mapping[str, str | Path | Sequence[str | Path]]
    | str
    | Path
    | Sequence[str | Path]
    | None = None,
    dependency_plan: object | None = None,
    workspace: str | Path = "zju_scatt_data",
    offline: bool = False,
    include_phase_matrix: bool | None = None,
    target_angles_degrees: Sequence[float] | None = None,
    phase_normalization: str = "preserve",
    truncation_policy: str | None = None,
    check_convergence: bool | None = None,
    convergence_tolerance: float | None = None,
    strict_convergence: bool | None = None,
    strict_qa: bool | None = None,
) -> BulkDataset:
    """Build every named component by repeatedly calling ``calculate_bulk_optics``."""
    from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble
    from zju_scatt_interface.bulk.models import BulkDataset
    from zju_scatt_interface.config.scheme import Scheme
    from zju_scatt_interface.sources.planning import prepare_scheme_dependencies

    if not isinstance(config, Scheme):
        if not isinstance(config, Mapping):
            raise TypeError("config must be Scheme or a configuration mapping")
        config = Scheme.from_mapping(config)
    include_phase_matrix = (
        config.include_phase_matrix if include_phase_matrix is None else include_phase_matrix
    )
    if target_angles_degrees is None and config.scattering_angles_degrees:
        target_angles_degrees = config.scattering_angles_degrees
    truncation_policy = truncation_policy or config.truncation_policy
    check_convergence = config.check_convergence if check_convergence is None else check_convergence
    convergence_tolerance = (
        config.convergence_tolerance if convergence_tolerance is None else convergence_tolerance
    )
    strict_convergence = (
        config.strict_convergence if strict_convergence is None else strict_convergence
    )
    strict_qa = config.strict_qa if strict_qa is None else strict_qa
    configured_sources = {
        component.name: component.source
        for component in config.particles
        if component.source is not None
    }
    if source_paths is None and configured_sources:
        missing_sources = [
            component.name for component in config.particles if component.source is None
        ]
        if missing_sources:
            raise ValueError(
                "components with configured local sources cannot be mixed with "
                "components requiring automatic download; missing source for: "
                + ", ".join(missing_sources)
            )
        source_paths = configured_sources
    plan = dependency_plan
    if source_paths is None and plan is None:
        plan = prepare_scheme_dependencies(
            config,
            workspace=workspace,
            offline=offline,
        )
        if not plan.complete:
            actions = "; ".join(issue.action for issue in plan.issues)
            raise ValueError("Bulk scheme dependencies are incomplete. " + actions)
    components: dict[str, tuple[PopulationResult, ...]] = {}
    calculation_angles = (
        list(map(float, target_angles_degrees))
        if target_angles_degrees is not None
        else [float(value) for value in range(181)]
        if include_phase_matrix
        else None
    )
    for component in config.particles:
        if plan is not None:
            component_sources = [
                source.cache_path
                for source in plan.sources
                if component.name in source.component_names and source.ready
            ]
            incomplete = [
                source
                for source in plan.sources
                if component.name in source.component_names and not source.ready
            ]
            if incomplete or not component_sources:
                raise ValueError(
                    f"Component {component.name!r} does not have a complete verified "
                    "source set in the dependency plan."
                )
        elif isinstance(source_paths, Mapping):
            try:
                component_sources = source_paths[component.name]
            except KeyError:
                try:
                    component_sources = source_paths[component.particle_type]
                except KeyError as exc:
                    raise ValueError(
                        f"No source_paths entry for component {component.name!r} "
                        f"or particle type {component.particle_type!r}."
                    ) from exc
        else:
            component_sources = source_paths
        parameters, tables = _component_calculation_inputs(component)
        shape_ensemble = (
            WeightedShapeEnsemble(component.shape_ensemble) if component.shape_ensemble else None
        )
        results = []
        for wavelength_um in config.wavelengths_um:
            results.append(
                compute_population(
                    component.particle_type,
                    component_sources,
                    component.size_distribution,
                    wavelength=wavelength_um,
                    parameters=parameters,
                    shape_ensemble=shape_ensemble,
                    refractive_index_tables=tables,
                    size_definition=component.size_distribution.size_definition,
                    truncation_policy=truncation_policy,
                    include_phase_matrix=include_phase_matrix,
                    target_angles_degrees=calculation_angles,
                    phase_normalization=phase_normalization,
                    check_convergence=check_convergence,
                    convergence_tolerance=convergence_tolerance,
                    strict_convergence=strict_convergence,
                    strict_qa=strict_qa,
                )
            )
        components[component.name] = tuple(results)
    return BulkDataset(
        name=config.name,
        wavelengths_um=tuple(config.wavelengths_um),
        components=components,
        dependency_plan=plan,
    )
