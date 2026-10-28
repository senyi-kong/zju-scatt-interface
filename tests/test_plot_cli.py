import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from zju_scatt_interface.cli.main import main
from zju_scatt_interface.cli.plotting import _plot_kind


class PlotCliTests(unittest.TestCase):
    def run_cli(self, arguments):
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def source_file(self, root):
        source = root / "optics.nc"
        source.touch()
        return source

    def test_plot_kind_recognizes_canonical_bulk_fields(self):
        content = {
            "datasets": {},
            "components": {"ice": {"datasets": {"beta_ext": {}}}},
        }
        with patch(
            'zju_scatt_interface.io.tables._normalize_content',
            return_value=content,
        ):
            self.assertEqual(_plot_kind(Path("bulk.nc")), "bulk")

    def test_plot_kind_defaults_to_single_for_noncanonical_input(self):
        with patch(
            'zju_scatt_interface.io.tables._normalize_content',
            side_effect=ValueError("not a canonical product"),
        ):
            self.assertEqual(_plot_kind(Path("single.nc")), "single")

    def test_explicit_single_plot_forwards_selection_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source_file(root)
            output = root / "figures"
            with patch(
                'zju_scatt_interface.plotting.single.plot_single_scattering',
                return_value={"output_dir": output},
            ) as plot:
                status, stdout, stderr = self.run_cli(
                    [
                        "plot",
                        str(source),
                        "--kind",
                        "single",
                        "--output-dir",
                        str(output),
                        "--wavelength-um",
                        "0.55",
                        "--index",
                        "rh=2",
                    ]
                )
        self.assertEqual(status, 0, stderr)
        self.assertIn("Single plots saved to:", stdout)
        plot.assert_called_once_with(
            source.resolve(),
            output_dir=output,
            wavelength_um=0.55,
            coordinate_indices={"rh": 2},
            show=False,
        )

    def test_auto_detected_bulk_plot_uses_bulk_plotter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source_file(root)
            output = root / "bulk_figures"
            with patch('zju_scatt_interface.cli.plotting._plot_kind', return_value="bulk"), patch(
                'zju_scatt_interface.plotting.bulk.plot_bulk_optics',
                return_value={"output_dir": output},
            ) as plot:
                status, stdout, stderr = self.run_cli(["plot", str(source)])
        self.assertEqual(status, 0, stderr)
        self.assertIn("Bulk plots saved to:", stdout)
        plot.assert_called_once_with(source.resolve(), output_dir=None, show=False)

    def test_bulk_plot_rejects_single_particle_selection_options(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source_file(Path(directory))
            status, stdout, stderr = self.run_cli(
                ["plot", str(source), "--kind", "bulk", "--index", "rh=0"]
            )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("apply only to single-particle files", stderr)

    def test_invalid_index_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source_file(Path(directory))
            with patch('zju_scatt_interface.plotting.single.plot_single_scattering'):
                status, stdout, stderr = self.run_cli(
                    ["plot", str(source), "--kind", "single", "--index", "rh=bad"]
                )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("DIM=INTEGER", stderr)

    def test_missing_plot_dependency_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source_file(Path(directory))
            with patch(
                'zju_scatt_interface.plotting.single.plot_single_scattering',
                side_effect=ImportError("matplotlib"),
            ):
                status, stdout, stderr = self.run_cli(
                    ["plot", str(source), "--kind", "single"]
                )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("zju-scatt-interface[plot]", stderr)


if __name__ == "__main__":
    unittest.main()
