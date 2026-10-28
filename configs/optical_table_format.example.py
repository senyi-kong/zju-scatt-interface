"""Starter format for a radiative-transfer-model bulk-optics table.

Role:
    Configuration

Inputs:
    Edit the trusted Python mappings below; physical arrays/axes use their explicitly declared
    units.

Outputs:
    Configuration only; the consuming loader/driver performs validation or calculation.

Run:
    Supply this file with --format-spec to example_08_export_model_table.py and provide an
    existing bulk file.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Starter format for a radiative-transfer-model bulk-optics table.

    Copy this file and change its columns, units, ordering, headers, and formatting
    to match the exact RTTOV, CRTM, ARTS, or other model/version interface in use.
    Python format files are trusted code and may define transformation functions.
"""


def inverse_metres_to_inverse_kilometres(value, record):
    """Example model-unit conversion usable in any column."""

    del record
    return float(value) * 1000.0


optical_table_format = {
    "name": "radiative_transfer_bulk_table_v1",
    "layout": "per_component",
    "filename_template": "{stem}_{component}{suffix}",
    "delimiter": " ",
    "comment_prefix": "# ",
    "header_lines": [
        "format={format_name}",
        "particle_component={component}",
        "records={record_count}",
    ],
    "include_column_header": True,
    "include_unit_header": True,
    "missing_value": "nan",
    "columns": [
        {"field": "wavelength_um", "name": "wavelength", "unit": "um", "format": ".6f"},
        {
            "field": "beta_ext",
            "name": "extinction",
            "unit": "km^-1",
            "format": ".8e",
            "transform": inverse_metres_to_inverse_kilometres,
        },
        {
            "field": "beta_sca",
            "name": "scattering",
            "unit": "km^-1",
            "format": ".8e",
            "scale": 1000.0,
        },
        {"field": "ssa", "unit": "1", "format": ".8f"},
        {"field": "g", "unit": "1", "format": ".8f"},
    ],
}

# To produce a phase-matrix long table, add sca_angle and any of
# p11, p12, p22, p33, p43, p44 to columns. Each bulk grid point will then be
# repeated once per scattering angle.
