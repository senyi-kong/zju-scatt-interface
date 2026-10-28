
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

import zju_scatt_interface.access.registration as _domain_access_registration
import zju_scatt_interface.cli.doctor as _domain_cli_doctor
import zju_scatt_interface.cli.doctor as doctor
import zju_scatt_interface.errors as _domain_errors


class FakeClient:
    def __init__(self, *, network_error=False, session_valid=True):
        self.network_error = network_error
        self.session_valid = session_valid

    def list_page(self, _prefix):
        if self.network_error:
            raise _domain_errors.NetworkError("test network failure")
        return object()

    def validate_session(self, _token):
        return self.session_valid


class DoctorTests(unittest.TestCase):
    @mock.patch.object(_domain_cli_doctor, 'writable_location', return_value=(True, Path(".")))
    @mock.patch.object(_domain_cli_doctor, 'module_available', return_value=False)
    @mock.patch.object(_domain_access_registration, 'load_session_token', return_value=None)
    def test_offline_report_requires_first_time_registration(
        self, _token, _module, _writable
    ):
        checks = _domain_cli_doctor.collect_checks(FakeClient(), offline=True)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = _domain_cli_doctor.print_report(checks)
        self.assertEqual(status, 1)
        report = stream.getvalue()
        self.assertIn("NOT READY", report)
        self.assertIn("zju-scatt register", report)
        self.assertIn("[SKIP]", report)

    @mock.patch.object(_domain_cli_doctor, 'writable_location', return_value=(True, Path(".")))
    @mock.patch.object(_domain_cli_doctor, 'module_available', return_value=True)
    @mock.patch.object(_domain_access_registration, 'load_session_token', return_value="secret-token")
    def test_online_report_checks_database_and_session(
        self, _token, _module, _writable
    ):
        checks = _domain_cli_doctor.collect_checks(FakeClient(), offline=False)
        by_name = {check.name: check for check in checks}
        self.assertEqual(by_name["database_connectivity"].status, "pass")
        self.assertEqual(by_name["session_valid"].status, "pass")
        self.assertNotIn("secret-token", repr(checks))

    @mock.patch.object(_domain_cli_doctor, 'writable_location', return_value=(True, Path(".")))
    @mock.patch.object(_domain_cli_doctor, 'module_available', return_value=True)
    @mock.patch.object(_domain_access_registration, 'load_session_token', return_value=None)
    def test_network_failure_is_not_ready(self, _token, _module, _writable):
        checks = _domain_cli_doctor.collect_checks(
            FakeClient(network_error=True),
            offline=False,
        )
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = _domain_cli_doctor.print_report(checks, json_output=True)
        self.assertEqual(status, 1)
        report = json.loads(stream.getvalue())
        self.assertFalse(report["ready"])

    @mock.patch.object(_domain_access_registration, 'load_session_token', return_value=None)
    def test_missing_session_error_contains_first_run_commands(self, _token):
        with self.assertRaises(_domain_errors.ScattError) as raised:
            _domain_access_registration.require_tracking_session(FakeClient())
        message = str(raised.exception)
        self.assertIn("zju-scatt register", message)
        self.assertIn("zju-scatt doctor", message)


if __name__ == "__main__":
    unittest.main()
