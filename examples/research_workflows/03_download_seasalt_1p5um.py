"""Retrieve sea-salt optics at 1.5 um, interpolating when necessary.

Role:
    Production example

Inputs:
    03_retrieval_config.py and optional saved catalog.

Outputs:
    Native sources, required native-schema target products and reports.

Run:
    python 03_download_seasalt_1p5um.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("03_retrieval_config.py")))
