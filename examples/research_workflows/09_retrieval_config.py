"""Configure: retrieve dimensionless dust for n=2.1, asp=1.7 and RI=1.51+0.0023i.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Native-schema wl_nan shape/RI product,
    sources and diagnostics.

Run:
    Edit this file, then run: python 09_download_super_spheroid_explicit_index.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "particle_types": "dust",
    "shapes": {
        "n": 2.1,
        "asp": 1.7,
    },
    "refractive_index_parameters": {
        "dust": {
            "refractive_index_real": 1.51,
            "refractive_index_imaginary": 0.0023,
        },
    },
    "output_dir": "downloads/super_spheroid_n2.1_asp1.7_ref1.51_0.0023",
}
