"""Contract conflicts and an isolated, end-to-end extension acceptance test."""

import os
import subprocess
import sys
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path

from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry, TypeRegistry


class ExtensionRegistryTests(unittest.TestCase):
    def test_alias_conflict_is_atomic_and_does_not_replace_an_entry(self):
        registry = NamedRegistry("test")
        original = object()
        registry.register("first", original, aliases=("alias",))
        with self.assertRaises(ExtensionError):
            registry.register("second", object(), aliases=("alias", "new_alias"))
        self.assertIs(registry.get("ALIAS"), original)
        self.assertFalse(registry.contains("second"))
        self.assertFalse(registry.contains("new_alias"))
        with self.assertRaises(ExtensionError):
            registry.register("first", object())

    def test_type_dispatch_inheritance_and_ambiguous_virtual_bases(self):
        registry = TypeRegistry("test")

        class Base:
            pass

        class Child(Base):
            pass

        registry.register(Base, lambda value: "base")
        self.assertEqual(registry(Child()), "base")
        registry.register(Child, lambda value: "child")
        self.assertEqual(registry(Child()), "child")
        with self.assertRaises(ExtensionError):
            registry.register(Child, lambda value: "replacement")
        with self.assertRaises(TypeError):
            registry(object())

        class Ambiguous:
            pass

        Mapping.register(Ambiguous)
        Sequence.register(Ambiguous)
        registry.register(Mapping, lambda value: "mapping")
        registry.register(Sequence, lambda value: "sequence")
        with self.assertRaises(ExtensionError):
            registry(Ambiguous())

    def test_new_modules_extend_real_workflows_without_changing_existing_files(self):
        root = Path(__file__).resolve().parents[1]
        output = root.parent / "output/extensions_acceptance_20261027"
        script = "from tests.extension_probe import run_probe; run_probe(" + repr(str(output)) + ")"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            env={**os.environ, "ZJU_SCATT_SESSION": "extension-acceptance"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Extension acceptance passed", result.stdout)

    def test_virtual_mapping_handler_precedes_object_fallback(self):
        registry = TypeRegistry("test")
        registry.register(object, lambda value: "object")
        registry.register(Mapping, lambda value: "mapping")
        self.assertEqual(registry({}), "mapping")
        self.assertEqual(registry(object()), "object")


if __name__ == "__main__":
    unittest.main()
