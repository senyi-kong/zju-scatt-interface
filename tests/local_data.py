"""Portable discovery of the optional local ZJU-SCATT database mount."""

from __future__ import annotations

import os
from pathlib import Path


def local_l1_root() -> Path:
    """Return the configured or detected L1 single-scattering data root."""

    configured = os.environ.get("ZJU_SCATT_L1_ROOT")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        (
            Path("/mnt/x/L1_single_scattering_property"),
            Path(r"X:\L1_single_scattering_property"),
        )
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


__all__ = ["local_l1_root"]
