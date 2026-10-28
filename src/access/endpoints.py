"""access / endpoints domain implementation."""

from __future__ import annotations

import urllib.parse

from zju_scatt_interface._version import __organization__, __version__

SITE_URL = "https://zju_radiation.deep-time.org"
SITE_HOST = urllib.parse.urlparse(SITE_URL).hostname or "zju_radiation.deep-time.org"
DOWNLOAD_PAGE_URL = f"{SITE_URL}/download"
TRACKING_API_URL = f"{SITE_URL}/api/download"
# The website is normally reached through its DNS name.  Keep the IP fallback
# separate so primary-host URLs remain stable for compatibility and can be
# retried transparently when DNS or the primary host is unavailable.  The
# server redirects HTTP to HTTPS; using HTTPS here preserves POST methods for
# registration and download-tracking requests.
BACKUP_SITE_URL = "https://47.242.92.150"
BACKUP_SITE_HOST = urllib.parse.urlparse(BACKUP_SITE_URL).hostname or "47.242.92.150"
BACKUP_DOWNLOAD_PAGE_URL = f"{BACKUP_SITE_URL}/download"
BACKUP_TRACKING_API_URL = f"{BACKUP_SITE_URL}/api/download"
OSS_BASE_URL = "https://zjugis-deeptimeorg-prod-global.oss-cn-hongkong.aliyuncs.com"
LIST_API_URL = f"{OSS_BASE_URL}/"
ROOT_PREFIX = (
    "data-service-dev-repo/original_data/"
    "database_11_ optical-properties-of-aerosol-clouds/"
    "Optics_data/BAMS/"
)
USER_AGENT = f"ZJU-SCATT-Interface/{__version__} (+{SITE_URL}; {__organization__})"


def backup_site_url(value: str) -> str:
    """Map a primary website URL to the configured IP fallback.

    Non-website URLs, including the verified OSS object endpoint, are returned
    unchanged so the fallback cannot silently redirect data transfers to the
    website host.
    """

    parsed = urllib.parse.urlsplit(value)
    if (parsed.hostname or "").casefold() != SITE_HOST.casefold():
        return value
    backup = urllib.parse.urlsplit(BACKUP_SITE_URL)
    return urllib.parse.urlunsplit(
        (backup.scheme, backup.netloc, parsed.path, parsed.query, parsed.fragment)
    )
