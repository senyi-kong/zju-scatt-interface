import importlib.util
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).parents[1]


def load_example(name: str):
    path = PROJECT / "examples" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase10ExampleTests(unittest.TestCase):
    def setUp(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is required")

    def test_observed_psd_example(self):
        module = load_example("example_04_observed_psd_csv.py")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_example(output)
            self.assertTrue((output / "observed_psd_scheme.json").is_file())
            figure = output / "observed_psd.png"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 15_000)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["point_count"], 11)

    def test_interpolation_modes_example(self):
        module = load_example("example_05_interpolation_modes.py")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_example(output)
            figure = output / "interpolation_modes.png"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 15_000)
        self.assertEqual(report["interpolated_method"], "multilinear")
        self.assertEqual(report["linear_retrieval_mode"], "interp")
        self.assertEqual(report["nearest_retrieval_mode"], "nearest")
        self.assertIn("No extrapolation", report["out_of_domain_error"])

    def test_phase10_usability_validation(self):
        module = load_example("example_15_phase10_usability_validation.py")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = module.run_validation(output)
            self.assertTrue(
                (output / "zju_scatt_scheme_reference.json").is_file()
            )
            figure = output / "phase10_usability_validation.png"
            self.assertTrue(figure.is_file())
            self.assertGreater(figure.stat().st_size, 30_000)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["registered_profile_count"], 8)
        self.assertEqual(report["recipe_component_counts"], [1, 1, 1, 3])


if __name__ == "__main__":
    unittest.main()
