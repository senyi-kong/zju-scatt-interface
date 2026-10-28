"""ZJU-SCATT scientific API. Domain modules own their implementations."""

from ._version import __author__, __organization__, __version__
from .api import *  # noqa: F403
from .api import __all__ as _api_names

__all__ = list(_api_names) + ["__version__", "__author__", "__organization__"]
