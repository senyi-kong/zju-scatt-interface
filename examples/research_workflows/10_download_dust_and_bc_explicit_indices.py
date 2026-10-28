"""Retrieve dust and coated BC using explicit RI grids without assigning a wavelength.

Role:
    Production example

Inputs:
    10_retrieval_config.py: dust shape/RI and BC df/core/coating RI.

Outputs:
    Separate wl_nan products and reports; native BC vf values retained.

Run:
    python 10_download_dust_and_bc_explicit_indices.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("10_retrieval_config.py")))
