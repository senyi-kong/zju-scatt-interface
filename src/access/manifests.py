"""Catalog manifests and remote-object serialization."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

from zju_scatt_interface.access.models import RemoteObject
from zju_scatt_interface.errors import ScattError


def infer_manifest_format(path: Path, requested: Optional[str]) -> str:
    if requested:
        return requested
    suffix = path.suffix.lower()
    return {".csv": "csv", ".jsonl": "jsonl", ".json": "jsonl"}.get(suffix, "txt")


def write_manifest(
    objects: Sequence[RemoteObject], path: Path, format_name: Optional[str] = None
) -> None:
    format_name = infer_manifest_format(path, format_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if format_name == "csv":
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=["key", "size", "last_modified", "etag", "url"]
            )
            writer.writeheader()
            for item in objects:
                writer.writerow({**asdict(item), "url": item.url})
    elif format_name == "jsonl":
        with path.open("w", encoding="utf-8") as stream:
            for item in objects:
                stream.write(json.dumps({**asdict(item), "url": item.url}) + "\n")
    else:
        with path.open("w", encoding="utf-8") as stream:
            for item in objects:
                stream.write(f"{item.key}\t{item.size}\t{item.last_modified}\t{item.etag}\n")


def load_manifest(path: Path) -> list[RemoteObject]:
    from zju_scatt_interface.access.catalog import resolve_remote_path
    from zju_scatt_interface.access.models import RemoteObject

    if not path.exists():
        raise ScattError(f"Manifest does not exist: {path}")
    format_name = infer_manifest_format(path, None)
    objects: list[RemoteObject] = []
    if format_name == "csv":
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                if row.get("key"):
                    objects.append(object_from_mapping(row))
    elif format_name == "jsonl":
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ScattError(f"Invalid JSON on line {line_number} of {path}") from exc
                objects.append(object_from_mapping(row))
    else:
        with path.open("r", encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = line.rstrip("\n").split("\t")
                key = parts[0]
                if key.startswith(("http://", "https://")):
                    key = resolve_remote_path(key)
                objects.append(
                    RemoteObject(
                        key=key,
                        size=safe_int(parts[1]) if len(parts) > 1 else 0,
                        last_modified=parts[2] if len(parts) > 2 else "",
                        etag=parts[3] if len(parts) > 3 else "",
                    )
                )
    return sorted({item.key: item for item in objects}.values(), key=lambda item: item.key)


def safe_int(value: object) -> int:
    try:
        return int(str(value or 0))
    except ValueError:
        return 0


def object_from_mapping(row: dict) -> RemoteObject:
    from zju_scatt_interface.access.models import RemoteObject

    key = str(row.get("key") or "")
    if not key:
        raise ScattError("Manifest entry has no key")
    return RemoteObject(
        key=key,
        size=safe_int(row.get("size")),
        last_modified=str(row.get("last_modified") or ""),
        etag=str(row.get("etag") or "").strip('"'),
    )
