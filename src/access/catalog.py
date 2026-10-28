"""Remote paths, catalog traversal, searching and estimation."""

from __future__ import annotations

import argparse
import urllib.error
import urllib.parse
import urllib.request
import urllib.response
from pathlib import PurePosixPath
from typing import Iterable, Optional, Sequence

from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.endpoints import (
    DOWNLOAD_PAGE_URL,
    OSS_BASE_URL,
    ROOT_PREFIX,
)
from zju_scatt_interface.access.filters import FilterSpec
from zju_scatt_interface.access.models import RemoteObject, ScanStats
from zju_scatt_interface.errors import ScattError


def object_url(key: str) -> str:
    return f"{OSS_BASE_URL}/{urllib.parse.quote(key.lstrip('/'), safe='/')}"


def download_page_url(key: str) -> str:
    prefix = ensure_directory_prefix(key)
    return f"{DOWNLOAD_PAGE_URL}?{urllib.parse.urlencode({'path': prefix})}"


def resolve_remote_path(value: Optional[str]) -> str:
    """Accept a relative path, full OSS key, download-page URL, or object URL."""
    from zju_scatt_interface.access.endpoints import OSS_BASE_URL, ROOT_PREFIX

    if not value or value in {".", "/"}:
        return ROOT_PREFIX
    value = value.strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        if host == urllib.parse.urlparse(DOWNLOAD_PAGE_URL).netloc.lower():
            if parsed.path.rstrip("/") == "/download":
                query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                value = query.get("path", [ROOT_PREFIX])[0]
            else:
                raise ScattError("Website URLs must be /download URLs containing a path query")
        elif host == urllib.parse.urlparse(OSS_BASE_URL).netloc.lower():
            value = urllib.parse.unquote(parsed.path.lstrip("/"))
        else:
            raise ScattError(f"Unsupported remote URL host: {parsed.netloc}")
    value = urllib.parse.unquote(value).replace("\\", "/").lstrip("/")
    parts = PurePosixPath(value).parts
    if any(part in {".", ".."} for part in parts):
        raise ScattError("Remote paths cannot contain '.' or '..' components")
    if value.startswith("data-service-dev-repo/"):
        return value
    return ROOT_PREFIX + value


def ensure_directory_prefix(value: str) -> str:
    return value if value.endswith("/") else value + "/"


def discover_source(client: ApiClient, source: str) -> tuple[str, Optional[RemoteObject]]:
    key = resolve_remote_path(source)
    if key.endswith("/"):
        return key, None
    obj = client.stat_object(key)
    if obj is not None:
        return key, obj
    return ensure_directory_prefix(key), None


def scan_sources(
    client: ApiClient,
    sources: Sequence[str],
    spec: FilterSpec,
    *,
    max_scan: Optional[int] = None,
    quiet: bool = False,
) -> tuple[list[RemoteObject], ScanStats]:
    from zju_scatt_interface.access.models import ScanStats
    from zju_scatt_interface.access.progress import ScanActivity

    stats = ScanStats()
    matches: dict[str, RemoteObject] = {}
    activity = ScanActivity(enabled=not quiet)

    def on_page(_page: int, count: int) -> None:
        stats.pages += 1
        activity.update(stats.pages, stats.scanned + count)

    stop = False
    try:
        for source in sources:
            key, exact_object = discover_source(client, source)
            iterator: Iterable[RemoteObject]
            if exact_object is not None:
                iterator = [exact_object]
            else:
                iterator = client.iter_objects(key, on_page=on_page)
            for obj in iterator:
                if max_scan is not None and stats.scanned >= max_scan:
                    stop = True
                    break
                stats.scanned += 1
                if spec.matches(obj):
                    matches[obj.key] = obj
            if stop:
                break
    finally:
        activity.close()
    result = sorted(matches.values(), key=lambda item: item.key)
    stats.matched = len(result)
    stats.bytes = sum(item.size for item in result)
    return result, stats


def relative_remote_key(key: str) -> str:
    return key[len(ROOT_PREFIX) :] if key.startswith(ROOT_PREFIX) else key


def objects_from_args(
    args: argparse.Namespace, client: ApiClient
) -> tuple[list[RemoteObject], ScanStats]:
    from zju_scatt_interface.access.filters import compile_filter
    from zju_scatt_interface.access.manifests import load_manifest
    from zju_scatt_interface.access.models import ScanStats
    from zju_scatt_interface.access.registration import require_registration

    client.registration_token = require_registration(getattr(args, "session", None))
    spec = compile_filter(args)
    manifest = getattr(args, "manifest", None)
    if manifest:
        all_objects = load_manifest(manifest)
        objects = [item for item in all_objects if spec.matches(item)]
        return objects, ScanStats(
            pages=0,
            scanned=len(all_objects),
            matched=len(objects),
            bytes=sum(item.size for item in objects),
        )
    sources = getattr(args, "source", None) or [ROOT_PREFIX]
    if isinstance(sources, str):
        sources = [sources]
    return scan_sources(
        client,
        sources,
        spec,
        max_scan=getattr(args, "max_scan", None),
        quiet=getattr(args, "quiet", False),
    )
