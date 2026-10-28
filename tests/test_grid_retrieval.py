"""Regression tests for wavelength-to-index retrieval (no network)."""

import contextlib
import io
import unittest
from itertools import product
from unittest import mock

import zju_scatt_interface.access.catalog as _domain_access_catalog
import zju_scatt_interface.access.metadata as _domain_access_metadata
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.errors as _domain_errors
import zju_scatt_interface.sources.coordinates as _domain_sources_coordinates
from zju_scatt_interface.optics.retrieval.grid import DEFAULT_INDEX_NOTICE


def dust_nodes():
    return [
        _domain_access_models.RemoteObject(
            f"Single_opt/super_spheroid/L1_super_spheroid_n_{shape}_asp_1.0_wl_nan_ref_{n}_{k}.nc",
            size=10,
        )
        for shape, n, k in product((1.4, 2.0), (1.4, 1.5), (0.001, 0.01))
    ]


def bc_nodes():
    return [
        _domain_access_models.RemoteObject(
            "Single_opt/encapsulated_fractal_aggregates_black_carbon/"
            f"L1_bc_df_2.0_ref_bc_{n}_{k}_hygro_{hn}_{hk}.nc",
            size=10,
        )
        for n, k, hn, hk in product((2.0, 2.2), (0.8, 0.9), (1.5, 1.55), (0.02, 0.03))
    ]


