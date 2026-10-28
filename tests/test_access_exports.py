"""Public discovery helpers resolve and delegate to their owning implementation."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import zju_scatt_interface.access as access
from zju_scatt_interface.access import retrieval


class PublicAccessExportsTests(unittest.TestCase):
    def test_every_declared_access_export_resolves(self):
        for name in access.__all__:
            with self.subTest(name=name):
                self.assertIsNotNone(getattr(access, name))

    def test_public_search_uses_existing_selector_and_returns_objects(self):
        from zju_scatt_interface.access import search_data

        self.assertIs(search_data, retrieval.search_data)
        objects = [access.RemoteObject("Single_opt/example.nc", 42)]
        result = SimpleNamespace(objects=objects, stats=access.ScanStats())
        with patch.object(retrieval, "retrieve_sources", return_value=result) as select:
            self.assertIs(search_data(sources=["Single_opt/"], quiet=True), objects)
        select.assert_called_once_with(sources=["Single_opt/"], quiet=True, download=False)

    def test_public_estimate_returns_query_statistics(self):
        from zju_scatt_interface.access import estimate_data

        self.assertIs(estimate_data, retrieval.estimate_data)
        stats = access.ScanStats()
        result = SimpleNamespace(objects=[], stats=stats)
        with patch.object(retrieval, "retrieve_sources", return_value=result) as select:
            self.assertIs(estimate_data(particle_types="ice", max_scan=10), stats)
        select.assert_called_once_with(particle_types="ice", max_scan=10, download=False)


if __name__ == "__main__":
    unittest.main()
