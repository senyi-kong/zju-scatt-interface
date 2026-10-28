import importlib.util
import tempfile
import unittest
from pathlib import Path


class Phase9GraphicalValidationTests(unittest.TestCase):
    def test_typed_and_cli_workflows_are_equivalent(self):
        try:
            import h5py  # noqa: F401
            import matplotlib  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("h5py, matplotlib, and netCDF4 are required")

        script = (
            Path(__file__).parents[1]
            / "examples"
            / "example_14_phase9_typed_and_cli_validation.py"
        )
        spec = importlib.util.spec_from_file_location(
            "phase9_validation", script
        )
        if spec is None or spec.loader is None:
            self.fail("could not load Phase 9 validation script")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_validation(output)
            self.assertTrue((output / "phase9_python_product.h5").is_file())
            self.assertTrue((output / "phase9_cli_product.nc").is_file())
            self.assertTrue((output / "phase9_scheme.json").is_file())
            self.assertTrue((output / "phase9_cli_report.json").is_file())
            figure = output / "phase9_workflow_validation.png"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 20_000)

        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["normalized_round_trip"])
        self.assertTrue(report["scientific_content_equivalent"])


if __name__ == "__main__":
    unittest.main()
