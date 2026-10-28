"""Particle-adapter registration, source resolution and interpolation entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
)
from zju_scatt_interface.optics.interpolation import (
    InterpolatedOpticalProduct,
)
from zju_scatt_interface.optics.refractive_index import (
    wavelength_to_um,
)
from zju_scatt_interface.sources.adapters.base import AdapterResolution, ParticleAdapter
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
    DatabaseBoundaryError,
)


@_registration_required
def get_particle_adapter(particle_type: str) -> ParticleAdapter:
    """Instantiate the registered adapter and check its declared capability."""
    from zju_scatt_interface.extensions.particles import get_particle_definition

    definition = get_particle_definition(particle_type)
    adapter = definition.adapter_factory()
    if not isinstance(adapter, ParticleAdapter):
        raise AdapterError("A particle adapter factory must return a ParticleAdapter")
    if adapter.particle_type != definition.profile.particle_type or not set(
        definition.axes
    ).issubset(adapter.axes):
        raise AdapterError("Adapter particle type/axes disagree with its ParticleDefinition")
    return adapter


@_registration_required
def resolve_particle_sources(
    particle_type: str,
    source_paths: str | Path | Sequence[str | Path],
    **kwargs: Any,
) -> AdapterResolution:
    """Resolve a public request to the minimal set of native L1 source nodes."""

    return get_particle_adapter(particle_type).resolve(source_paths, **kwargs)


@_registration_required
def resolve_plan_component_sources(
    plan: object,
    component_name: str,
    **kwargs: Any,
) -> AdapterResolution:
    """Resolve one component from the verified cache paths in a dependency plan."""

    sources = [
        source
        for source in getattr(plan, "sources", ())
        if component_name in getattr(source, "component_names", ())
    ]
    if not sources:
        raise AdapterError(f"Dependency plan contains no sources for component {component_name!r}.")
    not_ready = [source for source in sources if not getattr(source, "ready", False)]
    if not_ready:
        states = ", ".join(
            f"{getattr(source, 'cache_path', '?')} ({getattr(source, 'status', 'unknown')})"
            for source in not_ready
        )
        raise AdapterError(
            f"Component {component_name!r} has sources that are not ready: {states}."
        )
    particle_types = {str(source.particle_type) for source in sources}
    if len(particle_types) != 1:
        raise AdapterError(
            f"Component {component_name!r} maps to multiple particle types: "
            + ", ".join(sorted(particle_types))
        )
    return resolve_particle_sources(
        particle_types.pop(),
        [source.cache_path for source in sources],
        **kwargs,
    )


@_registration_required
def interpolate_particle(
    particle_type: str,
    source_paths: str | Path | Sequence[str | Path],
    *,
    target_size_um: Sequence[float] | None = None,
    target_angles_degrees: Sequence[float] | None = None,
    phase_normalization: str = "preserve",
    **kwargs: Any,
) -> InterpolatedOpticalProduct:
    """Resolve, minimally load, and interpolate one particle-family product."""
    from zju_scatt_interface.sources.adapters.base import _normalized_parameters

    try:
        resolution = resolve_particle_sources(particle_type, source_paths, **kwargs)
        return resolution.interpolate(
            target_size_um=target_size_um,
            target_angles_degrees=target_angles_degrees,
            phase_normalization=phase_normalization,
        )
    except DatabaseBoundaryError as exc:
        from zju_scatt_interface.sources.adapters.boundaries import nan_product

        sizes = list(target_size_um) if target_size_um is not None else [float("nan")]
        coordinates = _normalized_parameters(kwargs.get("parameters"))
        coordinates["wavelength"] = wavelength_to_um(
            kwargs["wavelength"], kwargs.get("wavelength_unit", "um")
        )
        return nan_product(
            get_particle_profile(particle_type).particle_type,
            coordinates,
            sizes,
            target_angles_degrees,
            str(exc),
        )
