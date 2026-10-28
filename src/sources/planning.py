"""sources / planning domain implementation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple, Union

import zju_scatt_interface.access.catalog as _domain_access_catalog
import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.config.particles import (
    get_particle_profile,
)
from zju_scatt_interface.config.scheme import Scheme
from zju_scatt_interface.sources.validation import inspect_source_file

PLAN_SCHEMA_VERSION = "1.0"
DEFAULT_WORKSPACE = Path("zju_scatt_data")

SearchFunction = Callable[["DependencyQuery"], Sequence[_domain_access_models.RemoteObject]]
DownloadFunction = Callable[
    [Sequence[_domain_access_models.RemoteObject], "WorkspaceLayout"],
    Sequence[_domain_access_models.DownloadResult],
]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_text(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _values(value: object) -> Tuple[object, ...]:
    if isinstance(value, Mapping):
        value = value.get("values", value.get("value"))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return () if value is None else (value,)


def _finite_values(value: object, label: str) -> Tuple[float, ...]:
    result = []
    for item in _values(value):
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("{} must contain finite values".format(label))
        result.append(number)
    return tuple(result)


@dataclass(frozen=True)
class WorkspaceLayout:
    """Deterministic directories used by a scheme source build."""

    root: Path
    cache_dir: Path
    work_dir: Path
    manifest_dir: Path
    output_file: Path

    @classmethod
    def create(
        cls,
        root: Union[str, Path],
        output: Union[str, Path],
    ) -> "WorkspaceLayout":
        root_path = Path(root).expanduser().resolve()
        requested_output = Path(output).expanduser()
        output_file = (
            requested_output.resolve()
            if requested_output.is_absolute()
            else root_path / requested_output
        )
        result = cls(
            root=root_path,
            cache_dir=root_path / "cache",
            work_dir=root_path / "work",
            manifest_dir=root_path / "manifests",
            output_file=output_file,
        )
        for directory in (
            result.root,
            result.cache_dir,
            result.work_dir,
            result.manifest_dir,
            result.output_file.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return result

    def to_dict(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "cache_dir": str(self.cache_dir),
            "work_dir": str(self.work_dir),
            "manifest_dir": str(self.manifest_dir),
            "output_file": str(self.output_file),
        }


@dataclass(frozen=True)
class DependencyQuery:
    """One component-level remote source query."""

    component_name: str
    particle_type: str
    remote_source: str
    scientific_coordinates: Mapping[str, object]
    retrieval_parameters: Mapping[str, object]
    cache_key: str

    def to_dict(self) -> dict[str, object]:
        return {
            "component_name": self.component_name,
            "particle_type": self.particle_type,
            "remote_source": self.remote_source,
            "scientific_coordinates": dict(self.scientific_coordinates),
            "retrieval_parameters": dict(self.retrieval_parameters),
            "cache_key": self.cache_key,
        }


@dataclass(frozen=True)
class SourceEntry:
    """One expected remote object and its local validation state."""

    key: str
    size: int
    last_modified: str
    etag: str
    cache_path: Path
    component_names: Tuple[str, ...]
    query_keys: Tuple[str, ...]
    particle_type: str
    status: str
    validation_messages: Tuple[str, ...] = ()
    local_sha256: str = ""
    schema_validated: bool = False

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def remote_object(self) -> _domain_access_models.RemoteObject:
        return _domain_access_models.RemoteObject(
            key=self.key,
            size=self.size,
            last_modified=self.last_modified,
            etag=self.etag,
        )

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["cache_path"] = str(self.cache_path)
        result["component_names"] = list(self.component_names)
        result["query_keys"] = list(self.query_keys)
        result["validation_messages"] = list(self.validation_messages)
        result["url"] = self.remote_object().url
        return result


@dataclass(frozen=True)
class DependencyIssue:
    component_name: str
    query_key: str
    reason: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DependencyPlan:
    """Complete source/cache state for one validated bulk scheme."""

    schema_version: str
    scheme_name: str
    scheme_cache_key: str
    offline: bool
    workspace: WorkspaceLayout
    manifest_path: Path
    queries: Tuple[DependencyQuery, ...]
    sources: Tuple[SourceEntry, ...]
    issues: Tuple[DependencyIssue, ...]

    @property
    def complete(self) -> bool:
        return (
            bool(self.sources) and not self.issues and all(source.ready for source in self.sources)
        )

    @property
    def missing_count(self) -> int:
        return sum(not source.ready for source in self.sources) + len(
            [issue for issue in self.issues if not issue.query_key]
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scheme_name": self.scheme_name,
            "scheme_cache_key": self.scheme_cache_key,
            "offline": self.offline,
            "complete": self.complete,
            "workspace": self.workspace.to_dict(),
            "manifest_path": str(self.manifest_path),
            "queries": [query.to_dict() for query in self.queries],
            "sources": [source.to_dict() for source in self.sources],
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": {
                "query_count": len(self.queries),
                "source_count": len(self.sources),
                "ready_count": sum(source.ready for source in self.sources),
                "missing_or_invalid_count": sum(not source.ready for source in self.sources),
                "total_remote_bytes": sum(source.size for source in self.sources),
            },
        }

    def write(self) -> Path:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return self.manifest_path


def _scheme_identity(config: Scheme) -> Mapping[str, object]:
    return config.to_dict()


def _component_coordinates(config, component):
    from zju_scatt_interface.extensions.particles import get_particle_definition

    return get_particle_definition(component.particle_type).planner(config, component)


@_registration_required
def build_dependency_queries(
    config: Scheme,
) -> Tuple[DependencyQuery, ...]:
    """Compile every scheme component into one deterministic retrieval query."""

    queries = []
    for component in config.particles:
        profile = get_particle_profile(component.particle_type)
        coordinates, retrieval = _component_coordinates(config, component)
        identity = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "component_name": component.name,
            "particle_type": profile.particle_type,
            "coordinates": coordinates,
            "retrieval": retrieval,
        }
        queries.append(
            DependencyQuery(
                component_name=component.name,
                particle_type=profile.particle_type,
                remote_source=str(retrieval["sources"][0]),
                scientific_coordinates=coordinates,
                retrieval_parameters=retrieval,
                cache_key=_sha256_text(identity),
            )
        )
    return tuple(queries)


def _cache_path(obj: _domain_access_models.RemoteObject, layout: WorkspaceLayout) -> Path:
    return _domain_access_download.destination_for(obj, layout.cache_dir, flat=False)


def _saved_manifest(path: Path, scheme_cache_key: str) -> Optional[Mapping[str, object]]:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read dependency manifest {}: {}".format(path, exc)) from exc
    if value.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError(
            "dependency manifest {} uses unsupported schema version {!r}".format(
                path, value.get("schema_version")
            )
        )
    if value.get("scheme_cache_key") != scheme_cache_key:
        return None
    return value


def _objects_from_saved_manifest(
    saved: Mapping[str, object],
) -> tuple[dict[str, _domain_access_models.RemoteObject], dict[str, str]]:
    objects = {}
    hashes = {}
    for item in saved.get("sources", []):
        if not isinstance(item, Mapping) or not item.get("key"):
            continue
        obj = _domain_access_models.RemoteObject(
            key=str(item["key"]),
            size=int(item.get("size", 0)),
            last_modified=str(item.get("last_modified", "")),
            etag=str(item.get("etag", "")),
        )
        objects[obj.key] = obj
        if item.get("local_sha256"):
            hashes[obj.key] = str(item["local_sha256"])
    return objects, hashes


def _assess_source(
    obj: _domain_access_models.RemoteObject,
    *,
    layout: WorkspaceLayout,
    particle_type: str,
    component_names: Sequence[str],
    query_keys: Sequence[str],
    expected_sha256: str = "",
    validate_schema: bool,
) -> SourceEntry:
    path = _cache_path(obj, layout)
    messages = []
    status = "ready"
    sha256 = ""
    schema_validated = False
    if not path.is_file():
        status = "missing"
        messages.append("file is not present in the local cache")
    else:
        actual_size = path.stat().st_size
        if obj.size and actual_size != obj.size:
            status = "invalid_size"
            messages.append("size mismatch: expected {}, found {}".format(obj.size, actual_size))
        if status == "ready" and obj.etag and "-" not in obj.etag:
            actual_md5 = _file_digest(path, "md5")
            if actual_md5.lower() != obj.etag.lower():
                status = "invalid_hash"
                messages.append("local MD5 does not match the remote ETag")
        if status == "ready":
            sha256 = _file_digest(path, "sha256")
            if expected_sha256 and sha256.lower() != expected_sha256.lower():
                status = "invalid_hash"
                messages.append("local SHA-256 differs from the saved manifest")
        if status == "ready" and validate_schema:
            try:
                inspection = inspect_source_file(path, particle_type)
            except (OSError, RuntimeError, ValueError) as exc:
                status = "invalid_schema"
                messages.append("schema inspection failed: {}".format(exc))
            else:
                schema_validated = True
                if not inspection.valid:
                    status = "invalid_schema"
                    messages.extend(inspection.errors)
    return SourceEntry(
        key=obj.key,
        size=obj.size,
        last_modified=obj.last_modified,
        etag=obj.etag,
        cache_path=path,
        component_names=tuple(sorted(set(component_names))),
        query_keys=tuple(sorted(set(query_keys))),
        particle_type=particle_type,
        status=status,
        validation_messages=tuple(messages),
        local_sha256=sha256,
        schema_validated=schema_validated,
    )


def _default_search(
    query: DependencyQuery,
    *,
    client: Optional[_domain_access_client.ApiClient],
) -> Sequence[_domain_access_models.RemoteObject]:
    result = _domain_access_retrieval.retrieve_sources(client=client, **query.retrieval_parameters)
    if result.status_code:
        raise RuntimeError("retrieval query failed with status {}".format(result.status_code))
    return result.objects


def _default_download(
    objects: Sequence[_domain_access_models.RemoteObject],
    layout: WorkspaceLayout,
    *,
    client: Optional[_domain_access_client.ApiClient],
    session: Optional[str],
    no_track: bool,
    resume: bool,
) -> Sequence[_domain_access_models.DownloadResult]:
    return _domain_access_retrieval.download_data(
        objects,
        output_dir=layout.cache_dir,
        client=client,
        overwrite=True,
        resume=resume,
        verify_etag=True,
        session=session,
        no_track=no_track,
        quiet=True,
    )


@_registration_required
def prepare_scheme_dependencies(
    config: Scheme,
    *,
    workspace: Union[str, Path] = DEFAULT_WORKSPACE,
    offline: bool = False,
    download: bool = True,
    validate_schema: bool = True,
    client: Optional[_domain_access_client.ApiClient] = None,
    session: Optional[str] = None,
    no_track: bool = False,
    resume: bool = True,
    searcher: Optional[SearchFunction] = None,
    downloader: Optional[DownloadFunction] = None,
    reuse_dirs: Sequence[Union[str, Path]] = (),
) -> DependencyPlan:
    """Plan, optionally download, validate, and manifest all scheme source files."""

    layout = WorkspaceLayout.create(workspace, config.output)
    scheme_cache_key = _sha256_text(_scheme_identity(config))
    manifest_path = layout.manifest_dir / (
        "{}-{}.sources.json".format(
            "".join(
                character if character.isalnum() or character in "-_" else "_"
                for character in config.name
            ),
            scheme_cache_key[:16],
        )
    )
    queries = build_dependency_queries(config)
    saved = _saved_manifest(manifest_path, scheme_cache_key)
    saved_objects, saved_hashes = (
        _objects_from_saved_manifest(saved) if saved is not None else ({}, {})
    )

    query_objects: dict[str, list[_domain_access_models.RemoteObject]] = {}
    issues = []
    if offline:
        for query in queries:
            matched = (
                [
                    obj
                    for obj in saved_objects.values()
                    if any(
                        query.cache_key == key
                        for item in saved.get("sources", [])
                        if isinstance(item, Mapping) and item.get("key") == obj.key
                        for key in item.get("query_keys", [])
                    )
                ]
                if saved is not None
                else []
            )
            query_objects[query.cache_key] = matched
            if not matched:
                issues.append(
                    DependencyIssue(
                        component_name=query.component_name,
                        query_key=query.cache_key,
                        reason="no saved remote dependency list is available",
                        action=(
                            "run the same command once without --offline while "
                            "connected to the ZJU-SCATT service"
                        ),
                    )
                )
    else:
        for query in queries:
            try:
                matched = list(
                    searcher(query)
                    if searcher is not None
                    else _default_search(query, client=client)
                )
            except Exception as exc:
                matched = []
                issues.append(
                    DependencyIssue(
                        component_name=query.component_name,
                        query_key=query.cache_key,
                        reason="remote search failed: {}".format(exc),
                        action="check connectivity/session and retry; no cache files were removed",
                    )
                )
            query_objects[query.cache_key] = matched
            if not matched and not any(issue.query_key == query.cache_key for issue in issues):
                issues.append(
                    DependencyIssue(
                        component_name=query.component_name,
                        query_key=query.cache_key,
                        reason="the query returned no source files",
                        action=(
                            "review particle coordinates and database coverage with "
                            "'zju-scatt describe {}'".format(query.particle_type)
                        ),
                    )
                )

    object_links: dict[str, dict[str, object]] = {}
    query_index = {query.cache_key: query for query in queries}
    for query_key, objects in query_objects.items():
        query = query_index[query_key]
        for obj in objects:
            link = object_links.setdefault(
                obj.key,
                {
                    "object": obj,
                    "components": set(),
                    "queries": set(),
                    "particle_type": query.particle_type,
                },
            )
            link["components"].add(query.component_name)
            link["queries"].add(query.cache_key)

    def assess_all() -> Tuple[SourceEntry, ...]:
        return tuple(
            _assess_source(
                link["object"],
                layout=layout,
                particle_type=str(link["particle_type"]),
                component_names=sorted(link["components"]),
                query_keys=sorted(link["queries"]),
                expected_sha256=saved_hashes.get(key, "") if offline else "",
                validate_schema=validate_schema,
            )
            for key, link in sorted(object_links.items())
        )

    # Import earlier downloads into the verified cache without relying on a
    # basename and byte count alone. Prefer a complete remote-key suffix; flat
    # caches require a matching content hash. No source files are moved/deleted.
    sources = assess_all()
    if reuse_dirs and any(not source.ready for source in sources):
        import shutil

        candidates = {}
        for directory in reuse_dirs:
            for path in Path(directory).expanduser().rglob("*.nc"):
                candidates.setdefault(path.name, []).append(path)
        for source in sources:
            if source.ready:
                continue
            obj = source.remote_object()
            target = Path(source.cache_path)
            relative = _domain_access_catalog.relative_remote_key(obj.key).replace("\\", "/")
            for candidate in candidates.get(target.name, ()):
                if candidate.resolve() == target.resolve() or candidate.stat().st_size != obj.size:
                    continue
                key_match = candidate.as_posix().endswith("/" + relative)
                content_match = False
                if obj.etag and "-" not in obj.etag:
                    content_match = _file_digest(candidate, "md5").lower() == obj.etag.lower()
                    if not content_match:
                        continue
                elif saved_hashes.get(obj.key):
                    content_match = _file_digest(candidate, "sha256") == saved_hashes[obj.key]
                    if not content_match:
                        continue
                if not key_match and not content_match:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".reuse.tmp")
                shutil.copy2(candidate, temporary)
                temporary.replace(target)
                break
        sources = assess_all()
    if download and not offline:
        pending = [source.remote_object() for source in sources if not source.ready]
        if pending:
            results = list(
                downloader(pending, layout)
                if downloader is not None
                else _default_download(
                    pending,
                    layout,
                    client=client,
                    session=session,
                    no_track=no_track,
                    resume=resume,
                )
            )
            failed = [result for result in results if result.status == "failed"]
            for result in failed:
                issues.append(
                    DependencyIssue(
                        component_name=", ".join(object_links[result.obj.key]["components"]),
                        query_key="",
                        reason="download failed for {}: {}".format(result.obj.key, result.message),
                        action="retry; resumable .part files are preserved",
                    )
                )
            sources = assess_all()

    for source in sources:
        if not source.ready:
            issues.append(
                DependencyIssue(
                    component_name=", ".join(source.component_names),
                    query_key=", ".join(source.query_keys),
                    reason="{}: {}".format(
                        source.status,
                        "; ".join(source.validation_messages),
                    ),
                    action=(
                        "reconnect and rerun without --offline"
                        if offline
                        else "retry download or inspect the source schema"
                    ),
                )
            )

    plan = DependencyPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        scheme_name=config.name,
        scheme_cache_key=scheme_cache_key,
        offline=offline,
        workspace=layout,
        manifest_path=manifest_path,
        queries=queries,
        sources=sources,
        issues=tuple(issues),
    )
    plan.write()
    return plan
