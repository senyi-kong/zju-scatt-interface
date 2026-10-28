"""Registration prerequisites, onboarding and persistent session management."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import webbrowser
from argparse import Namespace
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Iterable, Optional

from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.endpoints import (
    DOWNLOAD_PAGE_URL,
)
from zju_scatt_interface.errors import ScattError

operation_session = ContextVar("zju_scatt_operation_session", default=None)


def registration_required(function):
    """Require an existing registration, without prompting or registering again."""

    @wraps(function)
    def registered_operation(*args, **kwargs):
        pass

        token = require_registration(kwargs.get("session"))
        context = operation_session.set(token)
        try:
            return function(*args, **kwargs)
        finally:
            operation_session.reset(context)

    return registered_operation


def check_cli_registration(args):
    """Leave onboarding/help available; retrieve resolves session from its config."""
    pass

    if args.command in {"register", "session", "doctor", "retrieve"}:
        return None
    return require_registration(getattr(args, "session", None))


CONFIG_FILE = Path.home() / ".zju_scatt" / "session.json"


COUNTRY_NAMES = {
    "CN": "China",
    "HK": "Hong Kong SAR",
    "MO": "Macao SAR",
    "TW": "Taiwan",
    "US": "United States",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "JP": "Japan",
    "KR": "South Korea",
    "IN": "India",
    "AU": "Australia",
    "CA": "Canada",
    "SG": "Singapore",
    "MY": "Malaysia",
    "TH": "Thailand",
    "VN": "Vietnam",
    "ID": "Indonesia",
    "PH": "Philippines",
    "RU": "Russia",
    "IT": "Italy",
    "ES": "Spain",
    "NL": "Netherlands",
    "CH": "Switzerland",
    "SE": "Sweden",
    "NO": "Norway",
    "FI": "Finland",
    "DK": "Denmark",
    "BE": "Belgium",
    "AT": "Austria",
    "PL": "Poland",
    "CZ": "Czechia",
    "PT": "Portugal",
    "IE": "Ireland",
    "GR": "Greece",
    "TR": "Turkey",
    "IL": "Israel",
    "SA": "Saudi Arabia",
    "AE": "United Arab Emirates",
    "EG": "Egypt",
    "ZA": "South Africa",
    "NG": "Nigeria",
    "KE": "Kenya",
    "BR": "Brazil",
    "AR": "Argentina",
    "CL": "Chile",
    "MX": "Mexico",
    "CO": "Colombia",
    "NZ": "New Zealand",
    "PK": "Pakistan",
    "BD": "Bangladesh",
    "IR": "Iran",
    "IQ": "Iraq",
    "UA": "Ukraine",
    "RO": "Romania",
    "HU": "Hungary",
    "OTHER": "Other / Not listed",
}


COUNTRY_ALIASES = {name.casefold(): code for code, name in COUNTRY_NAMES.items()}


COUNTRY_ALIASES.update(
    {
        "uk": "GB",
        "u.k.": "GB",
        "great britain": "GB",
        "usa": "US",
        "u.s.": "US",
        "united states of america": "US",
        "hong kong": "HK",
        "macao": "MO",
        "macau": "MO",
        "south korea": "KR",
        "republic of korea": "KR",
        "russian federation": "RU",
        "czech republic": "CZ",
        "uae": "AE",
        "other": "OTHER",
        "not listed": "OTHER",
    }
)


DATASET_NEED_ALIASES = {
    "single": "single_optical",
    "single_optical": "single_optical",
    "single optical property": "single_optical",
    "bulk": "bulk_optical",
    "bulk_optical": "bulk_optical",
    "bulk optical property": "bulk_optical",
    "ml": "ml_model",
    "machine learning": "ml_model",
    "machine learning model": "ml_model",
    "ml_model": "ml_model",
}


def normalize_country(value: str) -> str:
    """Return a country/region value accepted by the website selector."""
    cleaned = value.strip()
    if not cleaned:
        raise ScattError("Country/region is required")
    upper = cleaned.upper()
    if upper in COUNTRY_NAMES:
        return upper
    alias = COUNTRY_ALIASES.get(cleaned.casefold())
    if alias:
        return alias
    raise ScattError(
        f"Unknown country/region {value!r}. Use the two-letter website code "
        "(for example CN, US, or GB), or OTHER."
    )


def normalize_dataset_needs(values: Iterable[str]) -> list[str]:
    """Normalize website dataset-interest labels while preserving order."""
    result: list[str] = []
    for raw in values:
        for part in raw.split(","):
            cleaned = part.strip().casefold()
            if not cleaned:
                continue
            normalized = DATASET_NEED_ALIASES.get(cleaned)
            if normalized is None:
                raise ScattError(
                    f"Unknown dataset interest {part.strip()!r}. Use single, bulk, or ml."
                )
            if normalized not in result:
                result.append(normalized)
    return result


def print_registration_debug(payload: dict) -> None:
    """Print the request structure without disclosing personal field values."""
    safe = {
        "name": "<provided>" if payload.get("name") else "<omitted>",
        "organization": "<provided>" if payload.get("organization") else "<missing>",
        "country": payload.get("country", "<missing>"),
        "email": "<provided>" if payload.get("email") else "<omitted>",
        "datasetNeeds": payload.get("datasetNeeds", "<omitted>"),
        "intendedUse": "<provided>" if payload.get("intendedUse") else "<omitted>",
        "consent": payload.get("consent", False),
    }
    print(
        "Registration request (personal values redacted):\n" + json.dumps(safe, indent=2),
        file=sys.stderr,
    )


def graphical_browser_available() -> bool:
    """Return whether automatic browser launch is likely to work.

    ``webbrowser.open`` can report success merely because it started
    ``xdg-open``; on headless Linux that helper then fails asynchronously.
    Check for a GUI session and an actual browser executable first.
    """
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    if not sys.platform.startswith("linux"):
        return bool(os.environ.get("BROWSER"))
    if os.environ.get("BROWSER"):
        return True
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    candidates = (
        "firefox",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "brave-browser",
        "microsoft-edge",
        "epiphany",
    )
    return any(shutil.which(candidate) for candidate in candidates)


def offer_registration_page(*, no_open: bool = False) -> None:
    """Print the registration URL and open it only when a GUI is available."""
    print(f"Open the ZJU-SCATT registration page:\n{DOWNLOAD_PAGE_URL}\n")
    if no_open or not graphical_browser_available():
        print(
            "Automatic browser opening is unavailable in this terminal. "
            "Open the URL manually in any desktop browser."
        )
        return
    try:
        if not webbrowser.open(DOWNLOAD_PAGE_URL, new=2):
            print("The browser did not open automatically; use the URL above.")
    except webbrowser.Error:
        print("The browser did not open automatically; use the URL above.")


def load_session_token(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit
    environment = os.environ.get("ZJU_SCATT_SESSION")
    if environment:
        return environment
    try:
        payload = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        token = payload.get("sessionToken") if isinstance(payload, dict) else None
        return token if isinstance(token, str) and token else None
    except (OSError, json.JSONDecodeError):
        return None


def save_session_token(token: str, metadata: Optional[dict] = None) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sessionToken": token,
        "savedAt": datetime.now(timezone.utc).isoformat(),
        **(metadata or {}),
    }
    CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def require_registration(explicit_token: Optional[str] = None) -> str:
    """Reuse saved registration for every operation, including offline work.

    Registration is a client-side onboarding prerequisite. The public OSS
    service itself remains public; tracked downloads still validate the session.
    No network request or repeat registration is performed by this local check.
    """
    pass

    token = load_session_token(explicit_token or operation_session.get())
    if isinstance(token, str) and token.strip():
        return token.strip()
    raise ScattError(
        "ZJU-SCATT registration is required before using the interface.\n"
        "First-time setup: run 'zju-scatt register', then 'zju-scatt doctor'.\n"
        "Registration is saved locally and reused automatically on later runs; "
        "you do not need to register again.\n"
        f"Session file: {CONFIG_FILE}\n"
        "An existing registered session can be imported with 'zju-scatt session --save TOKEN'."
    )


def require_tracking_session(
    client: ApiClient,
    *,
    explicit_token: Optional[str] = None,
    no_track: bool = False,
) -> Optional[str]:
    """Apply the website's token gate before a download operation."""
    token = require_registration(explicit_token)
    if no_track:
        return None
    if not client.validate_session(token):
        raise ScattError(
            "The saved ZJU-SCATT session is invalid or expired.\n"
            "Import a current registered token with 'zju-scatt session --save TOKEN'. "
            "If a replacement registration is necessary, explicitly clear the unusable "
            "session with 'zju-scatt session --clear' before running 'zju-scatt register'. "
            "Then run 'zju-scatt doctor'."
        )
    return token


