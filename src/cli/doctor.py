"""cli / doctor domain implementation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence, Union

import zju_scatt_interface._version as _domain__version
import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.access.endpoints as _domain_access_endpoints
import zju_scatt_interface.access.registration as _domain_access_registration
import zju_scatt_interface.errors as _domain_errors


def _cmd_doctor(args: argparse.Namespace, client: _domain_access_client.ApiClient) -> int:
    return run_doctor(
        client,
        offline=args.offline,
        data_dir=args.data_dir,
        json_output=args.json,
    )


@dataclass(frozen=True)
class DoctorCheck:
    """One diagnostic result without sensitive values."""

    name: str
    status: str
    message: str
    required: bool = False


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def writable_location(path: Path) -> tuple[bool, Path]:
    """Check the nearest existing parent without creating files or directories."""

    candidate = path.expanduser().resolve()
    if candidate.exists() and candidate.is_file():
        candidate = candidate.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.is_dir() and os.access(candidate, os.W_OK), candidate


def collect_checks(
    client: _domain_access_client.ApiClient,
    *,
    offline: bool = False,
    data_dir: Union[str, Path] = "zju_scatt_data",
) -> list[DoctorCheck]:
    """Collect read-only diagnostics used by the CLI and tests."""

    checks: list[DoctorCheck] = []
    python_ok = sys.version_info >= (3, 9)
    checks.append(
        DoctorCheck(
            "python",
            "pass" if python_ok else "fail",
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            required=True,
        )
    )

    config_ok, config_parent = writable_location(_domain_access_registration.CONFIG_FILE)
    checks.append(
        DoctorCheck(
            "config_directory",
            "pass" if config_ok else "fail",
            f"{config_parent} is {'writable' if config_ok else 'not writable'}",
            required=True,
        )
    )

    data_path = Path(data_dir).expanduser()
    data_ok, data_parent = writable_location(data_path)
    checks.append(
        DoctorCheck(
            "data_directory",
            "pass" if data_ok else "fail",
            (
                f"{data_path.resolve()} can be created/used"
                if data_ok
                else f"nearest existing directory {data_parent} is not writable"
            ),
            required=True,
        )
    )

    dependency_specs = (
        ("h5py", "single-particle NetCDF/HDF5 input", "netcdf"),
        ("netCDF4", "NetCDF4 output", "netcdf"),
        ("matplotlib", "plotting", "plot"),
    )
    for module_name, purpose, extra in dependency_specs:
        available = module_available(module_name)
        checks.append(
            DoctorCheck(
                f"dependency_{module_name.lower()}",
                "pass" if available else "warn",
                (
                    f"{module_name} is available for {purpose}"
                    if available
                    else (
                        f"{module_name} is not installed; install "
                        f"'zju-scatt-interface[{extra}]' for {purpose}"
                    )
                ),
            )
        )

    token = _domain_access_registration.load_session_token()
    if token:
        checks.append(
            DoctorCheck(
                "session_configured",
                "pass",
                f"a session is configured ({_domain_access_registration.CONFIG_FILE})",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "session_configured",
                "fail",
                (
                    "registration is required before interface operations; run 'zju-scatt register' "
                    "or 'zju-scatt register --method browser'"
                ),
                required=True,
            )
        )

    if offline or not token:
        checks.append(
            DoctorCheck(
                "database_connectivity",
                "skip",
                (
                    "offline mode requested; network and remote session validation skipped"
                    if offline
                    else "register first; database access is not attempted without registration"
                ),
            )
        )
    else:
        try:
            client.list_page(_domain_access_endpoints.ROOT_PREFIX)
        except _domain_errors.NetworkError as exc:
            checks.append(
                DoctorCheck(
                    "database_connectivity",
                    "fail",
                    f"read-only database listing failed: {exc}",
                    required=True,
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "database_connectivity",
                    "pass",
                    "read-only database listing succeeded",
                    required=True,
                )
            )
            if token:
                valid = client.validate_session(token)
                checks.append(
                    DoctorCheck(
                        "session_valid",
                        "pass" if valid else "fail",
                        (
                            "saved session is valid"
                            if valid
                            else (
                                "saved session is invalid or expired; run "
                                "'zju-scatt register' again"
                            )
                        ),
                        required=True,
                    )
                )
    return checks


def print_report(checks: Sequence[DoctorCheck], *, json_output: bool = False) -> int:
    """Print diagnostics and return 0 when all required checks pass."""

    ready = not any(check.required and check.status == "fail" for check in checks)
    if json_output:
        print(
            json.dumps(
                {
                    "interface_version": _domain__version.__version__,
                    "ready": ready,
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
    else:
        print(f"ZJU-SCATT Interface doctor {_domain__version.__version__}")
        for check in checks:
            print(f"[{check.status.upper():4}] {check.name}: {check.message}")
        warnings = sum(check.status == "warn" for check in checks)
        if ready:
            suffix = f" with {warnings} warning(s)" if warnings else ""
            print(f"Result: READY{suffix}")
        else:
            print("Result: NOT READY")
        print("Help: see docs/INSTALLATION.md or run 'zju-scatt register --help'.")
    return 0 if ready else 1


def run_doctor(
    client: _domain_access_client.ApiClient,
    *,
    offline: bool = False,
    data_dir: Union[str, Path] = "zju_scatt_data",
    json_output: bool = False,
) -> int:
    return print_report(
        collect_checks(client, offline=offline, data_dir=data_dir),
        json_output=json_output,
    )
