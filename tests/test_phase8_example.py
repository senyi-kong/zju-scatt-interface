import importlib.util
import tempfile
import unittest
from pathlib import Path


class Phase8GraphicalValidationTests(unittest.TestCase):
    def test_phase8_script_writes_both_formats_and_graphic(self):
        try:
            import h5py  # noqa: F401
            import matplotlib  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("h5py, matplotlib, and netCDF4 are required")

        examples = Path(__file__).parents[1] / "examples"
        script = examples / "example_13_phase8_output_validation.py"
        spec = importlib.util.spec_from_file_location("phase8_validation", script)
        if spec is None or spec.loader is None:
            self.fail("could not load Phase 8 validation script")
        module = importlib.util.module_from_spec(spec)
        import sys

        sys.path.insert(0, str(examples))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(examples))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_validation(output)
            self.assertTrue((output / "phase8_bulk_scheme.nc").is_file())
            self.assertTrue((output / "phase8_bulk_scheme.h5").is_file())
            figure = output / "phase8_output_validation.png"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 20_000)
            self.assertTrue((output / "phase8_validation_report.json").is_file())

        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["equivalent_scientific_content"])
        self.assertEqual(report["component_names"], ["cloud", "sulfate", "mixture"])


if __name__ == "__main__":
    unittest.main()
