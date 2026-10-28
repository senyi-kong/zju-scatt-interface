"""Fixed-PSD CRTM IR mass conversion, spectral ordering and phase conventions."""
import copy
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, chartostring
from test_rttov_bulk import fixture

from zju_scatt_interface.io.applications.crtm.ir import (
    _growth_factor,
    validate_crtm_ir_optical_table,
    write_crtm_ir_bulk_tables,
)
from zju_scatt_interface.io.applications.rttov.v13 import AEROSOL_NAMES
from zju_scatt_interface.io.applications.rttov.v14 import HYDROMETEOR_NAMES


class CRTMIRTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        for entry in self.data.report["species"].values():
            entry["psd"].update(size_definition="volume_equivalent_sphere_radius",
                                size_unit="um", dndr_unit="cm-3", integration_mode="discrete_bin")
        self.data.report["species"]["encapsulated_fractal_aggregates_black_carbon"]["effective_parameters"]["vf"] = 0.25
        self.densities = {name: 1000.0 for name in {**AEROSOL_NAMES, **HYDROMETEOR_NAMES}.values()}
        self.growth = {family: 2.0 for family in ("coated_super_spheroid_seasalt", "sphere_sulfate",
                                                "sphere_nitrate", "sphere_organic_carbon")}

    def export(self, directory, **kwargs):
        return write_crtm_ir_bulk_tables(self.data, directory,
            material_densities_kg_m3=self.densities, growth_factors=self.growth, **kwargs)

    def test_mass_phase_and_order_preserve_population(self):
        original = copy.deepcopy(self.data.report)
        # Intentionally ascending wavelengths => descending wavenumber input.
        self.data.scheme.wavelengths_um = (10.0, 11.6)
        for calculations in self.data.scheme.components.values():
            for calculation, wl in zip(calculations, (10.0, 11.6)):
                calculation.wavelength_um = wl
        with tempfile.TemporaryDirectory() as directory:
            result = self.export(directory)
            self.assertEqual(self.data.report, original)
            mass = (3+7*8)*4*math.pi/3*1e-12*1000
            self.assertAlmostEqual(result["populations"]["dust"]["mass_kg_m3"], mass)
            self.assertAlmostEqual(result["populations"]["black_carbon"]["mass_kg_m3"], mass/4)
            self.assertAlmostEqual(result["populations"]["sea_salt"]["mass_kg_m3"], mass/8)
            for kind in ("aerosol", "cloud"):
                validate_crtm_ir_optical_table(result["outputs"][kind])
            with Dataset(result["outputs"]["aerosol"]) as nc:
                self.assertEqual(nc.native_crtm_compatible, 0)
                self.assertNotIn("Frequency_MW", nc.variables)
                self.assertNotIn("n_Radii", nc.dimensions)
                np.testing.assert_allclose(nc["Wavelength"][:], [11.6, 10])
                np.testing.assert_allclose(nc["ke"][0], np.array([6e-4, 3e-4])/mass)
                np.testing.assert_allclose(nc["pcoeff"][0, [0, 5, 12, 21]], .5)
                np.testing.assert_allclose(nc["pcoeff"][0, [1, 6, 13, 22]], 0, atol=1e-12)
                self.assertEqual(list(chartostring(nc["Type_Name"][:]).astype(str))[1].strip(), "black_carbon")

    def test_density_scaling_and_invalid_mass(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.export(directory)
            with Dataset(first["outputs"]["aerosol"]) as nc:
                ke = nc["ke"][:].copy()
            self.densities = {n: 2*d for n, d in self.densities.items()}
            second = self.export(directory)
            with Dataset(second["outputs"]["aerosol"]) as nc:
                np.testing.assert_allclose(nc["ke"][:], ke/2)
            self.densities["dust"] = -1
            with self.assertRaisesRegex(ValueError, "density"):
                self.export(directory)

    def test_phase_normalization_explicit(self):
        for calculations in self.data.scheme.components.values():
            for calculation in calculations:
                calculation.bulk.phase_matrix = calculation.bulk.phase_matrix*1.02
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "not normalized"):
                self.export(directory)
            result = self.export(directory, phase_normalization="renormalize")
            self.assertAlmostEqual(result["phase_checks"]["dust"][0]["applied_phase_scale"], 1/1.02)
            self.assertEqual(self.data.report["species"]["super_spheroid"]["psd"]["dndr"], [3, 7])

    def test_reject_diameter_or_continuous_density_psd(self):
        with tempfile.TemporaryDirectory() as directory:
            self.data.report["species"]["super_spheroid"]["psd"]["size_definition"] = "maximum_dimension"
            with self.assertRaisesRegex(ValueError, "volume-equivalent radius"):
                self.export(directory)

    def test_growth_branch_interpolation_and_no_extrapolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"native.nc"
            with Dataset(path, "w") as nc:
                nc.createDimension("rh", 4)
                nc.createVariable("rh", "f8", ("rh",))[:] = [-70, -50, 50, 70]
                nc.createVariable("gf", "f8", ("rh",))[:] = [1.8, 1.4, 1.1, 1.3]
            entry = {"sources": [{"path": str(path)}], "effective_parameters": {
                "relative_humidity": .6, "humidity_branch": "crystallization"}}
            self.assertAlmostEqual(_growth_factor(entry), 1.6)
            entry["effective_parameters"]["humidity_branch"] = "deliquescence"
            self.assertAlmostEqual(_growth_factor(entry), 1.2)
            entry["effective_parameters"]["relative_humidity"] = .8
            with self.assertRaisesRegex(ValueError, "bracket"):
                _growth_factor(entry)


if __name__ == "__main__":
    unittest.main()
