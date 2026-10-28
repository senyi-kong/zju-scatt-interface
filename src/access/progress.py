"""Transfer/scan progress reporting and readable summaries."""

from __future__ import annotations

import sys
import threading
import time
from typing import Sequence

from zju_scatt_interface.access.models import RemoteObject, ScanStats


class ScanActivity:
    """Indeterminate terminal indicator for paginated remote scans."""

    FRAMES = (
        "[=       ]",
        "[ ==     ]",
        "[  ===   ]",
        "[    ==  ]",
        "[      = ]",
        "[    ==  ]",
        "[  ===   ]",
        "[ ==     ]",
    )

    def __init__(self, *, enabled: bool = True, stream=None) -> None:
        self.stream = stream or sys.stderr
        self.enabled = enabled
        self.interactive = enabled and self.stream.isatty()
        self.started = time.monotonic()
        self.rendered = False
        self.last_fallback_page = 0

    def update(self, pages: int, objects: int) -> None:
        from zju_scatt_interface.access.filters import human_duration

        elapsed = time.monotonic() - self.started
        if self.interactive:
            frame = self.FRAMES[(pages - 1) % len(self.FRAMES)]
            self.stream.write(
                f"\r\033[2KScanning {frame} {pages:,} pages | "
                f"{objects:,} objects | {human_duration(elapsed)}"
            )
            self.stream.flush()
            self.rendered = True
        elif self.enabled and pages - self.last_fallback_page >= 10:
            print(
                f"Scanning: {pages:,} pages, about {objects:,} objects...",
                file=self.stream,
            )
            self.last_fallback_page = pages

    def close(self) -> None:
        if self.rendered:
            self.stream.write("\r\033[2K")
            self.stream.flush()
            self.rendered = False


class DownloadProgress:
    """Thread-safe aggregate byte/file progress for concurrent downloads."""

    def __init__(
        self,
        total_bytes: int,
        total_files: int,
        *,
        enabled: bool = True,
        stream=None,
    ) -> None:
        self.total_bytes = max(0, total_bytes)
        self.total_files = max(0, total_files)
        self.completed_bytes = 0
        self.network_bytes = 0
        self.completed_files = 0
        self.started = time.monotonic()
        self.last_render = 0.0
        self.stream = stream or sys.stderr
        self.enabled = enabled and self.stream.isatty()
        self.rendered = False
        self.lock = threading.Lock()

    def advance_network(self, amount: int) -> None:
        if amount <= 0:
            return
        with self.lock:
            self.completed_bytes += amount
            self.network_bytes += amount
            self._render_locked()

    def finish_file(self, obj: RemoteObject, observed: int, status: str) -> None:
        with self.lock:
            if status in {"downloaded", "skipped"} and obj.size:
                self.completed_bytes += max(0, obj.size - observed)
            self.completed_files += 1
            self._render_locked(force=True)

    def write(self, message: str, *, error: bool = False) -> None:
        with self.lock:
            self._clear_locked()
            print(message, file=sys.stderr if error else sys.stdout)
            self._render_locked(force=True)

    def close(self) -> None:
        with self.lock:
            if self.rendered:
                self.stream.write("\n")
                self.stream.flush()
                self.rendered = False

    def _render_locked(self, force: bool = False) -> None:
        from zju_scatt_interface.access.filters import human_duration, human_size

        if not self.enabled:
            return
        now = time.monotonic()
        if not force and now - self.last_render < 0.1:
            return
        elapsed = max(now - self.started, 1e-6)
        if self.total_bytes:
            ratio = min(1.0, self.completed_bytes / self.total_bytes)
        elif self.total_files:
            ratio = min(1.0, self.completed_files / self.total_files)
        else:
            ratio = 1.0
        width = 24
        filled = min(width, int(ratio * width))
        bar = "#" * filled + "-" * (width - filled)
        rate = self.network_bytes / elapsed
        eta = "--"
        if self.total_bytes and rate > 0:
            eta = human_duration((self.total_bytes - self.completed_bytes) / rate)
        byte_text = (
            f"{human_size(min(self.completed_bytes, self.total_bytes))}/"
            f"{human_size(self.total_bytes)}"
            if self.total_bytes
            else "size unknown"
        )
        self.stream.write(
            f"\r\033[2KDownloading [{bar}] {ratio * 100:5.1f}% | "
            f"{byte_text} | {self.completed_files}/{self.total_files} files | "
            f"{human_size(int(rate))}/s | ETA {eta}"
        )
        self.stream.flush()
        self.last_render = now
        self.rendered = True

    def _clear_locked(self) -> None:
        if self.rendered:
            self.stream.write("\r\033[2K")
            self.stream.flush()
            self.rendered = False


def format_modified(value: str) -> str:
    from zju_scatt_interface.access.filters import parse_datetime

    parsed = parse_datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M UTC") if parsed else value or "-"


def print_table(
    objects: Sequence[RemoteObject], *, limit: int = 200, include_urls: bool = False
) -> None:
    from zju_scatt_interface.access.catalog import relative_remote_key
    from zju_scatt_interface.access.filters import human_size

    shown = objects if limit == 0 else objects[:limit]
    if not shown:
        print("No matching files.")
        return
    size_width = max(8, max(len(human_size(item.size)) for item in shown))
    print(f"{'SIZE':>{size_width}}  {'LAST MODIFIED':20}  PATH")
    print(f"{'-' * size_width}  {'-' * 20}  {'-' * 40}")
    for item in shown:
        print(
            f"{human_size(item.size):>{size_width}}  "
            f"{format_modified(item.last_modified):20}  {relative_remote_key(item.key)}"
        )
        if include_urls:
            print(f"{'':>{size_width}}  {'':20}  {item.url}")
    if len(shown) < len(objects):
        print(
            f"... {len(objects) - len(shown)} more files not displayed; "
            "use --display-limit 0 or --output to keep the complete list."
        )


def print_summary(stats: ScanStats, *, label: str = "Matched") -> None:
    from zju_scatt_interface.access.filters import human_size

    print(
        f"{label}: {stats.matched:,} files, {human_size(stats.bytes)} total "
        f"(scanned {stats.scanned:,} objects across {stats.pages:,} listing pages)."
    )
