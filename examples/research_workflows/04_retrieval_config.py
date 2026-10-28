"""Configure: retrieve dust, black carbon and sea salt at 1.5 um using default RI schemes.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Separate species folders containing sources,
    derived products and reports.

Run:
    Edit this file, then run: python 04_download_multispecies_1p5um.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "requests": {
        "dust": {

        },
        "black_carbon": {

        },
        "sea_salt": {

        },
    },
    "target_wavelengths": [1.5],
    "output_dir": "downloads/multispecies_1.5um",
}
