"""Authenticated management control plane for enterprise range targets."""
from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler
from typing import Any, Mapping
from urllib.parse import urlsplit

from runtime.lab.enterprise_range.services import TargetState


class ControlPlaneHandler(BaseHTTPRequestHandler):
    """Bounded lifecycle API isolated from the target data-plane handlers."""

    server_version = "MiniEnterpriseControlPlane/1.0"
    target_state: TargetState
    control_token: str

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, status: int, data: Mapping[str, Any]) -> None:
        encoded = json.dumps(dict(data), sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        candidate = header[len(prefix):]
        return bool(candidate) and hmac.compare_digest(candidate, self.control_token)

    def _require_authorization(self) -> bool:
        if self._authorized():
            return True
        self._send_json(403, {
            "outcome": "DENIED",
            "error": "CONTROL_AUTH_REQUIRED",
            "message": "Valid management-plane authorization is required",
        })
        return False

    def _read_body_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > 4096:
            return None
        if length == 0:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def do_GET(self) -> None:
        if not self._require_authorization():
            return
        if urlsplit(self.path).path != "/control/v1/health":
            self._send_json(404, {"error": "CONTROL_ROUTE_NOT_FOUND"})
            return
        self._send_json(200, {
            "status": "ok",
            "target_id": self.target_state.target_id,
            "zone": self.target_state.zone_id,
            "reset_count": self.target_state.reset_count,
        })

    def do_POST(self) -> None:
        if not self._require_authorization():
            return
        path = urlsplit(self.path).path
        body = self._read_body_json()
        if body is None:
            self._send_json(400, {"error": "INVALID_CONTROL_REQUEST"})
            return

        if path == "/control/v1/reset":
            self.target_state.reset()
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "reset_count": self.target_state.reset_count,
            })
            return

        if path in ("/control/v1/routes/block", "/control/v1/routes/unblock"):
            route = body.get("route")
            if route not in ("primary", "secondary"):
                self._send_json(400, {"error": "INVALID_ROUTE_NAME"})
                return
            with self.target_state.lock:
                if path.endswith("/block"):
                    self.target_state.blocked_routes.add(route)
                else:
                    self.target_state.blocked_routes.discard(route)
                blocked = sorted(self.target_state.blocked_routes)
            self._send_json(200, {
                "status": "ok",
                "target_id": self.target_state.target_id,
                "blocked_routes": blocked,
            })
            return

        self._send_json(404, {"error": "CONTROL_ROUTE_NOT_FOUND"})
