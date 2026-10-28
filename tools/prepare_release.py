"""Build and inspect a fresh local release candidate; never upload or delete files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stage = output / "source"
    stage.mkdir()
    for name in ("pyproject.toml", "setup.py", "MANIFEST.in", "README.md", "LICENSE", "CHANGELOG.md"):
        shutil.copy2(project / name, stage / name)
    for directory, suffixes in (
        ("src", {".py", ".csv"}),
        ("docs", {".md", ".png"}), ("configs", {".json", ".py"}),
        ("examples", {".py", ".csv", ".json", ".md", ".sh"}),
        ("tests", {".py", ".json"}),
    ):
        for path in sorted((project / directory).rglob("*")):
            if directory == "examples" and "downloads" in path.relative_to(project / directory).parts:
                continue
            if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
                destination = stage / path.relative_to(project)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
    dist = output / "dist"
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(dist)],
                   cwd=stage, check=True)
    artifacts = sorted(dist.iterdir())
    subprocess.run([sys.executable, "-m", "twine", "check", "--strict",
                    *map(str, artifacts)], check=True)
    expected = {
        "zju_scatt_interface/" + path.relative_to(stage / "src").as_posix(): path.read_bytes()
        for path in (stage / "src").rglob("*")
        if path.is_file() and path.suffix in {".py", ".csv"}
    }
    records = []
    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                contents = {name: archive.read(name) for name in archive.namelist()}
            packaged = {name: data for name, data in contents.items()
                        if name.startswith("zju_scatt_interface/")}
            if packaged != expected:
                raise RuntimeError("Wheel contents differ from the clean source snapshot")
        else:
            with tarfile.open(artifact) as archive:
                contents = {member.name.split("/", 1)[1]: archive.extractfile(member).read()
                            for member in archive.getmembers() if member.isfile()}
            for name, data in expected.items():
                source_name = "src/" + name.removeprefix("zju_scatt_interface/")
                if contents.get(source_name) != data:
                    raise RuntimeError("Source distribution mismatch: " + name)
            for name in ("CHANGELOG.md", "tests/test_refractive_index.py",
                         "docs/assets/LOGO_ZJU_SCATT.png",
                         "configs/bulk_scheme.example.py",
                         "tests/data/trusted_bulk_reference_v1.json"):
                if name not in contents:
                    raise RuntimeError("Missing source distribution file: " + name)
        if any(name.startswith("tools/") or "/tools/" in name for name in contents):
            raise RuntimeError("Developer tools must not be included in PyPI artifacts")
        records.append({"file": artifact.name, "bytes": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "published": False,
        "artifact_content_check": "passed", "twine_check": "passed",
        "developer_tools_in_artifacts": False,
        "artifacts": records,
        "data_sha256": {name: hashlib.sha256(data).hexdigest()
                        for name, data in expected.items() if name.endswith(".csv")},
    }
    (output / "artifact_report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                 encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
