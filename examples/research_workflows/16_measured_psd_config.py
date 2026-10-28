"""Synthetic measurement-format PSDs for all eight species, 10–12 um.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 16_all_species_measured_psd_bulk.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Synthetic measurement-format PSDs for all eight species, 10–12 um.

    Replace the CSV contents with your measurements; running the script never
    rewrites these inputs. Concentrations are per bin, in cm^-3, NOT dN/dr.
"""
import os
from pathlib import Path

bulk_table = {
    "species": "all",
    "wavelengths": [round(10.0 + 0.1*i, 8) for i in range(21)],
    "preset": "literature_v1",  # Default shapes, RI, humidity and temperature.
    "coverage_policy": "error",  # Reject uncovered measurements; preserve counts.
    "include_phase_matrix": False,
    "workspace": (str(Path.home()/".cache"/"zju_scatt_interface"/"bulk_table_workspace")
                  if os.name == "posix" else "downloads/bulk_table_workspace"),
    "catalog": "downloads/all_species_bulk_0p3_1p0um/catalog.jsonl",
    "reuse_dirs": ["downloads"],
    "output_dir": "downloads/all_species_measured_psd_10p0_12p0um",
    "formats": ["nc", "csv"],
    # Each explicit PSD replaces that species' analytical default. Its total
    # concentration is the SUM of its CSV counts, independent of default N=1.
    "overrides": {
        name: {"psd": {
            "file": f"input_psd/measured_example/{name}.csv",
            "size_column": "radius_um",
            "dndr_column": "number_per_bin_cm3",
            "size_unit": "um",
            "size_definition": "volume_equivalent_sphere_radius",
        }}
        for name in ("dust", "black_carbon", "sea_salt", "ice", "water_cloud",
                     "sulfate", "nitrate", "organic_carbon")
    },
}

# A saved catalog is optional in a fresh example installation.
_catalog = bulk_table.get("catalog")
if _catalog and not (Path(__file__).resolve().parent / _catalog).is_file():
    bulk_table["catalog"] = None
