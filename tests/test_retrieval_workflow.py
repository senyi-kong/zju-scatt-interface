"""Configuration, strict completion, partial batches and native RI retrieval."""

import json
import tempfile
import unittest
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.manifests as _domain_access_manifests
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
from tests.test_native_retrieval import native_fixture
from zju_scatt_interface.access.workflow import RetrievalRunError, load_retrieval_config, retrieve
from zju_scatt_interface.optics.retrieval.native import verify_native_schema


def result(objects=None, **kwargs):
    return _domain_access_models.RetrievalResult(
        objects or [_domain_access_models.RemoteObject("source.nc", size=10)],
        _domain_access_models.ScanStats(),
        _domain_access_models.WavelengthProcessing(),
        **kwargs,
    )


class RetrievalWorkflowTests(unittest.TestCase):
    def test_relative_paths_and_python_json_configs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"particle_types": "dust", "output_dir": "out", "manifest": "catalog.jsonl"}
            for name, source in (
                ("input.py", f"retrieval={config!r}"),
                ("input.json", json.dumps(config)),
            ):
                path = root / name
                path.write_text(source)
                loaded = load_retrieval_config(path)
                self.assertEqual(loaded["output_dir"], root / "out")
                self.assertEqual(loaded["manifest"], root / "catalog.jsonl")

    def test_preview_batch_and_report_without_download_checks(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(_domain_access_retrieval, 'retrieve_sources', side_effect=[result(), result()]) as source_retrieval,
        ):
            run = retrieve(
                {
                    "requests": {"dust": {"download": True}, "black_carbon": {"download": True}},
                    "target_wavelengths": [1.5],
                    "output_dir": directory,
                    "quiet": True,
                },
                download=False,
            )
            self.assertEqual(len(run.results), 2)
            self.assertTrue(
                all(call.kwargs["download"] is False for call in source_retrieval.call_args_list)
            )
            self.assertEqual(
                source_retrieval.call_args.kwargs["output_dir"], Path(directory) / "black_carbon"
            )
            self.assertEqual(json.loads(run.report_path.read_text())["status_code"], 0)

    def test_download_failures_write_report_and_attempt_later_jobs(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                _domain_access_retrieval, 'retrieve_sources', side_effect=[result(), result(status_code=2)]
            ) as source_retrieval,
        ):
            with self.assertRaises(RetrievalRunError) as caught:
                retrieve(
                    {
                        "requests": {"dust": {}, "black_carbon": {}},
                        "output_dir": directory,
                        "quiet": True,
                    }
                )
            run = caught.exception.result
            self.assertEqual(source_retrieval.call_count, 2)
            self.assertEqual(set(run.errors), {"dust", "black_carbon"})
            report = json.loads(run.report_path.read_text())
            self.assertIn("incomplete", report["species"]["dust"]["error"])

    def test_checks_detect_truncation_and_missing_products_but_accept_nan_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.nc"
            path.write_bytes(b"x")
            obj = _domain_access_models.RemoteObject("source.nc", size=2)
            value = result([obj], download_results=[_domain_access_models.DownloadResult(obj, path, "skipped")])
            with self.assertRaisesRegex(Exception, "byte-size"):
                value.raise_for_status(download=True)
            obj = _domain_access_models.RemoteObject("source.nc", size=1)
            value.objects = [obj]
            value.download_results = [_domain_access_models.DownloadResult(obj, path, "skipped")]
            from dataclasses import replace

            value.wavelength_processing = replace(
                value.wavelength_processing, interpolation_required=True
            )
            with self.assertRaisesRegex(Exception, "no target product"):
                value.raise_for_status(download=True, require_products=True)
            derived = Path(directory) / "boundary.nc"
            with Dataset(derived, "w") as ds:
                ds.createVariable("cext", "f4")[...] = np.nan
            value.interpolated_products = [SimpleNamespace(path=derived, status="created")]
            self.assertIs(value.raise_for_status(download=True, require_products=True), value)

    def test_all_species_checks_missing_and_unknown_profiles(self):
        client = SimpleNamespace(
            list_directory=lambda _: ([_domain_access_models.RemoteDirectory("Single_opt/unknown/")], [], None)
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(_domain_access_retrieval, 'retrieve_sources') as source_retrieval,
        ):
            with self.assertRaises(RetrievalRunError) as caught:
                retrieve(
                    {
                        "requests": "all",
                        "target_wavelengths": [1.5],
                        "output_dir": directory,
                        "quiet": True,
                    },
                    client=client,
                    download=False,
                )
            self.assertIn("unknown", caught.exception.result.errors)
            self.assertIn("super_spheroid", caught.exception.result.errors)
            source_retrieval.assert_not_called()

    def test_public_wavelength_free_shape_ri_interpolation_preserves_native_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {}
            objects = []
            for n, asp, mr, mi in product((2.0, 2.2), (1.6, 1.8), (1.5, 1.55), (0.001, 0.003)):
                name = f"L1_super_spheroid_n_{n:.3f}_asp_{asp:.3f}_wl_nan_ref_{mr:.3e}_{mi:.3e}_v1.0_20260409.nc"
                path = root / name
                native_fixture(path, None, mr + n)
                obj = _domain_access_models.RemoteObject(
                    "Single_opt/super_spheroid/" + name, size=path.stat().st_size
                )
                objects.append(obj)
                sources[obj.key] = path
            manifest = root / "sources.jsonl"
            _domain_access_manifests.write_manifest(objects, manifest, "jsonl")

            def download(runtime, client, selected, stats):
                return 0, [
                    _domain_access_models.DownloadResult(obj, sources[obj.key], "skipped") for obj in selected
                ]

            with patch.object(_domain_access_download, 'download_selected_objects', side_effect=download):
                run = retrieve(
                    {
                        "particle_types": "dust",
                        "manifest": manifest,
                        "shapes": {"n": 2.1, "asp": 1.7},
                        "refractive_index_parameters": {"dust": {"mr": 1.51, "mi": 0.0023}},
                        "output_dir": root / "out",
                        "quiet": True,
                    }
                )
            value = run.single
            self.assertEqual(len(value.objects), 16)
            self.assertEqual(len(value.interpolated_products), 1)
            target = value.interpolated_products[0]
            self.assertIsNone(target.target_wavelength_um)
            self.assertTrue(verify_native_schema(target.path, target.provenance["template_source"]))
            with Dataset(target.path) as ds:
                self.assertNotIn("wavelength", ds.variables)
                self.assertAlmostEqual(float(ds["ssph_n"][:]), 2.1, places=6)
                self.assertAlmostEqual(float(ds["mr"][:]), 1.51, places=6)
                self.assertTrue(np.isfinite(ds["cext"][:]).all())
            self.assertTrue(run.report_path.is_file())

    def test_bc_native_grid_interpolates_df_and_preserves_vf(self):
        family = "encapsulated_fractal_aggregates_black_carbon"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = {}
            objects = []
            for df, mr in product((1.8, 2.2), (1.7, 1.9)):
                name = f"L1_bc_df_{df:.2f}_wl_nan_ref_bc_{mr:.3e}_6.250e-01_hygro_1.475e+00_7.500e-03_v1.0_20260409.nc"
                path = root / name
                native_fixture(path, None, df + mr, family="bc")
                with Dataset(path, "a") as ds:
                    ds["Df"][:] = df
                obj = _domain_access_models.RemoteObject(f"Single_opt/{family}/{name}", size=path.stat().st_size)
                objects.append(obj)
                sources[obj.key] = path
            manifest = root / "sources.jsonl"
            _domain_access_manifests.write_manifest(objects, manifest, "jsonl")

            def download(runtime, client, selected, stats):
                return 0, [
                    _domain_access_models.DownloadResult(obj, sources[obj.key], "skipped") for obj in selected
                ]

            with patch.object(_domain_access_download, 'download_selected_objects', side_effect=download):
                value = retrieve(
                    {
                        "particle_types": "black_carbon",
                        "manifest": manifest,
                        "shapes": {"df": 2.0},
                        "refractive_index_parameters": {
                            "black_carbon": {
                                "black_carbon_refractive_index_real": 1.8,
                                "black_carbon_refractive_index_imaginary": 0.625,
                                "hygroscopic_refractive_index_real": 1.475,
                                "hygroscopic_refractive_index_imaginary": 0.0075,
                            }
                        },
                        "output_dir": root / "out",
                        "quiet": True,
                    }
                ).single
            target = value.interpolated_products[0]
            self.assertTrue(verify_native_schema(target.path, target.provenance["template_source"]))
            with Dataset(target.path) as ds:
                np.testing.assert_allclose(ds["Df"][:], [2.0])
                np.testing.assert_allclose(ds["vf"][:], [0.1, 0.5])
                # Positive optical fields use the existing logarithmic blend.
                expected = np.prod([df + mr for df, mr in product((1.8, 2.2), (1.7, 1.9))]) ** 0.25
                np.testing.assert_allclose(ds["qext"][:], expected)

    def test_cli_loads_config_and_allows_preview_override(self):
        from zju_scatt_interface.cli.retrieval import retrieve_from_config

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "input.py"
            config.write_text("retrieval={'particle_types':'sea_salt','target_wavelengths':[1.5]}")
            with patch('zju_scatt_interface.cli.retrieval.retrieve') as run:
                self.assertEqual(retrieve_from_config(argv=["--config", str(config), "--list-only"]), 0)
                self.assertIs(run.call_args.kwargs["download"], False)
                self.assertEqual(run.call_args.args[0]["target_wavelengths"], [1.5])


if __name__ == "__main__":
    unittest.main()
