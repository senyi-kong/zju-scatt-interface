"""Inspect existing single-scattering data with default scalar and phase plots.

Role:
    Production example

Inputs:
    Optional NC path; otherwise the unique interpolated ice file from example 08.

Outputs:
    Inspection figures and plot exports under downloads/single_scattering_inspection by
    default.

Run:
    python 25_plot_single_scattering.py [PATH_TO_DATA]

Notes:
    Inspects or exports existing information; it does not run a new single-scattering solver.
"""
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.cli.plotting import run_single_scattering_plot

if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    files = sorted((here / "downloads/ice_250K_1.6um_n2.1_asp1.7/interpolated").rglob("*.nc"))
    run_single_scattering_plot(
        default_file=files[0] if len(files) == 1 else None,
        default_output_dir=here / "downloads/single_scattering_inspection")
