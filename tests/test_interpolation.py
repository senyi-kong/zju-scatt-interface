import json
import math
import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.access.models import RemoteObject
from zju_scatt_interface.optics.interpolation import (
    InterpolationError,
    OpticalNode,
    OpticalSourceRequest,
    interpolate_downloaded_ice_series,
    interpolate_nodes,
    interpolate_sources,
    phase_matrix_solid_angle_relative_l2_errors,
    solid_angle_weighted_relative_l2_error,
    write_interpolated_optics_netcdf,
)
from zju_scatt_interface.optics.models import SingleParticleOptics


def optics(
    cext,
    *,
    csca=None,
    sizes=(1.0, 2.0),
    g=None,
    angles=None,
    phase=None,
):
    return SingleParticleOptics(
        sizes=list(sizes),
        extinction_cross_section=list(cext),
        scattering_cross_section=list(csca) if csca is not None else None,
        asymmetry_factor=list(g) if g is not None else None,
        scattering_angles=list(angles) if angles is not None else None,
        phase_matrix=phase,
        size_unit="um",
        cross_section_unit="m2",
    )


class Phase5InterpolationTests(unittest.TestCase):
    def test_cross_sections_are_log_interpolated_and_ssa_and_qext_are_derived(self):
        nodes = [
            OpticalNode(
                {"wavelength": 1.0},
                SingleParticleOptics(
                    sizes=[1.0],
                    extinction_cross_section=[4.0],
                    scattering_cross_section=[1.0],
                    extinction_efficiency=[100.0],
                    projected_area=[2.0],
                    size_unit="um",
                    cross_section_unit="m2",
                ),
            ),
            OpticalNode(
                {"wavelength": 3.0},
                SingleParticleOptics(
                    sizes=[1.0],
                    extinction_cross_section=[16.0],
                    scattering_cross_section=[8.0],
                    extinction_efficiency=[200.0],
                    projected_area=[8.0],
                    size_unit="um",
                    cross_section_unit="m2",
                ),
            ),
        ]
        result = interpolate_nodes(
            "sphere_water_cloud", nodes, {"wavelength": 2.0}
        )
        self.assertAlmostEqual(result.optics.extinction_cross_section[0], 8.0)
        self.assertAlmostEqual(
            result.optics.scattering_cross_section[0], math.sqrt(8.0)
        )
        self.assertAlmostEqual(result.optics.projected_area[0], 4.0)
        self.assertAlmostEqual(result.optics.extinction_efficiency[0], 2.0)
        self.assertAlmostEqual(
            result.optics.single_scattering_albedo[0], math.sqrt(8.0) / 8.0
        )
        self.assertNotAlmostEqual(result.optics.extinction_efficiency[0], 150.0)

    def test_phase_ratios_are_normalized_at_nodes_before_interpolation(self):
        def phase(p11, ratio):
            matrix = [
                [p11, ratio * p11, 0.0, 0.0],
                [ratio * p11, 0.7 * p11, 0.0, 0.0],
                [0.0, 0.0, 0.6 * p11, -0.1 * p11],
                [0.0, 0.0, 0.1 * p11, 0.5 * p11],
            ]
            return [[matrix, matrix]]

        nodes = [
            OpticalNode(
                {"wavelength": 1.0},
                optics(
                    [1.0],
                    sizes=(1.0,),
                    angles=(0.0, 180.0),
                    phase=phase(1.0, 0.2),
                ),
            ),
            OpticalNode(
                {"wavelength": 3.0},
                optics(
                    [3.0],
                    sizes=(1.0,),
                    angles=(0.0, 180.0),
                    phase=phase(9.0, 0.8),
                ),
            ),
        ]
        result = interpolate_nodes(
            "sphere_water_cloud", nodes, {"wavelength": 2.0}
        )
        output = result.optics.phase_matrix[0][0]
        self.assertAlmostEqual(output[0][0], 5.0)
        self.assertAlmostEqual(output[0][1], 2.5)
        self.assertNotAlmostEqual(output[0][1], 3.7)
        self.assertEqual(
            result.provenance.optical_transforms["phase_ratios"],
            "normalized_at_source_node_then_linear",
        )

    def test_four_corner_refractive_index_weights_use_linear_n_and_log_k(self):
        nodes = []
        fixed = {"roundness": 2.0, "aspect_ratio": 1.0}
        for real in (1.4, 1.6):
            for imaginary in (0.001, 0.1):
                nodes.append(
                    OpticalNode(
                        {
                            **fixed,
                            "refractive_index_real": real,
                            "refractive_index_imaginary": imaginary,
                        },
                        optics([real * 10.0 + imaginary]),
                    )
                )
        result = interpolate_nodes(
            "super_spheroid",
            nodes,
            {
                **fixed,
                "refractive_index_real": 1.5,
                "refractive_index_imaginary": 0.01,
            },
        )
        self.assertEqual(len(result.provenance.neighbors), 4)
        for neighbor in result.provenance.neighbors:
            self.assertAlmostEqual(neighbor.weight, 0.25)
        self.assertEqual(
            result.provenance.axis_transforms["refractive_index_real"], "linear"
        )
        self.assertTrue(
            result.provenance.axis_transforms[
                "refractive_index_imaginary"
            ].startswith("log10")
        )

    def test_solid_angle_phase_error_uses_ratios_and_arithmetic_size_mean(self):
        angles = [0.0, 30.0, 180.0]
        self.assertAlmostEqual(
            solid_angle_weighted_relative_l2_error(
                [1.1, 1.1, 1.1], [1.0, 1.0, 1.0], angles
            ),
            10.0,
        )

        def size_phase(p11_scale, ratio_scale):
            return [
                [
                    [p11_scale, 0.5 * ratio_scale * p11_scale, 0.0, 0.0],
                    [0.5 * ratio_scale * p11_scale, 0.7 * p11_scale, 0.0, 0.0],
                    [0.0, 0.0, 0.6 * p11_scale, -0.1 * p11_scale],
                    [0.0, 0.0, 0.1 * p11_scale, 0.5 * p11_scale],
                ]
                for _ in angles
            ]

        truth = [size_phase(1.0, 1.0) for _ in range(4)]
        candidate = [
            size_phase(99.0, 99.0),
            size_phase(1.1, 1.1),
            size_phase(1.2, 1.2),
            size_phase(99.0, 99.0),
        ]
        errors = phase_matrix_solid_angle_relative_l2_errors(
            candidate,
            truth,
            angles,
            [0.05, 0.1, 50.0, 60.0],
        )
        self.assertAlmostEqual(errors["p11"], 15.0)
        self.assertAlmostEqual(errors["p12_over_p11"], 15.0)

    def test_exact_and_linear_wavelength_products(self):
        nodes = [
            OpticalNode({"wavelength": 1.0}, optics([10.0, 20.0]), "one.nc"),
            OpticalNode({"wavelength": 3.0}, optics([30.0, 40.0]), "three.nc"),
        ]
        exact = interpolate_nodes(
            "water_cloud", nodes, {"wavelength": 1.0}
        )
        middle = interpolate_nodes(
            "sphere_water_cloud", nodes, {"wavelength_um": 2.0}
        )
        self.assertEqual(exact.provenance.method, "exact")
        self.assertEqual(exact.optics.extinction_cross_section, [10.0, 20.0])
        self.assertEqual(middle.provenance.method, "multilinear")
        self.assertAlmostEqual(middle.optics.extinction_cross_section[0], math.sqrt(300.0))
        self.assertAlmostEqual(middle.optics.extinction_cross_section[1], math.sqrt(800.0))
        self.assertEqual([n.weight for n in middle.provenance.neighbors], [0.5, 0.5])

    def test_no_extrapolation(self):
        nodes = [
            OpticalNode({"wavelength": 1.0}, optics([1.0, 2.0])),
            OpticalNode({"wavelength": 2.0}, optics([2.0, 3.0])),
        ]
        with self.assertRaisesRegex(InterpolationError, "No extrapolation"):
            interpolate_nodes(
                "sphere_water_cloud", nodes, {"wavelength": 3.0}
            )

    def test_complete_two_dimensional_multilinear_grid(self):
        nodes = []
        for wavelength in (1.0, 3.0):
            for rh in (0.0, 1.0):
                value = wavelength + 10.0 * rh
                nodes.append(
                    OpticalNode(
                        {"wavelength": wavelength, "relative_humidity": rh},
                        optics([value, 2.0 * value]),
                        f"{wavelength}-{rh}.nc",
                    )
                )
        result = interpolate_nodes(
            "sulfate",
            nodes,
            {"wavelength": 2.0, "relative_humidity": 0.25},
        )
        self.assertEqual(result.provenance.method, "multilinear")
        expected = 1.0**0.375 * 3.0**0.375 * 11.0**0.125 * 13.0**0.125
        self.assertAlmostEqual(result.optics.extinction_cross_section[0], expected)
        self.assertAlmostEqual(sum(n.weight for n in result.provenance.neighbors), 1.0)

    def test_sparse_grid_fallback_is_explicit(self):
        nodes = [
            OpticalNode(
                {"wavelength": wavelength, "relative_humidity": rh},
                optics([wavelength + rh, wavelength + rh + 1.0]),
                f"{index}.nc",
            )
            for index, (wavelength, rh) in enumerate(
                ((1.0, 0.0), (3.0, 0.0), (1.0, 1.0))
            )
        ]
        result = interpolate_nodes(
            "sphere_sulfate",
            nodes,
            {"wavelength": 1.5, "relative_humidity": 0.25},
        )
        self.assertEqual(result.provenance.method, "inverse_distance_sparse")
        self.assertTrue(result.provenance.warnings)
        self.assertAlmostEqual(sum(n.weight for n in result.provenance.neighbors), 1.0)

    def test_imaginary_index_uses_log_coordinate(self):
        fixed = {
            "refractive_index_real": 1.5,
            "roundness": 2.0,
            "aspect_ratio": 1.0,
        }
        nodes = [
            OpticalNode({**fixed, "refractive_index_imaginary": 0.001}, optics([1, 2])),
            OpticalNode({**fixed, "refractive_index_imaginary": 0.1}, optics([3, 4])),
        ]
        result = interpolate_nodes(
            "dust",
            nodes,
            {**fixed, "refractive_index_imaginary": 0.01},
        )
        self.assertAlmostEqual(result.optics.extinction_cross_section[0], math.sqrt(3.0))
        self.assertAlmostEqual(result.optics.extinction_cross_section[1], math.sqrt(8.0))
        self.assertTrue(
            result.provenance.axis_transforms[
                "refractive_index_imaginary"
            ].startswith("log10")
        )

    def test_size_alignment_and_energy_constraints(self):
        nodes = [
            OpticalNode(
                {"wavelength": 1.0},
                optics([2.0, 4.0], csca=[3.0, 5.0], sizes=(1.0, 3.0)),
            ),
            OpticalNode(
                {"wavelength": 3.0},
                optics([4.0, 8.0], csca=[5.0, 9.0], sizes=(1.0, 3.0)),
            ),
        ]
        result = interpolate_nodes(
            "water_cloud",
            nodes,
            {"wavelength": 2.0},
            target_size_um=[math.sqrt(3.0)],
        )
        self.assertEqual(len(result.optics.sizes), 1)
        self.assertLessEqual(
            result.optics.scattering_cross_section[0],
            result.optics.extinction_cross_section[0],
        )
        self.assertAlmostEqual(
            result.optics.absorption_cross_section[0],
            result.optics.extinction_cross_section[0]
            - result.optics.scattering_cross_section[0],
        )
        self.assertIn("csca:clipped_to_cext", result.provenance.constraint_corrections)

    def test_phase_alignment_and_optional_normalization(self):
        def phase_for(angles, multiplier):
            return [
                [
                    [[multiplier * (1.0 + math.cos(math.radians(a)) ** 2) if i == j == 0 else 0.0
                      for j in range(4)] for i in range(4)]
                    for a in angles
                ]
                for _ in range(2)
            ]

        nodes = [
            OpticalNode(
                {"wavelength": 1.0},
                optics(
                    [1, 2],
                    angles=(0, 90, 180),
                    phase=phase_for((0, 90, 180), 1.0),
                ),
            ),
            OpticalNode(
                {"wavelength": 3.0},
                optics(
                    [3, 4],
                    angles=(0, 60, 120, 180),
                    phase=phase_for((0, 60, 120, 180), 2.0),
                ),
            ),
        ]
        result = interpolate_nodes(
            "sphere_water_cloud",
            nodes,
            {"wavelength": 2.0},
            target_size_um=[1.5],
            target_angles_degrees=[0, 30, 60, 90, 120, 150, 180],
            phase_normalization="unit_solid_angle",
        )
        self.assertEqual(len(result.optics.phase_matrix), 1)
        self.assertEqual(len(result.optics.phase_matrix[0]), 7)
        angles = [math.radians(a) for a in result.optics.scattering_angles]
        p11 = [matrix[0][0] for matrix in result.optics.phase_matrix[0]]
        integral = sum(
            0.25
            * (
                p11[i - 1] * math.sin(angles[i - 1])
                + p11[i] * math.sin(angles[i])
            )
            * (angles[i] - angles[i - 1])
            for i in range(1, len(angles))
        )
        self.assertAlmostEqual(integral, 1.0)

    def test_profile_specific_validation(self):
        node = OpticalNode(
            {"wavelength": 10.0, "relative_humidity": 0.5},
            optics([1, 2]),
        )
        with self.assertRaisesRegex(InterpolationError, r"lie in \[0, 1\]"):
            interpolate_nodes(
                "sea_salt",
                [node],
                {"wavelength": 10.0, "relative_humidity": 50.0},
            )
        with self.assertRaisesRegex(InterpolationError, "requires target coordinates"):
            interpolate_nodes(
                "ice",
                [
                    OpticalNode(
                        {
                            "wavelength": 10.0,
                            "temperature": 220.0,
                            "roundness": 2.0,
                            "aspect_ratio": 1.0,
                        },
                        optics([1, 2]),
                    )
                ],
                {"wavelength": 10.0, "temperature": 220.0},
            )

    def test_netcdf_product_and_provenance(self):
        try:
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("netCDF4 is not installed")
        result = interpolate_nodes(
            "water_cloud",
            [
                OpticalNode({"wavelength": 1.0}, optics([1, 2])),
                OpticalNode({"wavelength": 2.0}, optics([2, 3])),
            ],
            {"wavelength": 1.5},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_interpolated_optics_netcdf(
                result, Path(directory) / "interpolated.nc"
            )
            with Dataset(path) as dataset:
                self.assertIn("extinction_cross_section", dataset.variables)
                provenance = json.loads(
                    dataset.getncattr("interpolation_provenance_json")
                )
                self.assertEqual(provenance["method"], "multilinear")
                self.assertEqual(dataset.getncattr("particle_type"), "sphere_water_cloud")


class Phase5SourceFileTests(unittest.TestCase):
    def test_downloaded_ice_series_preserves_non_wavelength_axes_and_size_grid(self):
        try:
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("netCDF4 is required")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pairs = []
            raw_sizes = [1.0, 2.0, 4.0]
            for wavelength, ref_real, multiplier in (
                (0.6, 1.30, 1.0),
                (1.0, 1.40, 3.0),
            ):
                path = root / (
                    "L1.5_super_spheroid_ice_n_2.000_asp_1.250_"
                    f"wl_{wavelength:.3f}_um_ref_{ref_real:.3f}_0.0_"
                    "t_270k_test.nc"
                )
                with Dataset(path, "w") as dataset:
                    dataset.setncatts(
                        {
                            "data_version": "test-v1",
                            "description": "Native test scattering product",
                            "processing_type": "L1.5",
                        }
                    )
                    dataset.createDimension("xsize_maxd", len(raw_sizes))
                    dataset.createDimension("sca_angle", 3)

                    def variable(name, dimensions=(), units="1"):
                        result = dataset.createVariable(name, "f8", dimensions)
                        result.setncatts(
                            {"units": units, "long_name": f"native {name}"}
                        )
                        return result

                    variable("xsize_maxd", ("xsize_maxd",))[:] = [1.2, 2.4, 4.8]
                    variable("sca_angle", ("sca_angle",), "degrees")[:] = [
                        0.0,
                        90.0,
                        180.0,
                    ]
                    variable("wavelength", units="um").assignValue(wavelength)
                    variable("mr").assignValue(ref_real)
                    variable("mi").assignValue(0.001 * multiplier)
                    variable("temperature", units="K").assignValue(270.0)
                    variable("ssph_n").assignValue(2.0)
                    variable("ssph_asp").assignValue(1.25)
                    variable("xsize_veq", ("xsize_maxd",))[:] = raw_sizes
                    variable("qext", ("xsize_maxd",))[:] = [
                        multiplier,
                        2 * multiplier,
                        4 * multiplier,
                    ]
                    cext_values = [
                        multiplier,
                        2 * multiplier,
                        4 * multiplier,
                    ]
                    variable("cext", ("xsize_maxd",))[:] = cext_values
                    ssa_values = [0.5, 0.6, 0.7]
                    variable("csca", ("xsize_maxd",))[:] = [
                        value * ssa
                        for value, ssa in zip(cext_values, ssa_values)
                    ]
                    variable("cabs", ("xsize_maxd",))[:] = [
                        value * (1.0 - ssa)
                        for value, ssa in zip(cext_values, ssa_values)
                    ]
                    variable("qsca", ("xsize_maxd",))[:] = [99.0, 99.0, 99.0]
                    variable("qabs", ("xsize_maxd",))[:] = [88.0, 88.0, 88.0]
                    variable("ssa", ("xsize_maxd",))[:] = ssa_values
                    variable("g", ("xsize_maxd",))[:] = [0.1, 0.2, 0.3]
                    variable("proj_area", ("xsize_maxd",))[:] = [1.0, 2.0, 4.0]
                    for phase_name in ("p11", "p12", "p22", "p33", "p44", "p43"):
                        if phase_name == "p12":
                            endpoints = (
                                (0.2, 0.4)
                                if multiplier == 1.0
                                else (2.4, 3.0)
                            )
                            phase_value = [
                                [endpoints[0], float("nan"), endpoints[1]]
                                for _ in raw_sizes
                            ]
                        else:
                            phase_value = 0.7 if phase_name == "p22" else multiplier
                        phase_variable = variable(
                            phase_name, ("xsize_maxd", "sca_angle")
                        )
                        if phase_name == "p22":
                            phase_variable.description = (
                                "phase matrix element scaled by p11"
                            )
                        phase_variable[:] = phase_value
                pairs.append((RemoteObject(path.as_posix(), path.stat().st_size), path))

            products = interpolate_downloaded_ice_series(
                pairs, [0.67], root / "products"
            )
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].status, "created")
            self.assertEqual(
                products[0].path.name,
                "L1.5_super_spheroid_ice_n_2.000_asp_1.250_"
                "wl_0.670_um_ref_1.317e+00_1.350e-03_"
                "t_270k_test_user_derived.nc",
            )
            self.assertEqual(products[0].fixed_coordinates["temperature"], 270.0)
            self.assertEqual(products[0].fixed_coordinates["roundness"], 2.0)
            self.assertEqual(products[0].fixed_coordinates["aspect_ratio"], 1.25)
            with Dataset(pairs[0][1]) as source, Dataset(products[0].path) as dataset:
                self.assertEqual(set(dataset.variables), set(source.variables))
                self.assertEqual(set(dataset.dimensions), set(source.dimensions))
                self.assertEqual(dataset.ncattrs(), source.ncattrs())
                for attribute in source.ncattrs():
                    self.assertEqual(
                        dataset.getncattr(attribute), source.getncattr(attribute)
                    )
                for name, source_variable in source.variables.items():
                    output_variable = dataset.variables[name]
                    self.assertEqual(output_variable.dimensions, source_variable.dimensions)
                    self.assertEqual(output_variable.dtype, source_variable.dtype)
                    self.assertEqual(output_variable.ncattrs(), source_variable.ncattrs())
                    for attribute in source_variable.ncattrs():
                        self.assertEqual(
                            output_variable.getncattr(attribute),
                            source_variable.getncattr(attribute),
                        )
                self.assertEqual(list(dataset.variables["xsize_veq"][:]), raw_sizes)
                self.assertNotIn("size", dataset.variables)
                self.assertIn("p11", dataset.variables)
                self.assertAlmostEqual(float(dataset.variables["wavelength"][:]), 0.67)
                self.assertAlmostEqual(float(dataset.variables["temperature"][:]), 270.0)
                self.assertAlmostEqual(float(dataset.variables["ssph_n"][:]), 2.0)
                self.assertAlmostEqual(float(dataset.variables["ssph_asp"][:]), 1.25)
                fraction = (0.67 - 0.6) / (1.0 - 0.6)
                expected_p11 = (1.0 - fraction) * 1.0 + fraction * 3.0
                expected_ratio = (1.0 - fraction) * 0.2 + fraction * 0.8
                self.assertAlmostEqual(
                    float(dataset.variables["p12"][0, 0]),
                    expected_p11 * expected_ratio,
                )
                expected_middle_ratio = (
                    (1.0 - fraction) * 0.3 + fraction * 0.9
                )
                self.assertAlmostEqual(
                    float(dataset.variables["p12"][0, 1]),
                    expected_p11 * expected_middle_ratio,
                )
                self.assertAlmostEqual(float(dataset.variables["p22"][0, 1]), 0.7)
                expected_qext = math.exp(fraction * math.log(3.0))
                self.assertAlmostEqual(float(dataset.variables["qext"][1]), expected_qext)
                self.assertAlmostEqual(
                    float(dataset.variables["qsca"][1]), expected_qext * 0.6
                )
                self.assertAlmostEqual(
                    float(dataset.variables["cext"][1]),
                    float(dataset.variables["csca"][1])
                    + float(dataset.variables["cabs"][1]),
                )

            cached = interpolate_downloaded_ice_series(
                pairs, [0.67], root / "products"
            )
            self.assertEqual(cached[0].status, "skipped")
            with Dataset(products[0].path, "r+") as dataset:
                dataset.variables["p12"][0, 0] = 999.0
            refreshed = interpolate_downloaded_ice_series(
                pairs, [0.67], root / "products"
            )
            self.assertEqual(refreshed[0].status, "created")
            with Dataset(products[0].path) as dataset:
                self.assertAlmostEqual(
                    float(dataset.variables["p12"][0, 0]),
                    expected_p11 * expected_ratio,
                )

    def test_cached_l1_sources_are_loaded(self):
        try:
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("netCDF4 is not installed")
        with tempfile.TemporaryDirectory() as directory:
            sources = []
            for wavelength, multiplier in ((1.0, 1.0), (3.0, 3.0)):
                path = Path(directory) / f"{wavelength}.nc"
                with Dataset(path, "w") as dataset:
                    dataset.createDimension("xsize_veq", 2)
                    dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = [
                        2.0 * math.pi / wavelength,
                        4.0 * math.pi / wavelength,
                    ]
                    dataset.createVariable("wavelength", "f8")[:] = wavelength
                    dataset.createVariable("cext", "f8", ("xsize_veq",))[:] = [
                        multiplier,
                        2 * multiplier,
                    ]
                    dataset.createVariable("ssa", "f8", ("xsize_veq",))[:] = [0.5, 0.5]
                    dataset.createVariable("g", "f8", ("xsize_veq",))[:] = [0.1, 0.2]
                sources.append(
                    OpticalSourceRequest(path, {"wavelength": wavelength})
                )
            result = interpolate_sources(
                "sphere_water_cloud", sources, {"wavelength": 2.0}
            )
        self.assertEqual(result.provenance.method, "multilinear")
        self.assertEqual(len(result.provenance.neighbors), 2)
        self.assertTrue(all(neighbor.source.endswith(".nc") for neighbor in result.provenance.neighbors))


if __name__ == "__main__":
    unittest.main()
