"""Reusable PSD exports and one-population bulk inspection outputs."""

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

import zju_scatt_interface.access.models as _domain_access_models
from tests.test_bulk_pipeline import create_source
from tests.test_native_retrieval import native_fixture
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.psd.analytical import gamma_psd, lognormal_psd
from zju_scatt_interface.psd.models import SizeDistribution


class BulkResultOutputTests(unittest.TestCase):
    def test_public_psd_constructors_share_implementation_and_keep_normalization_explicit(self):
        from zju_scatt_interface.psd.analytical import lognormal_psd as implementation
        from zju_scatt_interface.psd.analytical import lognormal_psd as legacy

        self.assertIs(lognormal_psd, implementation)
        self.assertIs(lognormal_psd, legacy)
        for construct, params in ((lognormal_psd, (1.0, 1.8)), (gamma_psd, (1.0, 0.2))):
            raw = construct(*params, 10, radius_range_um=(0.5, 2))
            finite = construct(*params, 10, radius_range_um=(0.5, 2), normalization="renormalize")
            self.assertLess(raw.number_concentration_cm3, 10)
            self.assertAlmostEqual(finite.number_concentration_cm3, 10)

    def test_psd_csv_roundtrip_preserves_size_definition_and_raw_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            for definition in ("volume_equivalent_sphere_radius", "maximum_dimension_radius"):
                psd = SizeDistribution([0.5, 1, 2], [2, 3, 5], size_definition=definition)
                path = psd.to_csv(Path(directory) / f"{definition}.csv")
                loaded = SizeDistribution.from_file(path)
                self.assertEqual(loaded.size_um, psd.size_um)
                self.assertEqual(loaded.dndr_cm3, psd.dndr_cm3)
                self.assertEqual(loaded.size_definition, definition)
            with self.assertRaisesRegex(ValueError, "conflicts"):
                SizeDistribution.from_file(path, size_definition="volume_equivalent_sphere_radius")

    def test_save_exports_original_population_and_phase_without_diagnostics_in_nc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "L1_sphere_water_cloud_wl_1.600_um_ref_1.330e+00_1.000e-06.nc"
            create_source(source, wavelength=1.6, phase=True)
            psd = lognormal_psd(0.7, 1.8, 10, radius_range_um=(0.2, 5), normalization="renormalize")
            calculation = compute_population(
                "water_cloud",
                source,
                psd,
                wavelength=1.6,
                include_phase_matrix=True,
                check_convergence=False,
                phase_normalization="unit_solid_angle",
            )
            outputs = calculation.save(root / "output", size_distribution=psd)
            with Path(outputs["scalars_csv"]).open() as stream:
                row = next(csv.DictReader(stream))
            self.assertAlmostEqual(float(row["number_concentration_cm-3"]), 10)
            self.assertAlmostEqual(
                float(row["extinction_coefficient_m-1"]), calculation.bulk.extinction_coefficient
            )
            with Path(outputs["phase_csv"]).open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), len(calculation.bulk.phase_matrix))
            self.assertAlmostEqual(float(rows[0]["P43"]), calculation.bulk.phase_matrix[0][3][2])
            with Dataset(outputs["nc"]) as ds:
                group = ds.groups["bulk_optics"]
                self.assertIn("ensemble_member", group.variables)
                self.assertNotIn("qa_passed", group.variables)
            report = json.loads(Path(outputs["report"]).read_text())
            self.assertIn("qa", report["calculation"])
            self.assertEqual(report["size_distribution"]["dndr"], list(psd.dndr_cm3))

    def test_simplified_local_example_runs_with_real_synthetic_native_data(self):
        local = Path(__file__).resolve().parents[2] / "test_zju_scatt/user_test_local"
        if not local.is_dir():
            self.skipTest("Local examples not present")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = (
                root
                / "L1_super_spheroid_n_2.000_asp_1.600_wl_nan_ref_1.500e+00_3.000e-03_v1.0_20260409.nc"
            )
            native_fixture(path, None, 2, grid=np.geomspace(0.01, 1000, 700))
            with Dataset(path, "a") as ds:
                ds.institution = "Synthetic test source"
                ds["ssph_asp"][...] = 1.6
            obj = _domain_access_models.RemoteObject("Single_opt/super_spheroid/" + path.name, path.stat().st_size)
            retrieved = _domain_access_models.RetrievalResult(
                [obj],
                _domain_access_models.ScanStats(),
                _domain_access_models.WavelengthProcessing(),
                download_results=[_domain_access_models.DownloadResult(obj, path, "skipped")],
            )
            with patch.object(sys, "path", [str(local), *sys.path]):
                spec = importlib.util.spec_from_file_location(
                    "example14", local / "14_super_spheroid_lognormal_bulk_optics.py"
                )
                example = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(example)
            with (
                patch.object(example, 'retrieve_sources', return_value=retrieved),
                patch.object(sys, "argv", ["example14", "--output-dir", str(root / "output")]),
            ):
                example.main()
            self.assertTrue((root / "output/application_outputs/bulk_optics_10_cm3.nc").is_file())
            self.assertEqual(
                len(list((root / "output/L2_bulk_scattering_property").rglob("*.nc"))), 1
            )
            self.assertEqual(
                len(list((root / "output/L2_bulk_scattering_property").rglob("*.md"))), 1
            )
            psd = SizeDistribution.from_file(root / "output/size_distribution.csv")
            self.assertAlmostEqual(psd.number_concentration_cm3, 10)


if __name__ == "__main__":
    unittest.main()
