"""Retrieve dust, black carbon and sea salt at 1.5 um using default RI schemes.

Role:
    Production example

Inputs:
    04_retrieval_config.py; --smoke-test limits dust/BC external shapes.

Outputs:
    Separate species folders containing sources, derived products and reports.

Run:
    python 04_download_multispecies_1p5um.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("04_retrieval_config.py")))
