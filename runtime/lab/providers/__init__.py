"""Shared HTTPS transport primitives for remote range providers."""
from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from runtime.lab.range_provider import RangeProviderError


@dataclass(frozen=True)
class JsonResponse:
    status: int
    body: Any
    headers: Mapping[str, str]


class JsonTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: Any = None,
        timeout: float = 10.0,
    ) -> JsonResponse: ...


class RedirectDenyHandler(HTTPRedirectHandler):
    """Keep authenticated provider calls pinned to the configured endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class UrllibJsonTransport:
    """TLS-verifying stdlib transport with bounded JSON responses."""

    def __init__(
        self,
        max_response_bytes: int = 1_048_576,
        allowed_hosts: frozenset[str] | None = None,
    ) -> None:
        self.max_response_bytes = max_response_bytes
        self.allowed_hosts = frozenset(host.lower() for host in (allowed_hosts or frozenset()))
        self.ssl_context = ssl.create_default_context()
        self.opener = build_opener(
            ProxyHandler({}),
            RedirectDenyHandler(),
            HTTPSHandler(context=self.ssl_context),
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: Any = None,
        timeout: float = 10.0,
    ) -> JsonResponse:
        parsed = urlsplit(url)
        hostname = parsed.hostname.lower() if parsed.hostname else ""
        if parsed.scheme != "https" or not hostname:
            raise RangeProviderError("REMOTE_DESTINATION_INVALID", "Remote provider destination must use HTTPS")
        if self.allowed_hosts and hostname not in self.allowed_hosts:
            raise RangeProviderError(
                "REMOTE_DESTINATION_DENIED",
                "Remote provider destination is outside the configured host allowlist",
            )
        encoded = None if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if encoded is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=encoded, headers=request_headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    raise RangeProviderError("REMOTE_RESPONSE_TOO_LARGE", "Remote response exceeded limit")
                return JsonResponse(
                    status=response.status,
                    body=_decode_json(raw),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            raw = exc.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                raw = b""
            return JsonResponse(status=exc.code, body=_decode_json(raw), headers=dict(exc.headers.items()))
        except (URLError, TimeoutError, OSError) as exc:
            raise RangeProviderError("REMOTE_TRANSPORT_FAILED", type(exc).__name__) from exc


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def require_status(response: JsonResponse, allowed: frozenset[int], code: str) -> JsonResponse:
    if response.status not in allowed:
        raise RangeProviderError(code, f"Remote API returned HTTP {response.status}")
    return response
