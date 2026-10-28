"""Scientific and configuration tests for the short bulk-table workflow."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_bulk_pipeline import create_source
from zju_scatt_interface.bulk.tables import (
    BulkTableConfig,
    _compute_table,
    _make_psd,
    _restrict_psd,
    _settings,
    _validate_psd_population,
    build_table,
    load_table_config,
    resolve_bulk_settings,
)
from zju_scatt_interface.psd.analytical import lognormal_psd
from zju_scatt_interface.psd.models import SizeDistribution


class DistributionTests(unittest.TestCase):
    def test_public_setting_resolver_keeps_population_and_environment_overrides(self):
        ice = resolve_bulk_settings("ice", {"temperature":250,"shapes":{"ssph_n":2.5,"ssph_asp":2}})
        self.assertEqual(ice["refractive_index"],{"mode":"database_temperature","temperature_k":250})
        self.assertEqual(ice["shape_ensemble"][0]["parameters"],{"roundness":2.5,"aspect_ratio":2})
        bc = resolve_bulk_settings("black_carbon", {"df":2.1,"vf":.4})
        self.assertEqual(bc["parameters"]["df"],2.1)
        self.assertEqual(bc["parameters"]["vf"],.4)
        self.assertEqual(resolve_bulk_settings("water_cloud")["reference"]["psd"]["type"],"gamma")

    def test_population_check_rejects_unrequested_changes_and_wrong_bulk_total(self):
        from types import SimpleNamespace
        original = SizeDistribution([0.5, 1, 2], [2, 3, 5])
        changed = SizeDistribution([0.5, 1, 2], [1, 1.5, 2.5])
        result = SimpleNamespace(wavelength_um=0.5,
                                 bulk=SimpleNamespace(number_concentration=5))
        with self.assertRaisesRegex(ValueError, "bins or counts changed"):
            _validate_psd_population(original, changed, [result], "error")
        with self.assertRaisesRegex(ValueError, "Bulk concentration differs"):
            _validate_psd_population(original, original, [result], "error")
        check = _validate_psd_population(original, changed, [result], "truncate")
        self.assertFalse(check["input_bins_preserved"])
        self.assertEqual(check["used_number_concentration_cm3"], 5)

    def test_cdf_masses_and_normalization(self):
        psd = lognormal_psd(1, 1.8, 10, radius_range_um=[1, 100])
        self.assertAlmostEqual(psd.number_concentration_cm3, 5, places=10)
        finite = lognormal_psd(1, 1.8, 10, radius_range_um=[1, 100], normalization="renormalize")
        self.assertAlmostEqual(finite.number_concentration_cm3, 10)
        self.assertEqual(finite.metadata["rg_um"], 1)
        self.assertAlmostEqual(finite.metadata["radius_bin_edges_um"][0], 1)
        self.assertAlmostEqual(finite.metadata["radius_bin_edges_um"][1], 100)

    def test_custom_psd_requires_explicit_truncation(self):
        psd = lognormal_psd(1, 1.8, 10, radius_range_um=[0.1, 10], normalization="renormalize")
        with self.assertRaisesRegex(ValueError, "common spectral size coverage"):
            _restrict_psd(psd, 0.5, 2, "error")
        clipped = _restrict_psd(psd, 0.5, 2, "truncate")
        normalized = _restrict_psd(psd, 0.5, 2, "truncate_renormalize")
        self.assertLess(clipped.number_concentration_cm3, psd.number_concentration_cm3)
        self.assertAlmostEqual(normalized.number_concentration_cm3, 10)

    def test_reference_does_not_shift_mean_and_uses_requested_concentration(self):
        reference = {"rg_um": 1, "sigma_g": 1.8, "number_concentration_cm3": 1}
        with self.assertRaisesRegex(ValueError, "geometric mean"):
            _make_psd(None, reference, 2, 3, 10, "error")
        psd = _make_psd(None, reference, 0.2, 5, 10, "error")
        self.assertAlmostEqual(psd.number_concentration_cm3, 10)

    def test_explicit_literature_conditioning_keeps_parent_mean_outside_covered_window(self):
        reference = {"type": "lognormal", "rg_um": 0.02, "sigma_g": 1.8}
        psd = _make_psd(None, reference, 0.03, 10, 1, "error", conditional_reference=True)
        self.assertEqual(psd.metadata["rg_um"], 0.02)
        self.assertFalse(psd.metadata["parent_characteristic_within_source_coverage"])
        self.assertGreater(psd.metadata["realized_geometric_mean_radius_um"], 0.03)
        self.assertTrue(0 < psd.metadata["retained_untruncated_lognormal_probability"] < 0.5)
        self.assertAlmostEqual(psd.number_concentration_cm3, 1)
        self.assertGreaterEqual(psd.metadata["radius_bin_edges_um"][0], 0.03*(1-1e-12))
        with self.assertRaisesRegex(ValueError, "no overlap"):
            _make_psd(None, reference, 10, 20, 1, "error", conditional_reference=True)

    def test_invalid_distribution_parameters(self):
        for kwargs in ({"sigma_g": 1}, {"rg_um": float("nan")}, {"bins": 2}, {"normalization": "auto"}):
            with self.assertRaises((ValueError, TypeError)):
                lognormal_psd(**{"rg_um": 1, "sigma_g": 1.8, **kwargs})


class ConfigurationTests(unittest.TestCase):
    def test_python_and_json_configs_resolve_paths_beside_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = {"species": ["dust"], "wavelengths": [0.55], "output_dir": "out",
                     "source_paths": {"dust": ["native.nc"]},
                     "overrides": {"dust": {"refractive_index": {"mode": "table", "file": "ri.csv"}}}}
            for suffix, content in ((".py", "bulk_table = " + repr(value)), (".json", json.dumps(value))):
                path = root / ("input" + suffix)
                path.write_text(content, encoding="utf-8")
                config = load_table_config(path)
                self.assertEqual(config.output_dir, str(root / "out"))
                self.assertEqual(config.source_paths["super_spheroid"], [str(root / "native.nc")])
                self.assertEqual(config.overrides["super_spheroid"]["refractive_index"]["file"], str(root / "ri.csv"))

    def test_shape_pairs_and_weights_preserved(self):
        _, _, shapes, _, _ = _settings("super_spheroid", {"shapes": [
            {"n": 2.7, "asp": 1.5, "weight": 1}, {"n": 2.8, "asp": 1.9, "weight": 3}]})
        self.assertEqual([s["parameters"] for s in shapes], [
            {"roundness": 2.7, "aspect_ratio": 1.5}, {"roundness": 2.8, "aspect_ratio": 1.9}])
        self.assertEqual([s["weight"] for s in shapes], [0.25, 0.75])
        with self.assertRaisesRegex(ValueError, "exactly"):
            _settings("super_spheroid", {"shapes": {"n": 2.7}})

    def test_configuration_rejects_ambiguous_or_unused_inputs(self):
        for kwargs in ({"species": []}, {"wavelengths": [0.5, 0.5]}, {"preset": "unknown"},
                       {"coverage_policy": "auto"}, {"overrides": {"ice": {}}}, {"offline": "false"}):
            with self.assertRaises(ValueError):
                BulkTableConfig(**{"wavelengths": [0.55], "species": ["dust"], **kwargs})

    def test_invalid_psd_is_rejected_before_catalog_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('zju_scatt_interface.access.retrieval.retrieve_sources', side_effect=AssertionError("Unexpected network access")):
                with self.assertRaisesRegex(ValueError, "sigma_g must exceed"):
                    _compute_table(species="dust", wavelengths=[0.55], workspace=directory,
                        overrides={"dust": {"psd": {"type": "lognormal", "rg_um": 1, "sigma_g": 1}}}, progress=None)


class WorkflowTests(unittest.TestCase):
    def test_measured_csv_counts_override_reference_total_without_normalization(self):
        from netCDF4 import Dataset
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "L1_sphere_water_cloud_wl_0.500_um_ref_1.3_0.nc"
            create_source(source, wavelength=0.5)
            csv = root / "measured.csv"
            csv.write_text("radius_um,number_per_bin_cm3\n0.5,2\n1,3\n2,5\n", encoding="utf-8")
            config = {"species": "water_cloud", "wavelengths": [0.5],
                "number_concentration_cm3": 999, "source_paths": {"water_cloud": [source]},
                "workspace": root / "work", "output_dir": root / "out",
                "overrides": {"water_cloud": {"psd": {"file": str(csv),
                    "size_column": "radius_um", "dndr_column": "number_per_bin_cm3"}}}}
            # Normalizing the input is forbidden in this path, including reruns.
            with patch.object(SizeDistribution, "normalized", side_effect=AssertionError("Unexpected normalization")):
                first = build_table(config, progress=None)
                cached = build_table(config, progress=None)
            self.assertEqual(first.rows, cached.rows)
            entry = cached.report["species"]["sphere_water_cloud"]
            self.assertTrue(entry["checkpoint_reused"])
            self.assertEqual(entry["psd"]["size"], [0.5, 1, 2])
            self.assertEqual(entry["psd"]["dndr"], [2, 3, 5])
            self.assertTrue(entry["psd_handling"]["input_bins_preserved"])
            self.assertTrue(entry["psd_handling"]["output_concentration_verified"])
            self.assertEqual(entry["psd_handling"]["input_number_concentration_cm3"], 10)
            self.assertAlmostEqual(cached.rows[0]["number_concentration_cm-3"], 10)
            with Dataset(root / "out" / "bulk_optics_all_species.nc") as nc:
                self.assertAlmostEqual(float(nc.groups["sphere_water_cloud"]["number_concentration"][0]), 10)

    def test_phase_matrix_toggle_reaches_calculator_and_export(self):
        from netCDF4 import Dataset
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "L1_sphere_water_cloud_wl_0.500_um_ref_1.3_0.nc"
            create_source(path, wavelength=0.5, phase=True)
            result = _compute_table(species="water_cloud", wavelengths=[0.5],
                source_paths={"water_cloud": [path]}, workspace=root / "work", include_phase_matrix=True,
                overrides={"water_cloud": {"psd": {"type": "gamma", "effective_radius_um": 2,
                    "effective_variance": 1/3, "radius_range_um": [0.2, 5]}}}, progress=None)
            outputs = result.save(root / "out", formats="nc")
            with Dataset(outputs["nc"]) as ds:
                group = ds.groups["sphere_water_cloud"]
                self.assertIn("p11", group.variables)
                self.assertIn("p44", group.variables)

    def test_dust_interpolates_paired_shapes_and_refractive_indices(self):
        from itertools import product
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for n, asp, mr, mi in product((2.6, 2.8), (1.4, 1.6), (1.5, 1.6), (0.01, 0.02)):
                path = root / (f"L1_super_spheroid_n_{n:.3f}_asp_{asp:.3f}_wl_nan_ref_{mr:.3e}_{mi:.3e}.nc")
                create_source(path, wavelength=None, multiplier=n + asp + mr + math.log(mi))
                paths.append(path)
            config = {"species": ["dust"], "wavelengths": [0.55, 0.65],
                "source_paths": {"dust": paths}, "workspace": root / "work",
                "overrides": {"dust": {"shapes": [
                    {"n": 2.7, "asp": 1.5, "weight": 1}, {"n": 2.65, "asp": 1.55, "weight": 3}],
                    "refractive_index": {"mode": "fixed", "real": 1.55, "imaginary": math.sqrt(0.0002)},
                    "psd": {"type": "lognormal", "rg_um": 0.3, "sigma_g": 1.4,
                            "radius_range_um": [0.08, 1.2], "normalization": "renormalize"}}}}
            result = build_table(config, progress=None)
            self.assertEqual(len(result.rows), 2)
            for calculation in result.scheme.components["super_spheroid"]:
                self.assertEqual(len(calculation.members), 2)
                self.assertEqual([m.weight for m in calculation.members], [0.25, 0.75])
                self.assertAlmostEqual(calculation.bulk.extinction_coefficient,
                    sum(m.weight * m.bulk.extinction_coefficient for m in calculation.members))

    def test_ice_interpolates_temperature_wavelength_and_shape_together(self):
        from itertools import product
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for n, asp, wavelength, temperature in product((2, 2.25), (1.5, 1.75), (1.5, 1.7), (220, 270)):
                path = root / (f"L1_super_spheroid_ice_n_{n:.3f}_asp_{asp:.3f}_wl_{wavelength:.3f}_um_ref_1.3_0.1_t_{temperature}k.nc")
                create_source(path, wavelength=wavelength, multiplier=n + asp + wavelength + temperature/100)
                paths.append(path)
            result = _compute_table(species=["ice"], wavelengths=[1.6], source_paths={"ice": paths},
                workspace=root / "work", overrides={"ice": {"temperature": 250,
                    "shapes": {"n": 2.1, "asp": 1.7}, "psd": {"type": "lognormal", "rg_um": 1,
                    "sigma_g": 1.4, "radius_range_um": [0.2, 5], "normalization": "renormalize"}}}, progress=None)
            self.assertTrue(result.scheme.components["super_spheroid_ice"][0].qa.passed)
            self.assertEqual(result.report["species"]["super_spheroid_ice"]["effective_parameters"]["temperature"], 250)

    def test_real_interpolation_shared_psd_export_and_checkpoint_invalidation(self):
        from netCDF4 import Dataset
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "sphere_water_cloud"
            sources = []
            for wavelength, multiplier in ((0.5, 1), (0.7, 3)):
                path = native / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc"
                create_source(path, wavelength=wavelength, multiplier=multiplier)
                sources.append(path)
            kwargs = {"species": ["water_cloud"], "wavelengths": [0.5, 0.6, 0.7],
                "workspace": root / "work", "source_paths": {"water_cloud": sources},
                "overrides": {"water_cloud": {"psd": {"type": "lognormal", "rg_um": 1,
                    "sigma_g": 1.4, "radius_range_um": [0.2, 5], "normalization": "renormalize"}}},
                "progress": None}
            first = _compute_table(**kwargs)
            self.assertEqual(len(first.rows), 3)
            beta = [r["beta_ext_m-1"] for r in first.rows]
            self.assertAlmostEqual(beta[1], (beta[0] + beta[2]) / 2)
            self.assertTrue(all(abs(row["number_concentration_cm-3"] - 1) < 1e-10 for row in first.rows))
            second = _compute_table(**kwargs)
            self.assertTrue(second.report["species"]["sphere_water_cloud"]["checkpoint_reused"])
            self.assertEqual(first.rows, second.rows)
            outputs = second.save(root / "out")
            with Dataset(outputs["nc"]) as ds:
                group = ds.groups["sphere_water_cloud"]
                self.assertEqual(list(group.variables["ensemble_member"][:]), [0])
                self.assertNotIn("qa_passed", group.variables)
                self.assertNotIn("wavelength", ds.variables)
            with Dataset(sources[0], "a") as ds:
                ds.variables["cext"][:] *= 2
            third = _compute_table(**kwargs)
            self.assertFalse(third.report["species"]["sphere_water_cloud"]["checkpoint_reused"])
            self.assertGreater(third.rows[0]["beta_ext_m-1"], first.rows[0]["beta_ext_m-1"])

    def test_run_config_saves_and_validates_parameters_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "L1_sphere_water_cloud_wl_0.500_um_ref_1.3_0.nc"
            create_source(path, wavelength=0.5)
            result = build_table({"species": "water_cloud", "wavelengths": [0.5],
                "source_paths": {"water_cloud": [path]}, "workspace": root / "work", "output_dir": root / "out",
                "overrides": {"water_cloud": {"psd": {"type": "gamma", "effective_radius_um": 2,
                    "effective_variance": 1/3, "radius_range_um": [0.2, 5]}}}}, progress=None)
            self.assertEqual(len(result.rows), 1)
            self.assertTrue((root / "out" / "report.json").exists())
            with self.assertRaisesRegex(ValueError, "Unknown parameter"):
                _compute_table(species="water_cloud", wavelengths=[0.5], source_paths={"water_cloud": [path]},
                    overrides={"water_cloud": {"temprature": 220}}, workspace=root / "work", progress=None)


if __name__ == "__main__":
    unittest.main()
