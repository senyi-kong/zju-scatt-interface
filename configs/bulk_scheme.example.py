"""Python bulk-scheme example with independently calculated components.

Role:
    Configuration

Inputs:
    Edit the trusted Python mappings below; physical arrays/axes use their explicitly declared
    units.

Outputs:
    Configuration only; the consuming loader/driver performs validation or calculation.

Run:
    From the package root: python examples/example_03_bulk_scheme_validation.py
    configs/bulk_scheme.example.py

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Python bulk-scheme example with independently calculated components.
"""


def wavelength_grid(start: float, stop: float, step: float) -> list[float]:
    count = round((stop - start) / step)
    return [round(start + index * step, 10) for index in range(count + 1)]


bulk_scheme = {
    "name": "separate_particle_components_demo",
    "wavelength_unit": "um",
    "wavelengths": wavelength_grid(0.4, 2.5, 0.1),
    "interpolation": "linear",
    "calculation": {
        "include_phase_matrix": False,
        "truncation_policy": "truncate",
        "check_convergence": True,
        "convergence_tolerance": 0.05,
        "strict_convergence": False,
        "strict_qa": True,
    },
    "particles": [
        {
            "name": "ice",
            "particle_type": "super_spheroid_ice",
            "shape_parameters": {"n": 2.0, "aspect_ratio": 1.0},
            "size_distribution": {
                "size": [5.0, 10.0, 20.0, 40.0, 80.0],
                "dndr": [50.0, 200.0, 400.0, 250.0, 100.0],
                "size_unit": "um",
                "size_definition": "volume_equivalent_sphere_radius",
                "integration_mode": "discrete_bin",
            },
            "refractive_index": {
                "mode": "database_temperature",
                "temperature_k": 220,
            },
        },
        {
            "name": "sulfate",
            "particle_type": "sphere_sulfate",
            "shape_parameters": {"relative_humidity": 0.8},
            "size_distribution": {
                "size": [0.03, 0.05, 0.08, 0.12, 0.20, 0.35],
                "dndr": [100.0, 600.0, 1800.0, 1500.0, 750.0, 250.0],
                "size_unit": "um",
                "size_definition": "volume_equivalent_sphere_radius",
                "integration_mode": "discrete_bin",
            },
            "refractive_index": {"mode": "database"},
        },
    ],
    "output": {
        "path": "outputs/separate_particle_components_demo.nc",
        "format": "netcdf4",
        "compression": True,
        "compression_level": 4,
        "shuffle": True,
        "atomic": True,
    },
}
