import importlib.util
import tempfile
import unittest
from pathlib import Path


class Phase4GraphicalValidationTests(unittest.TestCase):
    def test_detailed_phase4_script_generates_report_csv_and_figure(self) -> None:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is not installed")

        script = (
            Path(__file__).parents[1]
            / "examples"
            / "example_09_phase4_psd_validation.py"
        )
        spec = importlib.util.spec_from_file_location("phase4_validation", script)
        if spec is None or spec.loader is None:
            self.fail("could not load Phase 4 validation script")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            summary = module.run_validation(output)
            figure = output / "phase4_psd_validation.png"
            report = output / "phase4_validation_report.json"
            source_csv = output / "phase4_input_psd.csv"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 10_000)
            self.assertTrue(report.is_file())
            self.assertTrue(source_csv.is_file())

        self.assertEqual(summary["status"], "pass")
        self.assertTrue(summary["silent_truncation_rejected"])
        self.assertAlmostEqual(
            summary["full_remap"]["outside_fraction"],
            0.0,
        )
        self.assertGreater(
            summary["truncated_remap"]["outside_fraction"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
