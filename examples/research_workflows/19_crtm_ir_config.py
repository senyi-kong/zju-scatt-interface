"""Default all-species spectrum; custom CRTM IR-only fixed-PSD tables.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 19_default_bulk_crtm_ir.py

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
    "output_dir": "downloads/all_species_crtm_ir_wavelength_sequence",
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

crtm_output = {
    "phase_normalization": "renormalize",  # Angular P11 only; PSD stays fixed.
    # Editable representative material assumptions, not measured densities.
    # Hygroscopic water is excluded from aerosol mass via native radius gf;
    # BC mass counts only the core volume vf. Cloud mass is water/ice mass.
    "material_densities_kg_m3": {
        "dust": 2600.0, "black_carbon": 1800.0, "sea_salt": 2160.0,
        "sulfate": 1770.0, "nitrate": 1720.0, "organic_carbon": 1500.0,
        "water_cloud_zju_gamma": 1000.0, "ice_cloud_zju_super_spheroid": 917.0,
    },
}

# A saved catalog is optional in a fresh example installation.
_catalog = bulk_table.get("catalog")
if _catalog and not (Path(__file__).resolve().parent / _catalog).is_file():
    bulk_table["catalog"] = None
