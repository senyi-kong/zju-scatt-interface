"""Edit wavelengths; retain the default PSD, shape, RI, T and RH assumptions.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 17_default_bulk_rttov13.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import json
import os
from pathlib import Path

wavelengths_um = [10.0, 10.6, 10.8, 11.2, 11.6]

bulk_table = {
    "species": "all",
    "wavelengths": wavelengths_um,
    "preset": "literature_v1",
    "number_concentration_cm3": 1.0,
    "include_phase_matrix": True,  # Actual P11 is required for RTTOV BPR/moments.
    "coverage_policy": "error",
    "workspace": (str(Path.home()/".cache"/"zju_scatt_interface"/"bulk_table_workspace")
                  if os.name == "posix" else "downloads/bulk_table_workspace"),
    "catalog": "downloads/all_species_bulk_0p3_1p0um/catalog.jsonl",
    "reuse_dirs": ["downloads"],
    "output_dir": "downloads/all_species_rttov13_wavelength_sequence",
    "formats": ["nc", "csv"],
}

# Reuse the earlier verified IR source selection when it covers this sequence.
# This changes storage access only; all optics and phase functions are calculated.
previous = Path(__file__).parent/"downloads/all_species_bulk_10p0_12p0um/report.json"
if previous.is_file():
    saved = json.loads(previous.read_text(encoding="utf-8"))
    if set(wavelengths_um).issubset(saved["wavelengths_um"]):
        candidate = {name: [entry["path"] for entry in item["sources"]]
                     for name, item in saved["species"].items()}
        if all(Path(p).is_file() for paths in candidate.values() for p in paths):
            bulk_table["source_paths"] = candidate

rttov_output = {
    "max_moments": 32,
    # Normalize only the angular phase function to RTTOV's 4*pi convention.
    # Native 1-degree ice P11 has ~1.3% integral error. PSD counts are unchanged.
    "phase_normalization": "renormalize",
    "water_density_kg_m3": 1000.0,
    "ice_density_kg_m3": 917.0,
}

# A saved catalog is optional in a fresh example installation.
_catalog = bulk_table.get("catalog")
if _catalog and not (Path(__file__).resolve().parent / _catalog).is_file():
    bulk_table["catalog"] = None
