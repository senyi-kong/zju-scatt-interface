"""Configure: retrieve ice at 250 K and 1.6 um for interpolated shape n=2.1, asp=1.7.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Interpolated ice products, cached sources and
    reports.

Run:
    Edit this file, then run: bash run_local.sh
    08_download_ice_250k_1p6um_shape_interpolation.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "particle_types": "ice",
    "target_wavelengths": [1.6],
    "target_temperatures": [250],
    "shapes": {
        "n": 2.1,
        "asp": 1.7,
    },
    "output_dir": "downloads/ice_250K_1.6um_n2.1_asp1.7",
}
