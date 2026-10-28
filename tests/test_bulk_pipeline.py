
import math
import tempfile
import unittest
from pathlib import Path

import zju_scatt_interface.access.metadata as _domain_access_metadata
import zju_scatt_interface.optics.loading as _domain_optics_loading
from tests.local_data import local_l1_root
from zju_scatt_interface.bulk.ensemble import (
    WeightedShapeEnsemble,
    WeightedShapeMember,
    WeightedValues,
    combine,
)
from zju_scatt_interface.bulk.quality import validate_bulk_optics
from zju_scatt_interface.bulk.workflow import build_dataset, compute_population
from zju_scatt_interface.config.scheme import Scheme
from zju_scatt_interface.optics.models import BulkOptics
from zju_scatt_interface.psd.models import SizeDistribution


def create_source(
    path: Path,
    *,
    wavelength: float | None,
    multiplier: float = 1.0,
    rh=None,
    phase: bool = False,
):
    import numpy as np
    from netCDF4 import Dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    radii = np.geomspace(0.1, 10.0, 24)
    with Dataset(path, "w") as dataset:
        dataset.createDimension("xsize_veq", len(radii))
        if wavelength is not None:
            dataset.createVariable("wavelength", "f8")[:] = wavelength
            raw_size = radii * 2 * math.pi / wavelength
        else:
            raw_size = np.geomspace(0.5, 20.0, len(radii))
        dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = raw_size
        dimensions = ["xsize_veq"]
        if rh is not None:
            dataset.createDimension("rh", len(rh))
            dataset.createVariable("rh", "f8", ("rh",))[:] = rh
            dimensions.insert(0, "rh")
        shape = tuple(dataset.dimensions[name].size for name in dimensions)
        cext = np.empty(shape)
        if rh is None:
            cext[:] = multiplier * np.geomspace(0.2, 200.0, len(radii))
        else:
            for index, value in enumerate(rh):
                cext[index] = (
                    multiplier
                    * (1 + abs(float(value)) / 100)
                    * np.geomspace(0.2, 200.0, len(radii))
                )
        dataset.createVariable("cext", "f8", tuple(dimensions))[:] = cext
        dataset.createVariable("ssa", "f8", tuple(dimensions))[:] = 0.7
        dataset.createVariable("g", "f8", tuple(dimensions))[:] = 0.4
        if phase:
            dataset.createDimension("sca_angle", 7)
            angles = np.linspace(0, 180, 7)
            dataset.createVariable("sca_angle", "f8", ("sca_angle",))[:] = angles
            phase_dimensions = tuple(dimensions) + ("sca_angle",)
            phase_shape = shape + (len(angles),)
            p11 = np.ones(phase_shape) * 1.0
            dataset.createVariable("p11", "f8", phase_dimensions)[:] = p11
            dataset.createVariable("p12", "f8", phase_dimensions)[:] = 0.1
            dataset.createVariable("p22", "f8", phase_dimensions)[:] = 0.8
            dataset.createVariable("p33", "f8", phase_dimensions)[:] = 0.7
            dataset.createVariable("p43", "f8", phase_dimensions)[:] = 0.05
            dataset.createVariable("p44", "f8", phase_dimensions)[:] = 0.6
    return radii


