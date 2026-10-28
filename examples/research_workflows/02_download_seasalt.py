"""Download native sea-salt data in the inclusive 0.3-1.0 um range.

Role:
    Production example

Inputs:
    02_retrieval_config.py and optional saved catalog.

Outputs:
    Native source files, selection manifest and retrieval report.

Run:
    python 02_download_seasalt.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.retrieval import retrieve_from_config

if __name__ == "__main__":
    raise SystemExit(retrieve_from_config(Path(__file__).with_name("02_retrieval_config.py")))
