"""Comprehensive local release-readiness validation without publication.

Role:
    Validation demonstration

Inputs:
    Local package source and dependencies needed for builds, a clean virtual environment,
    installation and tests.

Outputs:
    Local distribution artifacts, isolated-install checks, JSON reports and figures; nothing
    is published.

Run:
    From the package root: python examples/example_16_phase11_release_readiness_validation.py
    --help

Notes:
    This script intentionally contains testing scaffolding. It is not required to generate
    production optical data; synthetic optics are not representative database coefficients.

Original example details:
    Comprehensive local release-readiness validation without publication.

    This script builds artifacts and creates a new clean virtual environment. It never
    uploads, publishes, pushes, or creates a release.

    Run from the project root:

        python examples/example_16_phase11_release_readiness_validation.py         --output-dir phase11_validation_output
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import venv
import zipfile
from pathlib import Path


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 300,
) -> dict[str, object]:
    """Run one local validation command and retain concise diagnostics."""

    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "passed": completed.returncode == 0,
    }


def _artifact_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


def _build_figure(path: Path, report: dict[str, object]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    commands = report["commands"]
    labels = [item["name"] for item in commands]
    values = [1 if item["passed"] else 0 for item in commands]
    colors = ["#55A868" if value else "#C44E52" for value in values]
    figure, axes = plt.subplots(1, 2, figsize=(13, 6), constrained_layout=True)
    axes[0].barh(labels, values, color=colors)
    axes[0].set(
        xlim=(0, 1.05),
        xlabel="Pass = 1",
        title="Release-readiness command gates",
    )
    axes[0].grid(True, axis="x", alpha=0.25)

    coverage = report["coverage"]
    coverage_labels = [
        "Profiles",
        "Profile vertical slices",
        "Output formats",
        "Python versions in CI",
        "Operating systems in CI",
    ]
    coverage_values = [
        coverage["registered_profiles"],
        coverage["fixture_profile_slices"],
        coverage["output_formats"],
        coverage["ci_python_versions"],
        coverage["ci_operating_systems"],
    ]
    axes[1].bar(coverage_labels, coverage_values, color="#4C72B0")
    axes[1].tick_params(axis="x", rotation=28)
    axes[1].set(
        ylabel="Count",
        title="Scientific and environment coverage",
    )
    axes[1].grid(True, axis="y", alpha=0.25)
    figure.suptitle(
        "ZJU-SCATT Phase 11 — validated locally, not published",
        fontsize=15,
    )
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_validation(output_dir: Path) -> dict[str, object]:
    """Run local quality gates and report artifact/install readiness.

    This is intentionally a local check.  It builds artifacts for inspection,
    but never uploads or publishes them.
    """

    project = Path(__file__).parents[1]
    output_dir.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    # These gates cover syntax, lint, tests, local packaging, and metadata.
    # They are recorded individually so one failure remains diagnosable.
    command_specs = [
        (
            "compile",
            [python, "-m", "compileall", "-q", "src", "tests", "examples"],
            180,
        ),
        (
            "ruff",
            [python, "-m", "ruff", "check", "src", "tests", "examples"],
            180,
        ),
        (
            "unit_and_integration_tests",
            [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
            600,
        ),
        ("build_sdist_and_wheel", [python, "-m", "build"], 600),
        ("artifact_metadata", [python, "-m", "twine", "check", "dist/*"], 180),
    ]
    commands: list[dict[str, object]] = []
    for name, command, timeout in command_specs:
        result = _run(command, cwd=project, timeout=timeout)
        result["name"] = name
        commands.append(result)

    # Inspect the newest local artifacts and verify that core modules,
    # documentation, examples, and trusted test data are packaged.
    distributions = sorted(
        (project / "dist").glob("zju_scatt_interface-0.9.0*"),
        key=lambda item: item.stat().st_mtime,
    )
    wheel = next(
        (item for item in reversed(distributions) if item.suffix == ".whl"),
        None,
    )
    sdist = next(
        (item for item in reversed(distributions) if item.name.endswith(".tar.gz")),
        None,
    )
    artifact_checks: dict[str, object] = {
        "wheel": str(wheel) if wheel else None,
        "sdist": str(sdist) if sdist else None,
        "passed": False,
        "missing": [],
    }
    if wheel and sdist:
        wheel_members = _artifact_members(wheel)
        sdist_members = _artifact_members(sdist)
        required_wheel = (
            "zju_scatt_interface/__init__.py",
            "zju_scatt_interface/cli.py",
            "zju_scatt_interface/optical_models.py",
            "zju_scatt_interface/schemes/reference.py",
        )
        required_sdist_fragments = (
            "configs/recipes/ice_multi_temperature_bulk.json",
            "docs/PARTICLE_PARAMETER_REFERENCE.md",
            "examples/data/observed_psd_example.csv",
            "tests/data/trusted_bulk_reference_v1.json",
        )
        missing = [name for name in required_wheel if name not in wheel_members]
        missing.extend(
            fragment
            for fragment in required_sdist_fragments
            if not any(member.endswith(fragment) for member in sdist_members)
        )
        artifact_checks["missing"] = missing
        artifact_checks["passed"] = not missing

    clean_install: dict[str, object]
    if wheel is None:
        clean_install = {
            "name": "clean_wheel_install",
            "passed": False,
            "error": "wheel was not built",
        }
    else:
        # Install the wheel into a fresh environment without dependencies, then
        # run import and offline-CLI smoke tests.  This catches missing package
        # files while keeping the check independent of external services.
        stamp = time.strftime("%Y%m%d_%H%M%S")
        environment = output_dir / f"clean_install_{stamp}"
        venv.EnvBuilder(with_pip=True).create(environment)
        clean_python = (
            environment / "Scripts" / "python.exe"
            if os.name == "nt"
            else environment / "bin" / "python"
        )
        install = _run(
            [
                str(clean_python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                str(wheel),
            ],
            cwd=project,
            timeout=300,
        )
        smoke = _run(
            [
                str(clean_python),
                "-c",
                (
                    "import zju_scatt_interface as z; "
                    "assert z.__version__ == '0.9.0'; "
                    "assert len(z.list_particle_profiles()) == 8"
                ),
            ],
            cwd=project,
            timeout=60,
        )
        cli = _run(
            [
                str(clean_python),
                "-m",
                "zju_scatt_interface",
                "doctor",
                "--offline",
                "--json",
            ],
            cwd=project,
            timeout=60,
        )
        clean_install = {
            "name": "clean_wheel_install",
            "environment": str(environment),
            "install": install,
            "import_smoke": smoke,
            "cli_smoke": cli,
            "passed": all(item["passed"] for item in (install, smoke, cli)),
        }
    commands.append(
        {
            "name": "artifact_contents",
            "passed": artifact_checks["passed"],
            "returncode": 0 if artifact_checks["passed"] else 1,
            "duration_seconds": 0,
            "stdout_tail": json.dumps(artifact_checks, indent=2),
            "stderr_tail": "",
        }
    )
    commands.append(
        {
            "name": "clean_wheel_install",
            "passed": clean_install["passed"],
            "returncode": 0 if clean_install["passed"] else 1,
            "duration_seconds": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }
    )

    # Extract the unittest count for the final human-readable summary.
    test_output = next(
        (item["stderr_tail"] for item in commands if item["name"] == "unit_and_integration_tests"),
        "",
    )
    match = re.search(r"Ran (\d+) tests", test_output)
    report = {
        "status": ("passed" if all(item["passed"] for item in commands) else "failed"),
        "published": False,
        "publication_actions_performed": [],
        "python": sys.version,
        "platform": sys.platform,
        "test_count": int(match.group(1)) if match else None,
        "commands": commands,
        "artifact_checks": artifact_checks,
        "clean_install": clean_install,
        "optional_dependencies": {
            name: importlib.util.find_spec(name) is not None
            for name in ("h5py", "netCDF4", "matplotlib")
        },
        "external_state": {
            "local_l1_mounted": Path(r"X:\L1_single_scattering_property").exists(),
            "live_tests_enabled": (os.environ.get("ZJU_SCATT_RUN_LIVE_TESTS") == "1"),
            "live_download_enabled": (os.environ.get("ZJU_SCATT_RUN_LIVE_DOWNLOAD") == "1"),
        },
        "coverage": {
            "registered_profiles": 8,
            "fixture_profile_slices": 8,
            "output_formats": 2,
            "ci_python_versions": 5,
            "ci_operating_systems": 3,
        },
    }
    # Keep the plot and JSON report beside all other validation outputs; neither
    # artifact is used to decide publication, because publication is out of
    # scope for this example.
    figure = output_dir / "phase11_release_readiness.png"
    _build_figure(figure, report)
    report["figure"] = str(figure)
    report_path = output_dir / "phase11_release_readiness_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report["report"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse the output directory and run local release-readiness checks."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("phase11_validation_output"),
    )
    args = parser.parse_args(argv)
    report = run_validation(args.output_dir)
    summary = {
        "status": report["status"],
        "published": report["published"],
        "test_count": report["test_count"],
        "report": report["report"],
        "figure": report["figure"],
        "clean_install_passed": report["clean_install"]["passed"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
