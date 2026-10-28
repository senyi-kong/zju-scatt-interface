"""Enforce physical ownership and the intentionally breaking public API."""
import ast
import importlib
import unittest
from pathlib import Path

import zju_scatt_interface as scatt


class DomainArchitectureTests(unittest.TestCase):
    def test_only_entry_points_and_shared_metadata_remain_at_root(self):
        root = Path(scatt.__file__).parent
        self.assertEqual({p.name for p in root.glob("*.py")},
            {"__init__.py", "__main__.py", "api.py", "_version.py", "errors.py"})
        for name in ("access", "config", "sources", "optics", "psd", "bulk", "io", "plotting", "cli"):
            self.assertTrue((root / name / "__init__.py").is_file())

    def test_no_legacy_module_or_export_fallback(self):
        self.assertNotIn("__getattr__", vars(scatt))
        for name in ("_engine", "compat", "schemes", "bulk_workflow", "analytical_psd", "applications", "commands"):
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module("zju_scatt_interface." + name)
        for name in ("BulkOpticalResult", "BulkCalculationResult", "BulkSchemeBuildResult",
                     "run_retrieval", "retrieve_data", "write_bulk_scheme_netcdf"):
            self.assertFalse(hasattr(scatt, name), name)

    def test_types_are_defined_in_their_actual_domains(self):
        expected = {"Scheme":"config.scheme", "BulkOptics":"optics.models",
                    "PopulationResult":"bulk.models", "BulkDataset":"bulk.models",
                    "SizeDistribution":"psd.models", "BulkGrid":"bulk.grid",
                    "DependencyPlan":"sources.planning"}
        for name, module in expected.items():
            self.assertEqual(getattr(scatt, name).__module__, "zju_scatt_interface." + module)
            self.assertEqual(getattr(scatt, name).__name__, name)
        self.assertEqual(len(scatt.__all__), 26)

    def test_every_module_imports_and_lower_layers_do_not_import_cli(self):
        root = Path(scatt.__file__).parent
        for path in root.rglob("*.py"):
            if path.name == "__main__.py":
                continue
            relative = path.relative_to(root)
            module = "zju_scatt_interface." + str(relative.with_suffix("")).replace("/", ".").replace(chr(92), ".")
            if module.endswith(".__init__"):
                module = module[:-9]
            importlib.import_module(module)
            if relative.parts[0] in {"access", "config", "sources", "optics", "psd", "bulk", "io", "plotting"}:
                for node in ast.walk(ast.parse(path.read_text())):
                    names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                    self.assertFalse(any(n.startswith("zju_scatt_interface.cli") for n in names), path)


if __name__ == "__main__":
    unittest.main()
