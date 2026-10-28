"""RTTOV13 bulk export units, channel ordering and native schemas."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np

from zju_scatt_interface.io.applications.rttov.v13 import AEROSOL_NAMES, write_rttov13_bulk_tables
from zju_scatt_interface.optics.models import BulkOptics


def fixture():
    wavelengths = (11.6, 10.0)
    families = list(AEROSOL_NAMES) + ["sphere_water_cloud", "super_spheroid_ice"]
    components, species = {}, {}
    phase = np.zeros((181, 4, 4))
    phase[:, 0, 0] = 1.0
    for family in families:
        components[family] = tuple(SimpleNamespace(wavelength_um=w, bulk=BulkOptics(
            extinction_coefficient=3e-4*(i+1), scattering_coefficient=2e-4*(i+1),
            absorption_coefficient=1e-4*(i+1), single_scattering_albedo=2/3,
            asymmetry_factor=0.0, phase_matrix=phase, number_concentration=10,
            metadata={"scattering_angles_degrees": list(range(181))})) for i, w in enumerate(wavelengths))
        species[family] = {"effective_parameters": {"relative_humidity": 0.6},
            "psd": {"size": [1, 2], "dndr": [3, 7], "number_concentration_cm3": 10}}
    return SimpleNamespace(scheme=SimpleNamespace(wavelengths_um=wavelengths, components=components),
                           report={"species": species})


class RTTOVBulkTests(unittest.TestCase):
    def test_phase_renormalization_is_explicit_and_does_not_modify_input(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fixture()
            for calculations in result.scheme.components.values():
                for calculation in calculations:
                    calculation.bulk.phase_matrix = np.asarray(calculation.bulk.phase_matrix)*1.02
            original = result.scheme.components["super_spheroid"][0].bulk.phase_matrix.copy()
            with self.assertRaisesRegex(ValueError, "not normalized"):
                write_rttov13_bulk_tables(result, directory, max_moments=8)
            manifest = write_rttov13_bulk_tables(result, directory, max_moments=8,
                                                 phase_normalization="renormalize")
            np.testing.assert_array_equal(result.scheme.components["super_spheroid"][0].bulk.phase_matrix, original)
            check = manifest["phase_checks"]["super_spheroid"][0]
            self.assertAlmostEqual(check["input_half_integral"], 1.02)
            self.assertAlmostEqual(check["applied_phase_scale"], 1/1.02)

    def test_native_units_and_phase_projection_preserve_psd_and_order(self):
        result = fixture()
        original = copy.deepcopy(result.report)
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_rttov13_bulk_tables(result, directory, max_moments=8)
            self.assertEqual(result.report, original)
            self.assertEqual(manifest["wavelengths_um"], (11.6, 10.0))
            self.assertFalse(manifest["profiles_mmr_cldaer"])
            mass_water = (3+7*8)*4*math.pi/3*1000*1e-9
            mass_ice = mass_water*917/1000
            with h5py.File(Path(directory)/"scaercoef_zju_default.H5") as f:
                self.assertEqual(int(f["SCAER/NTYPES"][0]), 6)
                names = [n.decode() for n in f["SCAER/NAMES"][:]]
                self.assertEqual(names, ["dust", "black_carbon", "sea_salt", "sulfate", "nitrate", "organic_carbon"])
                self.assertGreaterEqual(f["SCAER/NAMES"].dtype.itemsize, len("organic_carbon"))
                self.assertTrue(all(n in f["SCAER"] for n in names))
                np.testing.assert_allclose(f["SCAER/dust/ABS"][:, 0, 0], [1e-5, 2e-5])
                np.testing.assert_allclose(f["SCAER/dust/BPR"][:], 0.5)
                np.testing.assert_allclose(f["SCAER/dust/LEGCOEF"][:, 0, 0, 0], 1)
                self.assertEqual(f["SCAER/dust/CONFAC"][0], 0)
                np.testing.assert_array_equal(f["SCAER/dust/ABS"].attrs["UBOUND"], [1, 1, 2])
            with h5py.File(Path(directory)/"sccldcoef_zju_default.H5") as f:
                self.assertEqual(set(f["SCCLD"]), {"ICE_CLOUD_ZJU_SUPER_SPHEROID", "WATER_CLOUD_ZJU_GAMMA", "WATER_CLOUD_OPAC"})
                self.assertNotIn("ICE_CLOUD_BAUM", f["SCCLD"])
                self.assertNotIn("WATER_CLOUD_DEFF", f["SCCLD"])
                np.testing.assert_allclose(f["SCCLD/WATER_CLOUD_ZJU_GAMMA/DATA/ABS"][:, 0, 0],
                                           np.array([1e-4, 2e-4])/mass_water)
                np.testing.assert_allclose(f["SCCLD/ICE_CLOUD_ZJU_SUPER_SPHEROID/DATA/ABS"][:, 0, 0],
                                           np.array([1e-4, 2e-4])/mass_ice)
                for slot in ("STCO", "STMA", "CUCC", "CUCP", "CUMA"):
                    base = "SCCLD/WATER_CLOUD_OPAC/"+slot
                    np.testing.assert_allclose(f[base+"/ABS"][:, 0, 0], [1e-5, 2e-5])
                    self.assertAlmostEqual(f[base+"/CONFAC"][0], 10/mass_water)
            self.assertEqual(json.loads((Path(directory)/"rttov_manifest.json").read_text())
                             ["wavelengths_um"], [11.6, 10.0])
            self.assertFalse(manifest["direct_rttov13_cloud_read_compatible"])
            self.assertFalse(manifest["direct_rttov13_aerosol_read_compatible"])
            self.assertEqual(manifest["ice_cloud_group"], "SCCLD/ICE_CLOUD_ZJU_SUPER_SPHEROID")
            self.assertEqual(manifest["water_cloud_group"], "SCCLD/WATER_CLOUD_ZJU_GAMMA")
            from zju_scatt_interface.io.native import (
                native_template_from_reference,
                read_native_optical_arrays,
                write_native_optical_output,
            )
            cloud_path = Path(directory)/"sccldcoef_zju_default.H5"
            schema = native_template_from_reference(cloud_path, model="rttov13")
            self.assertEqual(schema["cloud_variant"], "zju_clouds")
            arrays = read_native_optical_arrays(cloud_path, model="rttov13")
            write_native_optical_output(Path(directory)/"cloud_roundtrip.H5", arrays, schema)
            schema.pop("cloud_variant")
            with self.assertRaisesRegex(ValueError, "all three"):
                write_native_optical_output(Path(directory)/"wrong_standard_schema.H5", arrays, schema)
            aerosol_path = Path(directory)/"scaercoef_zju_default.H5"
            aerosol_schema = native_template_from_reference(aerosol_path, model="rttov13")
            self.assertEqual(aerosol_schema["aerosol_variant"], "descriptive")
            write_native_optical_output(Path(directory)/"aerosol_roundtrip.H5",
                read_native_optical_arrays(aerosol_path, model="rttov13"), aerosol_schema)

    def test_incomplete_species_missing_phase_and_invalid_density_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            result = fixture()
            result.scheme.components.pop("sphere_water_cloud")
            with self.assertRaisesRegex(ValueError, "all eight"):
                write_rttov13_bulk_tables(result, directory)
            result = fixture()
            result.scheme.components["super_spheroid"][0].bulk.phase_matrix = None
            with self.assertRaisesRegex(ValueError, "include_phase_matrix"):
                write_rttov13_bulk_tables(result, directory)
            self.assertFalse((Path(directory)/"scaercoef_zju_default.H5").exists())
            with self.assertRaisesRegex(ValueError, "densities"):
                write_rttov13_bulk_tables(fixture(), directory, ice_density_kg_m3=-1)


if __name__ == "__main__":
    unittest.main()
