import json
import math
import unittest
from pathlib import Path

from zju_scatt_interface.bulk.integration import integrate_arrays
from zju_scatt_interface.psd.models import SizeDistribution

REFERENCE = (
    Path(__file__).parent / "data" / "trusted_bulk_reference_v1.json"
)


class Phase11TrustedNumericalRegressionTests(unittest.TestCase):
    def test_independent_three_bin_reference(self):
        reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
        result, remap = integrate_arrays(
            SizeDistribution(
                reference["size_um"],
                reference["dndr_cm3"],
            ),
            reference["size_um"],
            extinction_cross_section_m2=(
                reference["extinction_cross_section_m2"]
            ),
            scattering_cross_section_m2=(
                reference["scattering_cross_section_m2"]
            ),
            asymmetry_factor=reference["asymmetry_factor"],
        )
        expected = reference["expected"]
        rel_tol = reference["relative_tolerance"]
        abs_tol = reference["absolute_tolerance"]
        actual = {
            "number_concentration_cm3": result.number_concentration,
            "beta_ext_m-1": result.extinction_coefficient,
            "beta_sca_m-1": result.scattering_coefficient,
            "beta_abs_m-1": result.absorption_coefficient,
            "single_scattering_albedo": result.single_scattering_albedo,
            "asymmetry_factor": result.asymmetry_factor,
        }
        for name, target in expected.items():
            with self.subTest(quantity=name):
                self.assertTrue(
                    math.isclose(
                        actual[name],
                        target,
                        rel_tol=rel_tol,
                        abs_tol=abs_tol,
                    ),
                    f"{name}: {actual[name]} != {target}",
                )
        self.assertAlmostEqual(remap.outside_fraction, 0.0)
        self.assertEqual(result.metadata["bulk_coefficient_unit"], "m-1")

    def test_efficiency_and_cross_section_formulations_agree(self):
        sizes_um = [0.2, 0.5, 1.0]
        counts = [3.0, 5.0, 2.0]
        areas_m2 = [
            math.pi * (radius * 1.0e-6) ** 2 for radius in sizes_um
        ]
        qext = [1.0, 2.0, 2.5]
        qsca = [0.8, 1.5, 2.0]
        cross_ext = [
            efficiency * area
            for efficiency, area in zip(qext, areas_m2)
        ]
        cross_sca = [
            efficiency * area
            for efficiency, area in zip(qsca, areas_m2)
        ]
        distribution = SizeDistribution(sizes_um, counts)
        cross_result, _ = integrate_arrays(
            distribution,
            sizes_um,
            extinction_cross_section_m2=cross_ext,
            scattering_cross_section_m2=cross_sca,
        )
        efficiency_result, _ = integrate_arrays(
            distribution,
            sizes_um,
            extinction_efficiency=qext,
            scattering_efficiency=qsca,
        )
        self.assertAlmostEqual(
            cross_result.extinction_coefficient,
            efficiency_result.extinction_coefficient,
            places=15,
        )
        self.assertAlmostEqual(
            cross_result.scattering_coefficient,
            efficiency_result.scattering_coefficient,
            places=15,
        )
        self.assertAlmostEqual(
            cross_result.absorption_coefficient,
            efficiency_result.absorption_coefficient,
            places=15,
        )

    def test_scattering_weighted_phase_matrix_reference(self):
        distribution = SizeDistribution([0.5, 1.0], [1.0, 3.0])
        phase = [
            [[[1.0, 0.1], [0.1, 0.8]]],
            [[[3.0, 0.3], [0.3, 2.4]]],
        ]
        result, _ = integrate_arrays(
            distribution,
            [0.5, 1.0],
            extinction_cross_section_m2=[2e-12, 4e-12],
            scattering_cross_section_m2=[1e-12, 2e-12],
            phase_matrix=phase,
        )
        first_weight = 1e-12 * 1.0
        second_weight = 2e-12 * 3.0
        expected_p11 = (
            first_weight * 1.0 + second_weight * 3.0
        ) / (first_weight + second_weight)
        self.assertAlmostEqual(result.phase_matrix[0][0][0], expected_p11)


if __name__ == "__main__":
    unittest.main()
