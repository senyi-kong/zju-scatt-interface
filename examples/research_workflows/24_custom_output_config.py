"""One input file describes both a custom NetCDF and a custom HDF5 product.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 24_export_custom_output.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path

bulk_source=Path(__file__).parent/"downloads/all_species_rttov13_wavelength_sequence/bulk_optics_all_species.nc"

layout={
    "species_names":{
        "dust":"DU","black_carbon":"BC","sea_salt":"SS","sulfate":"SU",
        "nitrate":"NI","organic_carbon":"OC","water_cloud":"WC","ice":"IC",
    },
    "group":"OpticalProperties/{species}",
    # Preferred axis order; each variable keeps its actual dimensions only.
    "dimensions":["wavelength","sca_angle"],
    "coordinates":{
        "wavelength":{"name":"wavelength","units":"um"},
        "sca_angle":{"name":"angle","units":"degree"},
    },
    "variables":{
        "extinction":{"source":"beta_ext","units":"km^-1"},
        "scattering":{"source":"beta_sca","units":"km^-1"},
        "absorption":{"source":"beta_abs","units":"km^-1"},
        "albedo":{"source":"ssa","units":"1"},
        "asymmetry":{"source":"g","units":"1"},
        "number_density":{"source":"number_concentration","units":"m^-3"},
        "P11":{"source":"p11","units":"1","dtype":"float32"},
    },
    "attributes":{"title":"User-defined optical-property table","schema_version":"1"},
    "compression":4,
}
outputs=[
    {**layout,"format":"netcdf4","filename":"downloads/custom_output/user_optics.nc"},
    {**layout,"format":"hdf5","filename":"downloads/custom_output/user_optics.h5"},
]
