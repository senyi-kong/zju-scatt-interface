"""Use the active installed ZJU-SCATT interface (editable install optional)."""
from pathlib import Path
import sys


def verify_local_import(verbose=False):
    """Check the current API and return the active package without changing paths."""
    import zju_scatt_interface as zsi
    required = ("retrieve", "compute_population", "load_scheme", "build", "write", "plot")
    missing = [name for name in required if not callable(getattr(zsi, name, None))]
    if missing:
        raise ImportError("This collection requires the domain-based interface; missing: " + ", ".join(missing))
    if verbose:
        print(f"Python: {sys.executable}")
        print(f"Interface: {Path(zsi.__file__).resolve()}")
        print(f"Version: {zsi.__version__}")
    return zsi


if __name__ == "__main__":
    verify_local_import(verbose=True)
