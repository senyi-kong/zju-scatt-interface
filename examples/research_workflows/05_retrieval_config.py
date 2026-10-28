"""Configure: retrieve every registered species at 1.5 um with representative external shapes.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Per-species sources/products, manifests and
    combined completion report.

Run:
    Edit this file, then run: python 05_download_all_species_1p5um.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "requests": "all",
    "target_wavelengths": [1.5],
    "overrides": {
        "dust": {
            "shapes": {
                "n": 2,
                "asp": 1,
            },
        },
        "black_carbon": {
            "shapes": {
                "df": 1.8,
            },
        },
        "ice": {
            "shapes": {
                "n": 2,
                "asp": 1,
            },
            "target_temperatures": [270],
        },
    },
    "output_dir": "downloads/all_species_1.5um",
}
