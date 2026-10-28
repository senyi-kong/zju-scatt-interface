"""ARTS fixed-PSD export: number units, full phase tensor, temperature and XML."""
import copy
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from test_rttov_bulk import fixture

from zju_scatt_interface.bulk.models import BulkDataset, PopulationResult
from zju_scatt_interface.bulk.quality import validate_bulk_optics
from zju_scatt_interface.io.applications.arts.bulk import (
    validate_arts_bulk_table,
    write_arts_bulk_tables,
)
from zju_scatt_interface.io.native import read_native_optical_arrays


def population_fixture():
    data = fixture()
    components = {}
    for family, calculations in data.scheme.components.items():
        components[family] = tuple(PopulationResult(family, c.wavelength_um, c.bulk,
            validate_bulk_optics(c.bulk), (), {}) for c in calculations)
        for calculation in components[family]:
            calculation.bulk.phase_matrix = calculation.bulk.phase_matrix.copy()
            calculation.bulk.phase_matrix[:, 3, 2] = .1
            calculation.bulk.phase_matrix[:, 2, 3] = -.1
    data.scheme = BulkDataset("ARTS fixture", data.scheme.wavelengths_um, components)
    data.report["species"]["super_spheroid_ice"]["effective_parameters"]["temperature"] = 220.
    return data


class ARTSBulkTests(unittest.TestCase):
    def test_cross_sections_phase_sign_xml_and_temperatures(self):
        data = population_fixture()
        original = copy.deepcopy(data.report)
        with tempfile.TemporaryDirectory() as directory:
            result = write_arts_bulk_tables(data, directory)
            self.assertEqual(data.report, original)
            self.assertEqual(len(result["species_order"]), 8)
            arrays = read_native_optical_arrays(result["outputs"]["dust"], model="arts2")
            np.testing.assert_allclose(arrays["ext_mat_data"][:, 0, 0, 0, 0], np.array([3e-4, 6e-4])/1e7)
            np.testing.assert_allclose(arrays["abs_vec_data"][:, 0, 0, 0, 0], np.array([1e-4, 2e-4])/1e7)
            np.testing.assert_allclose(arrays["pha_mat_data"][0, 0, :, 0, 0, 0, 4], -.1*2e-4/(1e7*4*np.pi))
            np.testing.assert_allclose(arrays["f_grid"], 299792458/(np.array([11.6, 10])*1e-6))
            self.assertEqual(arrays["T_grid"].tolist(), [273.15])
            self.assertIn("fixed PSD", arrays["description"])
            ice = read_native_optical_arrays(result["outputs"]["ice_cloud_zju_super_spheroid"], model="arts2")
            self.assertEqual(ice["T_grid"].tolist(), [220.])
            root = ET.parse(result["outputs"]["scat_data"]).getroot()
            outer = root.find("Array")
            self.assertEqual(outer.attrib, {"type": "ArrayOfSingleScatteringData", "nelem": "8"})
            self.assertTrue(all(c.attrib["nelem"] == "1" and c[0].tag == "SingleScatteringData" for c in outer))
            for name in result["species_order"]:
                self.assertTrue(validate_arts_bulk_table(result["outputs"][name])["valid"])

    def test_angular_normalization_scales_all_elements_preserves_psd(self):
        data = population_fixture()
        for rows in data.scheme.components.values():
            for row in rows:
                row.bulk.phase_matrix *= 1.02
        before = copy.deepcopy(data.report)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "not normalized"):
                write_arts_bulk_tables(data, directory)
            result = write_arts_bulk_tables(data, directory, phase_normalization="renormalize")
            arrays = read_native_optical_arrays(result["outputs"]["dust"], model="arts2")
            phase = arrays["pha_mat_data"][0, 0, :, 0, 0, 0]
            np.testing.assert_allclose(phase[:, 4]/phase[:, 0], -.1)
            theta = np.deg2rad(arrays["za_grid"])
            integral = np.sum(np.diff(theta)*(phase[1:, 0]*np.sin(theta[1:])+phase[:-1, 0]*np.sin(theta[:-1])))*np.pi
            self.assertAlmostEqual(integral/(2e-4/1e7), 1, places=12)
            self.assertEqual(data.report, before)
            self.assertAlmostEqual(data.scheme.components["super_spheroid"][0].bulk.phase_matrix[0, 0, 0], 1.02)

    def test_nonuniform_wavelength_order_and_number_scaling(self):
        data = population_fixture()
        # Swapping the input wavelength labels also swaps the exported coefficients.
        data.scheme.wavelengths_um = (10., 11.6)
        for rows in data.scheme.components.values():
            for row, wavelength in zip(rows, data.scheme.wavelengths_um):
                row.wavelength_um = wavelength
                row.bulk.number_concentration *= 2
                row.bulk.extinction_coefficient *= 2
                row.bulk.scattering_coefficient *= 2
                row.bulk.absorption_coefficient *= 2
        for entry in data.report["species"].values():
            entry["psd"]["number_concentration_cm3"] *= 2
        with tempfile.TemporaryDirectory() as directory:
            result = write_arts_bulk_tables(data, directory)
            arrays = read_native_optical_arrays(result["outputs"]["dust"], model="arts2")
            np.testing.assert_allclose(arrays["ext_mat_data"][:, 0, 0, 0, 0], np.array([6e-4, 3e-4])/1e7)
            self.assertEqual(result["populations"]["dust"]["number_density_m3"], 2e7)

    def test_report_mismatch_and_missing_phase_raise(self):
        data = population_fixture()
        with tempfile.TemporaryDirectory() as directory:
            data.report["species"]["super_spheroid"]["psd"]["number_concentration_cm3"] = 99
            with self.assertRaisesRegex(ValueError, "number concentration"):
                write_arts_bulk_tables(data, directory)
            data = population_fixture()
            for row in data.scheme.components["super_spheroid"]:
                row.bulk.phase_matrix = None
            with self.assertRaisesRegex(ValueError, "phase_matrix"):
                write_arts_bulk_tables(data, directory)


if __name__ == "__main__":
    unittest.main()
