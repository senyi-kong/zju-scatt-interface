"""Multiple particle types with independently declared bulk-output grids.

Role:
    Configuration

Inputs:
    Edit the trusted Python mappings below; physical arrays/axes use their explicitly declared
    units.

Outputs:
    Configuration only; the consuming loader/driver performs validation or calculation.

Run:
    Supply this file with --scheme to example_07_multidimensional_bulk_scheme.py and provide
    native source paths.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Multiple particle types with independently declared bulk-output grids.
"""

multi_bulk_scheme = {
    "name": "multidimensional_particle_bulk_optics",
    "particles": [
        {
            "name": "ice",
            "particle_type": "super_spheroid_ice",
            "dimensions": [
                {
                    "name": "wavelength",
                    "size": 2,
                    "coordinates": [0.55, 0.67],
                    "unit": "um",
                },
                {
                    "name": "temperature",
                    "size": 2,
                    "coordinates": [220.0, 270.0],
                    "unit": "K",
                },
                {
                    "name": "roundness",
                    "size": 2,
                    "coordinates": [2.0, 2.5],
                },
                {
                    "name": "aspect_ratio",
                    "size": 2,
                    "coordinates": [1.0, 1.5],
                },
            ],
            "size_distribution": {
                "size": [5.0, 10.0, 20.0, 40.0, 80.0],
                "dndr": [50.0, 200.0, 400.0, 250.0, 100.0],
                "size_unit": "um",
                "size_definition": "volume_equivalent_sphere_radius",
            },
            "refractive_index": {
                "mode": "database_temperature",
                "temperature_k": 220.0,
            },
        },
        {
            "name": "sulfate",
            "particle_type": "sphere_sulfate",
            "dimensions": [
                {
                    "name": "wavelength",
                    "coordinates": [0.55, 0.67],
                    "unit": "um",
                },
                {
                    "name": "relative_humidity",
                    "coordinates": [0.0, 0.5, 0.8],
                },
            ],
            "size_distribution": {
                "size": [0.03, 0.05, 0.08, 0.12, 0.20, 0.35],
                "dndr": [100.0, 600.0, 1800.0, 1500.0, 750.0, 250.0],
                "size_unit": "um",
                "size_definition": "volume_equivalent_sphere_radius",
            },
            "shape_parameters": {"relative_humidity": 0.0},
            "refractive_index": {"mode": "database"},
        },
    ],
}
