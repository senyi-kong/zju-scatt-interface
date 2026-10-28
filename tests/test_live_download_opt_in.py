"""Network tests that are disabled unless maintainers explicitly opt in."""

import os
import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.access.registration import load_session_token
from zju_scatt_interface.access.retrieval import download_data, search_data

RUN_LIVE = os.environ.get("ZJU_SCATT_RUN_LIVE_TESTS") == "1"
RUN_DOWNLOAD = os.environ.get("ZJU_SCATT_RUN_LIVE_DOWNLOAD") == "1"


@unittest.skipUnless(
    RUN_LIVE,
    "set ZJU_SCATT_RUN_LIVE_TESTS=1 to enable read-only network tests",
)
class LiveCatalogTests(unittest.TestCase):
    def test_public_catalog_returns_scientific_files(self):
        objects = search_data(
            sources=["Single_opt/"],
            extension=["nc"],
            max_scan=200,
            max_files=5,
            timeout=30,
            retries=2,
            quiet=True,
        )
        self.assertTrue(objects)
        self.assertTrue(all(item.name.casefold().endswith(".nc") for item in objects))
        self.assertTrue(all(item.size >= 0 for item in objects))


@unittest.skipUnless(
    RUN_LIVE and RUN_DOWNLOAD,
    "also set ZJU_SCATT_RUN_LIVE_DOWNLOAD=1 for a real tracked download",
)
class LiveDownloadTests(unittest.TestCase):
    def test_one_small_file_downloads_with_tracking_session(self):
        session = load_session_token()
        if not session:
            self.skipTest("no local registration session is configured")
        maximum_bytes = int(
            os.environ.get("ZJU_SCATT_LIVE_MAX_BYTES", str(2 * 1024 * 1024))
        )
        objects = search_data(
            sources=["Single_opt/"],
            extension=["nc"],
            max_file_size=maximum_bytes,
            max_scan=2000,
            max_files=1,
            timeout=30,
            retries=2,
            quiet=True,
        )
        if not objects:
            self.skipTest(
                f"no NetCDF file <= {maximum_bytes} bytes in first 2000 objects"
            )
        with tempfile.TemporaryDirectory() as directory:
            results = download_data(
                objects,
                output_dir=directory,
                workers=1,
                session=session,
                quiet=True,
            )
            self.assertEqual(len(results), 1)
            self.assertTrue(Path(results[0].target).is_file())
            self.assertEqual(
                Path(results[0].target).stat().st_size, objects[0].size
            )


if __name__ == "__main__":
    unittest.main()
