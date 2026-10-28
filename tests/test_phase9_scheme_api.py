import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.config.scheme import (
    BlackCarbonComponent,
    BlackCarbonRefractiveIndex,
    DustComponent,
    FixedRefractiveIndex,
    HygroscopicSphereComponent,
    IceComponent,
    NitrateComponent,
    OrganicCarbonComponent,
    Scheme,
    SchemeOutput,
    SeaSaltComponent,
    SulfateComponent,
    TableRefractiveIndex,
    WaterCloudComponent,
    migrate_scheme_mapping,
)


class TypedSchemeTests(unittest.TestCase):
    def test_python_objects_and_normalized_dictionary_round_trip(self):
        ice = IceComponent(
            "ice",
            temperature_k=220,
            size=[1.0, 2.0, 4.0],
            dndr=[10.0, 20.0, 5.0],
            roundness={"values": [2.0, 2.5], "weights": [0.4, 0.6]},
            aspect_ratio=1.0,
        )
        cloud = WaterCloudComponent(
            "cloud",
            size=[0.1, 1.0, 10.0],
            dndr=[100.0, 50.0, 1.0],
        )
        scheme = Scheme(
            name="typed",
            wavelengths_um=(0.55, 0.67),
            particles=(ice, cloud),
            output_settings=SchemeOutput(
                "typed.h5",
                "hdf5",
                compression_level=6,
                chunk_wavelength=1,
            ),
        )
        normalized = scheme.to_dict()
        restored = Scheme.from_dict(normalized)

        self.assertEqual(restored.to_dict(), normalized)
        self.assertEqual(restored.schema_version, "1.0")
        self.assertEqual(restored.output_settings.format, "hdf5")
        self.assertEqual(
            restored.particles[0].size_distribution.size_definition,
            "volume_equivalent_sphere_radius",
        )

    def test_external_function_arrays_are_passed_without_executing_config_code(self):
        def observed_psd():
            return [0.1, 0.3, 1.0], [5.0, 20.0, 2.0]

        radius, concentration = observed_psd()
        component = WaterCloudComponent(
            "observed_cloud",
            size=radius,
            dndr=concentration,
        )
        self.assertEqual(component.size_distribution.size_um, (0.1, 0.3, 1.0))
        self.assertEqual(
            component.size_distribution.dndr_cm3, (5.0, 20.0, 2.0)
        )

    def test_all_typed_particle_families_expose_only_relevant_inputs(self):
        common = {"size": [0.1, 1.0], "dndr": [1.0, 2.0]}
        components = [
            IceComponent("ice", temperature_k=250, roundness=2.0, **common),
            SeaSaltComponent("salt", relative_humidity=0.8, **common),
            DustComponent(
                "dust",
                refractive_index=FixedRefractiveIndex(1.5, 0.01),
                roundness=2.5,
                aspect_ratio=1.5,
                **common,
            ),
            BlackCarbonComponent(
                "bc",
                df=2.4,
                vf=0.2,
                refractive_index=BlackCarbonRefractiveIndex(
                    1.85, 0.55, 1.4, 0.05
                ),
                **common,
            ),
            HygroscopicSphereComponent(
                "sulfate",
                material="sulfate",
                relative_humidity=0.5,
                **common,
            ),
            NitrateComponent(
                "nitrate", relative_humidity=0.5, **common
            ),
            OrganicCarbonComponent(
                "organic", relative_humidity=0.5, **common
            ),
            SulfateComponent(
                "typed_sulfate", relative_humidity=0.5, **common
            ),
            WaterCloudComponent("cloud", **common),
        ]
        self.assertEqual(
            [component.particle_type for component in components],
            [
                "super_spheroid_ice",
                "coated_super_spheroid_seasalt",
                "super_spheroid",
                "encapsulated_fractal_aggregates_black_carbon",
                "sphere_sulfate",
                "sphere_nitrate",
                "sphere_organic_carbon",
                "sphere_sulfate",
                "sphere_water_cloud",
            ],
        )
        with self.assertRaisesRegex(ValueError, "material must"):
            HygroscopicSphereComponent(
                "bad", material="dust", relative_humidity=0.5, **common
            )

    def test_migration_and_all_wavelength_units(self):
        legacy = {
            "name": "legacy",
            "wavelength_unit": "cm-1",
            "wavelength": [10_000, 20_000],
            "components": [
                {
                    "name": "cloud",
                    "particle_type": "water_cloud",
                    "psd": {
                        "r": [100, 1000],
                        "dNdr": [1, 2],
                        "size_unit": "nm",
                    },
                    "refractive_index": {"mode": "database"},
                }
            ],
            "output": "legacy.nc",
        }
        migrated = migrate_scheme_mapping(legacy)
        scheme = Scheme.from_dict(migrated)
        self.assertEqual(scheme.wavelengths_um, (0.5, 1.0))
        self.assertEqual(
            scheme.particles[0].size_distribution.size_um, (0.1, 1.0)
        )
        self.assertEqual(scheme.output_settings.format, "netcdf4")

        nanometres = dict(migrated)
        nanometres["wavelength_unit"] = "nm"
        nanometres["wavelengths"] = [500, 1000]
        self.assertEqual(
            Scheme.from_dict(nanometres).wavelengths_um, (0.5, 1.0)
        )

    def test_future_schema_is_rejected_and_table_paths_resolve(self):
        with self.assertRaisesRegex(ValueError, "unsupported scheme"):
            Scheme.from_dict({"schema_version": "2.0"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table = root / "ri.csv"
            table.write_text(
                "wavelength_um,mr,mi\n0.5,1.5,0.01\n", encoding="utf-8"
            )
            value = {
                "schema_version": "1.0",
                "name": "table",
                "wavelengths": [0.5],
                "particles": [
                    {
                        "name": "dust",
                        "particle_type": "super_spheroid",
                        "size_distribution": {
                            "size": [0.1],
                            "dndr": [1.0],
                        },
                        "refractive_index": {
                            "mode": "table",
                            "file": "ri.csv",
                        },
                    }
                ],
            }
            scheme = Scheme.from_dict(value, base_dir=root)
        self.assertEqual(
            scheme.particles[0].refractive_index["file"], str(table)
        )

    def test_typed_scheme_validate_compiles_particle_specific_queries(self):
        cloud = WaterCloudComponent(
            "cloud", size=[0.1, 1.0], dndr=[1.0, 2.0]
        )
        scheme = Scheme("validate", (0.55,), (cloud,))
        queries = scheme.validate()
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].particle_type, "sphere_water_cloud")

    def test_table_index_typed_object(self):
        value = TableRefractiveIndex("dust.csv").to_dict()
        self.assertEqual(
            value, {"mode": "table", "file": "dust.csv"}
        )


if __name__ == "__main__":
    unittest.main()
