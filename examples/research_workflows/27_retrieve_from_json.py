"""Retrieve sea-salt optics using an editable JSON CLI request.

Role:
    Production retrieval example.
Inputs:
    request.json, or --config PATH; remaining options go to zju-scatt retrieve.
Outputs:
    Data, selected-source manifest and operation log at the configured paths.
Run:
    python 27_retrieve_from_json.py; append --help or --no-download.
Notes:
    Relative configured paths resolve beside the chosen JSON file. Explicit CLI
    path overrides retain normal command-line working-directory semantics.
"""
import argparse
import json
from pathlib import Path

from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.main import main as run_command


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path,
                        default=Path(__file__).with_name("request.json"))
    options, remaining = parser.parse_known_args(argv)
    path = options.config.expanduser().resolve()
    settings = json.loads(path.read_text(encoding="utf-8"))
    command = ["retrieve", "--config", str(path)]
    for key, flag in (("output_dir", "--output-dir"),
                      ("manifest", "--manifest"),
                      ("manifest_output", "--manifest-output"),
                      ("operation_log", "--operation-log")):
        if settings.get(key):
            value = Path(settings[key]).expanduser()
            if not value.is_absolute():
                value = path.parent / value
            command.extend([flag, str(value)])
    return run_command([*command, *remaining])


if __name__ == "__main__":
    raise SystemExit(main())
