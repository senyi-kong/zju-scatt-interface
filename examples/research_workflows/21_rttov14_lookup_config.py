"""RH, PSD effective-radius and ice-temperature tables; all eight species.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 21_default_bulk_rttov14_lookup.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

RH, PSD effective-radius and ice-temperature tables; all eight species.

    Native inputs must cover the requested spectrum/environmental states. The
    source report below reuses the sources retrieved for script 17, not its fixed
    bulk coefficients: every new size/RH/temperature point is recomputed.
"""
from pathlib import Path
import os

source_report = Path(__file__).parent/"downloads/all_species_rttov13_wavelength_sequence/report.json"
output_dir = Path(__file__).parent/"downloads/all_species_rttov14_lookup"
wavelengths_um = [10.0, 10.6, 10.8, 11.2, 11.6]

# Example nodes span 0–99%. Set list(range(100)) for every integer percent.
relative_humidity_percent = [0, 50, 99]
ice_temperatures_k = [160, 220, 270]
effective_radii_um = {
    "dust": [1.0, 2.0],
    "black_carbon": [0.1, 0.2],  # Fixed native default vf; no RH dimension.
    "sea_salt": [0.3, 0.6],
    "sulfate": [0.1, 0.2],
    "nitrate": [0.1, 0.2],
    "organic_carbon": [0.05, 0.1],
    "water_cloud_zju_gamma": [5.0, 10.0],
    "ice_cloud_zju_super_spheroid": [20.0, 30.0],
}
sea_salt_branch = "deliquescence"  # Native branch covering 0–99%; do not mix branches.
bins = 160
max_moments = 32
catalog = Path(__file__).parent/"downloads/all_species_bulk_0p3_1p0um/catalog.jsonl"
source_workspace = (Path.home()/".cache/zju_scatt_interface/rttov14_lookup_sources"
                    if os.name=="posix" else output_dir/"sources")

# Standard RTTOV14 supports RH-only aerosols and Deff-only clouds. Select
# aerosol size and ice temperature from the master cubes for runtime files.
native_slice = {
    "aerosol_effective_radii_um": {name: radii[0] for name, radii in effective_radii_um.items()
                                   if name not in {"water_cloud_zju_gamma", "ice_cloud_zju_super_spheroid"}},
    "ice_temperature_k": 220.0,
}
