import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from zju_scatt_interface.cli.main import main
from zju_scatt_interface.config.particles import (
    DataStructure,
    ParameterRole,
    get_particle_profile,
    list_particle_profiles,
    normalize_parameter_name,
    validate_profile_parameters,
)
from zju_scatt_interface.sources.validation import inspect_source_file


class RegistryTests(unittest.TestCase):
    def test_all_eight_local_families_have_profiles(self) -> None:
        profiles = list_particle_profiles()
        self.assertEqual(len(profiles), 8)
        self.assertEqual(len({item.particle_type for item in profiles}), 8)

    def test_aliases_resolve_to_canonical_profiles(self) -> None:
        self.assertEqual(get_particle_profile("ice").particle_type, "super_spheroid_ice")
        self.assertEqual(
            get_particle_profile("black carbon").particle_type,
            "encapsulated_fractal_aggregates_black_carbon",
        )
        self.assertEqual(get_particle_profile("dust").particle_type, "super_spheroid")

    def test_parameter_aliases_normalize_without_losing_symbols(self) -> None:
        self.assertEqual(normalize_parameter_name("Df"), "df")
        self.assertEqual(normalize_parameter_name("Vf"), "vf")
        self.assertEqual(normalize_parameter_name("smoothness"), "roundness")
        self.assertEqual(normalize_parameter_name("alpha"), "aspect_ratio")
        self.assertEqual(normalize_parameter_name("RH"), "relative_humidity")

    def test_grid_and_wavelength_contracts_differ(self) -> None:
        dust = get_particle_profile("super_spheroid")
        ice = get_particle_profile("super_spheroid_ice")
        self.assertEqual(dust.data_structure, DataStructure.GRID_BASED)
        self.assertEqual(ice.data_structure, DataStructure.WAVELENGTH_BASED)
        self.assertEqual(
            dust.parameter("refractive_index_real").role,
            ParameterRole.OPTIONAL,
        )
        self.assertEqual(
            dust.default_wrapper_input_mode,
            "wavelength_to_refractive_index",
        )
        self.assertIn("refractive_index_real", dust.native_lookup_coordinates)
        self.assertEqual(
            ice.parameter("refractive_index_real").role,
            ParameterRole.DERIVED,
        )
        temperature = ice.parameter("temperature_k")
        self.assertEqual((temperature.minimum, temperature.maximum), (160.0, 270.0))
        self.assertEqual(temperature.grid_values, (160.0, 220.0, 270.0))

    def test_newest_black_carbon_release_coverage_is_registered(self) -> None:
        black_carbon = get_particle_profile("black_carbon")
        wavelength = black_carbon.parameter("wavelength")
        self.assertEqual((wavelength.minimum, wavelength.maximum), (0.3, 20.0))
        self.assertGreaterEqual(
            black_carbon.parameter("black_carbon_refractive_index_real").maximum,
            3.625,
        )
        self.assertLessEqual(
            black_carbon.parameter("hygroscopic_refractive_index_real").minimum,
            1.137,
        )

    def test_relative_humidity_uses_public_fraction_and_source_scale(self) -> None:
        parameter = get_particle_profile("sulfate").parameter("rh")
        self.assertEqual((parameter.minimum, parameter.maximum), (0.0, 0.99))
        self.assertEqual(parameter.source_scale, 100.0)

    def test_profile_validator_normalizes_aliases_and_accepts_intermediate_nodes(self) -> None:
        result = validate_profile_parameters(
            "ice",
            {
                "wl": [0.67, 12.0],
                "temperature_k": 200.0,
                "smoothness": 2.4,
                "alpha": 1.3,
            },
        )
        self.assertEqual(result["temperature"], 200.0)
        self.assertEqual(result["roundness"], 2.4)

    def test_profile_validator_rejects_derived_refractive_index(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not permit user input"):
            validate_profile_parameters(
                "ice",
                {
                    "wavelength": 0.67,
                    "temperature": 220.0,
                    "roundness": 2.5,
                    "aspect_ratio": 1.5,
                    "mr": 1.31,
                },
            )

    def test_grid_profile_accepts_wrapper_wavelength_without_native_index(self) -> None:
        result = validate_profile_parameters(
            "dust",
            {
                "wavelength": 0.55,
                "roundness": 2.0,
                "aspect_ratio": 1.0,
            },
        )
        self.assertNotIn("refractive_index_real", result)

    def test_grid_profile_rejects_partial_native_index_override(self) -> None:
        with self.assertRaisesRegex(ValueError, "complete native coordinate set"):
            validate_profile_parameters(
                "dust",
                {
                    "wavelength": 0.55,
                    "roundness": 2.0,
                    "aspect_ratio": 1.0,
                    "mr": 1.5,
                },
            )

    def test_cli_describe_lists_profiles(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["describe"])
        self.assertEqual(result, 0)
        self.assertIn("super_spheroid_ice", output.getvalue())

    def test_cli_describe_json_is_machine_readable(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["describe", "ice", "--json"])
        self.assertEqual(result, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["particle_type"], "super_spheroid_ice")
        self.assertEqual(data["data_structure"], "wavelength_based")

    def test_unknown_profile_is_an_actionable_cli_error(self) -> None:
        error = StringIO()
        with redirect_stderr(error):
            result = main(["describe", "not_a_particle"])
        self.assertEqual(result, 2)
        self.assertIn("Available particle types", error.getvalue())


class SourceInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from netCDF4 import Dataset  # noqa: F401
        except ImportError:
            self.skipTest("netCDF4 is not installed")

    def _make_ice_file(self, path: Path, *, version: str = "v1.0") -> None:
        from netCDF4 import Dataset

        with Dataset(path, "w") as dataset:
            dataset.dataset_name = "super_spheroid_ice"
            dataset.data_version = version
            dataset.createDimension("size", 1)
            dataset.createDimension("angle", 1)
            for name in (
                "wavelength",
                "temperature",
                "mr",
                "mi",
                "ssph_n",
                "ssph_asp",
            ):
                dataset.createVariable(name, "f8")[:] = 1.0
            for name in ("xsize_veq", "xsize_maxd"):
                dataset.createVariable(name, "f8", ("size",))[:] = [1.0]
            dataset.createVariable("sca_angle", "f8", ("angle",))[:] = [0.0]
            for name in ("cext", "ssa", "g"):
                dataset.createVariable(name, "f8", ("size",))[:] = [1.0]
            for name in ("p11", "p12", "p22", "p33", "p43", "p44"):
                dataset.createVariable(name, "f8", ("size", "angle"))[:] = [[1.0]]

    def test_valid_source_schema_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ice.nc"
            self._make_ice_file(path)
            result = inspect_source_file(path, "ice")
        self.assertTrue(result.valid)
        self.assertEqual(result.dataset_name, "super_spheroid_ice")

    def test_incompatible_major_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ice.nc"
            self._make_ice_file(path, version="v9.0")
            result = inspect_source_file(path, "ice")
        self.assertFalse(result.valid)
        self.assertIn("unsupported major version", result.errors[0])


if __name__ == "__main__":
    unittest.main()
