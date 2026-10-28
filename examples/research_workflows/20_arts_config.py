"""Default all-species spectrum; ARTS 2.x fixed-PSD scattering XML.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 20_default_bulk_arts.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import json
import os
from pathlib import Path

wavelengths_um = [10.0, 10.6, 10.8, 11.2, 11.6]
bulk_table = {
    "species": "all", "wavelengths": wavelengths_um, "preset": "literature_v1",
    "number_concentration_cm3": 1.0, "include_phase_matrix": True,
    "coverage_policy": "error",
    "workspace": (str(Path.home()/".cache"/"zju_scatt_interface"/"bulk_table_workspace")
                  if os.name == "posix" else "downloads/bulk_table_workspace"),
    "catalog": "downloads/all_species_bulk_0p3_1p0um/catalog.jsonl",
    "reuse_dirs": ["downloads"],
    "output_dir": "downloads/all_species_arts_wavelength_sequence",
    "formats": ["nc", "csv"],
}
previous = Path(__file__).parent/"downloads/all_species_bulk_10p0_12p0um/report.json"
if previous.is_file():
    saved = json.loads(previous.read_text(encoding="utf-8"))
    if set(wavelengths_um).issubset(saved["wavelengths_um"]):
        paths = {name: [entry["path"] for entry in item["sources"]]
                 for name, item in saved["species"].items()}
        if all(Path(p).is_file() for entries in paths.values() for p in entries):
            bulk_table["source_paths"] = paths

arts_output = {
    "phase_normalization": "renormalize",  # Angular P11 only; PSD stays fixed.
    # Label for species without a temperature-dependent optical calculation.
    # Ice uses its actual configured/calculated temperature (default 220 K).
    "reference_temperature_k": 273.15,
}

# A saved catalog is optional in a fresh example installation.
_catalog = bulk_table.get("catalog")
if _catalog and not (Path(__file__).resolve().parent / _catalog).is_file():
    bulk_table["catalog"] = None
