"""Retrieve ice at 250 K and 1.6 um for n=2, asp=1.

Role:
    Production example

Inputs:
    07_retrieval_config.py with wavelength, temperature and shape targets.

Outputs:
    Native-schema ice target data and source-selection diagnostics.

Run:
    python 07_download_ice_250k_1p6um.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("07_retrieval_config.py")))
