import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.cli.main import main
from zju_scatt_interface.cli.parser import build_parser


class CliTests(unittest.TestCase):
    def test_registration_defaults_to_direct_method(self):
        args = build_parser().parse_args(["register"])
        self.assertEqual(args.method, "direct")

    def test_browser_method_is_explicit(self):
        args = build_parser().parse_args(["register", "--method", "browser"])
        self.assertEqual(args.method, "browser")

    def test_scheme_config_validates_from_cli(self):
        example = Path(__file__).parents[1] / "configs" / "bulk_scheme.example.json"
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = main(["scheme", str(example)])
        self.assertEqual(status, 0)
        self.assertIn("Valid scheme", stream.getvalue())

    def test_doctor_command_is_available(self):
        args = build_parser().parse_args(["doctor", "--offline", "--json"])
        self.assertEqual(args.command, "doctor")
        self.assertTrue(args.offline)
        self.assertTrue(args.json)

    def test_resolve_ri_command_maps_wavelength_to_native_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "dust.csv"
            table.write_text(
                "wavelength_um,mr,mi\n0.5,1.5,0.01\n1.0,1.3,0.03\n",
                encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                status = main(
                    [
                        "resolve-ri",
                        "dust",
                        "--wavelength",
                        "750",
                        "--wavelength-unit",
                        "nm",
                        "--table",
                        "particle={}".format(table),
                        "--json",
                    ]
                )
        self.assertEqual(status, 0)
        self.assertIn('"wavelength_um": 0.75', stream.getvalue())
        self.assertIn('"refractive_index_real": 1.4', stream.getvalue())

    def test_scheme_sources_offline_prints_actionable_json_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "scheme.json"
            config.write_text(
                json.dumps(
                    {
                        "name": "offline",
                        "wavelengths": [0.55],
                        "particles": [
                            {
                                "name": "cloud",
                                "particle_type": "water_cloud",
                                "size_distribution": {
                                    "size": [1.0],
                                    "dndr": [1.0],
                                },
                                "refractive_index": {"mode": "database"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                status = main(
                    [
                        "scheme-sources",
                        str(config),
                        "--workspace",
                        str(root / "workspace"),
                        "--offline",
                        "--json",
                    ]
                )
            result = json.loads(stream.getvalue())
        self.assertEqual(status, 2)
        self.assertFalse(result["complete"])
        self.assertIn("without --offline", result["issues"][0]["action"])

    def test_psd_check_reports_array_first_component(self):
        example = Path(__file__).parents[1] / "configs" / "bulk_scheme.example.json"
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = main(
                [
                    "psd-check",
                    str(example),
                    "--component",
                    "ice",
                    "--json",
                ]
            )
        result = json.loads(stream.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["size_definition"],
            "volume_equivalent_sphere_radius",
        )
        self.assertEqual(result[0]["dndr_unit"], "cm-3")


if __name__ == "__main__":
    unittest.main()
