import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from zju_scatt_interface.cli.main import main
from zju_scatt_interface.config.reference import scheme_reference
from zju_scatt_interface.config.scheme import load_scheme

PROJECT = Path(__file__).parents[1]
RECIPES = PROJECT / "configs" / "recipes"


class Phase10ReferenceAndRecipeTests(unittest.TestCase):
    def test_reference_covers_all_profiles_and_scientific_rules(self):
        reference = scheme_reference()
        profiles = {
            item["particle_type"]: item
            for item in reference["particle_profiles"]
        }
        self.assertEqual(reference["schema_version"], "1.0")
        self.assertEqual(len(profiles), 8)
        self.assertEqual(
            profiles["encapsulated_fractal_aggregates_black_carbon"][
                "data_structure"
            ],
            "grid_based",
        )
        self.assertEqual(
            profiles["super_spheroid"]["data_structure"], "grid_based"
        )
        self.assertEqual(
            reference["units"]["wavenumber_conversion"],
            "wavelength_um = 10000 / wavenumber_cm-1",
        )
        self.assertIn(
            "maximum_dimension_radius", reference["size_definitions"]
        )

    def test_filtered_reference_is_canonical(self):
        reference = scheme_reference("ice")
        self.assertEqual(len(reference["particle_profiles"]), 1)
        self.assertEqual(
            reference["particle_profiles"][0]["particle_type"],
            "super_spheroid_ice",
        )

    def test_cli_schema_prints_and_writes_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "reference.json"
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(
                    [
                        "bulk-opt",
                        "schema",
                        "--particle-type",
                        "sea_salt",
                        "--output",
                        str(output),
                        "--json",
                    ]
                )
            written = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(status, 0, stderr.getvalue())
        self.assertEqual(json.loads(stdout.getvalue()), written)
        self.assertEqual(
            written["particle_profiles"][0]["particle_type"],
            "coated_super_spheroid_seasalt",
        )

    def test_all_particle_recipes_validate(self):
        expected = {
            "black_carbon_bulk.json": (1, 4),
            "dust_bulk.json": (1, 5),
            "sea_salt_bulk.json": (1, 7),
            "ice_multi_temperature_bulk.json": (3, 4),
        }
        for name, (component_count, wavelength_count) in expected.items():
            with self.subTest(recipe=name):
                scheme = load_scheme(RECIPES / name)
                queries = scheme.validate()
                self.assertEqual(len(scheme.particles), component_count)
                self.assertEqual(
                    len(scheme.wavelengths_um), wavelength_count
                )
                self.assertEqual(len(queries), component_count)

    def test_release_documents_and_recipes_validate(self):
        # Consolidated release docs replace the earlier per-topic documents.
        # Check executable examples, links and API contracts with the same
        # offline validator maintainers run, rather than frozen prose snippets.
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "docs_check.json"
            completed = subprocess.run(
                [sys.executable, str(PROJECT / "tools/docs/verify_release_docs.py"),
                 "--report", str(report)],
                cwd=PROJECT, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "passed")
            self.assertTrue(result["source_unchanged_during_checks"])


if __name__ == "__main__":
    unittest.main()