class WeightedEnsembleTests(unittest.TestCase):
    def test_weight_validation_and_normalization(self):
        values = WeightedValues([1.0, 2.0], [1.0, 3.0])
        self.assertEqual(values.weights, (0.25, 0.75))
        ensemble = WeightedShapeEnsemble(
            [
                WeightedShapeMember(roundness=2.0, aspect_ratio=1.0, weight=2),
                WeightedShapeMember(roundness=2.5, aspect_ratio=1.5, weight=3),
            ]
        )
        self.assertAlmostEqual(sum(member.weight for member in ensemble.members), 1.0)
        with self.assertRaisesRegex(ValueError, "equal length"):
            WeightedValues([1, 2], [1])
        with self.assertRaisesRegex(ValueError, "non-negative"):
            WeightedShapeMember(roundness=2.0, weight=-1)

    def test_extensive_combination_rederives_intensive_properties(self):
        first = BulkOptics(10, 8, 2, 0.8, 0.2, number_concentration=100)
        second = BulkOptics(20, 10, 10, 0.5, 0.8, number_concentration=100)
        result = combine([first, second], [0.25, 0.75])
        self.assertAlmostEqual(result.extinction_coefficient, 17.5)
        self.assertAlmostEqual(result.scattering_coefficient, 9.5)
        self.assertAlmostEqual(result.single_scattering_albedo, 9.5 / 17.5)
        self.assertAlmostEqual(
            result.asymmetry_factor,
            (0.25 * 8 * 0.2 + 0.75 * 10 * 0.8) / 9.5,
        )
        self.assertEqual(result.number_concentration, 100)

    def test_bulk_qa_detects_closure_and_preserves_phase_normalization_warning(self):
        phase = [
            [
                [1.0, 0.1, 0, 0],
                [0.1, 0.8, 0, 0],
                [0, 0, 0.7, -0.05],
                [0, 0, 0.05, 0.6],
            ]
            for _ in range(3)
        ]
        good = BulkOptics(10, 8, 2, 0.8, 0.4, phase_matrix=phase)
        report = validate_bulk_optics(good, scattering_angles=[0, 90, 180])
        self.assertTrue(report.passed)
        self.assertTrue(report.warnings)
        bad = BulkOptics(10, 12, -2, 1.2, 2.0)
        self.assertFalse(validate_bulk_optics(bad).passed)


