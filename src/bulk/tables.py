"""Preset/measurement-driven bulk spectra, checkpoints and assumptions reports."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import runpy
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from zju_scatt_interface._version import __version__
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.bulk.defaults import default_bulk_assumptions
from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble
from zju_scatt_interface.bulk.models import (
    BulkDataset,
    EnsembleMemberResult,
    PopulationResult,
)
from zju_scatt_interface.bulk.quality import (
    BulkConvergenceReport,
    BulkQualityReport,
    validate_bulk_optics,
)
from zju_scatt_interface.bulk.workflow import (
    _component_calculation_inputs,
    build_dataset,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
    list_particle_profiles,
    normalize_parameter_name,
)
from zju_scatt_interface.config.scheme import ParticleComponent, Scheme
from zju_scatt_interface.io.canonical import _write_dataset as write_bulk_scheme_netcdf
from zju_scatt_interface.io.canonical import validate_file
from zju_scatt_interface.optics.models import BulkOptics
from zju_scatt_interface.optics.refractive_index import (
    default_refractive_index_paths,
    wavelength_to_um,
)
from zju_scatt_interface.psd.analytical import (
    radius_moments,
)
from zju_scatt_interface.psd.coverage import check_size_coverage
from zju_scatt_interface.psd.models import RemapReport, SizeDistribution, _bin_edges
from zju_scatt_interface.sources.planning import (
    _file_digest,
    prepare_scheme_dependencies,
)


def _progress(message):
    print(message, flush=True)


def _json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def _positive(value, name):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


@_registration_required
def check_spectral_size_coverage(
    particle_type,
    source_paths,
    wavelengths,
    *,
    parameters=None,
    shape_ensemble=None,
    refractive_index_tables=None,
):
    """Common physical volume-equivalent radius across all members/wavelengths."""
    wavelengths = tuple(wavelength_to_um(w) for w in wavelengths)
    probe = SizeDistribution(
        [10 ** (-12 + 24 * i / 127) for i in range(128)], [1.0] * 128, gap_policy="allow"
    )
    reports = [
        check_size_coverage(
            particle_type,
            source_paths,
            probe,
            wavelength=w,
            parameters=parameters,
            shape_ensemble=shape_ensemble,
            refractive_index_tables=refractive_index_tables,
            truncation_policy="truncate",
        )
        for w in wavelengths
    ]
    if not reports:
        raise ValueError("At least one wavelength is required")
    lower = max(r["common_source_radius_um"][0] for r in reports)
    upper = min(r["common_source_radius_um"][1] for r in reports)
    if lower >= upper:
        raise ValueError(
            "No common physical size interval across the requested spectrum and shapes"
        )
    return {
        "common_source_radius_um": [lower, upper],
        "wavelengths_um": list(wavelengths),
        "coordinate": "volume_equivalent_sphere_radius",
        "per_wavelength": reports,
    }


@dataclass(frozen=True)
class BulkTableConfig:
    """Short workflow configuration; unspecified species settings use literature_v1."""

    wavelengths: object
    species: object = "all"
    preset: str = "literature_v1"
    overrides: Mapping = field(default_factory=dict)
    number_concentration_cm3: float = 1.0
    include_phase_matrix: bool = False
    coverage_policy: str = "error"
    workspace: object = "zju_scatt_data"
    offline: bool = False
    source_paths: Mapping = field(default_factory=dict)
    catalog: object = None
    reuse_dirs: object = ()
    output_dir: object = None
    formats: object = ("nc", "csv")

    def __post_init__(self):
        if self.preset not in {"reference_v1", "literature_v1"}:
            raise ValueError("preset must be literature_v1 or reference_v1")
        waves = tuple(wavelength_to_um(w) for w in self.wavelengths)
        if not waves or len(set(waves)) != len(waves):
            raise ValueError("wavelengths must be nonempty and contain no duplicates")
        object.__setattr__(self, "wavelengths", waves)
        names = (
            [p.particle_type for p in list_particle_profiles()]
            if self.species == "all"
            else [self.species]
            if isinstance(self.species, str)
            else list(self.species)
        )
        names = tuple(get_particle_profile(name).particle_type for name in names)
        if not names or len(names) != len(set(names)):
            raise ValueError("species must be nonempty and contain no duplicates")
        object.__setattr__(self, "species", names)
        for key in ("overrides", "source_paths"):
            value = getattr(self, key)
            if not isinstance(value, Mapping):
                raise ValueError(f"{key} must be a mapping keyed by species")
            normalized = {
                get_particle_profile(name).particle_type: item for name, item in value.items()
            }
            if len(normalized) != len(value) or set(normalized) - set(names):
                raise ValueError(f"{key} has duplicate aliases or species not selected")
            object.__setattr__(self, key, normalized)
        _positive(self.number_concentration_cm3, "number_concentration_cm3")
        if self.coverage_policy not in {"error", "truncate", "truncate_renormalize"}:
            raise ValueError("coverage_policy must be error, truncate, or truncate_renormalize")
        for key in ("include_phase_matrix", "offline"):
            if not isinstance(getattr(self, key), bool):
                raise ValueError(f"{key} must be a boolean")
        formats = (self.formats,) if isinstance(self.formats, str) else tuple(self.formats)
        if not formats or set(formats) - {"nc", "csv"}:
            raise ValueError("formats must contain nc and/or csv")
        object.__setattr__(self, "formats", formats)
        if isinstance(self.reuse_dirs, (str, Path)):
            object.__setattr__(self, "reuse_dirs", (self.reuse_dirs,))

    @classmethod
    def from_mapping(cls, value, *, base_dir=None):
        import copy

        value = copy.deepcopy(dict(value))
        if base_dir is not None:
            base = Path(base_dir)

            def path(p):
                p = Path(p).expanduser()
                return str(p if p.is_absolute() else (base / p).resolve())

            for name in ("workspace", "catalog", "output_dir"):
                if value.get(name) is not None:
                    value[name] = path(value[name])
            value.setdefault("workspace", path("zju_scatt_data"))
            roots = value.get("reuse_dirs", ())
            value["reuse_dirs"] = [
                path(p) for p in ([roots] if isinstance(roots, (str, Path)) else roots)
            ]
            value["source_paths"] = {
                name: [path(p) for p in ([paths] if isinstance(paths, (str, Path)) else paths)]
                for name, paths in value.get("source_paths", {}).items()
            }
            for override in value.get("overrides", {}).values():
                for name in ("file", "black_carbon_file", "hygroscopic_file"):
                    if (
                        isinstance(override.get("refractive_index"), dict)
                        and name in override["refractive_index"]
                    ):
                        override["refractive_index"][name] = path(
                            override["refractive_index"][name]
                        )
                if isinstance(override.get("psd"), dict) and "file" in override["psd"]:
                    override["psd"]["file"] = path(override["psd"]["file"])
        return cls(**value)


@_registration_required
def load_table_config(path):
    """Read a trusted .py file defining bulk_table, or an equivalent JSON object."""
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() == ".py":
        namespace = runpy.run_path(str(path))
        value = namespace.get("bulk_table")
    elif path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Bulk table configuration must be a .py or .json file")
    if isinstance(value, BulkTableConfig):
        return BulkTableConfig.from_mapping(vars(value), base_dir=path.parent)
    if not isinstance(value, Mapping):
        raise ValueError("Configuration must define bulk_table as a mapping or BulkTableConfig")
    return BulkTableConfig.from_mapping(value, base_dir=path.parent)


def _settings(family, override, preset="literature_v1"):
    if not isinstance(override, Mapping):
        raise ValueError(f"Override for {family} must be a mapping")
    settings = default_bulk_assumptions(family, preset=preset)
    parameters = {normalize_parameter_name(k): v for k, v in settings["parameters"].items()}
    shapes = settings["shape_ensemble"]
    override = dict(override)
    if "shapes" in override:
        selected = override.pop("shapes")
        selected = [selected] if isinstance(selected, Mapping) else selected
        shapes = [member.to_dict() for member in WeightedShapeEnsemble(selected).members]
        for member in shapes:
            member["parameters"] = {
                normalize_parameter_name(k): v for k, v in member["parameters"].items()
            }
        from zju_scatt_interface.extensions.particles import get_particle_definition

        required = set(get_particle_definition(family).ensemble_axes)
        if not required or any(set(member["parameters"]) != required for member in shapes):
            raise ValueError(f"shapes for {family} must specify exactly {sorted(required)}")
    psd = override.pop("psd", None)
    if psd is not None and not isinstance(psd, (Mapping, SizeDistribution)):
        raise ValueError("psd must be a SizeDistribution or a PSD configuration mapping")
    refractive = override.pop("refractive_index", {"mode": "database"})
    if not isinstance(refractive, Mapping):
        raise ValueError("refractive_index requires a mapping with mode")
    refractive = dict(refractive)
    parameters.update({normalize_parameter_name(k): v for k, v in override.items()})
    from zju_scatt_interface.extensions.particles import get_particle_definition

    policy = get_particle_definition(family).table_settings
    if policy is not None:
        parameters, shapes, refractive = policy(parameters, shapes, refractive)
    return settings, parameters, shapes, refractive, psd


@_registration_required
def resolve_bulk_settings(particle_type, overrides=None, *, preset="literature_v1"):
    """Resolve preset plus user overrides without downloading or calculating.

    Used by custom dependency planners so shape ensembles, environmental
    parameters and refractive-index modes follow the same rules as bulk tables.
    """
    family = get_particle_profile(particle_type).particle_type
    settings, parameters, shapes, refractive, psd = _settings(
        family, {} if overrides is None else overrides, preset
    )
    return {
        "particle_type": family,
        "reference": settings,
        "parameters": parameters,
        "shape_ensemble": shapes,
        "refractive_index": refractive,
        "psd": psd,
    }


def _computation_sources(paths, workspace):
    """Stage WSL mounted files on the Linux filesystem; never deletes sources."""
    from zju_scatt_interface.sources.adapters.base import _expand_netcdf_paths

    paths = _expand_netcdf_paths(paths)
    if os.name != "posix" or not any(str(p).startswith("/mnt/") for p in paths):
        return paths
    root = Path.home() / ".cache" / "zju_scatt_interface" / "computation"
    result = []
    for path in paths:
        identity = hashlib.sha256(str(path).encode()).hexdigest()[:24]
        target = root / identity / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        stat = path.stat()
        if (
            not target.exists()
            or target.stat().st_size != stat.st_size
            or target.stat().st_mtime_ns != stat.st_mtime_ns
            or _file_digest(target, "sha256") != _file_digest(path, "sha256")
        ):
            temporary = target.with_name(target.name + ".tmp")
            shutil.copy2(path, temporary)
            temporary.replace(target)
        if target.stat().st_size != stat.st_size:
            raise ValueError(f"Incomplete computation cache: {target}")
        result.append(target)
    return result


def _restrict_psd(psd, lower, upper, policy):
    import numpy as np

    edges = _bin_edges(psd.size_um)
    if edges[0] >= lower * (1 - 1e-12) and edges[-1] <= upper * (1 + 1e-12):
        return psd
    if policy == "error":
        raise ValueError(
            f"PSD bin edges [{edges[0]:g}, {edges[-1]:g}] um exceed common spectral size coverage "
            f"[{lower:g}, {upper:g}] um; choose coverage_policy='truncate' or 'truncate_renormalize' explicitly"
        )
    centers = np.geomspace(lower, upper, max(3, len(psd.size_um)))
    bounds = _bin_edges(centers)
    centers = lower + (centers - bounds[0]) * ((upper - lower) / (bounds[-1] - bounds[0]))
    restricted, remap = psd.remap(centers, truncation_policy="truncate")
    counts = restricted.dndr_cm3
    if policy == "truncate_renormalize":
        counts = [
            v * psd.number_concentration_cm3 / restricted.number_concentration_cm3 for v in counts
        ]
    return SizeDistribution(
        centers,
        counts,
        metadata={
            **psd.metadata,
            "spectral_restriction": remap.to_dict(),
            "coverage_policy": policy,
        },
        source=psd.source,
    )


def _make_psd(
    specification, reference, lower, upper, concentration, policy, *, conditional_reference=False
):
    from zju_scatt_interface.extensions.psd import PSDContext, create_psd

    if isinstance(specification, SizeDistribution):
        psd = specification
    else:
        config = dict(reference if specification is None else specification)
        if specification is None:
            config.setdefault("type", "lognormal")
        if config.get("type"):
            psd = create_psd(
                config,
                PSDContext(
                    lower,
                    upper,
                    concentration,
                    reference=specification is None,
                    conditional_reference=conditional_reference,
                ),
            )
        else:
            psd = SizeDistribution.from_mapping(config)
    if psd.size_definition != "volume_equivalent_sphere_radius":
        raise ValueError("Bulk table PSDs must use physical volume-equivalent radius")
    psd = _restrict_psd(psd, lower, upper, policy)
    return SizeDistribution(
        psd.size_um,
        psd.dndr_cm3,
        metadata={**psd.metadata, **radius_moments(psd)},
        source=psd.source,
    )


def _validate_psd_population(input_psd, used_psd, results, policy):
    """Check population preservation without normalizing or recalculating optics."""
    preserved = (
        (input_psd.size_um == used_psd.size_um and input_psd.dndr_cm3 == used_psd.dndr_cm3)
        if input_psd is not None
        else None
    )
    if input_psd is not None and policy == "error" and not preserved:
        raise ValueError("User PSD bins or counts changed without an explicit coverage policy")
    for result in results:
        if not math.isclose(
            result.bulk.number_concentration,
            used_psd.number_concentration_cm3,
            rel_tol=1e-10,
            abs_tol=0.0,
        ):
            raise ValueError(
                f"Bulk concentration differs from the supplied PSD at {result.wavelength_um:g} um"
            )
    return {
        "selection": "user_supplied" if input_psd is not None else "reference_preset",
        "coverage_policy": policy,
        "input_number_concentration_cm3": (
            input_psd.number_concentration_cm3 if input_psd is not None else None
        ),
        "used_number_concentration_cm3": used_psd.number_concentration_cm3,
        "input_bins_preserved": preserved,
        "output_concentration_verified": True,
    }


def _restore_calculation(value):
    members = []
    for item in value["members"]:
        members.append(
            EnsembleMemberResult(
                parameters=item["parameters"],
                weight=item["weight"],
                bulk=BulkOptics(**item["bulk"]),
                remap=RemapReport(**item["remap"]),
                qa=BulkQualityReport(**item["qa"]),
                convergence=BulkConvergenceReport(**item["convergence"]),
                interpolation_provenance=item["interpolation_provenance"],
            )
        )
    return PopulationResult(
        value["particle_type"],
        value["wavelength_um"],
        BulkOptics(**value["bulk"]),
        BulkQualityReport(**value["qa"]),
        tuple(members),
        value["ensemble"],
        value.get("uncertainty", {}),
    )


@dataclass
class BulkTableResult:
    scheme: BulkDataset
    report: dict

    @property
    def rows(self):
        rows = []
        for family, results in self.scheme.components.items():
            for result in results:
                b = result.bulk
                rows.append(
                    {
                        "particle_type": family,
                        "wavelength_um": result.wavelength_um,
                        "beta_ext_m-1": b.extinction_coefficient,
                        "beta_sca_m-1": b.scattering_coefficient,
                        "beta_abs_m-1": b.absorption_coefficient,
                        "beta_ext_Mm-1": b.extinction_coefficient * 1e6,
                        "ssa": b.single_scattering_albedo,
                        "g": b.asymmetry_factor,
                        "number_concentration_cm-3": b.number_concentration,
                    }
                )
        return rows

    def save(self, directory, formats=("nc", "csv")):
        formats = (formats,) if isinstance(formats, str) else tuple(formats)
        if not formats or set(formats) - {"nc", "csv"}:
            raise ValueError("formats must contain nc and/or csv")
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        outputs = {}
        if "nc" in formats:
            path = write_bulk_scheme_netcdf(
                root / "bulk_optics_all_species.nc",
                self.scheme,
                source_manifest=self.report.get("source_manifests", {}),
                format="netcdf4",
            )
            validate_file(path).require_valid()
            outputs["nc"] = str(path)
        if "csv" in formats:
            path = root / "bulk_optics_all_species.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)
            outputs["csv"] = str(path)
        _json(root / "report.json", {**self.report, "outputs": outputs})
        lines = [
            "# Bulk optical table",
            "",
            "Species are calculated independently; no inter-species mixture is implied.",
            "",
            f"PSD preset: {self.report.get('preset')}. The preset supplies defaults; explicit user PSDs replace the reference PSD and retain their supplied concentrations subject to the selected coverage policy. Reference PSDs are representative populations, not measured climatology. See report.json for each species' PSD selection, effective parameters, literature sources, RI files, population normalization, size coverage and validation.",
            "",
        ]
        for family, entry in self.report["species"].items():
            lines += [
                f"## {family}",
                "",
                entry["refractive_index_message"],
                "",
                f"Parameters: `{entry['effective_parameters']}`",
                "",
                f"PSD: `{entry['psd']['metadata']}`",
                "",
            ]
            lines.extend([warning + "\n" for warning in entry.get("warnings", [])])
        (root / "README.md").write_text("\n".join(lines), encoding="utf-8")
        return outputs


@_registration_required
def _compute_table(
    *,
    species="all",
    wavelengths,
    preset="literature_v1",
    overrides=None,
    number_concentration_cm3=1.0,
    include_phase_matrix=False,
    coverage_policy="error",
    workspace="zju_scatt_data",
    offline=False,
    source_paths=None,
    catalog=None,
    reuse_dirs=(),
    progress=_progress,
):
    """Retrieve sources, prepare one PSD per species, calculate and validate a spectrum.

    Defaults use an explicitly selected reference preset. Custom PSDs reject
    insufficient coverage unless truncation is explicitly requested. Checkpoints
    use source content hashes and effective scientific settings, not filenames.
    """
    config = BulkTableConfig(
        wavelengths=wavelengths,
        species=species,
        preset=preset,
        overrides=overrides or {},
        number_concentration_cm3=number_concentration_cm3,
        include_phase_matrix=include_phase_matrix,
        coverage_policy=coverage_policy,
        workspace=workspace,
        offline=offline,
        source_paths=source_paths or {},
        catalog=catalog,
        reuse_dirs=reuse_dirs,
    )
    root = Path(config.workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "1",
        "preset": preset,
        "interface_version": __version__,
        "wavelengths_um": list(config.wavelengths),
        "species": {},
        "source_manifests": {},
    }
    components = {}
    prepared = {}
    # Reject invalid inputs before any remote catalog access or downloads.
    for family in config.species:
        settings, parameters, shapes, refractive, psd_spec = _settings(
            family, config.overrides.get(family, {}), preset=preset
        )
        if psd_spec is not None:
            # Parse custom arrays/files and validate analytical PSD settings
            # before source selection. Physical coverage is checked later.
            psd_spec = _make_psd(
                psd_spec, settings["psd"], 1e-100, 1e100, number_concentration_cm3, "error"
            )
        placeholder = SizeDistribution([0.1, 1.0], [0.5, 0.5])
        component = ParticleComponent(
            family, family, placeholder, refractive, parameters, tuple(shapes)
        )
        scheme_config = Scheme(
            "bulk_table_" + family,
            config.wavelengths,
            (component,),
            include_phase_matrix=include_phase_matrix,
        )
        scheme_config.validate()
        prepared[family] = (
            settings,
            parameters,
            shapes,
            refractive,
            psd_spec,
            component,
            scheme_config,
        )
    _json(root / "bulk_table_progress.json", {**report, "complete": False})
    catalog_path = Path(catalog) if catalog is not None else root / "catalog.jsonl"
    if (
        len(config.source_paths) != len(config.species)
        and not offline
        and not catalog_path.exists()
    ):
        from zju_scatt_interface.access.retrieval import retrieve_sources

        if progress:
            progress("Reading the optical source catalog")
        listing = retrieve_sources(
            sources=["Single_opt/"], download=False, quiet=True, manifest_output=catalog_path
        )
        if listing.status_code:
            raise RuntimeError(f"Catalog retrieval failed with status {listing.status_code}")
    if catalog_path.is_file() and set(config.species) == {
        p.particle_type for p in list_particle_profiles()
    }:
        from zju_scatt_interface.access.manifests import load_manifest

        known = {p.database_directory for p in list_particle_profiles()}
        live = set()
        for obj in load_manifest(catalog_path):
            parts = obj.key.replace("\\", "/").split("/")
            if "Single_opt" in parts and parts.index("Single_opt") + 1 < len(parts):
                live.add(parts[parts.index("Single_opt") + 1])
        if live - known:
            raise ValueError(
                f"All-species run requires support for unregistered catalog species: {sorted(live - known)}"
            )
    for family in config.species:
        if progress:
            progress(f"{family}: preparing sources and shared spectral PSD")
        settings, parameters, shapes, refractive, psd_spec, component, scheme_config = prepared[
            family
        ]
        plan = None
        if family in config.source_paths:
            paths = config.source_paths[family]
        else:
            from zju_scatt_interface.access.retrieval import retrieve_sources

            def search(query):
                # The high-level workflow emits one concise default notice per
                # species; full resolved coordinates remain in its reports.
                import contextlib
                import io

                with contextlib.redirect_stdout(io.StringIO()):
                    selected = retrieve_sources(manifest=catalog_path, **query.retrieval_parameters)
                if selected.status_code:
                    raise RuntimeError(f"Source selection failed: {selected.status_code}")
                return selected.objects

            plan = prepare_scheme_dependencies(
                scheme_config,
                workspace=root,
                offline=offline,
                searcher=search,
                reuse_dirs=config.reuse_dirs,
            )
            if not plan.complete:
                raise ValueError(
                    "Incomplete bulk table sources: "
                    + "; ".join(issue.reason for issue in plan.issues)
                )
            paths = [entry.cache_path for entry in plan.sources]
            report["source_manifests"][family] = str(plan.manifest_path)
        paths = _computation_sources(paths, root)
        requested_vf = None
        if family == "encapsulated_fractal_aggregates_black_carbon" and not any(
            normalize_parameter_name(k) == "vf" for k in config.overrides.get(family, {})
        ):
            effective = default_bulk_assumptions(family, source_paths=paths, preset=preset)
            parameters["vf"] = effective["used_native_vf"]
            requested_vf = effective["requested_vf"]
        component = replace(component, shape_parameters=parameters)
        calculation_parameters, tables = _component_calculation_inputs(component)
        ensemble = WeightedShapeEnsemble(shapes) if shapes else None
        coverage = check_spectral_size_coverage(
            family,
            paths,
            config.wavelengths,
            parameters=calculation_parameters,
            shape_ensemble=ensemble,
            refractive_index_tables=tables,
        )
        lower, upper = coverage["common_source_radius_um"]
        psd = _make_psd(
            psd_spec,
            settings["psd"],
            lower,
            upper,
            number_concentration_cm3,
            coverage_policy,
            conditional_reference=preset == "literature_v1",
        )
        psd = SizeDistribution(
            psd.size_um,
            psd.dndr_cm3,
            metadata={
                **psd.metadata,
                "preset": preset,
                "uses_preset_psd": psd_spec is None,
                "literature_basis": settings.get("psd_reference") if psd_spec is None else None,
            },
            source=psd.source,
        )
        component = replace(component, size_distribution=psd)
        scheme_config = replace(scheme_config, particles=(component,))
        hashes = [{"path": str(p), "sha256": _file_digest(p, "sha256")} for p in paths]
        package = Path(__file__).resolve().parents[1]
        implementation = hashlib.sha256()
        for file in sorted(package.rglob("*.py")):
            implementation.update(str(file.relative_to(package)).encode())
            implementation.update(file.read_bytes())
        ri_hashes = {}
        if tables:
            ri_hashes = {str(p): _file_digest(Path(p), "sha256") for p in tables.values()}
        elif refractive.get("mode") == "database" and family == "super_spheroid":
            ri_hashes = {
                str(p): _file_digest(p, "sha256")
                for p in default_refractive_index_paths(family).values()
            }
        identity = {
            "workflow_version": 1,
            "interface_version": __version__,
            "implementation": implementation.hexdigest(),
            "config": scheme_config.to_dict(),
            "sources": hashes,
            "ri_tables": ri_hashes,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, default=str).encode()
        ).hexdigest()
        checkpoint = root / "work" / "bulk_tables" / (digest + ".json")
        results = []
        if checkpoint.is_file():
            try:
                saved = json.loads(checkpoint.read_text(encoding="utf-8"))
                payload_hash = hashlib.sha256(
                    json.dumps(saved["results"], sort_keys=True).encode()
                ).hexdigest()
                if saved["identity"] == digest and saved.get("results_sha256") == payload_hash:
                    results = [_restore_calculation(item) for item in saved["results"]]
                    if tuple(r.wavelength_um for r in results) != config.wavelengths:
                        results = []
                    for result in results:
                        if (
                            not result.qa.passed
                            or not validate_bulk_optics(result.bulk).passed
                            or not math.isclose(
                                result.bulk.number_concentration,
                                psd.number_concentration_cm3,
                                rel_tol=1e-10,
                                abs_tol=0.0,
                            )
                        ):
                            results = []
                            break
            except (ValueError, TypeError, KeyError):
                results = []
        reused = bool(results)
        if not results:
            # One shared engine, including the same PSD at every wavelength.
            built = build_dataset(scheme_config, source_paths={family: paths})
            results = list(built.components[family])
            for result in results:
                if (
                    not result.qa.passed
                    or not validate_bulk_optics(result.bulk).passed
                    or any(
                        not math.isfinite(float(getattr(result.bulk, name)))
                        for name in (
                            "extinction_coefficient",
                            "scattering_coefficient",
                            "absorption_coefficient",
                            "single_scattering_albedo",
                            "asymmetry_factor",
                            "number_concentration",
                        )
                    )
                ):
                    raise ValueError(
                        f"Invalid bulk optical result for {family} at {result.wavelength_um} um"
                    )
            payload = [r.to_dict() for r in results]
            _json(
                checkpoint,
                {
                    "identity": digest,
                    "results": payload,
                    "results_sha256": hashlib.sha256(
                        json.dumps(payload, sort_keys=True).encode()
                    ).hexdigest(),
                },
            )
        psd_handling = _validate_psd_population(psd_spec, psd, results, coverage_policy)
        ri_files = {}
        if refractive.get("mode") in {"database", "database_temperature"}:
            try:
                ri_files = {
                    name: "data/refractive_index/" + path.name
                    for name, path in default_refractive_index_paths(
                        family, ri_scheme=parameters.get("ri_scheme", "v1.2.1")
                    ).items()
                }
            except ValueError:
                pass
        else:
            ri_files = {k: str(v) for k, v in refractive.items() if k.endswith("file")}
        message = (
            "Since no refractive index was provided, the default refractive index scheme was used. "
            if "refractive_index" not in config.overrides.get(family, {})
            else "The supplied refractive index configuration was used. "
        )
        message += (
            "Reference file(s): " + ", ".join(ri_files.values())
            if ri_files
            else "Optical constants are embedded in the native wavelength data."
        )
        convergence_warnings = [
            f"Convergence diagnostic at {r.wavelength_um:g} um exceeds {m.convergence.tolerance:.0%}: "
            + ", ".join(
                f"{name}={error:.2%}"
                for name, error in m.convergence.relative_errors.items()
                if error > m.convergence.tolerance
            )
            for r in results
            for m in r.members
            if m.convergence.checked and not m.convergence.passed
        ]
        warnings = list(convergence_warnings)
        if psd.metadata.get("parent_characteristic_within_source_coverage") is False:
            retained = psd.metadata.get(
                "retained_untruncated_lognormal_probability",
                psd.metadata.get("retained_untruncated_gamma_probability"),
            )
            warnings.insert(
                0,
                f"The reference PSD parent characteristic radius lies outside common source coverage "
                f"[{lower:g}, {upper:g}] um. Parent parameters were preserved; the covered conditional population "
                f"was normalized to the reference concentration. Retained parent number probability={retained:.6g}.",
            )
        entry = {
            "status": "verified",
            "effective_parameters": calculation_parameters,
            "shapes": shapes,
            "requested_vf": requested_vf,
            "refractive_index": refractive,
            "refractive_index_message": message,
            "refractive_index_files": ri_files,
            "psd": psd.to_dict(),
            "psd_handling": psd_handling,
            "spectral_size_coverage": coverage,
            "sources": hashes,
            "psd_reference": settings.get("psd_reference")
            if psd_spec is None
            else {"selection_note": "Explicit user PSD override"},
            "warnings": warnings,
            "convergence_all_passed": not convergence_warnings,
            "checkpoint_reused": reused,
            "checks": [
                {
                    "wavelength_um": r.wavelength_um,
                    "qa": r.qa.to_dict(),
                    "size_coverage": r.bulk.metadata.get("size_coverage"),
                    "interpolation": [dict(m.interpolation_provenance) for m in r.members],
                    "convergence": [m.convergence.to_dict() for m in r.members],
                }
                for r in results
            ],
        }
        components[family] = tuple(results)
        report["species"][family] = entry
        _json(
            root / "bulk_table_progress.json",
            {**report, "complete": len(components) == len(config.species)},
        )
        if progress:
            progress(
                f"{family}: {len(results)} wavelengths verified"
                + (" (checkpoint reused)" if reused else "")
            )
            progress(message)
            for warning in warnings:
                progress("Warning: " + warning)
    return BulkTableResult(
        BulkDataset("Bulk optical table", config.wavelengths, components), report
    )


@_registration_required
def build_table(config, *, progress=_progress):
    """Compute from a trusted Python/JSON input file, config object, or mapping.

    If output_dir is configured, write validated NetCDF/CSV and an assumptions
    report automatically. Relative file paths are resolved beside the input file.
    """
    if isinstance(config, (str, Path)):
        config = load_table_config(config)
    elif isinstance(config, Mapping):
        config = BulkTableConfig.from_mapping(config)
    if not isinstance(config, BulkTableConfig):
        raise TypeError("config must be a path, mapping or BulkTableConfig")
    kwargs = dict(vars(config))
    output, formats = kwargs.pop("output_dir"), kwargs.pop("formats")
    result = _compute_table(**kwargs, progress=progress)
    if output is not None:
        result.save(output, formats=formats)
    return result
