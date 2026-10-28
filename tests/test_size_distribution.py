import math
import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.bulk.integration import integrate_arrays
from zju_scatt_interface.config.scheme import load_scheme
from zju_scatt_interface.psd.models import SizeDistribution


class SizeDistributionValidationTests(unittest.TestCase):
    def test_nm_is_normalized_and_default_definition_is_explicit(self) -> None:
        distribution = SizeDistribution([100, 200, 400], [1, 2, 1], "nm")
        self.assertEqual(distribution.size_um, (0.1, 0.2, 0.4))
        self.assertEqual(
            distribution.size_definition,
            "volume_equivalent_sphere_radius",
        )
        self.assertEqual(distribution.integration_mode, "discrete_bin")
        self.assertEqual(distribution.number_concentration_cm3, 4.0)

    def test_invalid_units_order_duplicates_and_concentrations_are_rejected(self) -> None:
        cases = (
            (([1, 2], [1, 1]), {"size_unit": "mm"}, "size_unit"),
            (([1, 1], [1, 1]), {}, "strictly increasing"),
            (([2, 1], [1, 1]), {}, "strictly increasing"),
            (([1, 2], [1, -1]), {}, "negative"),
            (([1, 2], [0, 0]), {}, "positive concentration"),
            (([1, math.nan], [1, 1]), {}, "finite"),
            (([1, 2], [1, 1]), {"dndr_unit": "m-3"}, "fixed"),
        )
        for positional, keywords, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    SizeDistribution(*positional, **keywords)

    def test_gap_detection_can_warn_or_fail(self) -> None:
        warned = SizeDistribution(
            [0.1, 0.11, 10.0],
            [1, 1, 1],
            gap_policy="warn",
            maximum_log_spacing_ratio=2,
        )
        self.assertTrue(warned.validation_messages)
        with self.assertRaisesRegex(ValueError, "spacing gap"):
            SizeDistribution(
                [0.1, 0.11, 10.0],
                [1, 1, 1],
                gap_policy="error",
                maximum_log_spacing_ratio=2,
            )

    def test_normalization_preserves_shape(self) -> None:
        distribution = SizeDistribution([1, 2, 3], [1, 2, 1])
        normalized = distribution.normalized(100)
        self.assertAlmostEqual(normalized.number_concentration_cm3, 100)
        self.assertEqual(normalized.dndr_cm3, (25.0, 50.0, 25.0))

    def test_function_generated_distribution(self) -> None:
        distribution = SizeDistribution.from_callable(
            [0.1, 0.2, 0.4],
            lambda radius: math.exp(-radius),
        )
        self.assertEqual(len(distribution.dndr_cm3), 3)
        self.assertGreater(distribution.dndr_cm3[0], distribution.dndr_cm3[-1])


