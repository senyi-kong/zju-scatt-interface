"""Exercise the real CLI JSON schema using a saved sea-salt catalog."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.manifests as _domain_access_manifests
import zju_scatt_interface.access.models as _domain_access_models
from zju_scatt_interface.cli.main import main

REQUEST = Path(__file__).resolve().parents[2] / "test_zju_scatt/user_test_local/request.json"


class JsonRetrievalExampleTests(unittest.TestCase):
    @unittest.skipUnless(REQUEST.is_file(), "Workspace JSON example not installed")
    def test_real_json_request_selects_wavelength_neighbors_without_network_or_download(self):
        self.assertTrue(json.loads(REQUEST.read_text())["download"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            objects = [
                _domain_access_models.RemoteObject(
                    f"Single_opt/coated_super_spheroid_seasalt/L1_coated_super_spheroid_seasalt_wl_{w}_um_ref_1.5_0.01_water_1.3_0.001.nc",
                    size=10,
                )
                for w in (1.0, 2.0)
            ]
            manifest = root / "catalog.jsonl"
            _domain_access_manifests.write_manifest(objects, manifest, "jsonl")
            selected = root / "selected.jsonl"
            with (
                patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
                patch.object(
                    _domain_access_download,
                    'download_selected_objects',
                    side_effect=AssertionError("Download forbidden"),
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = main(
                    [
                        "retrieve",
                        "--config",
                        str(REQUEST),
                        "--manifest",
                        str(manifest),
                        "--no-download",
                        "-d",
                        str(root / "data"),
                        "--manifest-output",
                        str(selected),
                        "--operation-log",
                        str(root / "operation.log"),
                        "--quiet",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(
                {o.key for o in _domain_access_manifests.load_manifest(selected)}, {o.key for o in objects}
            )
            self.assertTrue((root / "operation.log").is_file())
            self.assertFalse((root / "data").exists())
