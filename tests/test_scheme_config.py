import unittest
from pathlib import Path

from zju_scatt_interface.config.scheme import Scheme, load_scheme


class SchemeConfigTests(unittest.TestCase):
    def test_range_expands_and_particle_is_validated(self):
        config = Scheme.from_mapping(
            {
                "name": "demo",
                "wavelength_unit": "um",
                "wavelengths": {"min": 0.5, "max": 0.7, "step": 0.1},
                "particles": [
                    {
                        "name": "ice",
                        "particle_type": "super_spheroid_ice",
                        "size_distribution": {
                            "size": [0.5, 1.0, 2.0],
                            "dndr": [2.0, 6.0, 2.0],
                            "size_unit": "um",
                        },
                        "refractive_index": {"mode": "fixed", "real": 1.4, "imaginary": 0},
                    }
                ],
            }
        )
        self.assertEqual(config.wavelengths_um, (0.5, 0.6, 0.7))
        self.assertEqual(config.particles[0].name, "ice")

    def test_example_config_loads(self):
        example = Path(__file__).parents[1] / "configs" / "bulk_scheme.example.py"
        config = load_scheme(example)
        self.assertEqual(len(config.particles), 2)
        self.assertGreater(len(config.wavelengths_um), 10)
        self.assertNotIn("mixing_fraction", config.to_dict()["particles"][0])
        self.assertNotIn("include_mixture", config.to_dict()["calculation"])

    def test_scheme_rejects_implicit_component_mixing(self):
        particle = {
            "name": "ice",
            "particle_type": "super_spheroid_ice",
            "mixing_fraction": 0.5,
            "size_distribution": {"size": [1], "dndr": [1]},
            "refractive_index": {"mode": "database_temperature", "temperature_k": 220},
        }
        with self.assertRaisesRegex(ValueError, "calculated independently"):
            Scheme.from_mapping(
                {"wavelengths": [0.55], "particles": [particle]}
            )
        particle.pop("mixing_fraction")
        with self.assertRaisesRegex(ValueError, 'combine'):
            Scheme.from_mapping(
                {
                    "wavelengths": [0.55],
                    "particles": [particle],
                    "calculation": {"include_mixture": True},
                }
            )

    def test_duplicate_component_names_are_rejected(self):
        particle = {
            "name": "same",
            "particle_type": "sphere",
            "size_distribution": {"size": [1], "dndr": [1]},
            "refractive_index": {"mode": "fixed", "real": 1.4, "imaginary": 0},
        }
        with self.assertRaisesRegex(ValueError, "unique"):
            Scheme.from_mapping(
                {"wavelengths": [0.55], "particles": [particle, particle]}
            )


if __name__ == "__main__":
    unittest.main()
