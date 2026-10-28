"""Check release documentation without network access or scientific downloads.

Run from any directory: python tools/docs/verify_release_docs.py --report PATH
Uses only the standard library. Registration-dependent smoke checks use a clearly
labelled in-memory test fixture, never a saved or remote session. These checks do
not establish live registration, database availability, or numerical adequacy.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import importlib
import inspect
import io
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from source_checkout import load_source_package

load_source_package(ROOT)

MAINTAINED = ["README.md", *[str(path.relative_to(ROOT)).replace("\\", "/") for path in sorted((ROOT / "docs").rglob("*.md"))]]


def source_hashes():
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src").rglob("*.py"))
    }


def anchors(content):
    without_code = re.sub(r"```.*?```", "", content, flags=re.S)
    found = set(re.findall(r'<a\s+id="([^"]+)"', without_code))
    used = {}
    for heading in re.findall(r"^#{1,6}\s+(.+)$", without_code, re.M):
        slug = re.sub(r"[^\w\- ]", "", heading).lower().replace(" ", "-")
        number = used.get(slug, 0)
        used[slug] = number + 1
        found.add(slug if number == 0 else f"{slug}-{number}")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    before = source_hashes()
    failures = []
    counts = {"documents": 0, "local_links": 0, "heading_links": 0, "python_blocks": 0, "json_blocks": 0, "imports": 0}
    manual_schemes = []

    def forbid_network(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("Network access is forbidden during documentation checks")

    sys.addaudithook(forbid_network)

    for relative in MAINTAINED:
        path = ROOT / relative
        content = path.read_text(encoding="utf-8")
        counts["documents"] += 1
        # Check local files and heading links, including the manual contents.
        targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
        targets += re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', content)
        for target in targets:
            target = target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme:
                continue
            destination = path.parent / unquote(parsed.path) if parsed.path else path
            if parsed.path:
                counts["local_links"] += 1
            if not destination.exists():
                failures.append(f"{relative}: missing link target {target}")
            elif parsed.fragment and destination.suffix == ".md":
                counts["heading_links"] += 1
                if unquote(parsed.fragment) not in anchors(destination.read_text(encoding="utf-8")):
                    failures.append(f"{relative}: missing heading {target}")
        for block in re.findall(r"```json[^\n]*\n(.*?)\n```", content, re.S):
            counts["json_blocks"] += 1
            try:
                value = json.loads(block)
                if relative == "docs/USER_MANUAL.md" and value.get("schema_version"):
                    manual_schemes.append(value)
            except (ValueError, AttributeError) as exc:
                failures.append(f"{relative}: invalid JSON example: {exc}")
        for block in re.findall(r"```python[^\n]*\n(.*?)\n```", content, re.S):
            counts["python_blocks"] += 1
            try:
                tree = ast.parse(block)
            except SyntaxError as exc:
                failures.append(f"{relative}: Python block syntax: {exc}")
                continue
            # Check imports, without executing the example or its calculations.
            for node in ast.walk(tree):
                try:
                    if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("zju_scatt_interface"):
                        module = importlib.import_module(node.module)
                        for alias in node.names:
                            if alias.name != "*":
                                getattr(module, alias.name)
                                counts["imports"] += 1
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith("zju_scatt_interface"):
                                importlib.import_module(alias.name)
                                counts["imports"] += 1
                except (ImportError, AttributeError) as exc:
                    failures.append(f"{relative}: {exc}")

    from zju_scatt_interface.cli.main import main as cli
    from zju_scatt_interface.cli.parser import build_parser
    from build_function_reference import inventory

    functions, classes, unavailable = inventory()
    reference = (ROOT / "docs" / "FUNCTION_REFERENCE.md").read_text(encoding="utf-8")
    counts["referenced_functions"] = len(functions)
    counts["referenced_types"] = len(classes)
    counts["known_unavailable_exports"] = len(unavailable)
    if unavailable:
        failures.append("Declared public exports do not resolve: " + ", ".join(name for name, _error in unavailable))
    for fn, aliases in functions.items():
        public_name = aliases[0].rsplit(".", 1)[1]
        if f"### `{public_name}`" not in reference:
            failures.append(f"Missing function reference entry: {public_name}")
    for cls in classes:
        if f"### `{cls.__name__}`" not in reference:
            failures.append(f"Missing type reference entry: {cls.__name__}")
        for name, raw in cls.__dict__.items():
            if name.startswith("_") or isinstance(raw, property):
                continue
            fn = getattr(cls, name)
            if (inspect.isfunction(fn) or inspect.ismethod(fn)) and f"#### `{cls.__name__}.{name}`" not in reference:
                failures.append(f"Missing method reference entry: {cls.__name__}.{name}")
    for name, _error in unavailable:
        if f"`{name}`" not in reference:
            failures.append(f"Undocumented unresolved export: {name}")

    smoke = []

    def invoke(argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = cli(argv)
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    for argv in [["--help"], ["doctor", "--offline", "--json"]]:
        code, output, error = invoke(argv)
        if argv == ["--help"]:
            valid = code == 0
        else:
            diagnostic = json.loads(output)
            required_failed = any(check["required"] and check["status"] == "fail" for check in diagnostic["checks"])
            valid = code == (1 if required_failed else 0)
        smoke.append({"command": argv, "exit_code": code, "passed": valid})
        if not valid:
            failures.append(f"CLI diagnostic failed: {argv}: {error}")

    # Verify that onboarding is enforced, regardless of the machine's real session.
    with patch("zju_scatt_interface.access.registration.load_session_token", return_value=None):
        code, output, error = invoke(["bulk-opt", "schema", "--json"])
        gate_passed = code == 2 and "registration is required" in error
        smoke.append({"case": "unregistered schema access", "passed": gate_passed})
        if not gate_passed:
            failures.append("Registration prerequisite was not reported")

    # No identity/session is saved; no network call can succeed under the audit hook.
    with patch("zju_scatt_interface.access.registration.load_session_token", return_value="documentation-test-fixture"):
        from zju_scatt_interface.config.scheme import Scheme
        from zju_scatt_interface.psd import gamma_psd, lognormal_psd
        from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble

        for value in manual_schemes:
            scheme = Scheme.from_mapping(value)
            queries = scheme.validate()
            if not queries or scheme.to_dict() != Scheme.from_dict(scheme.to_dict()).to_dict():
                failures.append("Manual scheme normalization/round-trip failed")
            smoke.append({"case": "manual JSON scheme normalized/validated/round-tripped", "query_count": len(queries), "fixture_registration": True})
        # Exercise self-contained numerical-input examples without loading optical data.
        lognormal_psd(rg_um=0.7, sigma_g=1.8, number_concentration_cm3=10, bins=400, normalization="preserve")
        gamma_psd(effective_radius_um=10, effective_variance=0.1, number_concentration_cm3=1, bins=400)
        ensemble = WeightedShapeEnsemble.from_shapes(
            [{"roundness": 2.0, "aspect_ratio": 1.0}, {"roundness": 2.5, "aspect_ratio": 1.5}], [0.4, 0.6])
        if len(ensemble.members) != 2:
            failures.append("Manual joint-shape example expanded unexpectedly")
        smoke.append({"case": "manual analytical PSDs and paired ensemble constructed", "fixture_registration": True})
        code, output, error = invoke(["bulk-opt", "schema", "--particle-type", "super_spheroid_ice", "--json"])
        if code != 0:
            failures.append(f"Fixture schema check failed: {error}")
        else:
            reference = json.loads(output)
            if reference["schema_version"] != "1.0":
                failures.append("Unexpected machine reference schema version")
        smoke.append({"case": "schema with in-memory registration fixture", "exit_code": code})

        for recipe in sorted((ROOT / "configs" / "recipes").glob("*.json")):
            result = {"recipe": str(recipe.relative_to(ROOT)), "fixture_registration": True}
            validate_code, output, error = invoke(["bulk-opt", "validate", str(recipe), "--json"])
            result["validate_exit"] = validate_code
            if validate_code:
                failures.append(f"Recipe validation failed: {recipe.name}: {error}")
            else:
                validation = json.loads(output)
                if validation["status"] != "valid" or not validation["normalized_scheme"]["particles"]:
                    failures.append(f"Incomplete validation report: {recipe.name}")
            plan_code, output, error = invoke(["bulk-opt", "plan", str(recipe), "--dry-run", "--json"])
            result["dry_run_exit"] = plan_code
            if plan_code:
                failures.append(f"Recipe dry-run failed: {recipe.name}: {error}")
            else:
                plan = json.loads(output)
                if plan["status"] != "dry_run" or plan["download_performed"] or not plan["dependency_queries"]:
                    failures.append(f"Unexpected dry-run result: {recipe.name}")
                result["query_count"] = len(plan["dependency_queries"])
            smoke.append(result)

    # Parse documented command options without executing downloads or calculations.
    command_parser = build_parser()
    for argv in [
        ["bulk-opt", "validate", "scheme.json", "--json", "--report", "validation.json"],
        ["bulk-opt", "plan", "scheme.json", "--dry-run", "--json", "--report", "query_preview.json"],
        ["bulk-opt", "plan", "scheme.json", "--workspace", "research_data", "--offline", "--json", "--report", "dependency_plan.json"],
        ["bulk-opt", "build", "scheme.json", "--workspace", "research_data", "--report", "build_report.json"],
        ["retrieve", "--config", "input.py"],
        ["plot", "product.nc", "--kind", "bulk"],
    ]:
        command_parser.parse_args(argv)
        smoke.append({"command": argv, "options_parsed": True, "executed": False})

    import zju_scatt_interface as zsi

    unchanged = before == source_hashes()
    if not unchanged:
        failures.append("Source files changed during documentation checks")
    report = {
        "status": "passed" if not failures else "failed",
        "package_version": zsi.__version__,
        "source_root": str(ROOT),
        "network": "blocked by Python audit hook",
        "source_unchanged_during_checks": unchanged,
        "counts": counts,
        "smoke_checks": smoke,
        "failures": failures,
        "limitations": [
            "Registration-dependent smoke checks used an in-memory fixture; no live session was created or validated.",
            "No optical files were downloaded; no numerical build, NetCDF/HDF5 validation or independent agent evaluation was performed.",
            "Python snippets were syntax/import checked, not executed with real scientific inputs.",
            "Markdown checks verify local file/heading targets; external URLs are not fetched.",
        ],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
