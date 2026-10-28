"""Local retrieval cache configuration."""

from pathlib import Path

from .registration import registration_required


@registration_required
def initialize_data_directory(path="zju_scatt_data"):
    """Create and select the default local directory for source retrieval."""
    from . import requests

    target = Path(path).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    requests.API_DATA_DIR = target
    return target
