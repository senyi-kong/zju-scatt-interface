"""Native-format contracts for retrieval interpolation and named outputs."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.optics.loading as _domain_optics_loading
import zju_scatt_interface.sources.coordinates as _domain_sources_coordinates
from zju_scatt_interface.optics.retrieval.native import verify_native_schema
from zju_scatt_interface.optics.retrieval.workflow import interpolate_downloaded_particle_series


def native_fixture(path, wavelength, factor, *, family="dust", grid=(1.0, 2.0, 3.0), ratio=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(path, "w") as dataset:
        dataset.setncatts(
            {
                "data_level": "L1",
                "data_version": "v1.2.1" if family == "bc" else "v1.0",
                "dataset_name": "encapsulated_fractal_aggregates_black_carbon"
                if family == "bc"
                else "super_spheroid",
                "creator": "Original scientist",
                "creation_date": "20260417",
                "description": "Native source",
            }
        )
        dataset.createDimension("xsize_maxd", len(grid))
        dataset.createDimension("sca_angle", 3)
        dims = []
        if family == "bc":
            dataset.createDimension("Df", 1)
            dataset.createDimension("vf", 2)
            dataset.createVariable("Df", "f4", ("Df",))[:] = [1.8]
            dataset.createVariable("vf", "f4", ("vf",))[:] = [0.1, 0.5]
            dims += ["Df", "vf"]
        dims += ["xsize_maxd"]
        for name, values, dimensions, unit in (
            ("xsize_maxd", grid, ("xsize_maxd",), "1"),
            ("xsize_veq", np.asarray(grid) * 0.8, ("xsize_maxd",), "1"),
            ("sca_angle", [0, 90, 180], ("sca_angle",), "degrees"),
        ):
            variable = dataset.createVariable(name, "f4", dimensions)
            variable[:] = values
            variable.units = unit
        if wavelength is not None:
            variable = dataset.createVariable("wavelength", "f4")
            variable[...] = wavelength
            variable.units = "um"
        if family == "dust":
            for name, value in (("mr", 1.5), ("mi", 0.005), ("ssph_n", 2.0), ("ssph_asp", 1.0)):
                dataset.createVariable(name, "f4")[...] = value
        shape = tuple(len(dataset.dimensions[name]) for name in dims)
        area = np.broadcast_to(np.asarray(grid) ** 2, shape)
        for name, values in (
            ("proj_area", area),
            ("cext", factor * area),
            ("qext", factor * np.ones(shape)),
            ("ssa", np.full(shape, 0.7)),
            ("g", np.full(shape, 0.4)),
        ):
            variable = dataset.createVariable(
                name, "f4", tuple(dims), zlib=True, fill_value=np.float32(np.nan)
            )
            variable[:] = values
            variable.units = "1"
            variable.long_name = name + " original definition"
        p11 = np.broadcast_to(np.array([2.0, 1.0, 2.0]), shape + (3,))
        for name, scale in (
            ("p11", 1),
            ("p12", -0.2),
            ("p22", 0.8),
            ("p33", 0.4),
            ("p44", 0.5),
            ("p43", -0.1),
        ):
            variable = dataset.createVariable(name, "f4", tuple(dims) + ("sca_angle",), zlib=True)
            variable[:] = np.full_like(p11, scale) if ratio and name != "p11" else scale * p11
            variable.units = "1"
            variable.description = (
                "phase matrix element scaled by p11"
                if ratio and name != "p11"
                else "phase matrix element"
            )


class NativeRetrievalTests(unittest.TestCase):
    def test_explicit_grid_shape_product_needs_no_physical_wavelength(self):
        from itertools import product

        from zju_scatt_interface.optics.retrieval.native import write_native_source_product

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for n, asp, mr, mi in product((2, 2.2), (1.6, 1.8), (1.5, 1.55), (0.001, 0.003)):
                path = root / f"L1_super_spheroid_n_{n:.3f}_asp_{asp:.3f}_wl_nan_ref_{mr}_{mi}_v1.0_20260409.nc"
                native_fixture(path, None, 2)
                records.append({"obj": _domain_access_models.RemoteObject(path.name), "path": path, "is_grid": True,
                    "coordinates": {"roundness": n, "aspect_ratio": asp,
                                    "refractive_index_real": mr, "refractive_index_imaginary": mi}})
            path, _, provenance, _ = write_native_source_product(records, "super_spheroid", None,
                {"target_indices": {"refractive_index_real": 1.51, "refractive_index_imaginary": 0.0023},
                 "target_shape_parameters": {"roundness": 2.1, "aspect_ratio": 1.7}}, root / "out")
            self.assertIn("_n_2.100_asp_1.700_wl_nan_ref_1.510e+00_2.300e-03_", path.name)
            self.assertTrue(verify_native_schema(path, provenance["template_source"]))
            with Dataset(path) as ds:
                self.assertNotIn("wavelength", ds.variables)
                self.assertNotIn("target_wavelength_um", ds.ncattrs())
                for variable, value in (("ssph_n", 2.1), ("ssph_asp", 1.7), ("mr", 1.51), ("mi", 0.0023)):
                    self.assertAlmostEqual(float(ds.variables[variable][:]), value, places=6)
                self.assertTrue(np.isfinite(ds.variables["cext"][:]).all())
            self.assertEqual(len(provenance["neighbors"]), 16)

    def test_ice_native_product_interpolates_wavelength_and_temperature(self):
        from zju_scatt_interface.optics.retrieval.native import write_native_source_product

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for wavelength in (1.5, 2.0):
                for temperature in (220, 270):
                    path = root / (
                        f"L1_super_spheroid_ice_n_2.000_asp_1.000_wl_{wavelength:.3f}_um_"
                        f"ref_1.3_0.01_t_{temperature}k_v1.0_20260403.nc"
                    )
                    native_fixture(path, wavelength, temperature / 100)
                    with Dataset(path, "a") as dataset:
                        dataset.createVariable("temperature", "f8")[...] = temperature
                    records.append({"obj": _domain_access_models.RemoteObject(path.name), "path": path,
                                    "is_grid": False,
                                    "coordinates": {"wavelength": wavelength, "temperature": temperature}})
            path, _, provenance, _ = write_native_source_product(
                records, "super_spheroid_ice", 1.6, {"target_temperature_k": 250}, root / "out"
            )
            self.assertIn("_t_250k_", path.name)
            self.assertTrue(verify_native_schema(path, provenance["template_source"]))
            with Dataset(path) as dataset:
                self.assertAlmostEqual(float(dataset.variables["temperature"][:]), 250)
                self.assertAlmostEqual(float(dataset.variables["wavelength"][:]), 1.6, places=6)
            self.assertEqual(len(provenance["neighbors"]), 4)
            self.assertAlmostEqual(sum(node["weight"] for node in provenance["neighbors"]), 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def bc_sources(self, *, grids=None):
        family = "encapsulated_fractal_aggregates_black_carbon"
        sources = []
        for i, wavelength in enumerate((1.0, 2.0)):
            name = f"L1_{family}_df_1.80_wl_{wavelength:.3f}_um_ref_bc_2.0_0.9_hygro_1.51_0.02_v1.2.1_20260616.nc"
            path = self.root / family / name
            native_fixture(
                path,
                wavelength,
                (2.0, 8.0)[i],
                family="bc",
                ratio=True,
                grid=grids[i] if grids else (1.0, 2.0, 3.0),
            )
            sources.append(
                (_domain_access_models.RemoteObject(f"Single_opt/{family}/{name}", path.stat().st_size), path)
            )
        _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
        return sources, processing

    def test_complete_schema_and_internal_axes_survive(self):
        sources, processing = self.bc_sources()
        results = interpolate_downloaded_particle_series(
            sources, [1.5], processing, self.root / "outputs", include_phase_matrix=False
        )
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertTrue(verify_native_schema(result.path, result.provenance["template_source"]))
        self.assertNotRegex(result.path.name, r"_[0-9a-f]{20}_")
        self.assertRegex(
            result.path.name, r"^L1\.5_.*_wl_1\.500_um_ref_bc_.*_interp_from_l1_v1\.2\.1_\d{8}\.nc$"
        )
        with Dataset(result.path) as dataset:
            self.assertEqual(dataset.variables["cext"].dimensions, ("Df", "vf", "xsize_maxd"))
            self.assertEqual(
                dataset.variables["p12"].dimensions, ("Df", "vf", "xsize_maxd", "sca_angle")
            )
            self.assertEqual(dataset.variables["cext"].units, "1")
            self.assertNotIn("extinction_cross_section", dataset.variables)
            self.assertNotIn("phase_matrix", dataset.variables)
            self.assertEqual(dataset.creator, "Original scientist")
            self.assertEqual(dataset.data_level, "L1.5")
            self.assertIn("wavelength_interpolation", dataset.processing_type)
            np.testing.assert_allclose(dataset.variables["qext"][:], 4.0)
            np.testing.assert_allclose(
                dataset.variables["cext"][:] / dataset.variables["proj_area"][:], 4.0
            )
            np.testing.assert_allclose(dataset.variables["p12"][:], -0.2)
            np.testing.assert_allclose(dataset.variables["p11"][:][0, 0, 0], [2, 1, 2])
            self.assertIn("scaled by p11", dataset.variables["p12"].description)

    def test_native_xsize_grid_stays_intact_without_extrapolation(self):
        sources, processing = self.bc_sources(grids=((1, 2, 3), (2, 3, 4)))
        result = interpolate_downloaded_particle_series(
            sources, [1.5], processing, self.root / "outputs"
        )[0]
        with (
            Dataset(result.path) as dataset,
            Dataset(result.provenance["template_source"]) as template,
        ):
            np.testing.assert_array_equal(
                dataset.variables["xsize_maxd"][:], template.variables["xsize_maxd"][:]
            )
            values = np.ma.filled(dataset.variables["cext"][:], np.nan)
            self.assertTrue(np.any(np.isnan(values)))
            self.assertTrue(np.any(np.isfinite(values)))
            self.assertEqual(result.provenance["template_size_points_outside_common_support"], 1)

    def test_original_and_derived_files_use_the_same_public_loader(self):
        sources, processing = self.bc_sources()
        result = interpolate_downloaded_particle_series(sources, [1.5], processing, self.root / "outputs")[0]
        for path in (sources[0][1], result.path):
            optics = _domain_optics_loading.load_single(
                path, size_dataset="xsize_veq", coordinate_indices={"Df": 0, "vf": 0},
                include_phase_matrix=True,
            )
            self.assertEqual(len(optics.sizes), 3)
            self.assertTrue(np.all(np.isfinite(optics.extinction_cross_section)))
            self.assertIsNotNone(optics.phase_matrix)

    def test_dust_raw_phase_convention_and_no_added_variables(self):
        sources = []
        for n in (1.4, 1.5):
            for k in (0.001, 0.01):
                name = f"L1_super_spheroid_n_2.000_asp_1.000_wl_nan_ref_{n}_{k}_v1.0_20260417.nc"
                path = self.root / "super_spheroid" / name
                native_fixture(path, None, 2.0)
                sources.append((_domain_access_models.RemoteObject("Single_opt/super_spheroid/" + name), path))
        _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
        result = interpolate_downloaded_particle_series(
            sources, [1.5], processing, self.root / "outputs"
        )[0]
        self.assertTrue(verify_native_schema(result.path, result.provenance["template_source"]))
        with Dataset(result.path) as dataset:
            self.assertNotIn("wavelength", dataset.variables)
            self.assertAlmostEqual(dataset.target_wavelength_um, 1.5)
            self.assertAlmostEqual(float(dataset.variables["mr"][:]), 1.4662016426740325, places=6)
            np.testing.assert_allclose(
                dataset.variables["p12"][:], -0.2 * dataset.variables["p11"][:]
            )
            self.assertIn(
                "Dust_refractive_index_statistics.csv", dataset.interpolation_provenance_json
            )
            self.assertEqual(
                json.loads(dataset.target_refractive_indices_json)["refractive_index_real"],
                1.4662016426740325,
            )
        repeated = interpolate_downloaded_particle_series(
            list(reversed(sources)), [1.5], processing, self.root / "outputs"
        )
        self.assertEqual(repeated[0].path, result.path)
        self.assertEqual(repeated[0].status, "skipped")


if __name__ == "__main__":
    unittest.main()
