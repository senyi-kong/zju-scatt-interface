"""Retrieve dimensionless dust for n=2.1, asp=1.7 and RI=1.51+0.0023i.

Role:
    Production example

Inputs:
    09_retrieval_config.py; explicit shape/RI, no physical wavelength.

Outputs:
    Native-schema wl_nan shape/RI product, sources and diagnostics.

Run:
    python 09_download_super_spheroid_explicit_index.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("09_retrieval_config.py")))
