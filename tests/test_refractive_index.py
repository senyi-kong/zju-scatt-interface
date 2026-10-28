import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.optics.refractive_index import (
    RefractiveIndexTable,
    default_refractive_index_paths,
    resolve_grid_refractive_indices,
    wavelength_to_um,
)


class WavelengthConversionTests(unittest.TestCase):
    def test_supported_units_normalize_to_um(self) -> None:
        self.assertAlmostEqual(wavelength_to_um(550.0, "nm"), 0.55)
        self.assertAlmostEqual(wavelength_to_um(0.55, "um"), 0.55)
        self.assertAlmostEqual(wavelength_to_um(1000.0, "cm-1"), 10.0)
        self.assertAlmostEqual(wavelength_to_um(1000.0, "cm^-1"), 10.0)

    def test_invalid_wavelength_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            wavelength_to_um(0.0, "um")


class RefractiveIndexTableTests(unittest.TestCase):
    def test_linear_interpolation_and_no_extrapolation(self) -> None:
        table = RefractiveIndexTable(
            wavelength_um=(0.5, 1.0),
            real=(1.5, 1.3),
            imaginary=(0.01, 0.03),
            source="test",
        )
        index = table.interpolate(0.75)
        self.assertAlmostEqual(index.real, 1.4)
        self.assertAlmostEqual(index.imaginary, 0.02)
        with self.assertRaisesRegex(ValueError, "outside refractive-index table coverage"):
            table.interpolate(1.1)

    def test_csv_loader_detects_nm_and_mr_mi_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.csv"
            path.write_text(
                "wavelength_nm,mr,mi\n500,1.5,0.01\n1000,1.3,0.03\n",
                encoding="utf-8",
            )
            table = RefractiveIndexTable.from_csv(path)
        self.assertEqual(table.wavelength_um, (0.5, 1.0))
        self.assertAlmostEqual(table.interpolate(0.75).real, 1.4)

    def test_csv_loader_detects_project_statistics_columns(self) -> None:
        path = default_refractive_index_paths("dust")["particle"]
        table = RefractiveIndexTable.from_csv(path)
        self.assertGreater(len(table.wavelength_um), 2)
        self.assertGreater(table.real[0], 0.0)
        self.assertGreaterEqual(table.imaginary[0], 0.0)

    def test_duplicate_wavelength_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            RefractiveIndexTable(
                wavelength_um=(0.5, 0.5),
                real=(1.5, 1.4),
                imaginary=(0.01, 0.02),
            )

    def test_packaged_material_reference_tables_load(self) -> None:
        root = default_refractive_index_paths("dust")["particle"].parent
        for material in ("Nitrate", "Organic_carbon", "Sea_salt", "Sulfate", "Water"):
            with self.subTest(material=material):
                table = RefractiveIndexTable.from_csv(
                    root / (material + "_refractive_index_used.csv")
                )
                self.assertGreater(len(table.wavelength_um), 2)
                self.assertAlmostEqual(table.minimum_wavelength_um,
                                       0.3 if material == "Water" else 0.2)

    def test_ice_reference_requires_explicit_temperature_columns(self) -> None:
        root = default_refractive_index_paths("ice")["particle"].parent
        path = root / "Ice_refractive_index_used.csv"
        with self.assertRaisesRegex(ValueError, "cannot identify real"):
            RefractiveIndexTable.from_csv(path)
        for temperature in range(160, 271, 10):
            with self.subTest(temperature=temperature):
                table = RefractiveIndexTable.from_csv(
                    path, real_column="n({})".format(temperature),
                    imaginary_column="k({})".format(temperature),
                )
                self.assertAlmostEqual(table.minimum_wavelength_um, 0.0443)
                self.assertGreater(table.interpolate(0.55).real, 1.0)

    def test_revised_statistics_are_used_at_repaired_wavelengths(self) -> None:
        # Accepted September 2026 repairs; guard against packaging an older table.
        path = default_refractive_index_paths("black_carbon")["black_carbon"].with_name("Black_carbon_refractive_index_statistics.csv")
        self.assertAlmostEqual(RefractiveIndexTable.from_csv(path).interpolate(0.35).real, 1.5777745784420405)

    def test_used_bc_tables_default_to_v121_and_allow_v122(self):
        point = resolve_grid_refractive_indices("black_carbon", [1.5])[0]
        self.assertAlmostEqual(point.values["black_carbon_refractive_index_real"], 2.083)
        self.assertAlmostEqual(point.values["black_carbon_refractive_index_imaginary"], 0.8644)
        self.assertAlmostEqual(point.values["hygroscopic_refractive_index_real"], 1.51)
        self.assertAlmostEqual(point.values["hygroscopic_refractive_index_imaginary"], 0.02254)
        point = resolve_grid_refractive_indices("black_carbon", [1.5], ri_scheme="v1.2.2")[0]
        self.assertAlmostEqual(point.values["black_carbon_refractive_index_real"], 1.915)
        self.assertAlmostEqual(point.values["black_carbon_refractive_index_imaginary"], 0.8371)


class GridResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = RefractiveIndexTable(
            wavelength_um=(0.5, 1.0),
            real=(1.5, 1.3),
            imaginary=(0.01, 0.03),
            source="particle.csv",
        )

    def test_dust_wavelength_resolves_external_table_to_native_coordinates(self) -> None:
        result = resolve_grid_refractive_indices(
            "dust",
            [750.0],
            wavelength_unit="nm",
            parameters={},
            tables={"particle": self.table},
        )[0]
        self.assertEqual(result.input_mode, "wavelength_to_refractive_index")
        self.assertAlmostEqual(result.wavelength_um, 0.75)
        self.assertAlmostEqual(result.values["refractive_index_real"], 1.4)
        self.assertAlmostEqual(result.values["refractive_index_imaginary"], 0.02)

    def test_black_carbon_resolves_two_external_material_tables(self) -> None:
        coating = RefractiveIndexTable(
            wavelength_um=(0.5, 1.0),
            real=(1.4, 1.35),
            imaginary=(0.0, 0.01),
            source="coating.csv",
        )
        result = resolve_grid_refractive_indices(
            "black_carbon",
            [0.75],
            tables={"black_carbon": self.table, "hygroscopic": coating},
        )[0]
        self.assertAlmostEqual(
            result.values["black_carbon_refractive_index_real"],
            1.4,
        )
        self.assertAlmostEqual(
            result.values["hygroscopic_refractive_index_real"],
            1.375,
        )
        self.assertEqual(set(result.sources), {"black_carbon", "hygroscopic"})

    def test_explicit_native_override_does_not_require_a_table(self) -> None:
        result = resolve_grid_refractive_indices(
            "dust",
            [0.55],
            parameters={
                "mr": 1.45,
                "mi": 0.01,
            },
        )[0]
        self.assertEqual(result.input_mode, "explicit_refractive_index")
        self.assertEqual(result.values["refractive_index_real"], 1.45)

    def test_partial_native_override_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Incomplete explicit"):
            resolve_grid_refractive_indices(
                "dust",
                [0.55],
                parameters={"mr": 1.45},
            )

    def test_packaged_dust_default_is_used_without_explicit_table(self) -> None:
        result = resolve_grid_refractive_indices("dust", [0.55])[0]
        self.assertEqual(result.input_mode, "wavelength_to_refractive_index")
        self.assertIn("Dust_refractive_index_statistics.csv", result.sources["particle"])

    def test_packaged_black_carbon_defaults_are_complete(self) -> None:
        result = resolve_grid_refractive_indices("black_carbon", [0.55])[0]
        self.assertEqual(set(result.sources), {"black_carbon", "hygroscopic"})
        self.assertIn(
            "Black_carbon_refractive_index_used_v1.2.1.csv",
            result.sources["black_carbon"],
        )
        self.assertIn(
            "Hygroscopic_material_for_black_carbon_refractive_index_used.csv",
            result.sources["hygroscopic"],
        )

    def test_default_paths_use_canonical_profile_and_material_keys(self) -> None:
        dust = default_refractive_index_paths("dust")
        black_carbon = default_refractive_index_paths("black_carbon")
        ice = default_refractive_index_paths("ice")
        sea_salt = default_refractive_index_paths("sea_salt")
        self.assertEqual(set(dust), {"particle"})
        self.assertEqual(dust["particle"].name, "Dust_refractive_index_statistics.csv")
        self.assertEqual(set(black_carbon), {"black_carbon", "hygroscopic"})
        self.assertEqual(
            ice["particle"].name,
            "Ice_refractive_index_statistics_extend100um.csv",
        )
        self.assertEqual(
            sea_salt["particle"].name,
            "Sea_salt_refractive_index_statistics.csv",
        )

    def test_every_packaged_default_path_exists(self) -> None:
        for particle_type in ("dust", "black_carbon", "ice", "sea_salt"):
            for path in default_refractive_index_paths(particle_type).values():
                self.assertTrue(path.is_file(), path)


if __name__ == "__main__":
    unittest.main()
