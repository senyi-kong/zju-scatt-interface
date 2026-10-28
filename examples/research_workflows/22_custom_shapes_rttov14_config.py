"""Same lookup grids as script 21, with explicitly selected particle shapes.

Role:
    Configuration

Inputs:
    Edit mappings and paths below; inline comments declare axis units, PSD concentrations and
    output settings.

Outputs:
    Settings for the associated driver; optical products are generated when that driver runs.

Run:
    Edit this file, then run: python 22_custom_shapes_rttov14.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
import runpy

globals().update({key:value for key,value in runpy.run_path(
    str(Path(__file__).with_name("21_rttov14_lookup_config.py"))).items() if not key.startswith("__")})
output_dir=Path(__file__).parent/"downloads/custom_shapes_rttov14_lookup"

overrides={
    "black_carbon":{"df":2.1,"vf":0.4},
    # Equal number fractions: integrate each shape over the same physical PSD,
    # then combine the extensive coefficients and derive SSA/g/phase.
    "dust":{"shapes":[
        {"parameters":{"ssph_n":2.8,"ssph_asp":0.5},"weight":0.5},
        {"parameters":{"ssph_n":2.8,"ssph_asp":2.0},"weight":0.5},
    ]},
    "ice":{"shapes":{"ssph_n":2.5,"ssph_asp":2.0}},
}
