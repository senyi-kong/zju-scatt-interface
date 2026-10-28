"""L2 flat-schema naming and concentration normalization regression checks."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

from zju_scatt_interface.io.l2 import VARIABLES, write_l2_lognormal
from zju_scatt_interface.optics.models import BulkOptics


class L2OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.nc"
        with Dataset(self.source, "w") as ds:
            ds.setncatts({"institution": "Source institution", "data_level": "L1.5", "data_version": "v1.0"})
        self.phase = np.tile(np.eye(4), (3, 1, 1))*(4/np.pi)
        self.bulk = BulkOptics(1e-4, 9e-5, 1e-5, 0.9, 0.0,
            phase_matrix=self.phase.tolist(), number_concentration=10,
            metadata={"number_concentration_output_unit": "cm-3", "bulk_coefficient_unit": "m-1",
                      "scattering_angles_degrees": [0, 90, 180]})

    def write(self):
        return write_l2_lognormal(self.root, self.bulk, wavelength_um=1.6,
            parameters={"roundness": 2, "aspect_ratio": 1.6, "mr": 1.5, "mi": 0.003},
            rg_um=0.7, sigma_g=1.8, source_path=self.source)

    def test_filename_hierarchy_and_flat_variable_contract(self):
        path = self.write()
        self.assertEqual(path.parents[1].name, "psd_lognormal_normalized_veq_rg_0.700_um_sigma_1.800")
        self.assertTrue(path.name.startswith("L2_super_spheroid_dust_n_2.000_asp_1.600_wl_1.600_um_ref_1.500e+00_3.000e-03_psd_"))
        self.assertRegex(path.name, r"_v1\.0_\d{8}\.nc$")
        with Dataset(path) as ds:
            self.assertFalse(ds.groups)
            self.assertEqual(set(ds.variables), set(VARIABLES))
            self.assertEqual(set(ds.dimensions), {"sca_angle"})
            self.assertEqual(ds.data_level, "L2")
            self.assertEqual(ds.psd, "number_lognormal")
            self.assertEqual(ds.psd_normalization, "normalized")
            self.assertEqual(ds.institution, "Source institution")
            self.assertIn("T", ds.creation_date)
            for name, (units, _) in VARIABLES.items():
                self.assertEqual(ds.variables[name].units, units)
                self.assertEqual(ds.variables[name].dtype, np.dtype("f8"))

    def test_only_extensive_optics_are_normalized_to_one_cm3(self):
        with Dataset(self.write()) as ds:
            self.assertAlmostEqual(float(ds.variables["beta_ext"][:]), 1e-5)
            self.assertAlmostEqual(float(ds.variables["ssa"][:]), 0.9)
            self.assertAlmostEqual(float(ds.variables["g"][:]), 0)
            np.testing.assert_allclose(ds.variables["p11"][:], self.phase[:, 0, 0])
            np.testing.assert_allclose(ds.variables["p12"][:], self.phase[:, 0, 1])
            self.assertAlmostEqual(float(ds.variables["beta_ext"][:])*10, self.bulk.extinction_coefficient)
            self.assertEqual(ds.psd_reference_number_concentration_cm3, 1)

    def test_rejects_unknown_units_and_phase_normalization(self):
        self.bulk.metadata["number_concentration_output_unit"] = "m-3"
        with self.assertRaises(ValueError):
            self.write()
        self.bulk.metadata["number_concentration_output_unit"] = "cm-3"
        self.bulk.phase_matrix = (self.phase*2).tolist()
        with self.assertRaises(ValueError):
            self.write()
