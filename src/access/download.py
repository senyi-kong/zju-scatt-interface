"""Verified resumable downloads and transfer concurrency."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.models import DownloadResult, RemoteObject, ScanStats
from zju_scatt_interface.errors import NetworkError, ScattError
from zju_scatt_interface.io.paths import filesystem_path

WINDOWS_INVALID_CHARS = re.compile(r'[<>:"\\|?*]')


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_component(component: str) -> str:
    value = WINDOWS_INVALID_CHARS.sub("_", component).rstrip(" .")
    if not value:
        value = "_"
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        value = "_" + value
    return value


def destination_for(obj: RemoteObject, output_dir: Path, flat: bool) -> Path:
    from zju_scatt_interface.access.catalog import relative_remote_key

    relative = PurePosixPath(relative_remote_key(obj.key))
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ScattError(f"Unsafe remote key: {obj.key}")
    chosen = (parts[-1],) if flat else parts
    target = output_dir.joinpath(*(sanitize_component(part) for part in chosen))
    output_resolved = output_dir.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(output_resolved)
    except ValueError as exc:
        raise ScattError(f"Unsafe local destination for {obj.key}") from exc
    return target


def download_one(
    client: ApiClient,
    obj: RemoteObject,
    target: Path,
    *,
    resume: bool,
    overwrite: bool,
    verify_etag: bool,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> DownloadResult:
    from zju_scatt_interface.access.models import DownloadResult

    local_target = filesystem_path(target)
    local_target.parent.mkdir(parents=True, exist_ok=True)
    if local_target.exists():
        if obj.size and local_target.stat().st_size == obj.size and not overwrite:
            return DownloadResult(obj, target, "skipped", "already complete")
        if not overwrite:
            return DownloadResult(
                obj,
                target,
                "failed",
                "destination exists with a different size (use --overwrite)",
            )

    partial = local_target.with_name(local_target.name + ".part")
    offset = partial.stat().st_size if resume and partial.exists() else 0
    if obj.size and offset > obj.size:
        offset = 0
    if obj.size and offset == obj.size:
        if verify_etag and obj.etag and "-" not in obj.etag:
            if file_md5(partial).lower() != obj.etag.lower():
                return DownloadResult(obj, target, "failed", "MD5/ETag mismatch; partial file kept")
        os.replace(partial, local_target)
        return DownloadResult(obj, target, "downloaded", "completed from .part file")
    headers: dict[str, str] = {}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    try:
        with client._request(obj.url, headers=headers) as response:
            status = getattr(response, "status", response.getcode())
            append = bool(offset and status == 206)
            mode = "ab" if append else "wb"
            with partial.open(mode) as stream:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    if progress_callback:
                        progress_callback(len(chunk))
    except Exception as exc:
        return DownloadResult(obj, target, "failed", str(exc))

    actual_size = partial.stat().st_size
    if obj.size and actual_size != obj.size:
        return DownloadResult(
            obj,
            target,
            "failed",
            f"size mismatch: expected {obj.size}, received {actual_size}; partial file kept",
        )
    if verify_etag and obj.etag and "-" not in obj.etag:
        digest = file_md5(partial)
        if digest.lower() != obj.etag.lower():
            return DownloadResult(
                obj,
                target,
                "failed",
                "MD5/ETag mismatch; partial file kept",
            )
    os.replace(partial, local_target)
    return DownloadResult(obj, target, "downloaded")


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def limit_download_set(
    objects: list[RemoteObject], max_files: Optional[int], max_bytes: Optional[int]
) -> list[RemoteObject]:
    if max_files is not None:
        objects = objects[:max_files]
    if max_bytes is not None:
        selected: list[RemoteObject] = []
        total = 0
        for item in objects:
            if selected and total + item.size > max_bytes:
                break
            if item.size > max_bytes and not selected:
                break
            selected.append(item)
            total += item.size
        objects = selected
    return objects


def download_selected_objects(
    args: argparse.Namespace,
    client: ApiClient,
    objects: list[RemoteObject],
    stats: ScanStats,
) -> tuple[int, list[DownloadResult]]:
    from zju_scatt_interface.access.catalog import relative_remote_key
    from zju_scatt_interface.access.filters import human_size
    from zju_scatt_interface.access.progress import (
        DownloadProgress,
        print_summary,
        print_table,
    )
    from zju_scatt_interface.access.registration import require_tracking_session
    from zju_scatt_interface.errors import ScattError

    if not objects:
        print("No files matched; nothing to download.")
        return 0, []

    output_dir = args.output_dir.expanduser().resolve()
    targets: dict[Path, RemoteObject] = {}
    for obj in objects:
        target = destination_for(obj, output_dir, args.flat)
        if target in targets and targets[target].key != obj.key:
            raise ScattError(
                f"Destination collision: {targets[target].key} and {obj.key} both map to {target}"
            )
        targets[target] = obj

    print_summary(stats, label="Selected")
    print(f"Destination: {output_dir}")
    existing_dir = output_dir
    while not existing_dir.exists() and existing_dir != existing_dir.parent:
        existing_dir = existing_dir.parent
    free = shutil.disk_usage(existing_dir).free
    print(f"Free disk space: {human_size(free)}")
    if stats.bytes and stats.bytes > free and not args.ignore_space:
        raise ScattError(
            "Selected files exceed free disk space; choose another destination or use --ignore-space"
        )
    if args.dry_run:
        print_table(objects, limit=args.display_limit, include_urls=args.urls)
        print("Dry run: no files were downloaded.")
        return 0, []
    if not args.yes:
        if not sys.stdin.isatty():
            raise ScattError("Use --yes for non-interactive downloads")
        answer = input(f"Download {len(objects):,} files? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Cancelled.")
            return 0, []

    token = require_tracking_session(
        client,
        explicit_token=args.session,
        no_track=args.no_track,
    )
    if token:
        try:
            client.track_event(token, objects[0].key, "page_access")
        except NetworkError as exc:
            print(f"Warning: could not record page access: {exc}", file=sys.stderr)

    output_dir.mkdir(parents=True, exist_ok=True)
    progress = DownloadProgress(
        stats.bytes,
        len(objects),
        enabled=not args.no_progress,
    )
    observed_bytes: dict[str, int] = {obj.key: 0 for obj in objects}
    observed_lock = threading.Lock()

    def progress_callback(key: str) -> Callable[[int], None]:
        def update(amount: int) -> None:
            with observed_lock:
                observed_bytes[key] += amount
            progress.advance_network(amount)

        return update

    results: list[DownloadResult] = []
    future_map = {}
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(
                    download_one,
                    client,
                    obj,
                    target,
                    resume=not args.no_resume,
                    overwrite=args.overwrite,
                    verify_etag=args.verify_etag,
                    progress_callback=progress_callback(obj.key),
                ): (obj, target)
                for target, obj in targets.items()
            }
            for future in as_completed(future_map):
                result = future.result()
                results.append(result)
                with observed_lock:
                    observed = observed_bytes[result.obj.key]
                progress.finish_file(result.obj, observed, result.status)
                marker = {
                    "downloaded": "OK",
                    "skipped": "SKIP",
                    "failed": "FAIL",
                }[result.status]
                detail = f" - {result.message}" if result.message else ""
                progress.write(f"[{marker}] {relative_remote_key(result.obj.key)}{detail}")
                if result.status == "downloaded" and token:
                    try:
                        client.track_event(token, result.obj.key, "file_download")
                    except NetworkError as exc:
                        progress.write(
                            f"Warning: download completed but tracking failed: {exc}",
                            error=True,
                        )
    except KeyboardInterrupt:
        for future in future_map:
            future.cancel()
        progress.close()
        print("Interrupted. Partial .part files were kept for resume.", file=sys.stderr)
        return 130, results
    finally:
        progress.close()

    counts = {
        status: sum(result.status == status for result in results)
        for status in ("downloaded", "skipped", "failed")
    }
    print(
        f"Finished: {counts['downloaded']} downloaded, {counts['skipped']} skipped, "
        f"{counts['failed']} failed."
    )
    return 2 if counts["failed"] else 0, results
