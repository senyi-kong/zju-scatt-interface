"""HTTP/OSS client, TLS handling, retries and listing-page parsing."""

from __future__ import annotations

import http.cookiejar
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.response
import xml.etree.ElementTree as ET
from typing import Callable, Iterator, Optional

from zju_scatt_interface.access.endpoints import (
    BACKUP_SITE_HOST,
    LIST_API_URL,
    OSS_BASE_URL,
    SITE_HOST,
    TRACKING_API_URL,
    USER_AGENT,
    backup_site_url,
)
from zju_scatt_interface.access.models import ListPage, RemoteDirectory, RemoteObject
from zju_scatt_interface.errors import NetworkError, ScattError


class ApiClient:
    """Small retrying client for the website API and public OSS bucket."""

    def __init__(
        self,
        timeout: float = 30.0,
        retries: int = 3,
        insecure: bool = False,
        show_tls_warning: bool = True,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.insecure = insecure
        self.show_tls_warning = show_tls_warning
        self.cookie_jar = http.cookiejar.CookieJar()
        self.unverified_context = ssl._create_unverified_context()
        self.opener = self._build_opener(self.unverified_context if insecure else None)
        # The current website certificate does not cover its public hostname.
        # Match requests' verify=False for that host only; OSS remains verified.
        self.site_opener = self.opener if insecure else self._build_opener(self.unverified_context)
        self._site_tls_warning_emitted = False

    def _build_opener(self, context: Optional[ssl.SSLContext]) -> urllib.request.OpenerDirector:
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        ]
        if context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=context))
        return urllib.request.build_opener(*handlers)

    def _opener_for_url(self, url: str) -> urllib.request.OpenerDirector:
        host = urllib.parse.urlparse(url).hostname
        if host and host.casefold() in {
            SITE_HOST.casefold(),
            BACKUP_SITE_HOST.casefold(),
        }:
            if not self.insecure and self.show_tls_warning and not self._site_tls_warning_emitted:
                print(
                    "TLS note: website API verification bypassed (certificate "
                    "mismatch); OSS transfers remain verified.",
                    file=sys.stderr,
                )
                self._site_tls_warning_emitted = True
            return self.site_opener
        return self.opener

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        data: Optional[bytes] = None,
        allow_404: bool = False,
    ) -> urllib.response.addinfourl:
        from zju_scatt_interface.access.registration import require_registration
        from zju_scatt_interface.errors import NetworkError

        if urllib.parse.urlparse(url).hostname == urllib.parse.urlparse(OSS_BASE_URL).hostname:
            require_registration(getattr(self, "registration_token", None))
        request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if headers:
            request_headers.update(headers)
        candidate_urls = [url]
        fallback = backup_site_url(url)
        if fallback != url:
            candidate_urls.append(fallback)

        failures: list[str] = []
        for candidate_url in candidate_urls:
            request = urllib.request.Request(
                candidate_url,
                data=data,
                headers=request_headers,
                method=method,
            )
            last_error: Optional[BaseException] = None
            for attempt in range(self.retries + 1):
                try:
                    return self._opener_for_url(candidate_url).open(request, timeout=self.timeout)
                except urllib.error.HTTPError as exc:
                    if allow_404 and exc.code == 404:
                        raise
                    last_error = exc
                    if exc.code not in {408, 429, 500, 502, 503, 504}:
                        detail = read_error_detail(exc)
                        raise NetworkError(
                            f"HTTP {exc.code} for {candidate_url}: {detail}"
                        ) from exc
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 8))
            failures.append(f"{candidate_url} ({last_error})")

        raise NetworkError("Request failed after retries: " + "; ".join(failures))

    def get_bytes(self, url: str) -> bytes:
        with self._request(url) as response:
            return response.read()

    def get_json(self, url: str) -> dict:
        from zju_scatt_interface.errors import NetworkError

        try:
            return json.loads(self.get_bytes(url).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NetworkError(f"Invalid JSON response from {url}") from exc

    def post_json(self, url: str, payload: dict, headers: Optional[dict[str, str]] = None) -> dict:
        from zju_scatt_interface.errors import NetworkError

        encoded = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        with self._request(url, method="POST", headers=request_headers, data=encoded) as response:
            raw = response.read()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NetworkError(f"Invalid JSON response from {url}") from exc

    def list_page(
        self, prefix: str, *, delimiter: Optional[str] = None, marker: str = ""
    ) -> ListPage:
        parameters = {"prefix": prefix, "max-keys": "1000"}
        if delimiter is not None:
            parameters["delimiter"] = delimiter
        if marker:
            parameters["marker"] = marker
        query = urllib.parse.urlencode(parameters, quote_via=urllib.parse.quote)
        payload = self.get_bytes(f"{LIST_API_URL}?{query}")
        return parse_list_page(payload)

    def iter_objects(
        self,
        prefix: str,
        *,
        on_page: Optional[Callable[[int, int], None]] = None,
    ) -> Iterator[RemoteObject]:
        from zju_scatt_interface.errors import NetworkError

        marker = ""
        page_number = 0
        while True:
            page = self.list_page(prefix, marker=marker)
            page_number += 1
            if on_page:
                on_page(page_number, len(page.objects))
            for obj in page.objects:
                if obj.key != prefix.rstrip("/") and not (obj.size == 0 and obj.key.endswith("/")):
                    yield obj
            if not page.truncated:
                return
            next_marker = page.next_marker
            if not next_marker and page.objects:
                next_marker = page.objects[-1].key
            if not next_marker or next_marker == marker:
                raise NetworkError("The listing API returned an invalid pagination marker")
            marker = next_marker

    def list_directory(self, prefix: str) -> tuple[list[RemoteDirectory], list[RemoteObject], int]:
        from zju_scatt_interface.access.catalog import (
            ensure_directory_prefix,
        )
        from zju_scatt_interface.errors import NetworkError

        prefix = ensure_directory_prefix(prefix)
        marker = ""
        directories: dict[str, RemoteDirectory] = {}
        objects: dict[str, RemoteObject] = {}
        pages = 0
        while True:
            page = self.list_page(prefix, delimiter="/", marker=marker)
            pages += 1
            directories.update((item.key, item) for item in page.directories)
            for item in page.objects:
                if item.key != prefix.rstrip("/") and not (
                    item.size == 0 and item.key.endswith("/")
                ):
                    objects[item.key] = item
            if not page.truncated:
                break
            next_marker = page.next_marker
            candidates = [*directories.keys(), *objects.keys()]
            if not next_marker and candidates:
                next_marker = max(candidates)
            if not next_marker or next_marker == marker:
                raise NetworkError("The listing API returned an invalid pagination marker")
            marker = next_marker
        return (
            sorted(directories.values(), key=lambda item: item.key),
            sorted(objects.values(), key=lambda item: item.key),
            pages,
        )

    def stat_object(self, key: str) -> Optional[RemoteObject]:
        from zju_scatt_interface.access.catalog import (
            object_url,
        )
        from zju_scatt_interface.access.models import RemoteObject

        try:
            with self._request(object_url(key), method="HEAD", allow_404=True) as response:
                headers = response.headers
                return RemoteObject(
                    key=key,
                    size=int(headers.get("Content-Length", "0")),
                    last_modified=headers.get("Last-Modified", ""),
                    etag=headers.get("ETag", "").strip('"'),
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def validate_session(self, token: str) -> bool:
        from zju_scatt_interface.errors import NetworkError

        query = urllib.parse.urlencode({"session": token})
        try:
            return bool(self.get_json(f"{TRACKING_API_URL}/session/validate?{query}").get("valid"))
        except NetworkError:
            return False

    def register(self, payload: dict) -> str:
        from zju_scatt_interface.errors import NetworkError

        try:
            # Keep this intentionally identical to the proven short client:
            # requests.post(url, json=payload, verify=False).  In particular,
            # do not add Sec-Fetch/Origin headers to a non-browser request.
            response = self.post_json(f"{TRACKING_API_URL}/register", payload)
        except NetworkError as exc:
            if "HTTP 400" in str(exc):
                raise ScattError(
                    "The registration API rejected the record (HTTP 400). "
                    "Use a website country code such as CN, US, or GB; also "
                    "check that organization is non-empty and optional fields "
                    "are not unusually long. Server response: "
                    f"{exc}"
                ) from exc
            raise
        token = response.get("sessionToken") or response.get("session_token")
        if not isinstance(token, str) or not token:
            raise NetworkError("Registration succeeded but no session token was returned")
        return token

    def track_event(self, token: str, key: str, event_type: str) -> None:
        self.post_json(
            f"{TRACKING_API_URL}/event",
            {"fileKey": key, "eventType": event_type},
            headers={
                "X-Download-Session": token,
            },
        )


def read_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        return raw[:300]
    except Exception:
        return exc.reason or "request failed"


def text_of(parent: ET.Element, name: str) -> str:
    element = parent.find(name)
    return element.text.strip() if element is not None and element.text else ""


def parse_list_page(payload: bytes) -> ListPage:
    """Parse the S3/OSS ListObjects v1 XML returned by the website proxy."""
    from zju_scatt_interface.access.models import (
        ListPage,
        RemoteDirectory,
        RemoteObject,
    )

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise NetworkError("The listing API returned invalid XML") from exc

    objects: list[RemoteObject] = []
    for node in root.findall("Contents"):
        key = text_of(node, "Key")
        if not key:
            continue
        try:
            size = int(text_of(node, "Size") or "0")
        except ValueError:
            size = 0
        objects.append(
            RemoteObject(
                key=key,
                size=size,
                last_modified=text_of(node, "LastModified"),
                etag=text_of(node, "ETag").strip('"'),
            )
        )
    directories = tuple(
        RemoteDirectory(text_of(node, "Prefix"))
        for node in root.findall("CommonPrefixes")
        if text_of(node, "Prefix")
    )
    return ListPage(
        objects=tuple(objects),
        directories=directories,
        truncated=text_of(root, "IsTruncated").lower() == "true",
        next_marker=text_of(root, "NextMarker"),
    )
