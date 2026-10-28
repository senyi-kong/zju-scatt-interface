import math
import unittest

from zju_scatt_interface.bulk.tables import BulkTableConfig, _make_psd
from zju_scatt_interface.psd.analytical import _gamma_probabilities, gamma_psd, gamma_radius_bounds
from zju_scatt_interface.psd.models import SizeDistribution


class GammaPSDTests(unittest.TestCase):
    def test_probabilities_match_exponential_erf_and_integer_gamma(self):
        for x in (1e-8, 0.1, 1, 5, 20, 100):
            for a in (1, 2, 8):
                p, q = _gamma_probabilities(a, x)
                expected_q = math.exp(-x) * math.fsum(x**j / math.factorial(j) for j in range(a))
                self.assertAlmostEqual(q, expected_q, places=13)
                self.assertAlmostEqual(p + q, 1, places=14)
            p, q = _gamma_probabilities(0.5, x)
            self.assertAlmostEqual(p, math.erf(math.sqrt(x)), places=13)
            self.assertAlmostEqual(q, math.erfc(math.sqrt(x)), places=13)

    def test_preserve_and_conditional_normalization_use_exact_bin_probabilities(self):
        # v_eff=1/3 -> a=1, theta=10/3: exponential number distribution.
        theta = 10 / 3
        psd = gamma_psd(10, 1/3, 10, radius_range_um=[theta, 2*theta])
        self.assertAlmostEqual(psd.number_concentration_cm3, 10*(math.exp(-1) - math.exp(-2)), places=12)
        normalized = gamma_psd(10, 1/3, 10, radius_range_um=[theta, 2*theta], normalization="renormalize")
        self.assertAlmostEqual(normalized.number_concentration_cm3, 10)
        self.assertAlmostEqual(normalized.metadata["gamma_shape"], 1)
        self.assertAlmostEqual(normalized.metadata["parent_number_mean_radius_um"], theta)

    def test_untruncated_discrete_moments_reproduce_effective_parameters(self):
        for radius, variance in ((10, 1/3), (30, 0.1), (7, 0.4), (5, 0.07)):
            psd = gamma_psd(radius, variance, bins=10000)
            self.assertAlmostEqual(psd.number_concentration_cm3, 1-2e-8, places=12)
            # A small discarded number fraction can carry a larger fourth
            # moment. Compare discretization to exact finite-interval moments,
            # and separately bound the difference from infinite-parent values.
            lower, upper = psd.metadata["radius_bin_edges_um"]
            a, theta = 1/variance - 2, radius*variance
            moments = {}
            for j in (2, 3, 4):
                p0, q0 = _gamma_probabilities(a+j, lower/theta)
                p1, q1 = _gamma_probabilities(a+j, upper/theta)
                moments[j] = theta**j * math.exp(math.lgamma(a+j)-math.lgamma(a)) * (p1-p0)
            expected_radius = moments[3]/moments[2]
            expected_variance = moments[4]*moments[2]/moments[3]**2 - 1
            self.assertLess(abs(psd.metadata["realized_effective_radius_um"] / expected_radius - 1), 1e-5)
            self.assertLess(abs(psd.metadata["realized_effective_variance"] / expected_variance - 1), 1e-5)
            self.assertLess(abs(psd.metadata["realized_effective_radius_um"] / radius - 1), 5e-5)
            self.assertLess(abs(psd.metadata["realized_effective_variance"] / variance - 1), 5e-4)

    def test_invalid_parameters_and_coordinate_confusion_are_rejected(self):
        for variance in (0, -0.1, 0.5, 1, float("nan")):
            with self.assertRaisesRegex(ValueError, "effective_variance"):
                gamma_psd(10, variance)
        for kwargs in ({"effective_radius_um": -1}, {"normalization": "auto"}, {"bins": 2},
                       {"radius_range_um": [0, 10]}, {"number_concentration_cm3": float("inf")}):
            with self.assertRaises(ValueError):
                gamma_psd(**{"effective_radius_um": 10, "effective_variance": 0.1, **kwargs})
        with self.assertRaisesRegex(ValueError, "Unknown gamma"):
            _make_psd({"type": "gamma", "rg_um": 10, "sigma_g": 1.5}, {}, 1, 20, 1, "error")

    def test_spectral_restriction_reports_realized_moments_and_parent_probability(self):
        config = {"type": "gamma", "effective_radius_um": 10, "effective_variance": 1/3}
        psd = _make_psd(None, config, 1.5, 23, 1, "error")
        self.assertAlmostEqual(psd.number_concentration_cm3, 1)
        self.assertEqual(psd.metadata["effective_radius_um"], 10)
        self.assertGreater(psd.metadata["retained_untruncated_gamma_probability"], 0.6)
        self.assertLess(psd.metadata["retained_untruncated_gamma_probability"], 0.7)
        self.assertNotEqual(psd.metadata["realized_effective_radius_um"], 10)
        requested = gamma_psd(10, 1/3, radius_range_um=[0.01, 80])
        with self.assertRaisesRegex(ValueError, "common spectral"):
            _make_psd(requested, {}, 1.5, 23, 1, "error")
        clipped = _make_psd(requested, {}, 1.5, 23, 1, "truncate")
        self.assertLess(clipped.number_concentration_cm3, requested.number_concentration_cm3)
        self.assertNotEqual(clipped.metadata["realized_effective_radius_um"], requested.metadata["realized_effective_radius_um"])

    def test_default_and_legacy_config_presets_are_explicit(self):
        self.assertEqual(BulkTableConfig(wavelengths=[0.55]).preset, "literature_v1")
        self.assertEqual(BulkTableConfig(wavelengths=[0.55], preset="reference_v1").preset, "reference_v1")

    def test_workflow_exposes_coarsening_warnings_without_changing_psd(self):
        import tempfile
        from dataclasses import replace
        from pathlib import Path
        from unittest.mock import patch

        from tests.test_bulk_pipeline import create_source
        from zju_scatt_interface.bulk.tables import _compute_table
        from zju_scatt_interface.bulk.workflow import build_dataset

        def diagnostic_warning(*args, **kwargs):
            result = build_dataset(*args, **kwargs)
            member = result.components["sphere_water_cloud"][0].members[0]
            member.convergence = replace(member.convergence, checked=True, passed=False,
                relative_errors={"extinction_coefficient": 0.0542})
            return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "L1_sphere_water_cloud_wl_0.500_um_ref_1.3_0.nc"
            create_source(path, wavelength=0.5)
            messages = []
            with patch('zju_scatt_interface.bulk.tables.build_dataset', side_effect=diagnostic_warning):
                result = _compute_table(species="water_cloud", wavelengths=[0.5], source_paths={"water_cloud": [path]},
                    workspace=root / "work", progress=messages.append, overrides={"water_cloud": {"psd": {
                        "type": "gamma", "effective_radius_um": 2, "effective_variance": 1/3, "radius_range_um": [0.2, 5]}}})
            entry = result.report["species"]["sphere_water_cloud"]
            self.assertFalse(entry["convergence_all_passed"])
            self.assertIn("5.42%", entry["warnings"][0])
            self.assertTrue(any(message.startswith("Warning:") for message in messages))
            self.assertEqual(entry["psd"]["metadata"]["effective_radius_um"], 2)


if __name__ == "__main__":
    unittest.main()
