"""Internal-network executor with a closed target/action boundary."""
from __future__ import annotations

import json
from http.client import HTTPConnection
from urllib.parse import urlsplit

TARGET_IDS = ("lab-sqli-001", "lab-xss-001", "lab-path-001", "lab-clean-001")
TARGET_HOSTS = frozenset(TARGET_IDS)
TARGET_ENDPOINTS = {target_id: f"http://{target_id}:8080" for target_id in TARGET_IDS}
ACTIONS = {
    "ACTION-WEB-001": "SQLI",
    "ACTION-WEB-002": "XSS",
    "ACTION-WEB-003": "PATH_TRAVERSAL",
}


def validate_base_url(base_url: str) -> tuple[str, int]:
    if not isinstance(base_url, str):
        raise ValueError("executor requires internal target URL")
    try:
        parsed = urlsplit(base_url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("executor requires internal target URL") from exc
    if (
        parsed.scheme != "http"
        or host not in TARGET_HOSTS
        or port != 8080
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("executor requires allowlisted internal target URL")
    return host, port


class Executor:
    def __init__(self, endpoints: dict[str, str] | None = None, timeout: float = 2.0) -> None:
        self.endpoints = dict(endpoints or TARGET_ENDPOINTS)
        self.timeout = timeout
        for target_id, base_url in self.endpoints.items():
            if target_id not in TARGET_HOSTS:
                raise ValueError("unknown target")
            validate_base_url(base_url)

    def _request(self, target_id: str, method: str, path: str) -> dict[str, object]:
        if target_id not in self.endpoints:
            raise ValueError("unknown target")
        host, port = validate_base_url(self.endpoints[target_id])
        connection = HTTPConnection(host, port, timeout=self.timeout)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            body = response.read(65536)
            if response.status >= 500:
                raise RuntimeError(f"target returned HTTP {response.status}")
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise RuntimeError("target returned invalid observation")
            parsed["http_status"] = response.status
            return parsed
        finally:
            connection.close()

    def health(self, target_id: str) -> dict[str, object]:
        return self._request(target_id, "GET", "/health")

    def reset(self, target_id: str) -> dict[str, object]:
        return self._request(target_id, "POST", "/reset")

    def action(self, target_id: str, action_id: str) -> dict[str, object]:
        if action_id not in ACTIONS:
            raise ValueError("unknown action")
        return self._request(target_id, "POST", f"/action?action={action_id}")
