"""Small public scientific API and high-level product dispatch."""

from __future__ import annotations

from pathlib import Path

from zju_scatt_interface.access.registration import registration_required
from zju_scatt_interface.access.workflow import retrieve
from zju_scatt_interface.bulk.ensemble import combine
from zju_scatt_interface.bulk.grid import (
    BulkGrid,
    MultiBulkGrid,
)
from zju_scatt_interface.bulk.integration import integrate
from zju_scatt_interface.bulk.models import BulkDataset, PopulationResult
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.config.particles import (
    get_particle_profile as describe_particle,
)
from zju_scatt_interface.config.scheme import Scheme, load_scheme
from zju_scatt_interface.extensions.operations import dispatch, plot_with_kind
from zju_scatt_interface.io.canonical import OutputOptions, read
from zju_scatt_interface.io.products import write
from zju_scatt_interface.optics.models import BulkOptics, SingleParticleOptics
from zju_scatt_interface.psd.models import SizeDistribution
from zju_scatt_interface.sources.planning import (
    DependencyPlan,
)


@registration_required
def plan(scheme, **options):
    """Plan dependencies using the registered scheme handler; never download."""
    if options.pop("download", False) is not False:
        raise ValueError("plan never downloads; use build or access retrieval operations")
    return dispatch("plan", scheme, **options)


@registration_required
def build(scheme, *, plan=None, **options):
    """Build using the registered handler for this scheme's type."""
    return dispatch("build", scheme, plan=plan, **options)


@registration_required
def interpolate(sources, target, *, particle_type, **options):
    """Interpolate a nonempty homogeneous sequence using its source-type handler."""
    sources = tuple(sources)
    if not sources or not all(isinstance(source, type(sources[0])) for source in sources):
        raise TypeError("sources must be a nonempty homogeneous sequence")
    return dispatch(
        "interpolate", sources[0], sources, target, particle_type=particle_type, **options
    )


@registration_required
def validate(product, **options):
    """Validate with the registered product-type handler."""
    return dispatch("validate", product, **options)


@registration_required
def plot(product, *, kind=None, **options):
    """Plot with a product-type handler or an explicitly registered plot kind."""
    if kind is not None:
        return plot_with_kind(kind, product, **options)
    if isinstance(product, (str, Path)):
        raise ValueError("File plots require kind='single' or kind='bulk'")
    return dispatch("plot", product, **options)


__all__ = [
    "Scheme",
    "SizeDistribution",
    "SingleParticleOptics",
    "BulkOptics",
    "PopulationResult",
    "BulkDataset",
    "BulkGrid",
    "MultiBulkGrid",
    "DependencyPlan",
    "OutputOptions",
    "load_scheme",
    "describe_particle",
    "plan",
    "retrieve",
    "interpolate",
    "integrate",
    "combine",
    "compute_population",
    "build",
    "validate",
    "read",
    "write",
    "plot",
]
