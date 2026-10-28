"""errors domain implementation."""

from __future__ import annotations


class ScattError(RuntimeError):
    """Base exception for user-facing interface errors."""


class NetworkError(ScattError):
    """A remote request failed after retries."""
