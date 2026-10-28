import importlib.util
import tempfile
import unittest
from pathlib import Path


class Phase6GraphicalValidationTests(unittest.TestCase):
    def test_phase6_script_generates_report_and_figure(self):
        try:
            import matplotlib  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib and netCDF4 are required")

        script = (
            Path(__file__).parents[1]
            / "examples"
            / "example_11_phase6_particle_adapter_validation.py"
        )
        spec = importlib.util.spec_from_file_location("phase6_validation", script)
        if spec is None or spec.loader is None:
            self.fail("could not load Phase 6 validation script")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_validation(output)
            figure = output / "phase6_adapter_validation.png"
            report_file = output / "phase6_validation_report.json"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 10_000)
            self.assertTrue(report_file.is_file())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["water_selected_nodes"], 2)
        self.assertEqual(report["sulfate_selected_nodes"], 4)
        self.assertEqual(report["sea_branch"], "crystallization")


if __name__ == "__main__":
    unittest.main()
