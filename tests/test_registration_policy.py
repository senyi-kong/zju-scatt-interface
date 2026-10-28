"""Registration is mandatory, persistent and separate from download tracking."""

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import zju_scatt_interface as scatt
import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.access.endpoints as _domain_access_endpoints
import zju_scatt_interface.access.registration as _domain_access_registration
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.bulk.tables as _domain_bulk_tables
import zju_scatt_interface.cli.catalog as _domain_cli_catalog
import zju_scatt_interface.config.particles as _domain_config_particles
import zju_scatt_interface.errors as _domain_errors
import zju_scatt_interface.plotting.bulk as _domain_plotting_bulk
import zju_scatt_interface.psd.analytical as _domain_psd_analytical
from zju_scatt_interface.access.registration import register_direct
from zju_scatt_interface.cli.main import main


class RegistrationPolicyTests(unittest.TestCase):
    def test_explicit_session_is_available_to_nested_calls_only(self):
        from zju_scatt_interface.access.registration import registration_required

        @registration_required
        def operation(*, session=None):
            return _domain_config_particles.list_particle_profiles()

        self.assertTrue(operation(session="registered-token"))
        with self.assertRaises(_domain_errors.ScattError):
            _domain_config_particles.list_particle_profiles()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.session = Path(self.temporary.name) / "session.json"
        self.file_patch = patch.object(_domain_access_registration, 'CONFIG_FILE', self.session)
        self.environment = patch.dict(os.environ, {"ZJU_SCATT_SESSION": ""})
        self.file_patch.start()
        self.environment.start()
        self.addCleanup(self.file_patch.stop)
        self.addCleanup(self.environment.stop)

    def test_unregistered_cli_operations_fail_before_network(self):
        for command in (
            ["browse"],
            ["list"],
            ["search"],
            ["estimate"],
            ["metadata", "sample.nc"],
            ["retrieve", "Single_opt/", "--no-download", "--no-track"],
        ):
            with (
                self.subTest(command=command),
                patch.object(_domain_access_client.ApiClient, "_request") as request,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()) as errors,
            ):
                self.assertEqual(main(command), 2)
                self.assertIn("registration is required", errors.getvalue())
                request.assert_not_called()

    def test_python_operations_cannot_bypass_gate_with_offline_or_no_track(self):
        operations = [
            lambda: _domain_config_particles.list_particle_profiles(),
            lambda: _domain_psd_analytical.lognormal_psd(0.7, 1.8),
            lambda: _domain_access_retrieval.retrieve_sources(manifest="missing.jsonl", download=False, no_track=True),
            lambda: _domain_bulk_tables.build_table(
                {"species": "dust", "wavelengths": [1.6], "offline": True}
            ),
            lambda: _domain_plotting_bulk.plot_bulk_optics("missing.nc"),
        ]
        for operation in operations:
            with self.assertRaisesRegex(_domain_errors.ScattError, "registration is required"):
                operation()
        self.assertFalse(self.session.exists())

    def test_direct_oss_access_checks_registration_before_http(self):
        client = _domain_access_client.ApiClient()
        with patch.object(client, "_opener_for_url") as opener:
            with self.assertRaisesRegex(_domain_errors.ScattError, "registration is required"):
                client.get_bytes(_domain_access_endpoints.OSS_BASE_URL + "/example.nc")
            opener.assert_not_called()

    def test_registration_is_saved_once_and_reused_without_prompts_or_network(self):
        client = Mock()
        client.register.return_value = "registered-token"
        first = register_direct(
            "Example Institute", "CN", consent=True, minimal=True, client=client
        )
        self.assertEqual(first, "registered-token")
        self.assertEqual(json.loads(self.session.read_text())["sessionToken"], first)
        with (
            patch("builtins.input", side_effect=AssertionError("Repeat prompt")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            second = register_direct(
                "Example Institute", "CN", consent=True, minimal=True, client=client
            )
            status = _domain_cli_catalog.cmd_register(argparse.Namespace(method="browser"), client)
        self.assertEqual(second, first)
        self.assertEqual(status, 0)
        client.register.assert_called_once()
        client.validate_session.assert_not_called()
        with patch("socket.socket.connect", side_effect=AssertionError("Offline")):
            self.assertGreater(_domain_psd_analytical.lognormal_psd(0.7, 1.8).number_concentration_cm3, 0)
            self.assertTrue(_domain_config_particles.list_particle_profiles())

    def test_no_track_disables_tracking_only_after_registration(self):
        client = Mock()
        with self.assertRaises(_domain_errors.ScattError):
            _domain_access_registration.require_tracking_session(client, no_track=True)
        _domain_access_registration.save_session_token("registered-token")
        self.assertIsNone(_domain_access_registration.require_tracking_session(client, no_track=True))
        client.validate_session.assert_not_called()

    def test_clearing_saved_registration_blocks_subsequent_calls(self):
        _domain_access_registration.save_session_token("registered-token")
        self.assertTrue(_domain_config_particles.list_particle_profiles())
        self.session.unlink()
        with self.assertRaises(_domain_errors.ScattError):
            _domain_config_particles.list_particle_profiles()

    def test_help_and_diagnostics_remain_available_before_registration(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit_info:
            main(["--help"])
        self.assertEqual(exit_info.exception.code, 0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["doctor", "--offline"]), 1)
