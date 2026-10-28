"""Minimal trusted input for run_bulk_table('bulk_table.example.py').

Role:
    Configuration

Inputs:
    Edit the trusted Python mappings below; physical arrays/axes use their explicitly declared
    units.

Outputs:
    Configuration only; the consuming loader/driver performs validation or calculation.

Run:
    From the package root: python examples/example_17_reference_bulk_table.py
    configs/bulk_table.example.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Minimal trusted input for run_bulk_table('bulk_table.example.py').
"""

bulk_table = {
    "species": "all",
    "wavelengths": [round(0.30 + 0.05*i, 8) for i in range(15)],
    "preset": "literature_v1",
    "workspace": "../zju_scatt_data",
    "output_dir": "../bulk_table_outputs",
    "overrides": {},
}