class PublicBulkPipelineTests(unittest.TestCase):
    def setUp(self):
        try:
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("netCDF4 is not installed")

    def test_one_profile_pipeline_interpolates_integrates_and_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sphere_water_cloud"
            for wavelength, multiplier in ((0.5, 1.0), (0.7, 2.0)):
                create_source(
                    root
                    / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc",
                    wavelength=wavelength,
                    multiplier=multiplier,
                    phase=True,
                )
            psd = SizeDistribution(
                [0.1, 0.3, 1.0, 3.0, 10.0],
                [1, 5, 10, 5, 1],
            )
            result = compute_population(
                "water_cloud",
                root,
                psd,
                wavelength=600,
                wavelength_unit="nm",
                include_phase_matrix=True,
                target_angles_degrees=[0, 30, 60, 90, 120, 150, 180],
                truncation_policy="truncate",
            )
        self.assertTrue(result.qa.passed)
        self.assertEqual(result.particle_type, "sphere_water_cloud")
        self.assertEqual(len(result.members), 1)
        self.assertEqual(result.members[0].interpolation_provenance["method"], "multilinear")
        self.assertEqual(
            result.bulk.metadata["bulk_coefficient_unit"],
            "m-1",
        )
        self.assertAlmostEqual(
            result.bulk.number_concentration,
            result.members[0].remap.output_number_concentration_cm3,
        )
        self.assertLess(result.bulk.number_concentration, 22.0)
        self.assertTrue(result.members[0].convergence.checked)

    def test_joint_shape_ensemble_is_scattering_weighted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "super_spheroid"
            for roundness, multiplier in ((2.0, 1.0), (2.5, 3.0)):
                create_source(
                    root
                    / (
                        f"L1_super_spheroid_n_{roundness:.3f}_asp_1.000_"
                        "wl_nan_ref_1.500e+00_1.000e-02.nc"
                    ),
                    wavelength=None,
                    multiplier=multiplier,
                )
            factor = 0.55 / (2 * math.pi)
            psd = SizeDistribution(
                [0.5 * factor, 2 * factor, 8 * factor, 20 * factor],
                [1, 4, 4, 1],
            )
            result = compute_population(
                "dust",
                root,
                psd,
                wavelength=0.55,
                parameters={"mr": 1.5, "mi": 0.01},
                shape_ensemble=WeightedShapeEnsemble(
                    [
                        WeightedShapeMember(
                            roundness=2.0, aspect_ratio=1.0, weight=0.25
                        ),
                        WeightedShapeMember(
                            roundness=2.5, aspect_ratio=1.0, weight=0.75
                        ),
                    ]
                ),
                truncation_policy="truncate",
            )
        self.assertEqual(len(result.members), 2)
        self.assertEqual([member.weight for member in result.members], [0.25, 0.75])
        unscaled = sum(
            member.weight * member.bulk.extinction_coefficient
            for member in result.members
        )
        self.assertAlmostEqual(result.bulk.extinction_coefficient, unscaled)
        expected_number = sum(
            member.weight * member.remap.output_number_concentration_cm3
            for member in result.members
        )
        self.assertAlmostEqual(result.bulk.number_concentration, expected_number)

    def test_multi_component_scheme_repeats_public_calculation_and_keeps_components(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            water_root = root / "sphere_water_cloud"
            sulfate_root = root / "sphere_sulfate"
            for wavelength in (0.5, 0.7):
                create_source(
                    water_root
                    / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc",
                    wavelength=wavelength,
                )
                create_source(
                    sulfate_root
                    / f"L1_sphere_sulfate_wl_{wavelength:.3f}_um_ref_1.5_0.nc",
                    wavelength=wavelength,
                    rh=[0, 50],
                )
            config = Scheme.from_mapping(
                {
                    "name": "phase7",
                    "wavelengths": [0.5, 0.6],
                    "particles": [
                        {
                            "name": "cloud",
                            "particle_type": "water_cloud",
                            "size_distribution": {
                                "size": [0.1, 1, 10],
                                "dndr": [1, 8, 1],
                            },
                            "refractive_index": {"mode": "database"},
                        },
                        {
                            "name": "sulfate",
                            "particle_type": "sphere_sulfate",
                            "size_distribution": {
                                "size": [0.1, 1, 10],
                                "dndr": [2, 4, 2],
                            },
                            "shape_parameters": {"RH": 0.25},
                            "refractive_index": {"mode": "database"},
                        },
                    ],
                }
            )
            result = build_dataset(
                config,
                source_paths={"cloud": water_root, "sulfate": sulfate_root},
                truncation_policy="truncate",
            )
        self.assertEqual(set(result.components), {"cloud", "sulfate"})
        self.assertEqual(len(result.components["cloud"]), 2)
        self.assertIsNone(result.mixture)
        self.assertNotEqual(
            result.components["cloud"][1].bulk.extinction_coefficient,
            result.components["sulfate"][1].bulk.extinction_coefficient,
        )


class LocalL1BulkPipelineRegressionTests(unittest.TestCase):
    def test_real_water_cloud_exact_product_integrates(self):
        root = local_l1_root() / "sphere_water_cloud"
        if not root.exists():
            self.skipTest("Local ZJU-SCATT L1 database is not mounted")
        path = next(root.rglob("*.nc"))
        metadata = _domain_access_metadata.extract_scatt_metadata(path.name)
        optics = _domain_optics_loading.load_single(path)
        indices = [0, len(optics.sizes) // 2, len(optics.sizes) - 1]
        psd = SizeDistribution(
            [optics.sizes[index] for index in indices],
            [1.0, 10.0, 1.0],
        )
        result = compute_population(
            "water_cloud",
            path,
            psd,
            wavelength=metadata["wavelength_um"],
            truncation_policy="truncate",
        )
        self.assertTrue(result.qa.passed)
        self.assertGreater(result.bulk.extinction_coefficient, 0)
        self.assertEqual(result.members[0].interpolation_provenance["method"], "exact")


if __name__ == "__main__":
    unittest.main()
