"""Bindings for built-in public operations; extension handlers are independent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from zju_scatt_interface.bulk.grid import (
    BulkGrid,
    MultiBulkGrid,
    MultiBulkScheme,
    SingleBulkScheme,
    build_grid,
    build_grids,
)
from zju_scatt_interface.bulk.models import BulkDataset, PopulationResult
from zju_scatt_interface.bulk.quality import validate_bulk_optics
from zju_scatt_interface.bulk.tables import BulkTableResult
from zju_scatt_interface.bulk.workflow import build_dataset
from zju_scatt_interface.config.scheme import Scheme, load_scheme
from zju_scatt_interface.io.canonical import (
    _write_dataset,
    _write_grid,
    _write_optics,
    _write_population,
    validate_file,
)
from zju_scatt_interface.optics.interpolation import (
    OpticalNode,
    OpticalSourceRequest,
    interpolate_nodes,
    interpolate_sources,
)
from zju_scatt_interface.optics.models import BulkOptics, SingleParticleOptics
from zju_scatt_interface.sources.planning import (
    DependencyPlan,
    build_dependency_queries,
    prepare_scheme_dependencies,
)


def _scheme(value):
    if isinstance(value, (str, Path)):
        return load_scheme(value)
    if isinstance(value, Mapping):
        return Scheme.from_mapping(value)
    if isinstance(value, Scheme):
        return value
    raise TypeError("scheme must be a Scheme, mapping, or Python/JSON scheme path")


def _build_scheme(scheme, *, plan=None, **options):
    """Build a Scheme or retained SingleBulkScheme/MultiBulkScheme grid.

    Scheme paths and mappings are loaded as ordinary Schemes. A dependency plan
    applies to ordinary Schemes; grids use explicit local source_paths instead.
    Incomplete plans are refreshed in their workspace, downloading missing
    sources unless offline=True. Remaining options follow the existing builder.
    """
    if "dependency_plan" in options:
        raise TypeError("Use build(scheme, plan=...) for a dependency plan")
    config = _scheme(scheme)
    if plan is not None:
        if not isinstance(plan, DependencyPlan):
            raise TypeError("plan must be a DependencyPlan")
        if plan.scheme_name != config.name or plan.queries != build_dependency_queries(config):
            raise ValueError("The dependency plan does not match the requested scheme")
        if options.get("source_paths") is not None:
            raise ValueError("Choose plan or source_paths for an ordinary Scheme")
        if (
            "workspace" in options
            and Path(options["workspace"]).expanduser().resolve() != plan.workspace.root
        ):
            raise ValueError("workspace must match the supplied dependency plan")
        options.setdefault("workspace", plan.workspace.root)
        options.setdefault("offline", plan.offline)
        if not plan.complete:
            plan = prepare_scheme_dependencies(
                config,
                workspace=options["workspace"],
                offline=options["offline"],
            )
    return build_dataset(config, dependency_plan=plan, **options)


def _build_grid(value, *, plan=None, **options):
    if plan is not None:
        raise ValueError("Grid builds use source_paths rather than a dependency plan")
    return build_grid(value, **options)


def _build_grids(value, *, plan=None, **options):
    if plan is not None:
        raise ValueError("Grid builds use source_paths rather than a dependency plan")
    return build_grids(value, **options)


def _plan(value, **options):
    return prepare_scheme_dependencies(_scheme(value), download=False, **options)


def _validate_scheme(value, **options):
    return value.validate(**options)


def _plot_single(value, **options):
    from zju_scatt_interface.plotting.single import plot_single_scattering

    if isinstance(
        value, (BulkOptics, PopulationResult, BulkDataset, BulkGrid, MultiBulkGrid, Mapping)
    ):
        raise TypeError("A bulk product requires kind='bulk'")
    return plot_single_scattering(value, **options)


def _plot_bulk(value, **options):
    from zju_scatt_interface.plotting.bulk import plot_bulk_optics

    if isinstance(value, SingleParticleOptics):
        raise TypeError("SingleParticleOptics requires kind='single'")
    if isinstance(value, PopulationResult):
        value = value.bulk
    return plot_bulk_optics(value, **options)


def _no_wavelength(wavelength_um=None, wavelengths_um=None):
    if wavelength_um is not None or wavelengths_um is not None:
        raise ValueError("Wavelength options apply only to bare BulkOptics")


def _write_bulk(value, path, *, wavelength_um=None, wavelengths_um=None, **options):
    if wavelength_um is None or wavelengths_um is not None:
        raise ValueError("A BulkOptics requires wavelength_um only")
    return _write_optics(path, (wavelength_um,), (value,), **options)


def _writer(function):
    def write(value, path, *, wavelength_um=None, wavelengths_um=None, **options):
        _no_wavelength(wavelength_um, wavelengths_um)
        return function(path, value, **options)

    return write


def _write_table(value, path, **options):
    options.setdefault("source_manifest", value.report.get("source_manifests", {}))
    return _writer(_write_dataset)(value.scheme, path, **options)


def _write_sequence(values, path, *, wavelength_um=None, wavelengths_um=None, **options):
    if isinstance(values, (str, bytes)):
        raise TypeError("write expects an optical product, not a string")
    values = tuple(values)
    if values and all(isinstance(value, BulkOptics) for value in values):
        if wavelengths_um is None or wavelength_um is not None:
            raise ValueError("A BulkOptics sequence requires wavelengths_um only")
        return _write_optics(path, wavelengths_um, values, **options)
    _no_wavelength(wavelength_um, wavelengths_um)
    if values and all(isinstance(value, PopulationResult) for value in values):
        return _write_population(path, values, **options)
    raise TypeError("write requires a nonempty homogeneous optics/result sequence")


def _interpolate_nodes(first, sources, target, *, particle_type, **options):
    return interpolate_nodes(particle_type, sources, target, **options)


def _interpolate_sources(first, sources, target, *, particle_type, **options):
    return interpolate_sources(particle_type, sources, target, **options)


def install(operations, plotters):
    for cls in (Scheme, str, Path, Mapping):
        operations["build"].register(cls, _build_scheme)
        operations["plan"].register(cls, _plan)
    operations["build"].register(SingleBulkScheme, _build_grid)
    operations["build"].register(MultiBulkScheme, _build_grids)
    operations["validate"].register(Scheme, _validate_scheme)
    operations["validate"].register(BulkOptics, validate_bulk_optics)
    for cls in (str, Path):
        operations["validate"].register(cls, validate_file)
    operations["plot"].register(SingleParticleOptics, _plot_single)
    for cls in (BulkOptics, PopulationResult, BulkDataset, BulkGrid, MultiBulkGrid, Mapping):
        operations["plot"].register(cls, _plot_bulk)
    plotters.register("single", _plot_single)
    plotters.register("bulk", _plot_bulk)
    operations["write"].register(BulkOptics, _write_bulk)
    operations["write"].register(BulkDataset, _writer(_write_dataset))
    operations["write"].register(BulkGrid, _writer(_write_grid))
    operations["write"].register(MultiBulkGrid, _writer(_write_grid))
    operations["write"].register(PopulationResult, _writer(_write_population))
    operations["write"].register(BulkTableResult, _write_table)
    operations["write"].register(Sequence, _write_sequence)
    operations["interpolate"].register(OpticalNode, _interpolate_nodes)
    operations["interpolate"].register(OpticalSourceRequest, _interpolate_sources)
