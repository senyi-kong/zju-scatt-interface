"""Configured multi-species retrieval, completion checks and reports."""

from __future__ import annotations

import json
import math
import runpy
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path

import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.access.requests as _domain_access_requests
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.errors import ScattError


def _plain(value):
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(_plain(value), indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(target)
    return target


def validate_retrieval_result(
    result, *, download=False, require_matches=False, require_products=False
):
    issues = []
    if result.status_code:
        issues.append(f"retrieval status {result.status_code}")
    if require_matches and not result.objects:
        issues.append("no source data match the requested coordinates")
    if download:
        wanted = Counter(obj.key for obj in result.objects)
        actual = Counter(item.obj.key for item in result.download_results)
        if actual != wanted:
            issues.append(
                "downloaded source set is incomplete or contains duplicate/unexpected records"
            )
        for item in result.download_results:
            if item.status not in {"downloaded", "skipped"}:
                issues.append(f"{item.obj.key}: {item.message or item.status}")
            elif not item.target.is_file():
                issues.append(f"missing local source: {item.target}")
            elif item.obj.size and item.target.stat().st_size != item.obj.size:
                issues.append(f"source byte-size mismatch: {item.target}")
        if (
            require_products
            and result.wavelength_processing.interpolation_required
            and not result.interpolated_products
        ):
            issues.append("interpolation is required but no target product was produced")
        for product in result.interpolated_products:
            if product.status not in {"created", "skipped"} or not product.path.is_file():
                issues.append(f"incomplete derived product: {product.path}")
    if issues:
        raise ScattError("Retrieval incomplete: " + "; ".join(issues))


def retrieval_result_dict(result):
    return _plain(
        {
            "status_code": result.status_code,
            "matched_files": len(result.objects),
            "total_bytes": result.total_bytes,
            "source_keys": [obj.key for obj in result.objects],
            "wavelength_processing": result.wavelength_processing,
            "target_processings": result.target_processings,
            "manifest_path": result.manifest_path,
            "operation_log_path": result.operation_log_path,
            "files": [
                {
                    "key": item.obj.key,
                    "path": item.target,
                    "status": item.status,
                    "message": item.message,
                    "expected_bytes": item.obj.size,
                }
                for item in result.download_results
            ],
            "interpolated_products": result.interpolated_products,
        }
    )


@dataclass
class RetrievalRunResult:
    output_dir: Path
    report_path: Path
    results: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    requests: dict = field(default_factory=dict)

    @property
    def status_code(self):
        return int(bool(self.errors))

    @property
    def single(self):
        if len(self.results) != 1 or self.errors:
            raise ScattError("This run does not contain exactly one successful retrieval")
        return next(iter(self.results.values()))

    def to_dict(self):
        entries = {}
        for name, request in self.requests.items():
            entry = {
                "request": _plain(request),
                "status": "failed" if name in self.errors else "completed",
            }
            if name in self.results:
                entry.update(self.results[name].to_dict())
            if name in self.errors:
                entry["error"] = self.errors[name]
                entry["status_code"] = 1
            entries[name] = entry
        for name, error in self.errors.items():
            entries.setdefault(name, {"status": "failed", "status_code": 1, "error": error})
        return {
            "status_code": self.status_code,
            "output_dir": str(self.output_dir),
            "species": entries,
        }


class RetrievalRunError(ScattError):
    """An incomplete batch; successful results and the report remain accessible."""

    def __init__(self, result):
        self.result = result
        super().__init__(
            f"Retrieval failed for {', '.join(result.errors)}. Report: {result.report_path}"
        )


@_registration_required
def load_retrieval_config(config):
    """Read a trusted Python retrieval dictionary, JSON, or an in-memory mapping."""
    import copy

    base = Path.cwd()
    if isinstance(config, (str, Path)):
        path = Path(config).expanduser().resolve()
        base = path.parent
        if path.suffix.lower() == ".py":
            value = runpy.run_path(str(path)).get("retrieval")
        elif path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            raise ValueError("Retrieval input must be Python or JSON")
    else:
        value = config
    if isinstance(value, Mapping) and "retrieval" in value:
        value = value["retrieval"]
    if not isinstance(value, Mapping):
        raise ValueError("Input must define retrieval as a mapping")
    value = copy.deepcopy(dict(value))

    def resolve(entry):
        for key in (
            "output_dir",
            "manifest",
            "interpolation_output_dir",
            "manifest_output",
            "operation_log",
        ):
            if entry.get(key) is not None:
                path = Path(entry[key]).expanduser()
                entry[key] = path if path.is_absolute() else (base / path).resolve()

    resolve(value)
    for group in ("requests", "overrides"):
        if isinstance(value.get(group), Mapping):
            for entry in value[group].values():
                if isinstance(entry, Mapping):
                    resolve(entry)
    return value


def _requests(config):
    from zju_scatt_interface.config.particles import (
        get_particle_profile,
        list_particle_profiles,
    )

    config = dict(config)
    requested = config.pop("requests", None)
    overrides = config.pop("overrides", {})
    all_species = requested == "all" or config.get("particle_types") == "all"
    if all_species:
        config.pop("particle_types", None)
        requested = {profile.particle_type: {} for profile in list_particle_profiles()}
    elif requested is None:
        types = config.get("particle_types")
        if types is None:
            raise ValueError("Specify particle_types or named requests")
        types = [types] if isinstance(types, str) else list(types)
        if len(types) == 1:
            family = get_particle_profile(types[0]).particle_type
            requested = {family: {"particle_types": family}}
        else:
            requested = {get_particle_profile(name).particle_type: {} for name in types}
            config.pop("particle_types", None)
    if not isinstance(requested, Mapping) or not requested:
        raise ValueError("requests must be a nonempty mapping or 'all'")
    normalized = {
        get_particle_profile(key).particle_type: value for key, value in overrides.items()
    }
    jobs = {}
    for name, entry in requested.items():
        if not isinstance(name, str) or name in (".", "..") or any(c in name for c in "/\\"):
            raise ValueError(f"Invalid retrieval job name: {name!r}")
        if not isinstance(entry, Mapping):
            raise ValueError(f"{name}: request must be a mapping")
        family = get_particle_profile(entry.get("particle_types", name)).particle_type
        jobs[name] = {**config, "particle_types": family, **normalized.get(family, {}), **entry}
    unused = set(normalized) - {
        get_particle_profile(job["particle_types"]).particle_type for job in jobs.values()
    }
    if unused:
        raise ValueError(f"Overrides do not belong to selected species: {sorted(unused)}")
    return jobs, all_species


def _discover_all(jobs, client):
    """Audit completeness against a live listing, or against saved manifests."""
    from zju_scatt_interface.access.endpoints import ROOT_PREFIX
    from zju_scatt_interface.access.manifests import load_manifest
    from zju_scatt_interface.config.particles import list_particle_profiles

    known = {
        profile.database_directory: profile.particle_type for profile in list_particle_profiles()
    }
    if all(job.get("manifest") is not None for job in jobs.values()):
        objects = []
        for path in dict.fromkeys(job["manifest"] for job in jobs.values()):
            objects.extend(load_manifest(path))
        directories = {
            obj.key.replace("\\", "/").split("Single_opt/", 1)[1].split("/", 1)[0]
            for obj in objects
            if "Single_opt/" in obj.key.replace("\\", "/")
        }
    else:
        directories = {
            obj.key.rstrip("/").rsplit("/", 1)[-1]
            for obj in client.list_directory(ROOT_PREFIX + "Single_opt/")[0]
        }
    errors = {
        name: "Live/saved species has no registered interface profile"
        for name in directories - set(known)
    }
    errors.update(
        {
            family: "Registered species is absent from the live listing/saved catalog"
            for name, family in known.items()
            if name not in directories
        }
    )
    return errors


@_registration_required
def retrieve(
    config,
    *,
    download=None,
    output_dir=None,
    manifest=None,
    overwrite=None,
    diagnostics=None,
    client=None,
):
    """Retrieve one or many populations with standard validation and reports.

    Defaults to downloading, native interpolation, concise progress and strict
    completion checks. Preview with download=False. All jobs are attempted;
    partial failures write their report before RetrievalRunError is raised.
    """
    pass

    config = load_retrieval_config(config)
    for key, value in (("download", download), ("overwrite", overwrite), ("manifest", manifest)):
        if value is not None:
            config[key] = Path(value).expanduser().resolve() if key == "manifest" else value
    directory = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else Path(config.get("output_dir", "retrieved_data"))
    )
    verbose = config.pop("diagnostics", False) if diagnostics is None else diagnostics
    config.pop("diagnostics", None)
    quiet = config.pop("quiet", False)
    config["output_dir"] = directory
    config.setdefault("download", True)
    jobs, all_species = _requests(config)
    batch = "requests" in config or len(jobs) > 1 or all_species
    for name, job in jobs.items():
        # Explicit invocation options override even per-request input settings.
        # In particular, a preview must never inherit download=True from a job.
        for key, value in (
            ("download", download),
            ("overwrite", overwrite),
            ("manifest", manifest),
        ):
            if value is not None:
                job[key] = config[key]
        if not isinstance(job["download"], bool):
            raise ValueError("download must be a boolean")
        entries = config.get("requests", {})
        explicit = entries.get(name, {}) if isinstance(entries, Mapping) else {}
        if batch and "output_dir" not in explicit:
            job["output_dir"] = directory / name
        job.setdefault("quiet", not verbose)
        job.setdefault("manifest_output", Path(job["output_dir"]) / "selection_manifest.jsonl")
        # Resolve and validate options before creating files or opening the network.
        _domain_access_requests.make_retrieval_args(
            **{
                key: value
                for key, value in job.items()
                if key not in {"timeout", "retries", "insecure"}
            }
        )
    run = RetrievalRunResult(directory, directory / "retrieval_report.json", requests=jobs)
    directory.mkdir(parents=True, exist_ok=True)
    if all_species:
        active = client or _domain_access_client.ApiClient(
            timeout=config.get("timeout", 30),
            retries=config.get("retries", 3),
            insecure=config.get("insecure", False),
        )
        try:
            run.errors.update(_discover_all(jobs, active))
        except Exception as exc:
            run.errors["species_discovery"] = f"{type(exc).__name__}: {exc}"
    for name, job in jobs.items():
        if name not in run.errors:
            try:
                result = _domain_access_retrieval.retrieve_sources(client=client, **job)
                run.results[name] = result
                result.raise_for_status(
                    download=job["download"],
                    require_matches=True,
                    require_products=job["download"] and job.get("apply_interpolation", True),
                )
                result.write_report(Path(job["output_dir"]) / "retrieval_report.json")
                if not quiet:
                    notices = set()
                    for resolution in result.wavelength_processing.refractive_index_resolutions:
                        if resolution.get("used_default"):
                            notice = f"{resolution['message']} RI: {resolution['target_indices']}; tables: {resolution.get('table_relative_paths', {})}"
                            if notice not in notices:
                                print(notice, flush=True)
                                notices.add(notice)
                    print(
                        f"{name}: {len(result.objects)} sources, {len(result.interpolated_products)} derived products; "
                        f"{'downloaded' if job['download'] else 'selected only'} -> {job['output_dir']}",
                        flush=True,
                    )
            except Exception as exc:
                run.errors[name] = f"{type(exc).__name__}: {exc}"
                if not quiet:
                    print(f"{name}: failed: {exc}", flush=True)
        _write_json(run.report_path, run.to_dict())
    if not quiet:
        print(f"Retrieval report: {run.report_path}", flush=True)
    if run.errors:
        raise RetrievalRunError(run)
    return run
