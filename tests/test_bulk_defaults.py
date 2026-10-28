import unittest

from zju_scatt_interface.bulk.defaults import default_bulk_assumptions
from zju_scatt_interface.config.particles import list_particle_profiles


class ReferenceBulkDefaultsTests(unittest.TestCase):
    def test_every_species_has_normalized_reference_psd(self):
        for profile in list_particle_profiles():
            settings = default_bulk_assumptions(profile.particle_type)
            self.assertEqual(settings["psd"]["number_concentration_cm3"], 1)
            if profile.particle_type in {"sphere_water_cloud", "super_spheroid_ice"}:
                self.assertEqual(settings["psd"]["type"], "gamma")
                self.assertGreater(settings["psd"]["effective_radius_um"], 0)
                self.assertTrue(0 < settings["psd"]["effective_variance"] < 0.5)
            else:
                self.assertEqual(settings["psd"]["type"], "lognormal")
                self.assertGreater(settings["psd"]["rg_um"], 0)
                self.assertGreater(settings["psd"]["sigma_g"], 1)
            self.assertEqual(settings["psd"]["size_definition"], "volume_equivalent_sphere_radius")
            self.assertEqual(settings["psd_reference"]["doi"], "10.1175/BAMS-D-25-0258.1")

    def test_species_parameters_match_bi_2026_table_2(self):
        expected = {"dust": (0.5, 2.0), "bc": (0.1, 1.5), "sea_salt": (0.1, 2.0),
                    "sulfate": (0.07, 1.6), "nitrate": (0.07, 1.6), "oc": (0.02, 1.8)}
        for name, pair in expected.items():
            psd = default_bulk_assumptions(name)["psd"]
            self.assertEqual((psd["rg_um"], psd["sigma_g"]), pair)
        for name, pair in {"water_cloud": (10, 1/3), "ice": (30, 0.1)}.items():
            psd = default_bulk_assumptions(name)["psd"]
            self.assertEqual((psd["effective_radius_um"], psd["effective_variance"]), pair)

    def test_legacy_preset_remains_reproducible(self):
        self.assertEqual(default_bulk_assumptions("water_cloud", preset="reference_v1")["psd"]["type"], "lognormal")
        self.assertEqual(default_bulk_assumptions("dust", preset="reference_v1")["psd"]["sigma_g"], 1.8)
        with self.assertRaises(ValueError):
            default_bulk_assumptions("dust", preset="unknown")

    def test_dust_averages_all_native_aspects_at_fixed_n(self):
        members = default_bulk_assumptions("dust")["shape_ensemble"]
        self.assertEqual(len(members), 11)
        self.assertEqual([m["parameters"]["ssph_asp"] for m in members],
                         [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.2, 1.4, 1.6, 1.8, 2])
        self.assertTrue(all(m["parameters"]["ssph_n"] == 2.6 for m in members))
        self.assertAlmostEqual(sum(m["weight"] for m in members), 1)

    def test_ice_shapes_and_temperature(self):
        settings = default_bulk_assumptions("ice")
        self.assertEqual(settings["parameters"], {"temperature": 220})
        self.assertEqual([(m["parameters"]["ssph_n"], m["parameters"]["ssph_asp"])
                          for m in settings["shape_ensemble"]], [(2.5, 1.75), (2.5, 2), (2.75, 2)])
        self.assertAlmostEqual(sum(m["weight"] for m in settings["shape_ensemble"]), 1)

    def test_bc_native_scheme_and_requested_fraction(self):
        settings = default_bulk_assumptions("bc")
        self.assertEqual(settings["parameters"],
                         {"df": 2.1, "vf": 0.3, "database_type": "wavelength", "ri_scheme": "v1.2.1"})
        self.assertIn("nearest", settings["vf_selection"])

    def test_bc_resolves_nearest_common_native_fraction_with_stable_ties(self):
        import tempfile
        from pathlib import Path
        try:
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("netCDF4 is required for native vf fixtures")

        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory)/f"source_{i}.nc" for i in range(2)]
            for path, values in zip(paths, ([0.1, 0.25, 0.374], [0.1, 0.25, 0.5])):
                with Dataset(path, "w") as ds:
                    ds.createDimension("vf", 3)
                    ds.createVariable("vf", "f8", ("vf",))[:] = values
            settings = default_bulk_assumptions("bc", source_paths=paths)
            self.assertEqual(settings["requested_vf"], 0.3)
            self.assertEqual(settings["used_native_vf"], 0.25)
            self.assertEqual(settings["parameters"]["vf"], 0.25)
            self.assertEqual(default_bulk_assumptions("bc")["parameters"]["vf"], 0.3)
            for path in paths:
                with Dataset(path, "a") as ds:
                    ds.variables["vf"][:] = [0.1, 0.2, 0.4]
            self.assertEqual(default_bulk_assumptions("bc", source_paths=paths)["used_native_vf"], 0.2)
            with Dataset(paths[1], "a") as ds:
                ds.variables["vf"][:] = [0.5, 0.7, 0.9]
            with self.assertRaisesRegex(ValueError, "no common native vf"):
                default_bulk_assumptions("bc", source_paths=paths)

    def test_humidity_applies_only_where_exposed_and_salt_uses_crystallization(self):
        for name in ("sea_salt", "sulfate", "nitrate", "oc"):
            self.assertEqual(default_bulk_assumptions(name)["parameters"]["relative_humidity"], 0.6)
        self.assertEqual(default_bulk_assumptions("sea_salt")["parameters"]["humidity_branch"], "crystallization")
        self.assertNotIn("relative_humidity", default_bulk_assumptions("water_cloud")["parameters"])
        settings = default_bulk_assumptions("dust")
        settings["shape_ensemble"].clear()
        self.assertEqual(len(default_bulk_assumptions("dust")["shape_ensemble"]), 11)


if __name__ == "__main__":
    unittest.main()
