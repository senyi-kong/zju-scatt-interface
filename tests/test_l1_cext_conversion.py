import math
import tempfile
import unittest
from pathlib import Path

from tests.local_data import local_l1_root
from zju_scatt_interface.bulk.lowlevel import calculate_bulk_optics_from_file
from zju_scatt_interface.errors import ScattError
from zju_scatt_interface.optics.loading import load_single


class L1CextConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from netCDF4 import Dataset  # noqa: F401
        except ImportError:
            self.skipTest("netCDF4 is not installed")

    def _create_file(
        self,
        path: Path,
        *,
        include_wavelength: bool = True,
        multidimensional: bool = False,
    ) -> None:
        from netCDF4 import Dataset

        with Dataset(path, "w") as dataset:
            dataset.createDimension("xsize_maxd", 2)
            dataset.createDimension("sca_angle", 2)
            dataset.createVariable("xsize_maxd", "f8", ("xsize_maxd",))[:] = [1.0, 2.0]
            if multidimensional:
                dataset.createDimension("rh", 2)
                dataset.createVariable("rh", "f8", ("rh",))[:] = [0.0, 50.0]
                size = dataset.createVariable(
                    "xsize_veq", "f8", ("rh", "xsize_maxd")
                )
                size[:] = [[1.0, 2.0], [1.5, 2.5]]
                optical_dimensions = ("rh", "xsize_maxd")
                phase_dimensions = ("rh", "xsize_maxd", "sca_angle")
            else:
                size = dataset.createVariable("xsize_veq", "f8", ("xsize_maxd",))
                size[:] = [1.0, 2.0]
                optical_dimensions = ("xsize_maxd",)
                phase_dimensions = ("xsize_maxd", "sca_angle")
            if include_wavelength:
                dataset.createVariable("wavelength", "f8")[:] = 2.0 * math.pi
            dataset.createVariable("sca_angle", "f8", ("sca_angle",))[:] = [0.0, 180.0]
            if multidimensional:
                dataset.createVariable("cext", "f8", optical_dimensions)[:] = [
                    [1.0, 2.0],
                    [3.0, 4.0],
                ]
                dataset.createVariable("ssa", "f8", optical_dimensions)[:] = [
                    [0.5, 0.6],
                    [0.7, 0.8],
                ]
                dataset.createVariable("g", "f8", optical_dimensions)[:] = [
                    [0.1, 0.2],
                    [0.3, 0.4],
                ]
                dataset.createVariable("p11", "f8", phase_dimensions)[:] = [
                    [[1.0, 2.0], [3.0, 4.0]],
                    [[5.0, 6.0], [7.0, 8.0]],
                ]
            else:
                dataset.createVariable("cext", "f8", optical_dimensions)[:] = [
                    math.pi,
                    4.0 * math.pi,
                ]
                dataset.createVariable("ssa", "f8", optical_dimensions)[:] = [0.5, 0.75]
                dataset.createVariable("g", "f8", optical_dimensions)[:] = [0.1, 0.2]
                dataset.createVariable("proj_area", "f8", optical_dimensions)[:] = [
                    2.0 * math.pi,
                    8.0 * math.pi,
                ]

    def test_scaled_cext_and_size_parameter_are_converted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scaled.nc"
            self._create_file(path)
            optics = load_single(path)

        self.assertEqual(optics.size_unit, "um")
        self.assertEqual(optics.cross_section_unit, "m2")
        self.assertEqual(optics.metadata["size_definition"], "volume_equivalent_sphere_radius")
        self.assertAlmostEqual(optics.sizes[0], 1.0)
        self.assertAlmostEqual(optics.extinction_cross_section[0], math.pi * 1.0e-12)
        self.assertAlmostEqual(
            optics.scattering_cross_section[0],
            0.5 * math.pi * 1.0e-12,
        )
        self.assertAlmostEqual(optics.projected_area[0], 2.0 * math.pi * 1.0e-12)
        self.assertAlmostEqual(optics.single_scattering_albedo[0], 0.5)

    def test_bulk_coefficient_converts_cm3_to_m3(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scaled.nc"
            self._create_file(path)
            result = calculate_bulk_optics_from_file(
                path,
                [1.0, 0.0],
                distribution_mode="bin",
            )

        self.assertAlmostEqual(result.extinction_coefficient, math.pi * 1.0e-6)
        self.assertAlmostEqual(result.number_concentration, 1.0)
        self.assertEqual(result.metadata["extinction_coefficient_unit"], "m-1")
        self.assertEqual(result.metadata["number_concentration_output_unit"], "cm-3")

    def test_native_efficiency_retained_with_cross_sections_and_bulk_still_works(self):
        from netCDF4 import Dataset
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "with_efficiency.nc"
            self._create_file(path)
            with Dataset(path, "a") as dataset:
                dataset.createVariable("qext", "f8", ("xsize_maxd",))[:] = [3.5, 2.1]
            optics = load_single(path)
            self.assertEqual(optics.extinction_efficiency, [3.5, 2.1])
            for actual, expected in zip(optics.scattering_efficiency, [1.75, 1.575]):
                self.assertAlmostEqual(actual, expected)
            result = calculate_bulk_optics_from_file(path, [1., 0.], distribution_mode="bin")
            # Cross sections remain authoritative even when native Q differs.
            self.assertAlmostEqual(result.extinction_coefficient, math.pi * 1.e-6)
            import matplotlib.pyplot as plt

            from zju_scatt_interface.plotting.single import plot_single_particle_optics
            figures = plot_single_particle_optics(optics)
            self.assertEqual(len(figures["properties"].axes[1].lines), 3)
            self.assertGreater(figures["properties"].axes[1].get_ylim()[1], 3.5)
            plt.close(figures["properties"])

    def test_one_command_plot_loads_file_and_uses_sibling_output_directory(self):
        from zju_scatt_interface.cli.plotting import run_single_scattering_plot
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"obtained.nc"
            self._create_file(path)
            result=run_single_scattering_plot([str(path)])
            self.assertEqual(result["output_dir"],Path(directory)/"obtained_plots")
            self.assertTrue(result["files"]["properties_png"].is_file())
            self.assertNotIn("phase_png",result["files"])

    def test_multidimensional_file_requires_and_applies_coordinate_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multidimensional.nc"
            self._create_file(path, multidimensional=True)
            with self.assertRaisesRegex(ScattError, "unresolved dimension 'rh'"):
                load_single(path)
            optics = load_single(
                path,
                coordinate_indices={"RH": 1},
                include_phase_matrix=True,
            )

        self.assertEqual(optics.sizes, [1.5, 2.5])
        self.assertAlmostEqual(optics.extinction_cross_section[0], 3.0e-12)
        self.assertAlmostEqual(optics.scattering_cross_section[0], 2.1e-12)
        self.assertEqual(optics.phase_matrix[0][0][0][0], 5.0)
        self.assertEqual(optics.metadata["coordinate_indices"], {"RH": 1})

    def test_grid_file_requires_user_wavelength(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid_wl_nan.nc"
            self._create_file(path, include_wavelength=False)
            with self.assertRaisesRegex(ScattError, "requires wavelength metadata"):
                load_single(path)
            optics = load_single(path, wavelength_um=2.0 * math.pi)

        self.assertAlmostEqual(optics.sizes[0], 1.0)
        self.assertEqual(optics.metadata["wavelength_source"], "user")

    def test_source_wavelength_cannot_be_overridden_inconsistently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wavelength.nc"
            self._create_file(path)
            with self.assertRaisesRegex(ScattError, "does not match source wavelength"):
                load_single(path, wavelength_um=0.55)

    def test_unknown_coordinate_dimension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multidimensional.nc"
            self._create_file(path, multidimensional=True)
            with self.assertRaisesRegex(
                ScattError,
                "Unknown coordinate_indices dimensions: relative_humidty",
            ):
                load_single(
                    path,
                    coordinate_indices={"relative_humidty": 1},
                )

    def test_phase_elements_declared_scaled_by_p11_are_expanded(self) -> None:
        from netCDF4 import Dataset

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scaled_phase.nc"
            self._create_file(path)
            with Dataset(path, "a") as dataset:
                dimensions = ("xsize_maxd", "sca_angle")
                p11 = dataset.createVariable("p11", "f8", dimensions)
                p11.description = "normalized phase function"
                p11[:] = [[2.0, 4.0], [3.0, 5.0]]
                p12 = dataset.createVariable("p12", "f8", dimensions)
                p12.description = "phase matrix element scaled by p11"
                p12[:] = [[-0.5, 0.25], [-0.25, 0.5]]
                p22 = dataset.createVariable("p22", "f8", dimensions)
                p22.description = "phase matrix element scaled by p11"
                p22[:] = 1.0
            optics = load_single(path, include_phase_matrix=True)

        self.assertEqual(optics.phase_matrix[0][0][0][0], 2.0)
        self.assertEqual(optics.phase_matrix[0][0][0][1], -1.0)
        self.assertEqual(optics.phase_matrix[0][1][0][1], 1.0)
        self.assertEqual(optics.phase_matrix[1][1][1][1], 5.0)


class LocalL1RegressionTests(unittest.TestCase):
    def test_real_ice_file_matches_k2_conversion(self) -> None:
        root = local_l1_root() / "super_spheroid_ice"
        if not root.exists():
            self.skipTest("Local ZJU-SCATT L1 database is not mounted")
        path = next(root.rglob("*.nc"))
        optics = load_single(path)

        from netCDF4 import Dataset

        with Dataset(path) as dataset:
            wavelength_um = float(dataset.variables["wavelength"][:])
            raw_size = float(dataset.variables["xsize_veq"][0])
            raw_cext = float(dataset.variables["cext"][0])
        factor = wavelength_um / (2.0 * math.pi)
        self.assertAlmostEqual(optics.sizes[0], raw_size * factor)
        self.assertAlmostEqual(
            optics.extinction_cross_section[0],
            raw_cext * factor**2 * 1.0e-12,
        )

    def test_all_eight_local_families_load_one_physical_slice(self) -> None:
        root = local_l1_root()
        if not root.exists():
            self.skipTest("Local ZJU-SCATT L1 database is not mounted")
        cases = {
            "coated_super_spheroid_seasalt": {"coordinate_indices": {"rh": 0}},
            "encapsulated_fractal_aggregates_black_carbon": {
                "coordinate_indices": {"vf": 0},
                "wavelength_um": 0.55,
            },
            "sphere_nitrate": {"coordinate_indices": {"rh": 0}},
            "sphere_organic_carbon": {"coordinate_indices": {"rh": 0}},
            "sphere_sulfate": {"coordinate_indices": {"rh": 0}},
            "sphere_water_cloud": {},
            "super_spheroid": {"wavelength_um": 0.55},
            "super_spheroid_ice": {},
        }
        for family, options in cases.items():
            with self.subTest(family=family):
                path = next((root / family).rglob("*.nc"))
                optics = load_single(path, **options)
                self.assertGreater(len(optics.sizes), 1)
                self.assertEqual(len(optics.sizes), len(optics.extinction_cross_section))
                self.assertEqual(optics.size_unit, "um")
                self.assertEqual(optics.cross_section_unit, "m2")
                for extinction, scattering, absorption in zip(
                    optics.extinction_cross_section,
                    optics.scattering_cross_section,
                    optics.absorption_cross_section,
                ):
                    self.assertAlmostEqual(extinction, scattering + absorption)


if __name__ == "__main__":
    unittest.main()
