"""Retrieve every registered species at 1.6 um with interpolation where needed.

Role:
    Production example

Inputs:
    06_retrieval_config.py; ice explicitly uses 270 K.

Outputs:
    Per-species sources/products, manifests and combined completion report.

Run:
    python 06_download_all_species_1p6um.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("06_retrieval_config.py")))
