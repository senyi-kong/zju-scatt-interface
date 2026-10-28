import importlib.util
import tempfile
import unittest
from pathlib import Path


class Phase7GraphicalValidationTests(unittest.TestCase):
    def test_phase7_script_generates_report_and_figure(self):
        try:
            import matplotlib  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib and netCDF4 are required")

        script = (
            Path(__file__).parents[1]
            / "examples"
            / "example_12_phase7_bulk_pipeline_validation.py"
        )
        spec = importlib.util.spec_from_file_location("phase7_validation", script)
        if spec is None or spec.loader is None:
            self.fail("could not load Phase 7 validation script")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_validation(output)
            figure = output / "phase7_bulk_pipeline_validation.png"
            report_file = output / "phase7_validation_report.json"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 10_000)
            self.assertTrue(report_file.is_file())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["component_names"], ["cloud", "sulfate"])
        self.assertTrue(report["components_stored_separately"])
        self.assertEqual(report["sulfate_ensemble_member_count"], 2)
        self.assertTrue(report["all_qa_passed"])


if __name__ == "__main__":
    unittest.main()
