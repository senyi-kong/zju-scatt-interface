"""Build RTTOV14 lookup tables for user-selected BC, dust and ice shapes.

Role:
    Production example

Inputs:
    22_custom_shapes_rttov14_config.py: BC df=2.1/vf=0.4, two dust shapes, one ice shape.

Outputs:
    Custom-shape lookup cubes/runtime slices through the shared example-21 driver.

Run:
    python 22_custom_shapes_rttov14.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
from pathlib import Path
import runpy

if __name__=="__main__":
    driver=runpy.run_path(str(Path(__file__).with_name("21_default_bulk_rttov14_lookup.py")))
    driver["main"](Path(__file__).with_name("22_custom_shapes_rttov14_config.py"))
