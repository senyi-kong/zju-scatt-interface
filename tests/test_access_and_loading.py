"""Domain regressions for catalog access, transfer and optical loading.

Author: Senyi Kong
Organization: ZJU-SCATT Team
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os as _domain_os
import sys as _domain_sys
import tempfile
import unittest
import uuid
import webbrowser as _domain_webbrowser
from pathlib import Path
from unittest import mock

import test_super_spheroid_ice_requirements as ice_requirements

import zju_scatt_interface.access.cache as _domain_access_cache
import zju_scatt_interface.access.catalog as _domain_access_catalog
import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.endpoints as _domain_access_endpoints
import zju_scatt_interface.access.filters as _domain_access_filters
import zju_scatt_interface.access.manifests as _domain_access_manifests
import zju_scatt_interface.access.metadata as _domain_access_metadata
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.progress as _domain_access_progress
import zju_scatt_interface.access.registration as _domain_access_registration
import zju_scatt_interface.access.reports as _domain_access_reports
import zju_scatt_interface.access.requests as _domain_access_requests
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.bulk.lowlevel as _domain_bulk_lowlevel
import zju_scatt_interface.errors as _domain_errors
import zju_scatt_interface.io.paths as _domain_io_paths
import zju_scatt_interface.optics.models as _domain_optics_models
import zju_scatt_interface.plotting.diagnostics as _domain_plotting_diagnostics
import zju_scatt_interface.sources.coordinates as _domain_sources_coordinates


def base_filter_args(**overrides):
    values = dict(
        glob=None,
        exclude_glob=None,
        contains=None,
        exclude=None,
        regex=None,
        ignore_case=False,
        extension=None,
        min_size=None,
        max_size=None,
        after=None,
        before=None,
        particle_type=None,
        wavelength=None,
        wavelength_unit=None,
        size_range=None,
        target_size=None,
        target_size_tolerance=None,
        ref_real=None,
        ref_real_target=None,
        ref_real_target_tolerance=None,
        ref_imag=None,
        ref_imag_target=None,
        ref_imag_target_tolerance=None,
        n_range=None,
        aspect_ratio=None,
        param=None,
        shape_target=None,
        shape_target_tolerance=None,
        value_regex=None,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class ListParsingTests(unittest.TestCase):
    def test_parse_list_page(self) -> None:
        payload = b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult>
          <IsTruncated>true</IsTruncated>
          <NextMarker>root/file.nc</NextMarker>
          <Contents>
            <Key>root/file.nc</Key><Size>42</Size>
            <LastModified>2026-04-20T00:00:00.000Z</LastModified>
            <ETag>\"abc\"</ETag>
          </Contents>
          <CommonPrefixes><Prefix>root/folder/</Prefix></CommonPrefixes>
        </ListBucketResult>"""
        page = _domain_access_client.parse_list_page(payload)
        self.assertTrue(page.truncated)
        self.assertEqual(page.next_marker, "root/file.nc")
        self.assertEqual(page.objects[0].size, 42)
        self.assertEqual(page.objects[0].etag, "abc")
        self.assertEqual(page.directories[0].key, "root/folder/")

    def test_iter_objects_follows_markers(self) -> None:
        class FakeClient(_domain_access_client.ApiClient):
            def __init__(self) -> None:
                super().__init__(retries=0)
                self.markers = []

            def list_page(self, prefix, *, delimiter=None, marker=""):
                self.markers.append(marker)
                if not marker:
                    return _domain_access_models.ListPage(
                        (_domain_access_models.RemoteObject("root/a.nc", 1),), (), True, "root/a.nc"
                    )
                return _domain_access_models.ListPage(
                    (_domain_access_models.RemoteObject("root/b.nc", 2),), (), False, ""
                )

        client = FakeClient()
        objects = list(client.iter_objects("root/"))
        self.assertEqual([item.key for item in objects], ["root/a.nc", "root/b.nc"])
        self.assertEqual(client.markers, ["", "root/a.nc"])


class PathTests(unittest.TestCase):
    def test_resolve_download_page_url_preserves_plus(self) -> None:
        url = (
            "https://zju_radiation.deep-time.org/download?path="
            "data-service-dev-repo%2Foriginal_data%2Ffolder%2Fref_1.0e%2B00%2F"
        )
        self.assertEqual(
            _domain_access_catalog.resolve_remote_path(url),
            "data-service-dev-repo/original_data/folder/ref_1.0e+00/",
        )

    def test_resolve_relative_path(self) -> None:
        self.assertEqual(
            _domain_access_catalog.resolve_remote_path("Single_opt/sphere_sulfate/data/"),
            _domain_access_endpoints.ROOT_PREFIX + "Single_opt/sphere_sulfate/data/",
        )

    def test_object_url_encodes_spaces_and_plus(self) -> None:
        url = _domain_access_catalog.object_url("folder with space/ref_1e+00.nc")
        self.assertIn("folder%20with%20space", url)
        self.assertIn("1e%2B00.nc", url)


