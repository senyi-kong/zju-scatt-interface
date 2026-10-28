"""RTTOV14 version-4 NetCDF schema, scientific units and long particle names."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, chartostring

from tests.test_rttov_bulk import fixture
from zju_scatt_interface.io.applications.rttov.v14 import (
    validate_rttov14_optical_table,
    write_rttov14_bulk_tables,
)
from zju_scatt_interface.io.native import scalar_phase_to_model


class RTTOV14Tests(unittest.TestCase):
    def test_native_schema_and_fortran_axis_order_number_and_mass_units(self):
        result = fixture()
        original = copy.deepcopy(result.report)
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_rttov14_bulk_tables(result, directory, max_moments=8)
            self.assertEqual(result.report, original)
            self.assertEqual(manifest["wavelengths_um"], (11.6, 10.0))
            self.assertFalse(manifest["schema_requires_reader_renaming"])
            with Dataset(manifest["outputs"]["aertable"]) as nc:
                self.assertEqual(set(nc.groups), {"aertable"})
                table = nc["aertable"]
                self.assertEqual(table["names"].dimensions, ("ntypes", "str_name_dim"))
                names = [s.strip() for s in chartostring(table["names"][:])]
                self.assertEqual(names, ["dust", "black_carbon", "sea_salt", "sulfate", "nitrate", "organic_carbon"])
                self.assertIn("black_carbon", names)
                self.assertIn("organic_carbon", names)
                self.assertEqual(len(table.dimensions["str_name_dim"]), 32)
                self.assertEqual(int(table["version"][...]), 4)
                self.assertEqual(int(table["id"][...]), 0)
                self.assertEqual(int(table["has_zef"][...]), 0)
                self.assertEqual(table["version"].dimensions, ())
                group = table["dust"]
                self.assertEqual(group["ext"].dtype, np.dtype("float32"))
                self.assertEqual(group["ext"].dimensions,
                    ("dim_id_4", "dim_id_3", "dim_id_2", "dim_id_1", "nwvn"))
                self.assertEqual(group["lcoef"].shape, (1, 1, 1, 1, 2, 9))
                np.testing.assert_allclose(group["ext"][:].reshape(-1), [.03, .06], rtol=1e-6)
                np.testing.assert_allclose(group["ssa"][:], 2/3, rtol=1e-6)
                np.testing.assert_allclose(group["bpr"][:], .5, rtol=1e-6)
                np.testing.assert_array_equal(group["dim_type"][:], [0]*4)
                self.assertEqual(len(table.dimensions["nchan_pha"]), 0)
            with Dataset(manifest["outputs"]["hydrotable"]) as nc:
                table = nc["hydrotable"]
                self.assertEqual(set(table.groups), {"water_cloud_zju_gamma", "ice_cloud_zju_super_spheroid"})
                mass_water = (3+7*8)*4*math.pi/3*1000*1e-9
                for name, mass, frozen in (("water_cloud_zju_gamma", mass_water, 0),
                    ("ice_cloud_zju_super_spheroid", mass_water*917/1000, 1)):
                    group = table[name]
                    self.assertEqual(int(group["is_frozen"][...]), frozen)
                    np.testing.assert_allclose(group["ext"][:].reshape(-1), np.array([.3, .6])/mass, rtol=1e-6)
                    self.assertNotIn("WATER_CLOUD_OPAC", table.groups)
                # Removing part of the format is caught on read-back.
            validate_rttov14_optical_table(manifest["outputs"]["hydrotable"])
            with Dataset(manifest["outputs"]["hydrotable"], "a") as nc:
                nc["hydrotable/water_cloud_zju_gamma/dim_size"][:] = [2, 1, 1, 1]
            with self.assertRaisesRegex(ValueError, "singleton"):
                validate_rttov14_optical_table(manifest["outputs"]["hydrotable"])

    def test_explicit_phase_normalization_and_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fixture()
            for calculations in result.scheme.components.values():
                for calculation in calculations:
                    calculation.bulk.phase_matrix = calculation.bulk.phase_matrix*1.02
            with self.assertRaisesRegex(ValueError, "not normalized"):
                write_rttov14_bulk_tables(result, directory)
            manifest = write_rttov14_bulk_tables(result, directory, phase_normalization="renormalize")
            self.assertAlmostEqual(manifest["phase_checks"]["super_spheroid"][0]["applied_phase_scale"], 1/1.02)
            with self.assertRaisesRegex(ValueError, "densities"):
                write_rttov14_bulk_tables(result, directory, ice_density_kg_m3=0)
            result.scheme.components.pop("sphere_water_cloud")
            with self.assertRaisesRegex(ValueError, "all eight"):
                write_rttov14_bulk_tables(result, directory)

    def test_phase_projection_same_mathematical_convention_as_rttov13(self):
        angles = np.arange(181)
        p = 1+.9*np.cos(np.deg2rad(angles))
        a = scalar_phase_to_model(angles, p, model="rttov13", max_moments=8)
        b = scalar_phase_to_model(angles, p, model="rttov14", max_moments=8)
        np.testing.assert_array_equal(a["LEGCOEF"], b["LEGCOEF"])
        self.assertAlmostEqual(b["BPR"], .3875)
        self.assertAlmostEqual(b["LEGCOEF"][1], .9)


if __name__ == "__main__":
    unittest.main()
