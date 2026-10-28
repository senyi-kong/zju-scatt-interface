"""Unified shape filters through the public retrieval API and native output."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from netCDF4 import Dataset

import zju_scatt_interface.access.catalog as _domain_access_catalog
import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.manifests as _domain_access_manifests
import zju_scatt_interface.access.metadata as _domain_access_metadata
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.requests as _domain_access_requests
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.errors as _domain_errors
from tests.test_native_retrieval import native_fixture


class ShapesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.objects = [_domain_access_models.RemoteObject(
            f"Single_opt/super_spheroid/L1_super_spheroid_n_{n:.3f}_asp_{asp:.3f}_wl_nan_ref_1.5_0.01.nc"
        ) for n in (2, 2.5, 3) for asp in (1, 1.5, 2)]
        self.manifest = self.root / "catalog.jsonl"
        _domain_access_manifests.write_manifest(self.objects, self.manifest, "jsonl")

    def retrieve(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return _domain_access_retrieval.retrieve_sources(manifest=self.manifest, **kwargs)

    def pairs(self, result):
        return {(_domain_access_metadata.extract_scatt_metadata(obj.name)["n"],
                 _domain_access_metadata.extract_scatt_metadata(obj.name)["aspect_ratio"]) for obj in result.objects}

    def test_single_exact_shape_and_canonical_aliases(self):
        for shape in ({"n": 2, "asp": 1}, {"roundness": 2, "aspect_ratio": 1},
                      {"ssph_n": 2, "ssph_asp": 1}):
            self.assertEqual(self.pairs(self.retrieve(shapes=shape)), {(2, 1)})

    def test_paired_shapes_do_not_create_cross_combinations(self):
        self.assertEqual(self.pairs(self.retrieve(shapes=[{"n": 2, "asp": 1}, {"n": 3, "asp": 2}])),
                         {(2, 1), (3, 2)})

    def test_inclusive_ranges_mixed_values_and_omission(self):
        self.assertEqual(len(self.retrieve(shapes={"n": (2, 3), "asp": (1, 2)}).objects), 9)
        self.assertEqual(self.pairs(self.retrieve(shapes={"n": (2, 3), "asp": 1})),
                         {(2, 1), (2.5, 1), (3, 1)})
        self.assertEqual(len(self.retrieve().objects), 9)
        self.assertEqual(len(self.retrieve(shapes={"n": 4}).objects), 0)

    def test_duplicate_entries_do_not_duplicate_files_and_missing_axis_does_not_match(self):
        self.assertEqual(len(self.retrieve(shapes=[{"n": 2}, {"n": 2}]).objects), 3)
        self.assertEqual(len(self.retrieve(shapes={"df": 1.8}).objects), 0)

    def test_bc_fractal_dimension(self):
        objects = [_domain_access_models.RemoteObject(
            f"Single_opt/encapsulated_fractal_aggregates_black_carbon/L1_bc_df_{df}_ref_bc_2_0.8_hygro_1.5_0.02.nc"
        ) for df in (1.8, 2)]
        _domain_access_manifests.write_manifest(objects, self.manifest, "jsonl")
        self.assertEqual(len(self.retrieve(shapes={"fractal_dimension": 1.8}).objects), 1)

    def test_live_scan_uses_the_same_paired_filter(self):
        client = mock.Mock()
        client.iter_objects.return_value = iter(self.objects)
        with contextlib.redirect_stdout(io.StringIO()):
            result = _domain_access_retrieval.retrieve_sources(client=client, sources="Single_opt/super_spheroid/",
                shapes=[{"n": 2, "asp": 1}, {"n": 3, "asp": 2}])
        self.assertEqual(self.pairs(result), {(2, 1), (3, 2)})

    def test_removed_options_are_rejected_with_migration_guidance(self):
        import inspect
        parameters = inspect.signature(_domain_access_requests.make_retrieval_args).parameters
        self.assertIn("shapes", parameters)
        self.assertNotIn("shape_ranges", parameters)
        self.assertNotIn("shape_targets", parameters)
        self.assertNotIn("shape_target_tolerance", parameters)
        for legacy in ({"shape_ranges": {"n": (2, 3)}}, {"shape_targets": {"n": [2, 3]}},
                       {"shape_ranges": {}}, {"shape_targets": {}}, {"shape_target_tolerance": 0.1}):
            for current in ({}, {"shapes": {"n": 2}}):
                with self.assertRaisesRegex(_domain_errors.ScattError, "Use shapes instead"):
                    self.retrieve(**current, **legacy)

    def test_invalid_shapes_rejected_before_scanning(self):
        invalid = [[], {}, "n=2", [None], [{"n": 2}, {}], {"n": [2, 3]},
                   {"n": (3, 2)}, {"n": (2,)}, {"n": float("nan")},
                   {"n": float("inf")}, {"n": True}, {"n": "2"},
                   {"unknown": 2}, {"temperature": 250}, {"n": 2, "roundness": 3}]
        for shapes in invalid:
            with self.subTest(shapes=shapes), mock.patch.object(_domain_access_catalog, 'objects_from_args') as scan:
                with self.assertRaises(_domain_errors.ScattError):
                    self.retrieve(shapes=shapes)
                scan.assert_not_called()

    def test_pairs_produce_only_two_temperature_interpolated_products(self):
        paths = {}
        objects = []
        for n, asp in ((2, 1), (2, 2), (3, 1), (3, 2)):
            for temperature in (220, 270):
                for wavelength in (1.5, 2):
                    name = (f"L1.5_super_spheroid_ice_n_{n:.3f}_asp_{asp:.3f}_wl_{wavelength:.3f}_um_"
                            f"ref_1.3_0.01_t_{temperature}k_v1.0_20260403.nc")
                    path = self.root / name
                    native_fixture(path, wavelength, temperature / 100)
                    with Dataset(path, "a") as ds:
                        ds.createVariable("temperature", "f8")[...] = temperature
                        ds.variables["ssph_n"][...] = n
                        ds.variables["ssph_asp"][...] = asp
                    obj = _domain_access_models.RemoteObject("Single_opt/super_spheroid_ice/" + name, path.stat().st_size)
                    objects.append(obj)
                    paths[obj.key] = path
        _domain_access_manifests.write_manifest(objects, self.manifest, "jsonl")

        def downloads(runtime, client, selected, stats):
            return 0, [_domain_access_models.DownloadResult(obj, paths[obj.key], "skipped") for obj in selected]

        with mock.patch.object(_domain_access_download, 'download_selected_objects', side_effect=downloads):
            result = self.retrieve(shapes=[{"n": 2, "asp": 1}, {"n": 3, "asp": 2}],
                target_wavelengths=[1.6], target_temperatures=[250], download=True,
                interpolation_output_dir=self.root / "derived")
        self.assertEqual(len(result.objects), 8)
        self.assertEqual(len(result.interpolated_products), 2)
        pairs = set()
        for product in result.interpolated_products:
            with Dataset(product.path) as ds:
                pairs.add((float(ds.variables["ssph_n"][:]), float(ds.variables["ssph_asp"][:])))
                self.assertEqual(float(ds.variables["temperature"][:]), 250)
        self.assertEqual(pairs, {(2, 1), (3, 2)})

    def test_non_native_ice_shape_and_temperature_interpolate_together(self):
        import math

        import numpy as np

        paths, objects = {}, []
        for n in (2, 2.25):
            for asp in (1.5, 1.75):
                for temperature in (220, 270):
                    for wavelength in (1.5, 2):
                        name = (f"L1.5_super_spheroid_ice_n_{n:.3f}_asp_{asp:.3f}_wl_{wavelength:.3f}_um_"
                                f"ref_1.3_0.01_t_{temperature}k_v1.0_20260403.nc")
                        path = self.root / name
                        factor = math.exp(0.1*n + 0.2*asp + 0.001*temperature + 0.3*wavelength)
                        native_fixture(path, wavelength, factor)
                        with Dataset(path, "a") as ds:
                            ds.createVariable("temperature", "f8")[...] = temperature
                            ds.variables["ssph_n"][...] = n
                            ds.variables["ssph_asp"][...] = asp
                        obj = _domain_access_models.RemoteObject("Single_opt/super_spheroid_ice/" + name, path.stat().st_size)
                        paths[obj.key] = path
                        objects.append(obj)
        _domain_access_manifests.write_manifest(objects, self.manifest, "jsonl")

        def downloads(runtime, client, selected, stats):
            return 0, [_domain_access_models.DownloadResult(obj, paths[obj.key], "skipped") for obj in selected]

        with mock.patch.object(_domain_access_download, 'download_selected_objects', side_effect=downloads):
            result = self.retrieve(particle_types="ice", shapes={"n": 2.1, "asp": 1.7},
                target_wavelengths=[1.6], target_temperatures=[250], download=True,
                interpolation_output_dir=self.root / "derived")
        self.assertEqual(len(result.objects), 16)
        self.assertEqual(len(result.interpolated_products), 1)
        product = result.interpolated_products[0]
        self.assertIn("_n_2.100_asp_1.700_", product.path.name)
        with Dataset(product.path) as ds:
            self.assertAlmostEqual(float(ds.variables["ssph_n"][:]), 2.1, places=6)
            self.assertAlmostEqual(float(ds.variables["ssph_asp"][:]), 1.7, places=6)
            self.assertEqual(float(ds.variables["temperature"][:]), 250)
            np.testing.assert_allclose(ds.variables["qext"][:], math.exp(1.28), rtol=1e-6)
        neighbors = product.provenance["neighbors"]
        self.assertEqual(len(neighbors), 16)
        self.assertAlmostEqual(sum(item["weight"] for item in neighbors), 1)
        for axis, upper, fraction in (("roundness", 2.25, 0.4), ("aspect_ratio", 1.75, 0.8),
                                      ("temperature", 270, 0.6), ("wavelength", 2, 0.2)):
            self.assertAlmostEqual(sum(item["weight"] for item in neighbors
                if item["coordinates"][axis] == upper), fraction)
