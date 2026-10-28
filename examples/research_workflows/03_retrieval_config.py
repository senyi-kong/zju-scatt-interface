"""Configure: retrieve sea-salt optics at 1.5 um, interpolating when necessary.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Native sources, required native-schema target
    products and reports.

Run:
    Edit this file, then run: python 03_download_seasalt_1p5um.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "particle_types": "sea_salt",
    "target_wavelengths": [1.5],
    "output_dir": "downloads/seasalt_1.5um",
}
