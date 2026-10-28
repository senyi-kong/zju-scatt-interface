"""Configure scientific inputs and output choices shared by examples 11-13.

Role:
    Configuration

Inputs:
    Edit PSD_SETTINGS, COMMON, CALCULATION_OPTIONS and EXAMPLES for shape targets, weights and
    optional L2 exports.

Outputs:
    Imported settings only; this file does not generate optical data.

Run:
    Edit this file, then run example 11, 12 or 13 with python SCRIPT.py.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import math

FAMILY = "super_spheroid"
WAVELENGTH_UM = 1.6
COMMON = {"mr": 1.50, "mi": 0.003}
DG_UM, SIGMA_G, N_CM3 = 1.4, 1.8, 10.0  # Dg is volume-equivalent DIAMETER.
PSD_SETTINGS = dict(
    rg_um=DG_UM/2, sigma_g=SIGMA_G, number_concentration_cm3=N_CM3,
    radius_range_um=[DG_UM/2*math.exp(s*6*math.log(SIGMA_G)) for s in (-1,1)],
    bins=600, normalization="renormalize",  # Explicit finite-grid normalization.
)
CALCULATION_OPTIONS = dict(
    size_definition="volume_equivalent_sphere_radius", truncation_policy="error",
    include_phase_matrix=True, target_angles_degrees=[i/4 for i in range(721)],
    phase_normalization="unit_solid_angle", check_convergence=True,
    convergence_tolerance=0.05, strict_convergence=True, strict_qa=True,
)
EXAMPLES = {
    "12": dict(
        shapes=[{"ssph_n":2.8,"ssph_asp":asp} for asp in (.5,1.,2.)],
        weights=[1/3]*3,
        output_dir="downloads/super_spheroid_lognormal_shape_average",
        component_name="super_spheroid_lognormal_shape_average",
        l2_lognormal=True,  # Explicitly request normalized per-shape L2 exports.
    ),
    "13": dict(
        shapes=[{"ssph_n":n,"ssph_asp":asp} for n,asp in ((2.7,1.5),(2.8,1.9),(2.5,1.3))],
        weights=[1/3]*3,
        output_dir="downloads/super_spheroid_interpolated_shapes_bulk",
        component_name="super_spheroid_interpolated_shapes_average",
        l2_lognormal=False,
    ),
}