def register_interactively(client: ApiClient, args: argparse.Namespace) -> str:
    existing = load_session_token()
    if isinstance(existing, str) and existing.strip():
        print("Already registered. Reusing the saved session; no registration form is needed.")
        return existing.strip()
    if not sys.stdin.isatty() and not (args.organization and args.country and args.consent):
        raise ScattError(
            "Non-interactive registration needs --organization, --country, and --consent"
        )
    minimal = bool(args.minimal)
    name = (
        None if minimal else (args.name or input("Name or username (optional): ")).strip() or None
    )
    organization = (args.organization or input("Organization (required): ")).strip()
    country_input = (
        args.country
        or input("Country/region code or English name, e.g. CN or China (required): ").strip()
    )
    country = normalize_country(country_input)
    email = None if minimal else (args.email or input("Email (optional): ")).strip() or None
    if minimal:
        dataset_needs: list[str] = []
    elif args.dataset_need:
        dataset_needs = normalize_dataset_needs(args.dataset_need)
    else:
        interests = input(
            "Dataset interest (optional; comma-separated: single, bulk, ml): "
        ).strip()
        dataset_needs = normalize_dataset_needs([interests]) if interests else []
    intended_use = (
        None
        if minimal
        else (args.intended_use or input("Intended use (optional): ")).strip() or None
    )
    consent = args.consent
    if not consent:
        answer = (
            input("Consent to use this information for dataset usage and impact reporting? [y/N] ")
            .strip()
            .lower()
        )
        consent = answer in {"y", "yes"}
    if not organization or not country or not consent:
        raise ScattError("Organization, country/region, and consent are required")
    payload = {
        "name": name,
        "organization": organization,
        "country": country,
        "email": email,
        "datasetNeeds": dataset_needs or None,
        "intendedUse": intended_use,
        "consent": True,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    if args.debug:
        print_registration_debug(payload)
    token = client.register(payload)
    save_session_token(token, {"organization": organization, "country": country})
    return token


def register_direct(
    organization: str,
    country: str,
    *,
    consent: bool,
    name: Optional[str] = None,
    email: Optional[str] = None,
    intended_use: Optional[str] = None,
    dataset_needs: Iterable[str] = (),
    minimal: bool = False,
    client: Optional[ApiClient] = None,
) -> str:
    """Register through the API and save the returned token locally."""

    args = Namespace(
        organization=organization,
        country=country,
        consent=consent,
        name=name,
        email=email,
        intended_use=intended_use,
        dataset_need=list(dataset_needs),
        minimal=minimal,
        debug=False,
    )
    return register_interactively(client or ApiClient(), args)


def import_browser_token(token: str, *, client: Optional[ApiClient] = None) -> None:
    """Validate and save a token copied from the website registration flow."""

    clean_token = token.strip()
    if not clean_token:
        raise ValueError("token cannot be empty")
    api = client or ApiClient()
    if not api.validate_session(clean_token):
        raise ValueError("the browser token is invalid or expired")
    save_session_token(clean_token, {"source": "browser"})