class GridRetrievalTests(unittest.TestCase):
    def test_duplicate_index_nodes_prefer_l15_before_neighbor_selection(self):
        original = dust_nodes()
        higher = [_domain_access_models.RemoteObject(obj.key.replace("/L1_", "/L1.5_")) for obj in original]
        for objects in (original + higher, higher + original):
            selected, _ = _domain_sources_coordinates.select_for_target_wavelength(objects, [1.5])
            self.assertEqual(len(selected), 8)
            self.assertTrue(all(obj.name.startswith("L1.5_") for obj in selected))

    def test_nearby_l1_beats_distant_l15_and_missing_corners_use_l1(self):
        original = dust_nodes()
        # Only one of the four nearby corners has a higher-level duplicate.
        higher = _domain_access_models.RemoteObject(original[0].key.replace("/L1_", "/L1.5_"))
        distant = _domain_access_models.RemoteObject(higher.key.replace("ref_1.4_", "ref_1.9_"))
        selected, _ = _domain_sources_coordinates.select_for_target_wavelength(original + [higher, distant], [1.5])
        self.assertEqual(len(selected), 8)
        self.assertIn(higher, selected)
        self.assertNotIn(original[0], selected)
        self.assertNotIn(distant, selected)
        self.assertEqual(sum(obj.name.startswith("L1.5_") for obj in selected), 1)

    def test_registry_aliases_do_not_mix_dust_with_ice_or_seasalt(self):
        self.assertTrue(_domain_access_metadata.particle_type_matches(dust_nodes()[0].key, "dust"))
        self.assertTrue(_domain_access_metadata.particle_type_matches(bc_nodes()[0].key, "black_carbon"))
        self.assertFalse(
            _domain_access_metadata.particle_type_matches(
                "Single_opt/coated_super_spheroid_seasalt/L1_seasalt.nc",
                "super_spheroid",
            )
        )
        self.assertFalse(
            _domain_access_metadata.particle_type_matches(
                "Single_opt/super_spheroid_ice/L1_ice.nc",
                "dust",
            )
        )

    def test_mixed_species_use_default_tables_and_keep_shape_series(self):
        sea = _domain_access_models.RemoteObject(
            "Single_opt/coated_super_spheroid_seasalt/L1_seasalt_wl_1.5_um_ref_1.4_0.001.nc"
        )
        selected, info = _domain_sources_coordinates.select_for_target_wavelength(
            dust_nodes() + bc_nodes() + [sea], [1.5]
        )
        self.assertEqual(len(selected), 25)
        self.assertEqual(len(info.refractive_index_resolutions), 2)
        self.assertIn(DEFAULT_INDEX_NOTICE, info.message)
        self.assertTrue(info.interpolation_required)
        self.assertFalse(info.interpolation_applied)
        for record in info.refractive_index_resolutions:
            self.assertTrue(record["used_default"])
            self.assertTrue(record["table_sources"])
            for path in record["table_relative_paths"].values():
                self.assertTrue(path.startswith("data/refractive_index/"))
                self.assertNotIn("/mnt/", path)
            self.assertEqual(record["wavelength_um"], 1.5)
        bc = info.refractive_index_resolutions[1]
        self.assertEqual(len(bc["target_indices"]), 4)
        self.assertEqual(len(bc["selected_index_nodes"]), 16)

    def test_explicit_dust_indices_bypass_default(self):
        selected, info = _domain_sources_coordinates.select_for_target_wavelength(
            dust_nodes(),
            [1.5],
            refractive_index_parameters={
                "dust": {"mr": 1.4, "mi": 0.001},
            },
        )
        self.assertEqual(len(selected), 2)
        self.assertFalse(info.refractive_index_resolutions[0]["used_default"])
        self.assertNotIn(DEFAULT_INDEX_NOTICE, info.message)
        self.assertFalse(info.interpolation_required)

    def test_partial_override_does_not_silently_use_default(self):
        with self.assertRaisesRegex(_domain_errors.ScattError, "complete native coordinate set"):
            _domain_sources_coordinates.select_for_target_wavelength(
                dust_nodes(),
                [1.5],
                refractive_index_parameters={"dust": {"mr": 1.4}},
            )

    def test_out_of_grid_is_an_error_and_sparse_grid_uses_existing_policy(self):
        with self.assertRaisesRegex(_domain_errors.ScattError, "outside the source interval"):
            _domain_sources_coordinates.select_for_target_wavelength(
                dust_nodes(),
                [1.5],
                refractive_index_parameters={"dust": {"mr": 1.8, "mi": 0.001}},
            )
        _, info = _domain_sources_coordinates.select_for_target_wavelength(dust_nodes()[1:], [1.5])
        self.assertIn(
            "inverse_distance_sparse",
            info.refractive_index_resolutions[0]["source_selection_methods"],
        )

    def test_raw_retrieval_without_wavelength_keeps_all_native_nodes(self):
        selected, info = _domain_sources_coordinates.select_for_target_wavelength(dust_nodes(), None)
        self.assertEqual(len(selected), 8)
        self.assertEqual(info.refractive_index_resolutions, ())

    def test_multiple_wavelengths_and_nearest_mode(self):
        selected, info = _domain_sources_coordinates.select_for_target_wavelength(
            dust_nodes(), [1.5, 1.6], mode="nearest"
        )
        self.assertEqual(len(info.refractive_index_resolutions), 2)
        self.assertEqual(len(selected), 2)

    def test_api_notice_and_provenance_survive_runtime_building(self):
        with (
            mock.patch.object(
                _domain_access_catalog, 'objects_from_args', return_value=(dust_nodes(), _domain_access_models.ScanStats())
            ),
            contextlib.redirect_stdout(io.StringIO()) as stream,
        ):
            result = _domain_access_retrieval.retrieve_sources(particle_types="dust", target_wavelengths=[1.5])
        self.assertIn(DEFAULT_INDEX_NOTICE, stream.getvalue())
        self.assertIn("relative to zju_scatt_interface/", stream.getvalue())
        self.assertIn(
            "data/refractive_index/Dust_refractive_index_statistics.csv", stream.getvalue()
        )
        self.assertEqual(len(result.objects), 8)
        self.assertEqual(len(result.wavelength_processing.refractive_index_resolutions), 1)

    def test_legacy_explicit_dust_targets_are_not_filtered_twice(self):
        with (
            mock.patch.object(
                _domain_access_catalog, 'objects_from_args', return_value=(dust_nodes(), _domain_access_models.ScanStats())
            ),
            contextlib.redirect_stdout(io.StringIO()) as stream,
        ):
            result = _domain_access_retrieval.retrieve_sources(
                particle_types="dust",
                target_wavelengths=[1.5],
                ref_real_targets=[1.45],
                ref_imag_targets=[0.005],
            )
        self.assertEqual(len(result.objects), 8)
        self.assertNotIn(DEFAULT_INDEX_NOTICE, stream.getvalue())

    def test_bc_explicit_override_is_preserved_by_public_api(self):
        override = {"bc_mr": 2.0, "bc_mi": 0.8, "hygro_mr": 1.5, "hygro_mi": 0.02}
        with (
            mock.patch.object(
                _domain_access_catalog, 'objects_from_args', return_value=(bc_nodes(), _domain_access_models.ScanStats())
            ),
            contextlib.redirect_stdout(io.StringIO()) as stream,
        ):
            result = _domain_access_retrieval.retrieve_sources(
                particle_types="encapsulated_fractal_aggregates_black_carbon",
                target_wavelengths=[1.5],
                refractive_index_parameters={"black_carbon": override},
            )
        self.assertEqual(len(result.objects), 1)
        self.assertFalse(
            result.wavelength_processing.refractive_index_resolutions[0]["used_default"]
        )
        self.assertNotIn(DEFAULT_INDEX_NOTICE, stream.getvalue())

    def test_partial_legacy_index_target_is_rejected(self):
        with mock.patch.object(
            _domain_access_catalog, 'objects_from_args', return_value=(dust_nodes(), _domain_access_models.ScanStats())
        ):
            with self.assertRaisesRegex(_domain_errors.ScattError, "require both"):
                _domain_access_retrieval.retrieve_sources(
                    particle_types="super_spheroid",
                    target_wavelengths=[1.5],
                    ref_real_targets=[1.45],
                )

    def test_default_tables_do_not_extrapolate_spectrally(self):
        with self.assertRaisesRegex(_domain_errors.ScattError, "outside"):
            _domain_sources_coordinates.select_for_target_wavelength(dust_nodes(), [50.0])

    def test_unsupported_series_are_reported_without_extrapolation(self):
        unsupported = [
            _domain_access_models.RemoteObject(
                obj.key.replace("df_2.0", "df_2.1").replace("_0.9_hygro", "_0.85_hygro"),
                size=10,
            )
            for obj in bc_nodes()
        ]
        selected, info = _domain_sources_coordinates.select_for_target_wavelength(bc_nodes() + unsupported, [1.5])
        self.assertEqual(len(selected), 16)
        record = info.refractive_index_resolutions[0]
        self.assertEqual(len(record["unsupported_series"]), 1)
        self.assertIn("outside the source interval", record["unsupported_series"][0]["reason"])
        self.assertIn("omitted", info.message)


if __name__ == "__main__":
    unittest.main()
