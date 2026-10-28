import importlib.util
import tempfile
import unittest
from pathlib import Path


class Phase5GraphicalValidationTests(unittest.TestCase):
    def test_detailed_phase5_script_generates_netcdf_report_and_figure(self):
        try:
            import matplotlib  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib and netCDF4 are required")

        script = (
            Path(__file__).parents[1]
            / "examples"
            / "example_10_phase5_interpolation_validation.py"
        )
        spec = importlib.util.spec_from_file_location("phase5_validation", script)
        if spec is None or spec.loader is None:
            self.fail("could not load Phase 5 validation script")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_validation(output)
            figure = output / "phase5_interpolation_validation.png"
            netcdf = output / "phase5_interpolated_product.nc"
            report_file = output / "phase5_validation_report.json"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 10_000)
            self.assertTrue(netcdf.is_file())
            self.assertTrue(report_file.is_file())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["method"], "multilinear")
        self.assertEqual(report["neighbor_count"], 4)
        self.assertAlmostEqual(report["weight_sum"], 1.0)
        self.assertEqual(report["angle_count"], 37)


if __name__ == "__main__":
    unittest.main()
