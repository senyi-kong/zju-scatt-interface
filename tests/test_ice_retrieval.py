"""Public ice temperature targets and native output boundary behavior."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from netCDF4 import Dataset

import zju_scatt_interface.access.catalog as _domain_access_catalog
import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.errors as _domain_errors
from tests.test_native_retrieval import native_fixture
from zju_scatt_interface.optics.retrieval.native import verify_native_schema
from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryWarning


class IceRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = {}
        for temperature in (160, 220, 270):
            for wavelength in (1.5, 2.0):
                name = (f"L1.5_super_spheroid_ice_n_2.000_asp_1.000_wl_{wavelength:.3f}_um_"
                        f"ref_1.3_0.01_t_{temperature}k_v1.0_20260403.nc")
                path = self.root / name
                native_fixture(path, wavelength, temperature / 100)
                with Dataset(path, "a") as dataset:
                    dataset.createVariable("temperature", "f8")[...] = temperature
                obj = _domain_access_models.RemoteObject(f"Single_opt/super_spheroid_ice/{name}", path.stat().st_size)
                self.sources[obj.key] = (obj, path)

    def retrieve(self, **parameters):
        def downloads(runtime, client, objects, stats):
            return 0, [_domain_access_models.DownloadResult(obj, self.sources[obj.key][1], "skipped") for obj in objects]
        with mock.patch.object(_domain_access_catalog, 'objects_from_args', return_value=(
            [obj for obj, _ in self.sources.values()], _domain_access_models.ScanStats()
        )), mock.patch.object(_domain_access_download, 'download_selected_objects', side_effect=downloads), contextlib.redirect_stdout(io.StringIO()):
            return _domain_access_retrieval.retrieve_sources(particle_types="ice", interpolation_output_dir=self.root / "out", **parameters)

    def test_250k_uses_four_nodes_and_preserves_schema(self):
        result = self.retrieve(target_wavelengths=[1.6], target_temperatures=[250], download=True)
        self.assertEqual(len(result.objects), 4)
        self.assertEqual(len(result.interpolated_products), 1)
        self.assertEqual(result.wavelength_processing.target_temperatures_k, (250,))
        product = result.interpolated_products[0]
        self.assertTrue(verify_native_schema(product.path, product.provenance["template_source"]))
        with Dataset(product.path) as dataset:
            self.assertEqual(float(dataset.variables["temperature"][:]), 250)
            self.assertAlmostEqual(float(dataset.variables["wavelength"][:]), 1.6, places=6)
            self.assertTrue(np.isfinite(dataset.variables["cext"][:]).all())
        self.assertEqual(len(product.provenance["neighbors"]), 4)
        self.assertAlmostEqual(sum(item["weight"] for item in product.provenance["neighbors"]
                                   if item["coordinates"]["temperature"] == 270), 0.6)

    def test_exact_native_coordinates_reuse_source(self):
        result = self.retrieve(target_wavelengths=[1.5], target_temperatures=220, download=True)
        self.assertEqual(len(result.objects), 1)
        self.assertFalse(result.wavelength_processing.interpolation_required)
        self.assertEqual(result.interpolated_products, [])

    def test_partial_shape_keeps_available_unspecified_geometry(self):
        result = self.retrieve(target_wavelengths=[1.6], target_temperatures=[250],
                               shapes={"n": 2}, download=True)
        self.assertEqual(len(result.objects), 4)
        self.assertEqual(len(result.interpolated_products), 1)

    def test_omitted_temperature_keeps_all_temperatures(self):
        self.assertEqual(len(self.retrieve(target_wavelengths=[1.5]).objects), 3)

    def test_omitted_temperature_interpolates_each_temperature_separately(self):
        result = self.retrieve(target_wavelengths=[1.6], download=True)
        self.assertEqual(len(result.interpolated_products), 3)

    def test_outside_coverage_writes_nan_optics(self):
        for temperature in (110, 300):
            with self.subTest(temperature=temperature), self.assertWarns(DatabaseBoundaryWarning):
                result = self.retrieve(target_wavelengths=[1.6], target_temperatures=[temperature], download=True)
            self.assertEqual(len(result.objects), 2)
            product = result.interpolated_products[0]
            self.assertEqual(product.provenance["status"], "out_of_database_bounds")
            with Dataset(product.path) as dataset:
                self.assertEqual(float(dataset.variables["temperature"][:]), temperature)
                for name in ("cext", "ssa", "g", "p11", "p12", "proj_area", "qext"):
                    self.assertTrue(np.isnan(np.ma.filled(dataset.variables[name][:], np.nan)).all(), name)
                self.assertTrue(np.isfinite(dataset.variables["xsize_maxd"][:]).all())

    def test_multiple_targets_and_source_only(self):
        result = self.retrieve(target_wavelengths=[1.6, 1.7], target_temperatures=[240, 250], download=True)
        self.assertEqual(len(result.interpolated_products), 4)
        result = self.retrieve(target_wavelengths=[1.6], target_temperatures=[250], download=True,
                               apply_interpolation=False)
        self.assertEqual(result.interpolated_products, [])

    def test_mixed_species_temperature_target_only_changes_ice(self):
        name = "L1_sphere_water_cloud_wl_1.500_um_ref_1.3_0.01.nc"
        path = self.root / name
        native_fixture(path, 1.5, 2)
        obj = _domain_access_models.RemoteObject("Single_opt/sphere_water_cloud/" + name, path.stat().st_size)
        self.sources[obj.key] = (obj, path)
        # The helper passes particle_types='ice', but the mocked catalog already
        # represents the filtered source set; this exercises mixed processing.
        result = self.retrieve(target_wavelengths=[1.5], target_temperatures=[250], download=True)
        self.assertIn(obj, result.objects)
        self.assertEqual(len(result.objects), 3)
        self.assertEqual(len(result.interpolated_products), 1)
        self.assertEqual(result.interpolated_products[0].particle_type, "super_spheroid_ice")

    def test_invalid_inputs_are_errors(self):
        for temperature in (0, -1, float("nan"), float("inf"), []):
            with self.subTest(temperature=temperature), self.assertRaises(_domain_errors.ScattError):
                self.retrieve(target_wavelengths=[1.6], target_temperatures=temperature)
        with self.assertRaises(_domain_errors.ScattError):
            self.retrieve(target_temperatures=[250])
