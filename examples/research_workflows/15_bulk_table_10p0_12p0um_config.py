"""Default bulk optics for ALL species, 10.0-12.0 um inclusive.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 15_all_species_bulk_10p0_12p0um.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Default bulk optics for ALL species, 10.0-12.0 um inclusive.

    Edit this input file, then run 15_all_species_bulk_10p0_12p0um.py.
    The 0.1 um step produces 21 wavelengths and 168 rows for the eight species.
    Each species is an independent reference population normalized to 1 cm^-3.
"""
import os
from pathlib import Path

bulk_table = {
    # Dust, black carbon, sea salt, ice, water cloud, sulfate, nitrate and OC.
    "species": "all",
    "wavelengths": [round(10.0 + 0.1*i, 8) for i in range(21)],
    "preset": "literature_v1",
    "number_concentration_cm3": 1.0,
    "include_phase_matrix": False,
    "coverage_policy": "error",
    "workspace": (str(Path.home()/".cache"/"zju_scatt_interface"/"bulk_table_workspace")
                  if os.name == "posix" else "downloads/bulk_table_workspace"),
    "catalog": "downloads/all_species_bulk_0p3_1p0um/catalog.jsonl",
    "reuse_dirs": ["downloads"],
    "output_dir": "downloads/all_species_bulk_10p0_12p0um",
    "formats": ["nc", "csv"],
    # Retain default PSDs, shape ensembles, refractive indices, T=220 K for ice,
    # and RH=60% where supported (sea salt uses the crystallization branch).
    "overrides": {},
}

# A saved catalog is optional in a fresh example installation.
_catalog = bulk_table.get("catalog")
if _catalog and not (Path(__file__).resolve().parent / _catalog).is_file():
    bulk_table["catalog"] = None
