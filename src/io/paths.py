"""io / paths domain implementation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


def filesystem_path(path: Union[str, Path]) -> Path:
    """Return an absolute path suitable for long local operations on Windows."""

    resolved = Path(path).expanduser().resolve()
    if os.name != "nt":
        return resolved
    value = str(resolved)
    if value.startswith("\\\\?\\"):
        return resolved
    # Keep ordinary Windows paths readable and portable whenever Win32's
    # historical path limit is not relevant.
    if len(value) < 248:
        return resolved
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)
