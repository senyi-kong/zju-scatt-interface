import math
import tempfile
import unittest
from pathlib import Path

from tests.test_bulk_pipeline import create_source
from zju_scatt_interface.bulk.ensemble import WeightedShapeMember
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.psd.coverage import check_size_coverage
from zju_scatt_interface.psd.models import SizeDistribution


class SizeCoverageTests(unittest.TestCase):
    def setUp(self):
        try:
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("netCDF4 is required for source coverage fixtures")

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "super_spheroid"
        self.members = [WeightedShapeMember(n=2, asp=1, weight=0.5),
                        WeightedShapeMember(n=2.8, asp=1.6, weight=0.5)]
        for n, asp, factor in ((2, 1, 1.0), (2.8, 1.6, 0.5)):
            path = self.root / f"L1_super_spheroid_n_{n:.3f}_asp_{asp:.3f}_wl_nan_ref_1.500e+00_1.000e-02.nc"
            create_source(path, wavelength=None)
            with Dataset(path, "a") as ds:
                # Equal max-dimension size parameters do not imply equal volumes.
                raw = ds.variables["xsize_veq"][:].copy()
                ds.createVariable("xsize_maxd", "f8", ("xsize_veq",))[:] = raw
                ds.variables["xsize_veq"][:] = factor * raw
        self.kwargs = {"wavelength": 2*math.pi, "parameters": {"mr": 1.5, "mi": 0.01},
                       "shape_ensemble": self.members}

    def test_uses_each_shapes_volume_equivalent_radius(self):
        psd = SizeDistribution([1, 2, 4], [1, 3, 1])
        report = check_size_coverage("dust", self.root, psd, **self.kwargs)
        self.assertEqual(report["common_source_radius_um"], [0.5, 10.0])
        self.assertTrue(report["fully_covered"])
        self.assertEqual(len(report["source_ranges"]), 2)
        calculation = compute_population("dust", self.root, psd, **self.kwargs)
        self.assertEqual(calculation.bulk.metadata["size_coverage"], report)
        self.assertAlmostEqual(calculation.bulk.number_concentration, 5)

    def test_automatic_error_rejects_missing_common_coverage(self):
        psd = SizeDistribution([0.1, 1, 8, 18], [1, 2, 3, 4])
        with self.assertRaisesRegex(ValueError, "common physical size range"):
            compute_population("dust", self.root, psd, **self.kwargs)

    def test_explicit_truncation_retains_same_population_for_all_shapes(self):
        psd = SizeDistribution([0.1, 1, 8, 18], [1, 2, 3, 4])
        calculation = compute_population("dust", self.root, psd,
            truncation_policy="truncate", **self.kwargs)
        report = calculation.bulk.metadata["size_coverage"]
        self.assertFalse(report["fully_covered"])
        self.assertGreater(report["outside_number_fraction"], 0)
        self.assertLess(calculation.bulk.number_concentration, psd.number_concentration_cm3)
        for member in calculation.members:
            self.assertAlmostEqual(member.bulk.number_concentration, calculation.bulk.number_concentration)
        self.assertAlmostEqual(calculation.bulk.number_concentration,
                               report["retained_number_concentration_cm3"])

    def test_size_and_wavelength_units_and_definition_validation(self):
        psd = SizeDistribution([1000, 2000, 4000], [1, 3, 1], size_unit="nm")
        kwargs = {**self.kwargs, "wavelength": 2000*math.pi, "wavelength_unit": "nm"}
        report = check_size_coverage("dust", self.root, psd, **kwargs)
        self.assertTrue(report["fully_covered"])
        with self.assertRaisesRegex(ValueError, "size definitions must match"):
            check_size_coverage("dust", self.root, psd,
                                size_definition="maximum_dimension_radius", **kwargs)


if __name__ == "__main__":
    unittest.main()