class SizeDistributionInputTests(unittest.TestCase):
    def test_csv_and_tsv_named_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "psd.csv"
            csv_path.write_text(
                "radius_nm,observed_number\n100,2\n200,3\n",
                encoding="utf-8",
            )
            csv_psd = SizeDistribution.from_delimited(
                csv_path,
                size_column="radius_nm",
                dndr_column="observed_number",
                size_unit="nm",
            )
            tsv_path = root / "psd.tsv"
            tsv_path.write_text("size\tdndr\n0.1\t2\n0.2\t3\n", encoding="utf-8")
            tsv_psd = SizeDistribution.from_file(tsv_path)
        self.assertEqual(csv_psd.size_um, (0.1, 0.2))
        self.assertEqual(tsv_psd.dndr_cm3, (2.0, 3.0))

    def test_netcdf_and_hdf5_inputs(self) -> None:
        try:
            import h5py
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("NetCDF/HDF5 optional dependencies are not installed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nc_path = root / "psd.nc"
            with Dataset(nc_path, "w") as dataset:
                dataset.createDimension("size", 2)
                size = dataset.createVariable("radius", "f8", ("size",))
                size.units = "nm"
                size.size_definition = "maximum_dimension_radius"
                size[:] = [100, 200]
                dndr = dataset.createVariable("number", "f8", ("size",))
                dndr.units = "cm-3"
                dndr[:] = [2, 3]
            nc_psd = SizeDistribution.from_netcdf(
                nc_path,
                size_variable="radius",
                dndr_variable="number",
            )

            h5_path = root / "psd.h5"
            with h5py.File(h5_path, "w") as handle:
                size = handle.create_dataset("radius", data=[0.1, 0.2])
                size.attrs["units"] = "um"
                size.attrs["size_definition"] = "volume_equivalent_sphere_radius"
                number = handle.create_dataset("number", data=[2, 3])
                number.attrs["units"] = "cm-3"
            h5_psd = SizeDistribution.from_hdf5(
                h5_path,
                size_dataset="radius",
                dndr_dataset="number",
            )
        self.assertEqual(nc_psd.size_um, (0.1, 0.2))
        self.assertEqual(nc_psd.size_definition, "maximum_dimension_radius")
        self.assertEqual(h5_psd.number_concentration_cm3, 5)

    def test_scheme_resolves_relative_psd_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "observed.csv").write_text(
                "size,dndr\n0.1,2\n0.2,3\n",
                encoding="utf-8",
            )
            config_path = root / "scheme.json"
            config_path.write_text(
                """
{
  "wavelengths": [0.55],
  "particles": [{
    "name": "cloud",
    "particle_type": "water_cloud",
    "size_distribution": {
      "file": "observed.csv",
      "size_column": "size",
      "dndr_column": "dndr"
    },
    "refractive_index": {"mode": "database"}
  }]
}
""".strip(),
                encoding="utf-8",
            )
            config = load_scheme(config_path)
        self.assertEqual(config.particles[0].size_distribution.dndr_cm3, (2.0, 3.0))


class ConservativeRemappingTests(unittest.TestCase):
    def test_full_coverage_remap_conserves_number(self) -> None:
        source = SizeDistribution([1, 2, 3, 4], [10, 20, 30, 40])
        remapped, report = source.remap([0.5, 1.5, 2.5, 3.5, 4.5])
        self.assertAlmostEqual(remapped.number_concentration_cm3, 100)
        self.assertAlmostEqual(report.outside_fraction, 0)

    def test_truncation_must_be_explicit_and_is_reported(self) -> None:
        source = SizeDistribution([1, 2, 3, 4], [10, 20, 30, 40])
        with self.assertRaisesRegex(ValueError, "truncation_policy"):
            source.remap([1.5, 2.5, 3.5])
        remapped, report = source.remap(
            [1.5, 2.5, 3.5],
            truncation_policy="truncate",
        )
        self.assertGreater(report.outside_fraction, 0)
        self.assertLess(remapped.number_concentration_cm3, 100)

    def test_size_definition_change_requires_validated_geometry(self) -> None:
        source = SizeDistribution([1, 2], [1, 1])
        with self.assertRaisesRegex(ValueError, "validated particle-specific"):
            source.convert_size_definition("maximum_dimension_radius")
        converted = source.convert_size_definition(
            "maximum_dimension_radius",
            converter=lambda values: [2 * value for value in values],
            geometry_source="validated_test_geometry",
        )
        self.assertEqual(converted.size_um, (2.0, 4.0))
        self.assertEqual(
            converted.metadata["geometry_source"],
            "validated_test_geometry",
        )


class BulkIntegrationTests(unittest.TestCase):
    def test_cm3_counts_and_m2_cross_sections_produce_m1(self) -> None:
        distribution = SizeDistribution([1, 2], [1, 2])
        result, report = integrate_arrays(
            distribution,
            [1, 2],
            extinction_cross_section_m2=[1e-12, 1e-12],
            scattering_cross_section_m2=[0.5e-12, 0.5e-12],
            asymmetry_factor=[0.5, 0.7],
        )
        self.assertAlmostEqual(result.extinction_coefficient, 3e-6)
        self.assertAlmostEqual(result.single_scattering_albedo, 0.5)
        self.assertAlmostEqual(result.asymmetry_factor, (0.5 + 2 * 0.7) / 3)
        self.assertAlmostEqual(result.number_concentration, 3)
        self.assertEqual(result.metadata["bulk_coefficient_unit"], "m-1")
        self.assertAlmostEqual(report.outside_fraction, 0)


if __name__ == "__main__":
    unittest.main()
