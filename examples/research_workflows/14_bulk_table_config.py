"""Edit this input file, then run 14_all_species_bulk_0p3_1p0um.py.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 14_all_species_bulk_0p3_1p0um.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Edit this input file, then run 14_all_species_bulk_0p3_1p0um.py.

    All wavelengths and lognormal mean radii use micrometres. Species are separate
    populations, each normalized to 1 cm^-3. No cross-species mixture is calculated.
"""
from pathlib import Path
import os

bulk_table = {
    "species": "all",
    "wavelengths": [round(0.30 + 0.05*i, 8) for i in range(15)],
    "preset": "literature_v1",  # Bi et al. (2026), Table 2; gamma clouds, lognormal aerosols.
    "number_concentration_cm3": 1.0,
    "include_phase_matrix": False,
    "coverage_policy": "error",  # Custom PSDs must fit all selected sources.
    # Linux storage avoids slow repeated NetCDF reads through a WSL mount.
    "workspace": (str(Path.home()/".cache"/"zju_scatt_interface"/"bulk_table_workspace")
                  if os.name == "posix" else "downloads/bulk_table_workspace"),
    "catalog": "downloads/all_species_bulk_0p3_1p0um/catalog.jsonl",
    "reuse_dirs": ["downloads"],
    "output_dir": "downloads/all_species_bulk_0p3_1p0um_literature",
    "formats": ["nc", "csv"],
    "overrides": {
        # Examples (uncomment to replace a species' preset settings):
        # "ice": {"temperature": 250},
        # "water_cloud": {"psd": {"type": "gamma", "effective_radius_um": 10,
        #                         "effective_variance": 1/3, "number_concentration_cm3": 1,
        #                         "radius_range_um": [1, 20], "normalization": "renormalize"}},
        # "dust": {
        #     "shapes": [{"n": 2.7, "asp": 1.5}, {"n": 2.8, "asp": 1.9}],
        #     "refractive_index": {"mode": "fixed", "real": 1.5, "imaginary": 0.003},
        #     "psd": {"type": "lognormal", "rg_um": 0.7, "sigma_g": 1.8,
        #             "number_concentration_cm3": 10,
        #             "radius_range_um": [0.05, 5.0], "normalization": "renormalize"},
        # },
    },
}

# A saved catalog is optional in a fresh example installation.
_catalog = bulk_table.get("catalog")
if _catalog and not (Path(__file__).resolve().parent / _catalog).is_file():
    bulk_table["catalog"] = None
