"""Configure: download native sea-salt data in the inclusive 0.3-1.0 um range.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Native source files, selection manifest and
    retrieval report.

Run:
    Edit this file, then run: python 02_download_seasalt.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "particle_types": "sea_salt",
    "wavelength_range": [0.3, 1],
    "apply_interpolation": False,
    "output_dir": "downloads/seasalt_0.3-1um",
}