class MetadataAndFilterTests(unittest.TestCase):
    def test_extract_wavelength_and_refractive_index(self) -> None:
        name = (
            "L1_sphere_sulfate_wl_00.532_um_ref_1.431e+00_1.000e-08_"
            "water_1.334e+00_1.559e-09_t_270k_v1.0_20260417.nc"
        )
        values = _domain_access_metadata.extract_scatt_metadata(name)
        self.assertAlmostEqual(values["wavelength_um"], 0.532)
        self.assertAlmostEqual(values["ref_real"], 1.431)
        self.assertAlmostEqual(values["ref_imag"], 1e-8)
        self.assertAlmostEqual(values["temperature_k"], 270.0)

    def test_extract_shape_parameters(self) -> None:
        name = "L1_super_spheroid_n_1.400_asp_0.600_wl_nan_ref_1.5_0.01.nc"
        values = _domain_access_metadata.extract_scatt_metadata(name)
        self.assertAlmostEqual(values["n"], 1.4)
        self.assertAlmostEqual(values["aspect_ratio"], 0.6)
        self.assertNotIn("wavelength_um", values)

    def test_scientific_filter(self) -> None:
        spec = _domain_access_filters.FilterSpec(
            numeric=[
                _domain_access_models.NumericConstraint("wavelength_um", 0.5, 0.8),
                _domain_access_models.NumericConstraint("ref_real", 1.4, 1.5),
            ]
        )
        matching = _domain_access_models.RemoteObject(
            "root/L1_x_wl_00.532_um_ref_1.431e+00_1.000e-08.nc", 100
        )
        rejected = _domain_access_models.RemoteObject(
            "root/L1_x_wl_01.064_um_ref_1.420e+00_1.000e-08.nc", 100
        )
        self.assertTrue(spec.matches(matching))
        self.assertFalse(spec.matches(rejected))

    def test_custom_numeric_filter(self) -> None:
        args = base_filter_args(param=[["temp", "250", "300"]])
        spec = _domain_access_filters.compile_filter(args)
        self.assertTrue(spec.matches(_domain_access_models.RemoteObject("root/model_temp_273.15.nc")))
        self.assertFalse(spec.matches(_domain_access_models.RemoteObject("root/model_temp_310.nc")))

    def test_wavelength_range_accepts_wavenumber_units(self) -> None:
        args = base_filter_args(wavelength=[10000, 20000], wavelength_unit="cm-1")
        spec = _domain_access_filters.compile_filter(args)
        self.assertTrue(spec.matches(_domain_access_models.RemoteObject("root/model_wl_0.600_um.nc")))
        self.assertFalse(spec.matches(_domain_access_models.RemoteObject("root/model_wl_1.200_um.nc")))

    def test_particle_type_and_size_range_filters(self) -> None:
        spec = _domain_access_filters.compile_filter(
            base_filter_args(
                particle_type=["super spheroid ice"],
                size_range=[1.0, 2.0],
            )
        )
        matching = _domain_access_models.RemoteObject(
            "root/Single_opt/super_spheroid_ice/data/"
            "L1.5_super_spheroid_ice_n_2.000_asp_1.000_wl_0.600_um_ref_1.3_0.0.nc",
            100,
        )
        wrong_particle = _domain_access_models.RemoteObject(
            "root/Single_opt/sphere_sulfate/data/"
            "L1.5_sphere_sulfate_wl_0.600_um_ref_1.3_0.0.nc",
            100,
        )
        wrong_size = _domain_access_models.RemoteObject(
            "root/Single_opt/super_spheroid_ice/data/"
            "L3.0_super_spheroid_ice_n_2.000_asp_1.000_wl_0.600_um_ref_1.3_0.0.nc",
            100,
        )
        self.assertTrue(spec.matches(matching))
        self.assertFalse(spec.matches(wrong_particle))
        self.assertFalse(spec.matches(wrong_size))

    def test_direct_target_filters(self) -> None:
        spec = _domain_access_filters.compile_filter(
            base_filter_args(
                ref_real_target=["1.306"],
                target_size=["1.5"],
                shape_target=[["asp", "1.25"]],
            )
        )
        matching = _domain_access_models.RemoteObject(
            "root/L1.5_super_spheroid_ice_asp_1.25_wl_0.600_um_ref_1.306e+00_0.0.nc"
        )
        rejected = _domain_access_models.RemoteObject(
            "root/L2.0_super_spheroid_ice_asp_1.50_wl_0.600_um_ref_1.400e+00_0.0.nc"
        )
        self.assertTrue(spec.matches(matching))
        self.assertFalse(spec.matches(rejected))

    def test_target_wavelength_selects_bracketing_sources(self) -> None:
        objects = [
            _domain_access_models.RemoteObject("root/shape_a_wl_0.500_um_ref_1.30_0.00.nc", 10),
            _domain_access_models.RemoteObject("root/shape_a_wl_0.700_um_ref_1.40_0.10.nc", 20),
            _domain_access_models.RemoteObject("root/shape_a_wl_0.900_um_ref_1.80_0.30.nc", 30),
        ]
        selected, processing = _domain_sources_coordinates.select_for_target_wavelength(
            objects, [0.6, 0.9], tolerance_um=1e-9
        )
        self.assertTrue(processing.interpolation_required)
        self.assertEqual(processing.interpolation_basis, "refractive_index_nk")
        self.assertEqual(
            [item.key for item in selected],
            [objects[0].key, objects[1].key, objects[2].key],
        )
        self.assertEqual(processing.target_wavelengths_um, (0.6, 0.9))
        self.assertIn((1.35, 0.05), processing.target_refractive_points)

    def test_target_wavelength_nearest_mode_selects_nearest_wavelength(self) -> None:
        objects = [
            _domain_access_models.RemoteObject("root/shape_wl_0.500_um_ref_1.30_0.00.nc", 10),
            _domain_access_models.RemoteObject("root/shape_wl_0.700_um_ref_1.40_0.10.nc", 20),
            _domain_access_models.RemoteObject("root/shape_wl_0.900_um_ref_1.80_0.30.nc", 30),
        ]
        selected, processing = _domain_sources_coordinates.select_for_target_wavelength(
            objects,
            [0.68],
            tolerance_um=1e-9,
            mode="nearest",
        )
        self.assertFalse(processing.interpolation_required)
        self.assertEqual(processing.interpolation_basis, "nearest_wavelength")
        self.assertEqual([item.key for item in selected], [objects[1].key])

    def test_retrieve_config_compiles_scientific_request(self) -> None:
        path = Path(tempfile.gettempdir()) / f"zju_scatt_request_{uuid.uuid4().hex}.json"
        try:
            path.write_text(
                json.dumps(
                    {
                        "sources": ["Single_opt/"],
                        "particle_types": ["ice"],
                        "wavelength_unit": "um",
                        "wavelength_range": {"start_um": 0.38, "end_um": 0.78},
                        "size_range": {"min": 1.0, "max": 2.0},
                        "target_size": [1.5],
                        "refractive_index": {
                            "real": {"min": 1.3, "max": 1.5, "targets": [1.306]},
                            "imag": {"min": 0.0, "max": 1e-6, "targets": [0.0]},
                        },
                        "shapes": [{"roundness": 0.2}, {"roundness": 0.4}],
                        "download": False,
                        "manifest": "saved.csv",
                        "operation_log": "run.log",
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(config=path, source=[])
            runtime, _config = _domain_access_requests.build_retrieve_runtime_args(args)
            self.assertEqual(runtime.source, ["Single_opt/"])
            self.assertEqual(runtime.particle_type, ["ice"])
            self.assertEqual(runtime.wavelength, [0.38, 0.78])
            self.assertEqual(runtime.ref_real, [1.3, 1.5])
            self.assertEqual(runtime.ref_real_target, [1.306])
            self.assertEqual(runtime.ref_imag, [0.0, 1e-6])
            self.assertEqual(runtime.ref_imag_target, [0.0])
            self.assertEqual(runtime.size_range, [1.0, 2.0])
            self.assertEqual(runtime.target_size, [1.5])
            self.assertEqual(runtime.shapes, [{"roundness": 0.2}, {"roundness": 0.4}])
            self.assertFalse(runtime.download)
            self.assertEqual(runtime.manifest, Path("saved.csv"))
        finally:
            if path.exists():
                path.unlink()

    def test_wavelength_config_unit_applies_to_ranges_and_targets(self) -> None:
        path = Path(tempfile.gettempdir()) / f"zju_scatt_request_{uuid.uuid4().hex}.json"
        try:
            path.write_text(
                json.dumps(
                    {
                        "wavelength_unit": "cm-1",
                        "target_wavelength_mode": "nearest",
                        "target_wavelengths": [10000, 20000],
                        "download": False,
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(config=path, source=[])
            runtime, _config = _domain_access_requests.build_retrieve_runtime_args(args)
            self.assertEqual(runtime.target_wavelengths, [1.0, 0.5])
            self.assertEqual(runtime.target_wavelength_mode, "nearest")
            self.assertEqual(runtime.wavelength_unit, "cm-1")
        finally:
            if path.exists():
                path.unlink()

    def test_python_api_retrieve_accepts_keyword_parameters(self) -> None:
        manifest = Path(tempfile.gettempdir()) / f"zju_scatt_api_{uuid.uuid4().hex}.csv"
        output = Path(tempfile.gettempdir()) / f"zju_scatt_api_out_{uuid.uuid4().hex}.csv"
        log = Path(tempfile.gettempdir()) / f"zju_scatt_api_log_{uuid.uuid4().hex}.txt"
        objects = [
            _domain_access_models.RemoteObject(
                "root/Single_opt/super_spheroid_ice/data/"
                "L1.5_super_spheroid_ice_asp_1.25_wl_0.600_um_ref_1.306e+00_0.0.nc",
                10,
            ),
            _domain_access_models.RemoteObject(
                "root/Single_opt/super_spheroid_ice/data/"
                "L2.0_super_spheroid_ice_asp_1.50_wl_0.700_um_ref_1.400e+00_0.0.nc",
                20,
            ),
        ]
        try:
            _domain_access_manifests.write_manifest(objects, manifest)
            result = _domain_access_retrieval.retrieve_sources(
                manifest=manifest,
                particle_types="super_spheroid_ice",
                wavelength_range=(0.5, 0.8),
                ref_real_targets=[1.306],
                target_sizes=[1.5],
                shapes={"asp": 1.25},
                manifest_output=output,
                operation_log=log,
                download=False,
            )
            self.assertEqual([item.key for item in result.objects], [objects[0].key])
            self.assertEqual(result.stats.matched, 1)
            self.assertEqual(result.manifest_path, output)
            self.assertTrue(output.exists())
            self.assertTrue(log.exists())
            self.assertIn("DATA RETRIEVAL SUCCESSFUL", log.read_text(encoding="utf-8"))
        finally:
            for path in (manifest, output, log):
                if path.exists():
                    path.unlink()

    def test_python_api_default_does_not_write_manifest_or_log(self) -> None:
        manifest = Path(tempfile.gettempdir()) / f"zju_scatt_api_{uuid.uuid4().hex}.csv"
        objects = [_domain_access_models.RemoteObject("root/a_wl_0.600_um_ref_1.3_0.0.nc", 10)]
        try:
            _domain_access_manifests.write_manifest(objects, manifest)
            result = _domain_access_retrieval.retrieve_sources(manifest=manifest, download=False)
            self.assertIsNone(result.manifest_path)
            self.assertIsNone(result.operation_log_path)
            self.assertEqual(len(result.objects), 1)
        finally:
            if manifest.exists():
                manifest.unlink()

    def test_db_begin_sets_python_api_data_directory(self) -> None:
        path = Path(tempfile.gettempdir()) / f"zju_scatt_api_dir_{uuid.uuid4().hex}"
        try:
            self.assertEqual(_domain_access_cache.initialize_data_directory(path), path)
            self.assertTrue(path.exists())
        finally:
            if path.exists():
                path.rmdir()


class BulkOpticsTests(unittest.TestCase):
    def test_normalize_number_distribution_scales_user_values(self) -> None:
        density = _domain_bulk_lowlevel.normalize_number_distribution(
            [1.0, 2.0],
            [10.0, 10.0],
            100.0,
        )
        self.assertEqual(density, [100.0, 100.0])
        per_bin = _domain_bulk_lowlevel.normalize_number_distribution(
            [1.0, 2.0],
            [2.0, 3.0],
            10.0,
            distribution_mode="bin",
        )
        self.assertEqual(per_bin, [4.0, 6.0])

    def test_integrate_bulk_optics_includes_g_and_phase_matrix(self) -> None:
        result = _domain_bulk_lowlevel._integrate_kernel(
            [1.0, 2.0],
            [10.0, 10.0],
            extinction_cross_section=[2.0, 4.0],
            scattering_cross_section=[1.0, 3.0],
            asymmetry_factor=[0.2, 0.8],
            phase_matrix=[
                [[1.0, 0.0], [0.0, 1.0]],
                [[3.0, 1.0], [1.0, 3.0]],
            ],
        )
        self.assertAlmostEqual(result.extinction_coefficient or 0.0, 30.0)
        self.assertAlmostEqual(result.scattering_coefficient or 0.0, 20.0)
        self.assertAlmostEqual(result.absorption_coefficient or 0.0, 10.0)
        self.assertAlmostEqual(result.single_scattering_albedo or 0.0, 2.0 / 3.0)
        self.assertAlmostEqual(result.asymmetry_factor or 0.0, 0.65)
        self.assertEqual(result.phase_matrix, [[2.5, 0.75], [0.75, 2.5]])

    def test_bulk_cli_writes_json_and_operation_log(self) -> None:
        source = Path(tempfile.gettempdir()) / f"zju_scatt_bulk_{uuid.uuid4().hex}.csv"
        output = Path(tempfile.gettempdir()) / f"zju_scatt_bulk_{uuid.uuid4().hex}.json"
        log = Path(tempfile.gettempdir()) / f"zju_scatt_bulk_{uuid.uuid4().hex}.log"
        try:
            source.write_text(
                "radius,number,c_ext,c_sca,g\n"
                "1,10,2,1,0.2\n"
                "2,10,4,3,0.8\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                from zju_scatt_interface.cli.main import main
                status = main(
                    [
                        "bulk",
                        "--input",
                        str(source),
                        "--output",
                        str(output),
                        "--operation-log",
                        str(log),
                    ]
                )
            self.assertEqual(status, 0)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertAlmostEqual(data["extinction_coefficient"], 30.0)
            self.assertAlmostEqual(data["scattering_coefficient"], 20.0)
            self.assertAlmostEqual(data["absorption_coefficient"], 10.0)
            self.assertAlmostEqual(data["asymmetry_factor"], 0.65)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("BULK OPTICAL CALCULATION SUCCESSFUL", stderr.getvalue())
            self.assertIn(
                "BULK OPTICAL CALCULATION SUCCESSFUL",
                log.read_text(encoding="utf-8"),
            )
        finally:
            for path in (source, output, log):
                if path.exists():
                    path.unlink()


class UtilityTests(unittest.TestCase):
    class TtyBuffer(io.StringIO):
        def isatty(self):
            return True

    def test_country_codes_and_names_are_normalized(self) -> None:
        self.assertEqual(_domain_access_registration.normalize_country("CN"), "CN")
        self.assertEqual(_domain_access_registration.normalize_country("China"), "CN")
        self.assertEqual(_domain_access_registration.normalize_country("United Kingdom"), "GB")
        self.assertEqual(_domain_access_registration.normalize_country("usa"), "US")

    def test_unknown_country_is_rejected_before_api_request(self) -> None:
        with self.assertRaises(_domain_errors.ScattError):
            _domain_access_registration.normalize_country("not-a-country")

    def test_dataset_interests_match_website_values(self) -> None:
        self.assertEqual(
            _domain_access_registration.normalize_dataset_needs(["single, bulk", "ml"]),
            ["single_optical", "bulk_optical", "ml_model"],
        )

    def test_registration_sends_normalized_website_payload(self) -> None:
        class FakeClient:
            payload = None

            def register(self, payload):
                self.payload = payload
                return "test-token"

        args = argparse.Namespace(
            name=" Test User ",
            organization=" ZJU-SCATT Team ",
            country="China",
            email=" ",
            intended_use=" Test ",
            consent=True,
            dataset_need=["single_optical"],
            minimal=False,
            debug=False,
        )
        client = FakeClient()
        with mock.patch.object(_domain_access_registration, 'load_session_token', return_value=None), mock.patch.object(_domain_access_registration, 'save_session_token') as save:
            token = _domain_access_registration.register_interactively(client, args)
        self.assertEqual(token, "test-token")
        self.assertEqual(client.payload["country"], "CN")
        self.assertEqual(client.payload["organization"], "ZJU-SCATT Team")
        self.assertNotIn("email", client.payload)
        save.assert_called_once()

    def test_minimal_registration_omits_every_optional_field(self) -> None:
        class FakeClient:
            payload = None

            def register(self, payload):
                self.payload = payload
                return "test-token"

        args = argparse.Namespace(
            name=None,
            organization="ZJU-SCATT Team",
            country="CN",
            email=None,
            intended_use=None,
            consent=True,
            dataset_need=None,
            minimal=True,
            debug=False,
        )
        client = FakeClient()
        with mock.patch.object(_domain_access_registration, 'load_session_token', return_value=None), mock.patch.object(_domain_access_registration, 'save_session_token'):
            _domain_access_registration.register_interactively(client, args)
        self.assertEqual(
            client.payload,
            {"organization": "ZJU-SCATT Team", "country": "CN", "consent": True},
        )

    def test_download_gate_requires_a_valid_session_by_default(self) -> None:
        client = mock.Mock()
        with mock.patch.object(_domain_access_registration, 'load_session_token', return_value=None):
            with self.assertRaises(_domain_errors.ScattError):
                _domain_access_registration.require_tracking_session(client)
        with mock.patch.object(_domain_access_registration, 'load_session_token', return_value="registered-token"):
            self.assertIsNone(_domain_access_registration.require_tracking_session(client, no_track=True))
        client.validate_session.return_value = True
        with mock.patch.object(_domain_access_registration, 'load_session_token', return_value="token"):
            self.assertEqual(_domain_access_registration.require_tracking_session(client), "token")

    def test_headless_linux_does_not_launch_xdg_open(self) -> None:
        with mock.patch.object(_domain_sys, "platform", "linux"):
            with mock.patch.dict(_domain_os.environ, {}, clear=True):
                self.assertFalse(_domain_access_registration.graphical_browser_available())
        with mock.patch.object(_domain_webbrowser, "open") as browser_open:
            _domain_access_registration.offer_registration_page(no_open=True)
        browser_open.assert_not_called()

    def test_tls_bypass_is_limited_to_website_host(self) -> None:
        client = _domain_access_client.ApiClient(retries=0)
        with mock.patch.object(_domain_sys, "stderr"):
            self.assertIs(
                client._opener_for_url(_domain_access_endpoints.TRACKING_API_URL), client.site_opener
            )
            self.assertIs(
                client._opener_for_url(
                    f"{_domain_access_endpoints.BACKUP_SITE_URL}/api/download/session/validate"
                ),
                client.site_opener,
            )
        self.assertIs(client._opener_for_url(_domain_access_endpoints.OSS_BASE_URL), client.opener)
        self.assertIsNot(client.site_opener, client.opener)

    def test_primary_website_request_falls_back_to_backup_ip(self) -> None:
        client = _domain_access_client.ApiClient(retries=0, show_tls_warning=False)
        primary = f"{_domain_access_endpoints.TRACKING_API_URL}/session/validate?session=test"
        calls = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class FakeOpener:
            def open(self, request, timeout):
                calls.append((request.full_url, timeout))
                if request.full_url == primary:
                    raise OSError("primary DNS unavailable")
                return FakeResponse()

        with mock.patch.object(client, "_opener_for_url", return_value=FakeOpener()):
            response = client._request(primary)

        self.assertIsInstance(response, FakeResponse)
        self.assertEqual(
            [item[0] for item in calls],
            [primary, _domain_access_endpoints.backup_site_url(primary)],
        )

    def test_oss_request_does_not_use_website_backup(self) -> None:
        client = _domain_access_client.ApiClient(retries=0, show_tls_warning=False)
        object_url = _domain_access_catalog.object_url("root/test.nc")
        calls = []

        class FakeOpener:
            def open(self, request, timeout):
                calls.append(request.full_url)
                raise OSError("object endpoint unavailable")

        with mock.patch.object(client, "_opener_for_url", return_value=FakeOpener()):
            with self.assertRaises(_domain_errors.NetworkError):
                client._request(object_url)

        self.assertEqual(calls, [object_url])

    def test_quiet_mode_suppresses_routine_tls_note(self) -> None:
        client = _domain_access_client.ApiClient(retries=0, show_tls_warning=False)
        stream = io.StringIO()
        with mock.patch.object(_domain_sys, "stderr", stream):
            client._opener_for_url(_domain_access_endpoints.TRACKING_API_URL)
        self.assertEqual(stream.getvalue(), "")

    def test_registration_uses_plain_json_post_without_browser_headers(self) -> None:
        client = _domain_access_client.ApiClient(retries=0)
        payload = {"organization": "ZJU", "country": "CN", "consent": True}
        with mock.patch.object(
            client, "post_json", return_value={"sessionToken": "token"}
        ) as post:
            self.assertEqual(client.register(payload), "token")
        post.assert_called_once_with(f"{_domain_access_endpoints.TRACKING_API_URL}/register", payload)

    def test_download_progress_reports_bytes_and_files(self) -> None:
        stream = self.TtyBuffer()
        progress = _domain_access_progress.DownloadProgress(100, 1, stream=stream)
        progress.advance_network(40)
        progress.finish_file(_domain_access_models.RemoteObject("root/a.nc", 100), 40, "downloaded")
        progress.close()
        output = stream.getvalue()
        self.assertIn("100.0%", output)
        self.assertIn("1/1 files", output)

    def test_scan_activity_reports_page_and_object_counts(self) -> None:
        stream = self.TtyBuffer()
        activity = _domain_access_progress.ScanActivity(stream=stream)
        activity.update(2, 1500)
        activity.close()
        self.assertIn("2 pages", stream.getvalue())
        self.assertIn("1,500 objects", stream.getvalue())

    def test_parse_size(self) -> None:
        self.assertEqual(_domain_access_filters.parse_size("2GiB"), 2 * 1024**3)
        self.assertEqual(_domain_access_filters.parse_size("5MB"), 5_000_000)

    def test_manifest_round_trip(self) -> None:
        path = Path(tempfile.gettempdir()) / f"zju_scatt_test_{uuid.uuid4().hex}.csv"
        objects = [_domain_access_models.RemoteObject("root/a.nc", 42, "2026-04-20T00:00:00Z", "abc")]
        try:
            _domain_access_manifests.write_manifest(objects, path)
            loaded = _domain_access_manifests.load_manifest(path)
            self.assertEqual(loaded, objects)
        finally:
            if path.exists():
                path.unlink()

    def test_plot_optical_properties_validates_inputs_before_matplotlib(self) -> None:
        with self.assertRaises(_domain_errors.ScattError):
            _domain_plotting_diagnostics.plot_optical_properties([])

    def test_bulk_phase_matrix_element_uses_nearest_angle(self) -> None:
        result = _domain_optics_models.BulkOptics(
            extinction_coefficient=1.0,
            scattering_coefficient=1.0,
            absorption_coefficient=0.0,
            single_scattering_albedo=1.0,
            asymmetry_factor=0.5,
            phase_matrix=[
                [[1.0, 0.0], [0.0, 1.0]],
                [[2.0, 0.0], [0.0, 2.0]],
            ],
            metadata={"scattering_angles": [0.0, 180.0]},
        )
        value, angle = _domain_bulk_lowlevel.bulk_phase_matrix_element(result, angle=179.5)
        self.assertEqual(value, 2.0)
        self.assertEqual(angle, 180.0)

    def test_wavelength_series_plot_validates_inputs_before_matplotlib(self) -> None:
        with self.assertRaises(_domain_errors.ScattError):
            _domain_plotting_diagnostics.plot_bulk_wavelength_series([])

    def test_requirement_retrieve_download_uses_python_api_keywords(self) -> None:
        args = argparse.Namespace(
            no_track=True,
            session=None,
            workers=1,
            no_progress=True,
            shape_n=2.0,
            shape_aspect_ratio=1.0,
            visible_wavelength_mode="nearest",
        )
        sentinel = object()
        with mock.patch.object(_domain_access_retrieval, 'retrieve_sources', return_value=sentinel) as retrieve:
            result = ice_requirements.retrieve_download(
                client=mock.Mock(),
                args=args,
                output_dir=Path("out"),
                target_wavelengths=[0.67],
                max_files=1,
            )
        self.assertIs(result, sentinel)
        self.assertNotIn("yes", retrieve.call_args.kwargs)
        self.assertEqual(retrieve.call_args.kwargs["target_wavelengths"], [0.67])
        self.assertEqual(retrieve.call_args.kwargs["target_wavelength_mode"], "nearest")

    def test_requirement_downloaded_paths_uses_download_result_target(self) -> None:
        target = Path("downloaded.nc")
        retrieval = _domain_access_models.RetrievalResult(
            objects=[],
            stats=_domain_access_models.ScanStats(),
            wavelength_processing=_domain_access_models.WavelengthProcessing(),
            download_results=[
                _domain_access_models.DownloadResult(
                    _domain_access_models.RemoteObject("root/downloaded.nc", 1),
                    target,
                    "downloaded",
                )
            ],
        )
        self.assertEqual(ice_requirements.downloaded_paths(retrieval), [target])

    def test_operation_log_records_success_and_processing(self) -> None:
        path = Path(tempfile.gettempdir()) / f"zju_scatt_log_{uuid.uuid4().hex}.txt"
        manifest = Path(tempfile.gettempdir()) / f"zju_scatt_manifest_{uuid.uuid4().hex}.csv"
        args = argparse.Namespace(
            source=["Single_opt/"],
            particle_type=["ice"],
            wavelength=[0.4, 0.8],
            wavelength_unit="um",
            target_wavelengths=[],
            size_range=None,
            target_size=None,
            ref_real=None,
            ref_real_target=None,
            ref_imag=None,
            ref_imag_target=None,
            n_range=None,
            aspect_ratio=None,
            shape_targets=[],
            extension=["nc"],
            output_dir=Path("zju_scatt_data"),
        )
        objects = [_domain_access_models.RemoteObject("root/a_wl_0.600_um_ref_1.3_0.0.nc", 42)]
        try:
            _domain_access_reports.write_operation_log(
                path,
                args=args,
                config_path=None,
                stats=_domain_access_models.ScanStats(pages=1, scanned=2, matched=1, bytes=42),
                objects=objects,
                manifest_path=manifest,
                wavelength_processing=_domain_access_models.WavelengthProcessing(
                    selected_wavelengths_um=(0.6,),
                    message="Exact data selected.",
                ),
                target_processings=[],
                download_enabled=False,
                results=[],
                exit_code=0,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("Wavelength processing: Exact data selected.", text)
            self.assertIn("Interpolation source selection: no", text)
            self.assertIn("Interpolated data product generated: no", text)
            self.assertIn("DATA RETRIEVAL SUCCESSFUL", text)
        finally:
            if path.exists():
                path.unlink()

    def test_requirement_operation_log_records_bulk_interpolation(self) -> None:
        path = Path(tempfile.gettempdir()) / f"zju_scatt_req_log_{uuid.uuid4().hex}.txt"
        args = argparse.Namespace(
            visible_wavelength=0.67,
            visible_wavelength_mode="interp",
            infrared_range=(10.0, 13.0),
        )
        visible_result = _domain_optics_models.BulkOptics(
            extinction_coefficient=1.0,
            scattering_coefficient=0.8,
            absorption_coefficient=0.2,
            single_scattering_albedo=0.8,
            asymmetry_factor=0.7,
            number_concentration=1.0,
            metadata={
                "temperature_k": 220.0,
                "interpolation": (
                    "inverse-distance interpolation of bulk scalar quantities "
                    "in refractive-index (n,k) space"
                ),
            },
        )
        infrared_result = _domain_optics_models.BulkOptics(
            extinction_coefficient=1.0,
            scattering_coefficient=0.8,
            absorption_coefficient=0.2,
            single_scattering_albedo=0.8,
            asymmetry_factor=0.7,
            number_concentration=1.0,
            metadata={"temperature_k": 220.0, "wavelength_um": 10.0},
        )
        try:
            ice_requirements.write_requirement_operation_log(
                path,
                args=args,
                visible_target_results=[visible_result],
                infrared_results=[infrared_result],
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("Bulk interpolation applied: yes", text)
            self.assertIn("Bulk interpolation basis: refractive_index_nk", text)
            self.assertIn("BULK OPTICS REQUIREMENT PROCESSING SUCCESSFUL", text)
        finally:
            if path.exists():
                path.unlink()

    def test_complete_part_file_is_finalized_without_network(self) -> None:
        target = Path(tempfile.gettempdir()) / f"zju_scatt_part_{uuid.uuid4().hex}.nc"
        partial = target.with_name(target.name + ".part")
        payload = b"complete"
        try:
            partial.write_bytes(payload)
            obj = _domain_access_models.RemoteObject("root/complete.nc", len(payload))
            result = _domain_access_download.download_one(
                _domain_access_client.ApiClient(retries=0),
                obj,
                target,
                resume=True,
                overwrite=False,
                verify_etag=False,
            )
            self.assertEqual(result.status, "downloaded")
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(partial.exists())
        finally:
            if target.exists():
                target.unlink()
            if partial.exists():
                partial.unlink()

    def test_windows_filesystem_path_uses_extended_length_prefix(self) -> None:
        if _domain_os.name != "nt":
            self.skipTest("Windows-only extended-length path behavior")
        path = _domain_io_paths.filesystem_path(
            Path.cwd() / ("nested_" + "x" * 240) / "file.nc"
        )
        self.assertTrue(str(path).startswith("\\\\?\\"))


if __name__ == "__main__":
    unittest.main()
