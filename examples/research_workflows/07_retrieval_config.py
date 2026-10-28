"""Configure: retrieve ice at 250 K and 1.6 um for n=2, asp=1.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Native-schema ice target data and source-
    selection diagnostics.

Run:
    Edit this file, then run: python 07_download_ice_250k_1p6um.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "particle_types": "ice",
    "target_wavelengths": [1.6],
    "target_temperatures": [250],
    "shapes": {
        "n": 2,
        "asp": 1,
    },
    "output_dir": "downloads/ice_250K_1.6um",
}
