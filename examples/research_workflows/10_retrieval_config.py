"""Configure: retrieve dust and coated BC using explicit RI grids without assigning a wavelength.

Role:
    Configuration

Inputs:
    Edit the retrieval mapping. Wavelengths use um, temperatures K; file paths resolve beside
    this configuration.

Outputs:
    Settings only on import. The driver creates: Separate wl_nan products and reports; native
    BC vf values retained.

Run:
    Edit this file, then run: python 10_download_dust_and_bc_explicit_indices.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
retrieval = {
    "requests": {
        "dust": {
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
        },
        "black_carbon": {
            "shapes": {
                "df": 1.8,
            },
            "refractive_index_parameters": {
                "black_carbon": {
                    "black_carbon_refractive_index_real": 1.8,
                    "black_carbon_refractive_index_imaginary": 0.625,
                    "hygroscopic_refractive_index_real": 1.475,
                    "hygroscopic_refractive_index_imaginary": 0.0075,
                },
            },
        },
    },
    "output_dir": "downloads/dust_and_bc_explicit_indices",
}
