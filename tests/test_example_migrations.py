"""Exercise updated user workflows with local synthetic source data."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tests.test_bulk_pipeline import create_source

PROJECT = Path(__file__).resolve().parents[1]


def load_example(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigratedExampleTests(unittest.TestCase):
    def test_audit_detects_removed_retrieval_keywords(self):
        audit = load_example(PROJECT / "examples/audit_example_interfaces.py")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old_example.py"
            path.write_text(
                'from zju_scatt_interface.access.retrieval import retrieve_sources\nretrieve_sources(shape_ranges={"n":(2,3)})\n'
            )
            _, result = audit.audit_static(path)
            self.assertEqual(result["package_imports_and_signatures"], "failed")
            self.assertIn("shape_ranges", result["errors"][0])

    def test_weighted_ice_example_uses_shared_coverage_and_retains_members(self):
        from netCDF4 import Dataset

        example = load_example(PROJECT / "examples/example_06_weighted_ice_shapes.py")
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for n in (2.0, 2.5, 3.0):
                path = (
                    Path(directory)
                    / f"L1.5_super_spheroid_ice_n_{n:.3f}_asp_1.000_wl_0.670_um_ref_1.310e+00_1.000e-06_t_220k_v1.0_20260409.nc"
                )
                create_source(path, wavelength=0.67, multiplier=n)
                paths.append(path)
            result = example.calculate_weighted_ice(paths, 0.67, 220)
            self.assertEqual(len(result.members), 3)
            self.assertLess(result.bulk.number_concentration, 1000)
            self.assertIn("size_coverage", result.bulk.metadata)
            self.assertAlmostEqual(result.bulk.single_scattering_albedo, 0.7)
            self.assertAlmostEqual(result.bulk.asymmetry_factor, 0.4)
            target = Path(directory) / "weighted.nc"
            example.run_example(paths, 0.67, 220, target)
            with Dataset(target) as ds:
                group = ds.groups["weighted_ice_shapes"]
                self.assertEqual(len(group.dimensions["ensemble_member"]), 3)
                self.assertEqual(group.variables["ensemble_member"][:].tolist(), [0, 1, 2])

    def test_all_species_examples_request_numeric_ice_temperature(self):
        from zju_scatt_interface.access.workflow import _requests, load_retrieval_config

        local = PROJECT.parent / "test_zju_scatt/user_test_local"
        if not local.is_dir():
            self.skipTest("Local user examples are outside this package installation")
        for name in ("08_retrieval_config.py", "09_retrieval_config.py"):
            with self.subTest(config=name):
                jobs, all_species = _requests(load_retrieval_config(local / name))
                self.assertTrue(all_species)
                ice = jobs["super_spheroid_ice"]
                self.assertEqual(ice["target_temperatures"], [270])
                self.assertNotIn("contains", ice)


if __name__ == "__main__":
    unittest.main()
