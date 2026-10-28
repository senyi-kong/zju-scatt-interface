"""Public retrieval selects interpolation support from a catalog, without network."""

import tempfile
import unittest
from itertools import product
from pathlib import Path
from unittest.mock import Mock, patch

import zju_scatt_interface.access.manifests as _domain_access_manifests
import zju_scatt_interface.access.metadata as _domain_access_metadata
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.errors as _domain_errors
from zju_scatt_interface.optics.retrieval.workflow import interpolate_downloaded_particle_series

SHAPES = [{"n": n, "asp": asp} for n, asp in ((2.7, 1.5), (2.8, 1.9), (2.5, 1.3))]


def dust_objects(ns=(2.4, 2.6, 2.8), aspects=(1.2, 1.4, 1.6, 1.8, 2.0),
                 real=(1.5,), imaginary=(0.003,), version="v1.0"):
    return [_domain_access_models.RemoteObject(
        f"Single_opt/super_spheroid/data/{version}/L{level}_super_spheroid_n_{n:.3f}_asp_{asp:.3f}"
        f"_wl_nan_ref_{mr:.3e}_{mi:.3e}_{version}_20260409.nc", size=10)
        for n, asp, mr, mi, level in product(ns, aspects, real, imaginary, ("1", "1.5"))]


class ShapeSourcePlanningTests(unittest.TestCase):
    def test_public_dimensionless_planner_does_not_assign_a_wavelength(self):
        from zju_scatt_interface.optics.refractive_index import ResolvedGridRefractiveIndex
        from zju_scatt_interface.sources.selection import select_shape_grid_sources
        point=ResolvedGridRefractiveIndex("super_spheroid",None,
            {"refractive_index_real":1.51,"refractive_index_imaginary":.0023},
            "explicit_refractive_index",{})
        selected,resolutions,required=select_shape_grid_sources(
            dust_objects(ns=(2.,2.2),aspects=(1.6,1.8),real=(1.5,1.6),imaginary=(.001,.003)),
            "super_spheroid",[point],[{"roundness":2.1,"aspect_ratio":1.7}])
        self.assertEqual(len(selected),16)
        self.assertTrue(required)
        self.assertIsNone(resolutions[0]["wavelength_um"])
        self.assertTrue(all(obj.name.startswith("L1.5_") for obj in selected))
        self.assertAlmostEqual(sum(node["weight"] for node in resolutions[0]["shape_stencils"][0]["neighbors"]),1)

    def request(self, objects, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "catalog.jsonl"
            _domain_access_manifests.write_manifest(objects, manifest, "jsonl")
            parameters = {"particle_types": "dust", "shapes": SHAPES,
                "target_wavelengths": [1.6], "apply_interpolation": False,
                "refractive_index_parameters": {"dust": {"mr": 1.5, "mi": 0.003}}}
            parameters.update(kwargs)
            return _domain_access_retrieval.retrieve_sources(manifest=manifest, client=Mock(), **parameters)

    def test_public_api_selects_paired_neighbors_and_prefers_l15(self):
        result = self.request(dust_objects())
        self.assertEqual(len(result.objects), 9)
        self.assertTrue(all(obj.name.startswith("L1.5_") for obj in result.objects))
        stencils = result.wavelength_processing.refractive_index_resolutions[0]["shape_stencils"]
        self.assertEqual([len(item["source_keys"]) for item in stencils], [4, 2, 4])
        self.assertEqual([item["target_shape_parameters"] for item in stencils],
                         [{"roundness": s["n"], "aspect_ratio": s["asp"]} for s in SHAPES])
        for stencil in stencils:
            self.assertAlmostEqual(sum(node["weight"] for node in stencil["neighbors"]), 1)
            self.assertEqual(stencil["method"], "multilinear")
        self.assertFalse(any("n_2.800_asp_1.200" in obj.name for obj in result.objects))

    def test_joint_shape_and_refractive_index_grid(self):
        result = self.request(dust_objects(ns=(2.6, 2.8), aspects=(1.4, 1.6),
                                          real=(1.4, 1.6), imaginary=(0.001, 0.01)),
                              shapes=SHAPES[0])
        self.assertEqual(len(result.objects), 16)
        self.assertTrue(result.wavelength_processing.interpolation_required)

    def test_compact_complete_stencil_preserves_full_catalog_weights(self):
        from zju_scatt_interface.optics.interpolation import OpticalNode, _select_neighbors
        objects = dust_objects(ns=(2.4, 2.6, 2.8), aspects=(1.2, 1.4, 1.6),
                               real=(1.4, 1.5, 1.6), imaginary=(0.0001, 0.001, 0.01))
        result = self.request(objects, shapes=SHAPES[0],
                              refractive_index_parameters={"dust": {"mr": 1.51, "mi": 0.003}})
        full = []
        for obj in objects:
            if not obj.name.startswith("L1.5_"):
                continue
            meta = _domain_access_metadata.extract_scatt_metadata(obj.name)
            full.append(OpticalNode({"roundness": meta["n"], "aspect_ratio": meta["aspect_ratio"],
                "refractive_index_real": meta["ref_real"], "refractive_index_imaginary": meta["ref_imag"]}, None, obj.key))
        target = {"refractive_index_real": 1.51, "refractive_index_imaginary": 0.003,
                  "roundness": 2.7, "aspect_ratio": 1.5}
        _, selected, weights, _, _ = _select_neighbors(tuple(target), target, full, sparse_power=2)
        expected = {node.source: weight for node, weight in zip(selected, weights)}
        stencil = result.wavelength_processing.refractive_index_resolutions[0]["shape_stencils"][0]
        self.assertEqual(set(stencil["source_keys"]), set(expected))
        for item in stencil["neighbors"]:
            self.assertAlmostEqual(item["weight"], expected[item["source"]])

    def test_exact_shapes_and_raw_filter_semantics(self):
        objects = dust_objects()
        exact = self.request(objects, shapes={"ssph_n": 2.8, "ssph_asp": 1.4})
        self.assertEqual(len(exact.objects), 1)
        self.assertFalse(exact.wavelength_processing.interpolation_required)
        native = self.request(objects, target_wavelengths=None)
        self.assertEqual(len(native.objects), 9)
        self.assertIsNone(native.wavelength_processing.refractive_index_resolutions[0]["wavelength_um"])
        raw = self.request(objects, target_wavelengths=None, refractive_index_parameters=None)
        self.assertEqual(raw.objects, [])
        ranged = self.request(objects, shapes={"n": (2.6, 2.8), "asp": (1.4, 1.6)})
        self.assertEqual(len(ranged.objects), 4)
        self.assertNotIn("shape_stencils", ranged.wavelength_processing.refractive_index_resolutions[0])

    def test_outside_coverage_and_incomplete_download_limits_rejected(self):
        for shape in ({"n": 4, "asp": 1.5}, {"n": 2.7, "asp": 3}):
            with self.subTest(shape=shape), self.assertRaises(_domain_errors.ScattError):
                self.request(dust_objects(), shapes=shape)
        with self.assertRaisesRegex(_domain_errors.ScattError, "truncate an interpolation stencil"):
            self.request(dust_objects(), max_files=1)

    def test_ambiguous_revisions_are_not_mixed(self):
        with self.assertRaisesRegex(_domain_errors.ScattError, "found 2"):
            self.request(dust_objects() + dust_objects(version="v2.0"))

    def test_different_targets_cannot_silently_use_different_revisions(self):
        objects = dust_objects(ns=(2.4, 2.6), aspects=(1.2, 1.4))
        objects += dust_objects(ns=(2.6, 2.8), aspects=(1.4, 1.6), version="v2.0")
        with self.assertRaisesRegex(_domain_errors.ScattError, "different database series"):
            self.request(objects, shapes=[SHAPES[0], SHAPES[2]])

    def test_default_refractive_index_notice_and_table_preserved(self):
        result = self.request(dust_objects(real=(1.4, 1.6), imaginary=(0.001, 0.01)),
                              refractive_index_parameters=None)
        resolution = result.wavelength_processing.refractive_index_resolutions[0]
        self.assertTrue(resolution["used_default"])
        self.assertTrue(resolution["table_relative_paths"])
        self.assertEqual(len(resolution["shape_stencils"]), 3)

    def test_grid_black_carbon_geometry_and_all_four_indices(self):
        axes = ((2.0, 2.2), (2.0, 2.2), (0.8, 0.9), (1.5, 1.55), (0.02, 0.03))
        objects = [_domain_access_models.RemoteObject(
            "Single_opt/encapsulated_fractal_aggregates_black_carbon/"
            f"L1_bc_df_{df:.3f}_ref_bc_{mr}_{mi}_hygro_{hr}_{hi}_v1.0_20260409.nc", size=10)
            for df, mr, mi, hr, hi in product(*axes)]
        result = self.request(objects, particle_types="black_carbon", shapes={"df": 2.1},
            refractive_index_parameters={"black_carbon": {
                "black_carbon_refractive_index_real": 2.1,
                "black_carbon_refractive_index_imaginary": 0.85,
                "hygroscopic_refractive_index_real": 1.525,
                "hygroscopic_refractive_index_imaginary": 0.025}})
        self.assertEqual(len(result.objects), 32)
        resolution = result.wavelength_processing.refractive_index_resolutions[0]
        self.assertEqual(resolution["shape_stencils"][0]["target_shape_parameters"], {"df": 2.1})

    def test_derived_products_use_each_target_stencil(self):
        result = self.request(dust_objects())
        sources = [(obj, Path(obj.name)) for obj in result.objects]
        def write(records, family, wavelength, resolution, output_dir, **kwargs):
            return Path(output_dir) / f"target_{resolution['target_shape_parameters']}.nc", "created", {}, [r["path"] for r in records]
        with patch('zju_scatt_interface.optics.retrieval.native.write_native_source_product', side_effect=write) as writer:
            products = interpolate_downloaded_particle_series(sources, [1.6], result.wavelength_processing, Path("output"))
        self.assertEqual(len(products), 3)
        self.assertEqual([len(call.args[0]) for call in writer.call_args_list], [4, 2, 4])
        self.assertEqual([p.fixed_coordinates for p in products],
                         [{"roundness": s["n"], "aspect_ratio": s["asp"]} for s in SHAPES])


if __name__ == "__main__":
    unittest.main()
