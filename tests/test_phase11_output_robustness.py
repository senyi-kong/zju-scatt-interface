import math
import tempfile
import unittest
from pathlib import Path

from tests.test_phase8_output import scheme_result
from zju_scatt_interface.io.canonical import _write_dataset as _write_dataset
from zju_scatt_interface.io.canonical import read, validate_file


class Phase11OutputRobustnessTests(unittest.TestCase):
    def setUp(self):
        try:
            import h5py  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("h5py and netCDF4 are required")

    def test_required_schema_is_identical_in_both_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = (
                _write_dataset(root / "product.nc", scheme_result(), format='netcdf4'),
                _write_dataset(root / "product.h5", scheme_result(), format='hdf5'),
            )
            contents = [read(path) for path in paths]
        for content in contents:
            self.assertEqual(
                content["attributes"]["schema_name"],
                "zju_scatt_bulk_optical_scheme",
            )
            self.assertEqual(content["attributes"]["schema_version"], "1.0")
            datasets = content["components"]["ice"]["datasets"]
            self.assertEqual(datasets["beta_ext"]["units"], "m^-1")
            self.assertEqual(datasets["ssa"]["units"], "1")
            self.assertEqual(datasets["sca_angle"]["units"], "degree")
            self.assertEqual(datasets["psd_size"]["units"], "um")
            self.assertEqual(datasets["psd_dndr"]["units"], "cm-3")
            self.assertTrue(
                {
                    "p11",
                    "p12",
                    "p22",
                    "p33",
                    "p43",
                    "p44",
                }.issubset(datasets)
            )

    def test_missing_required_variable_is_detected_in_hdf5(self):
        import h5py

        with tempfile.TemporaryDirectory() as directory:
            path = _write_dataset(
                Path(directory) / "missing.h5", scheme_result()
            , format='hdf5')
            with h5py.File(path, "r+") as handle:
                del handle["ice"]["ssa"]
            report = validate_file(path)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("required variable ssa is missing" in item for item in report.errors)
        )

    def test_wrong_unit_is_detected_in_netcdf(self):
        from netCDF4 import Dataset

        with tempfile.TemporaryDirectory() as directory:
            path = _write_dataset(
                Path(directory) / "unit.nc", scheme_result()
            , format='netcdf4')
            with Dataset(path, "r+") as handle:
                handle.groups["ice"].variables["beta_ext"].units = "km^-1"
            report = validate_file(path)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("beta_ext unit must be m^-1" in item for item in report.errors)
        )

    def test_infinity_and_incomplete_phase_matrix_are_detected(self):
        import h5py

        with tempfile.TemporaryDirectory() as directory:
            path = _write_dataset(
                Path(directory) / "corrupt.h5", scheme_result()
            , format='hdf5')
            with h5py.File(path, "r+") as handle:
                handle["ice"]["g"][0] = math.inf
                del handle["ice"]["p44"]
            report = validate_file(path)
        self.assertFalse(report.passed)
        self.assertTrue(any("contains infinity" in item for item in report.errors))
        self.assertTrue(
            any(
                "phase-matrix variables are incomplete" in item
                for item in report.errors
            )
        )


if __name__ == "__main__":
    unittest.main()
