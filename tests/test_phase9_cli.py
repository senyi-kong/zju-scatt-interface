import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from zju_scatt_interface.cli.main import main
from zju_scatt_interface.io.canonical import validate_file


def create_cloud_sources(root: Path) -> None:
    import numpy as np
    from netCDF4 import Dataset

    root.mkdir(parents=True, exist_ok=True)
    radius = np.geomspace(0.1, 10.0, 24)
    for wavelength, multiplier in ((0.5, 1.0), (0.7, 1.5)):
        path = (
            root
            / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc"
        )
        with Dataset(path, "w") as dataset:
            dataset.createDimension("xsize_veq", len(radius))
            dataset.createVariable("wavelength", "f8")[:] = wavelength
            dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = (
                radius * 2 * math.pi / wavelength
            )
            dataset.createVariable("cext", "f8", ("xsize_veq",))[:] = (
                multiplier * np.geomspace(0.2, 200.0, len(radius))
            )
            dataset.createVariable("ssa", "f8", ("xsize_veq",))[:] = 0.8
            dataset.createVariable("g", "f8", ("xsize_veq",))[:] = 0.5


def write_scheme(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "name": "phase9_cli",
                "wavelength_unit": "nm",
                "wavelengths": [500, 600],
                "particles": [
                    {
                        "name": "cloud",
                        "particle_type": "water_cloud",
                        "size_distribution": {
                            "size": [0.1, 0.3, 1.0, 3.0, 10.0],
                            "dndr": [1, 5, 10, 5, 1],
                            "size_definition": (
                                "volume_equivalent_sphere_radius"
                            ),
                        },
                        "refractive_index": {"mode": "database"},
                    }
                ],
                "calculation": {
                    "truncation_policy": "truncate",
                    "strict_qa": True,
                },
                "output": {
                    "path": "products/phase9_cli.nc",
                    "format": "netcdf4",
                    "compression": True,
                },
            }
        ),
        encoding="utf-8",
    )


class Phase9CliTests(unittest.TestCase):
    def setUp(self):
        try:
            import h5py  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("h5py and netCDF4 are required")

    def run_cli(self, arguments):
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_validate_writes_normalized_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scheme = root / "scheme.json"
            report = root / "reports" / "validate.json"
            write_scheme(scheme)
            status, stdout, stderr = self.run_cli(
                [
                    "bulk-opt",
                    "validate",
                    str(scheme),
                    "--report",
                    str(report),
                    "--json",
                ]
            )
            content = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["status"], "valid")
        self.assertEqual(content["normalized_scheme"]["schema_version"], "1.0")
        self.assertEqual(content["wavelengths_um"], [0.5, 0.6])

    def test_plan_dry_run_has_no_workspace_or_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scheme = root / "scheme.json"
            workspace = root / "must_not_exist"
            write_scheme(scheme)
            status, stdout, stderr = self.run_cli(
                [
                    "bulk-opt",
                    "plan",
                    str(scheme),
                    "--workspace",
                    str(workspace),
                    "--dry-run",
                    "--json",
                ]
            )
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["status"], "dry_run")
        self.assertFalse(workspace.exists())

    def test_build_from_local_sources_with_format_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "sources"
            create_cloud_sources(sources)
            scheme = root / "scheme.json"
            write_scheme(scheme)
            output = root / "bulk.h5"
            report = root / "build_report.json"
            status, stdout, stderr = self.run_cli(
                [
                    "bulk-opt",
                    "build",
                    str(scheme),
                    "--source",
                    f"cloud={sources}",
                    "--output",
                    str(output),
                    "--format",
                    "hdf5",
                    "--no-check-convergence",
                    "--report",
                    str(report),
                    "--json",
                ]
            )
            validation = validate_file(output)
            build_report = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["status"], "complete")
        self.assertTrue(validation.passed, validation.errors)
        self.assertEqual(build_report["format"], "hdf5")
        self.assertEqual(build_report["component_names"], ["cloud"])
        self.assertTrue(build_report["all_qa_passed"])

    def test_build_dry_run_creates_no_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scheme = root / "scheme.json"
            workspace = root / "workspace"
            output = root / "never.nc"
            write_scheme(scheme)
            status, stdout, stderr = self.run_cli(
                [
                    "bulk-opt",
                    "build",
                    str(scheme),
                    "--workspace",
                    str(workspace),
                    "--output",
                    str(output),
                    "--dry-run",
                    "--json",
                ]
            )
        self.assertEqual(status, 0, stderr)
        self.assertEqual(json.loads(stdout)["status"], "dry_run")
        self.assertFalse(output.exists())
        self.assertFalse(workspace.exists())

    def test_invalid_particle_coordinates_suggest_describe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            value = {
                "name": "bad",
                "wavelengths": [0.55],
                "particles": [
                    {
                        "name": "ice",
                        "particle_type": "super_spheroid_ice",
                        "size_distribution": {"size": [1], "dndr": [1]},
                        "refractive_index": {"mode": "database"},
                    }
                ],
            }
            path.write_text(json.dumps(value), encoding="utf-8")
            status, stdout, stderr = self.run_cli(
                ["bulk-opt", "validate", str(path)]
            )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("zju-scatt describe PARTICLE_TYPE", stderr)
        self.assertIn("temperature", stderr)


if __name__ == "__main__":
    unittest.main()
