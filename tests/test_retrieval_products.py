"""End-to-end derived NetCDF tests using small local native fixtures."""

import argparse
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import zju_scatt_interface.access.catalog as _domain_access_catalog
import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.requests as _domain_access_requests
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.cli.arguments as _domain_cli_arguments
import zju_scatt_interface.optics.retrieval.workflow as _domain_optics_retrieval_workflow
import zju_scatt_interface.sources.coordinates as _domain_sources_coordinates
from tests.test_adapters import create_l1
from zju_scatt_interface.optics.interpolation import (
    InterpolatedOpticalProduct,
    InterpolationProvenance,
    write_interpolated_optics_netcdf,
)
from zju_scatt_interface.optics.models import SingleParticleOptics
from zju_scatt_interface.optics.retrieval.workflow import interpolate_downloaded_particle_series


class RetrievalProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def bc_sources(self, wavelengths=(1.0, 2.0)):
        sources = []
        family = "encapsulated_fractal_aggregates_black_carbon"
        for wavelength in wavelengths:
            name = f"L1_{family}_df_1.80_wl_{wavelength:.3f}_um_ref_bc_2.0_0.9_hygro_1.51_0.02_v1.2.1_20260616.nc"
            path = self.root / family / name
            create_l1(path, wavelength=wavelength, df=True, vf=[0.1, 0.5])
            sources.append(
                (_domain_access_models.RemoteObject(f"Single_opt/{family}/{name}", path.stat().st_size), path)
            )
        return sources

    def test_all_sphere_species_support_native_wavelength_interpolation(self):
        from zju_scatt_interface.optics.retrieval.native import verify_native_schema

        for family in ("sphere_sulfate", "sphere_nitrate", "sphere_organic_carbon", "sphere_water_cloud"):
            with self.subTest(family=family):
                sources = []
                for wavelength in (1.0, 2.0):
                    name = f"L1_{family}_wl_{wavelength}_um_ref_1.5_0.01.nc"
                    path = self.root / family / name
                    create_l1(path, wavelength=wavelength)
                    sources.append((_domain_access_models.RemoteObject(f"Single_opt/{family}/{name}"), path))
                _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
                results = interpolate_downloaded_particle_series(
                    sources, [1.5], processing, self.root / "derived"
                )
                self.assertEqual(len(results), 1)
                self.assertTrue(verify_native_schema(results[0].path, sources[0][1]))

    def test_bc_non_native_wavelength_creates_values_and_reuses_products(self):
        from netCDF4 import Dataset

        sources = self.bc_sources()
        _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
        self.assertEqual(processing.refractive_index_resolutions[0]["ri_scheme"], "v1.2.1")
        output = self.root / "derived"
        results = interpolate_downloaded_particle_series(sources, [1.5], processing, output)
        self.assertEqual(len(results), 1)
        for result in results:
            self.assertEqual(result.status, "created")
            with Dataset(result.path) as ds:
                self.assertAlmostEqual(float(ds.variables["wavelength"][:]), 1.5)
                self.assertTrue(
                    any(math.isfinite(value) for value in ds.variables["cext"][:].reshape(-1))
                )
                self.assertEqual(len(ds.dimensions["vf"]), 2)
                self.assertEqual(ds.interpolation_method, "multilinear")
                self.assertIn("v1.2.1", ds.interpolation_provenance_json)
        reused = interpolate_downloaded_particle_series(sources, [1.5], processing, output)
        self.assertTrue(all(result.status == "skipped" for result in reused))

    def test_exact_bc_native_wavelength_does_not_create_unneeded_product(self):
        sources = self.bc_sources((1.5,))
        _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
        self.assertFalse(processing.interpolation_required)
        self.assertEqual(
            interpolate_downloaded_particle_series(
                sources, [1.5], processing, self.root / "derived"
            ),
            [],
        )

    def test_dust_defaults_create_physical_product_with_index_provenance(self):
        from netCDF4 import Dataset

        sources = []
        for n in (1.4, 1.5):
            for k in (0.001, 0.01):
                name = f"L1_super_spheroid_n_2.0_asp_1.0_wl_nan_ref_{n}_{k}.nc"
                path = self.root / "super_spheroid" / name
                create_l1(path, wavelength=None)
                sources.append(
                    (
                        _domain_access_models.RemoteObject(
                            "Single_opt/super_spheroid/" + name, path.stat().st_size
                        ),
                        path,
                    )
                )
        # Legacy cached downloads may contain both levels. They must produce
        # one result using the preferred node, even without a fresh download.
        import shutil

        lower_obj, lower_path = sources[0]
        higher_path = lower_path.with_name(lower_path.name.replace("L1_", "L1.5_", 1))
        shutil.copyfile(lower_path, higher_path)
        higher_obj = _domain_access_models.RemoteObject(lower_obj.key.replace("/L1_", "/L1.5_", 1))
        sources.append((higher_obj, higher_path))
        _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
        results = interpolate_downloaded_particle_series(
            sources, [1.5], processing, self.root / "derived"
        )
        self.assertEqual(len(results), 1)
        self.assertIn(higher_path, results[0].source_paths)
        self.assertNotIn(lower_path, results[0].source_paths)
        with Dataset(results[0].path) as ds:
            self.assertAlmostEqual(ds.target_wavelength_um, 1.5)
            self.assertNotIn("wavelength", ds.variables)  # Native fixture has none.
            self.assertAlmostEqual(
                json.loads(ds.target_refractive_indices_json)["refractive_index_real"],
                1.4662016426740325,
            )
            provenance = json.loads(ds.interpolation_provenance_json)
            self.assertIn("Dust_refractive_index_statistics.csv", json.dumps(provenance))

    def test_seasalt_non_native_wavelength_preserves_humidity_branches(self):
        sources = []
        for wavelength in (1.0, 2.0):
            name = f"L1_coated_super_spheroid_seasalt_wl_{wavelength}_um_ref_1.5_0.01_water_1.3_0.001.nc"
            path = self.root / "coated_super_spheroid_seasalt" / name
            create_l1(path, wavelength=wavelength, rh=[-50.0, 0.0, 50.0])
            sources.append(
                (
                    _domain_access_models.RemoteObject(
                        "Single_opt/coated_super_spheroid_seasalt/" + name, path.stat().st_size
                    ),
                    path,
                )
            )
        processing = _domain_access_models.WavelengthProcessing(
            target_wavelengths_um=(1.5,), interpolation_required=True
        )
        results = interpolate_downloaded_particle_series(
            sources, [1.5], processing, self.root / "derived"
        )
        self.assertEqual(len(results), 1)
        from netCDF4 import Dataset

        with Dataset(results[0].path) as dataset:
            self.assertEqual(dataset.variables["rh"][:].tolist(), [-50.0, 0.0, 50.0])
            self.assertEqual(dataset.variables["cext"].dimensions, ("rh", "xsize_veq"))

    def test_enabled_option_materializes_values_while_disabled_only_selects(self):
        sources = self.bc_sources()
        _, processing = _domain_sources_coordinates.select_for_target_wavelength([obj for obj, _ in sources], [1.5])
        downloads = [_domain_access_models.DownloadResult(obj, path, "skipped") for obj, path in sources]
        runtime = argparse.Namespace(
            apply_interpolation=False,
            particle_type=["black_carbon"],
            output_dir=self.root,
            interpolation_output_dir=self.root / "derived",
            target_tolerance=1e-9,
            overwrite=False,
        )
        info, results = _domain_optics_retrieval_workflow.apply_downloaded_wavelength_interpolation(
            runtime, processing, downloads
        )
        self.assertEqual(results, [])
        self.assertFalse(info.interpolation_applied)
        runtime.apply_interpolation = True
        info, results = _domain_optics_retrieval_workflow.apply_downloaded_wavelength_interpolation(
            runtime, processing, downloads
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(info.interpolation_applied)

    def test_export_retains_cross_section_unit(self):
        from netCDF4 import Dataset

        optics = SingleParticleOptics(
            sizes=[1.0], extinction_cross_section=[2.0], cross_section_unit="um2"
        )
        provenance = InterpolationProvenance("exact", "super_spheroid", {}, {}, {}, [], [1.0], [])
        product = InterpolatedOpticalProduct("super_spheroid", {}, optics, provenance)
        output = write_interpolated_optics_netcdf(product, self.root / "units.nc")
        with Dataset(output) as dataset:
            self.assertEqual(dataset.variables["extinction_cross_section"].units, "um2")

    def test_public_api_honors_interpolation_switch_and_destination(self):
        sources = self.bc_sources()
        downloads = [_domain_access_models.DownloadResult(obj, path, "skipped") for obj, path in sources]
        output = self.root / "chosen_destination"
        for enabled in (False, True):
            with (
                mock.patch.object(
                    _domain_access_catalog,
                    'objects_from_args',
                    return_value=([obj for obj, _ in sources], _domain_access_models.ScanStats()),
                ),
                mock.patch.object(_domain_access_download, 'download_selected_objects', return_value=(0, downloads)),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                result = _domain_access_retrieval.retrieve_sources(
                    particle_types="black_carbon",
                    target_wavelengths=[1.5],
                    download=True,
                    apply_interpolation=enabled,
                    interpolation_output_dir=output,
                )
            self.assertEqual(bool(result.interpolated_products), enabled)
            self.assertEqual(result.wavelength_processing.interpolation_applied, enabled)
            if enabled:
                self.assertTrue(
                    all(
                        product.path.is_relative_to(output)
                        for product in result.interpolated_products
                    )
                )

    def test_cli_interpolation_option_reaches_runtime(self):
        arguments = _domain_cli_arguments.build_parser().parse_args(
            [
                "retrieve",
                "--target-wavelength",
                "1.5",
                "--no-apply-interpolation",
                "--interpolation-output-dir",
                str(self.root),
            ]
        )
        runtime, _ = _domain_access_requests.build_retrieve_runtime_args(arguments)
        self.assertFalse(runtime.apply_interpolation)
        self.assertEqual(runtime.interpolation_output_dir, self.root)


if __name__ == "__main__":
    unittest.main()
