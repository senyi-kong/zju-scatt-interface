"""Inspect existing bulk optics with automatic scalar-axis and phase plots.

Role:
    Production example

Inputs:
    Optional NC/HDF5 path; default is example 12's ensemble application file.

Outputs:
    Inspection figures/exports under downloads/bulk_optics_inspection by default.

Run:
    python 26_plot_bulk_optics.py [PATH_TO_DATA]

Notes:
    Inspects or exports existing information; it does not run a new single-scattering solver.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.plotting import run_bulk_optics_plot

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    run_bulk_optics_plot(
        default_file=here / "downloads/super_spheroid_lognormal_shape_average/application_outputs/bulk_optics_10_cm3.nc",
        default_output_dir=here / "downloads/bulk_optics_inspection")
