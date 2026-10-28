"""Default-scheme tables with user-configurable two-letter particle names.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 23_default_scheme_rttov14_two_letter.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path

source_dir=Path(__file__).parent/"downloads/all_species_rttov14_lookup"
output_dir=Path(__file__).parent/"downloads/default_scheme_rttov14_two_letter"
output_names={
    "black_carbon":"BC", "dust":"DU", "sea_salt":"SS",
    "sulfate":"SU", "nitrate":"NI", "organic_carbon":"OC",
    "water_cloud_zju_gamma":"WC", "ice_cloud_zju_super_spheroid":"IC",
}
