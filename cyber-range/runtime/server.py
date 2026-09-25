"""Deterministic, harmless local-only cyber-range target server."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

TARGET_ID = os.environ.get("TARGET_ID", "lab-clean-001")
PORT = int(os.environ.get("PORT", "8080"))


class TargetState:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1


state = TargetState()


class Handler(BaseHTTPRequestHandler):
    server_version = "CyberRangeTarget/1"

    def _send(self, status: int, body: dict[str, object]) -> None:
        encoded = json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._send(200, {"status": "ok", "target_id": TARGET_ID, "reset_count": state.reset_count})
            return
        if path == "/":
            self._send(200, {"status": "ready", "target_id": TARGET_ID})
            return
        self._send(404, {"status": "not_found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/reset":
            self._send(404, {"status": "not_found"})
            return
        content_length = self.headers.get("Content-Length", "0")
        try:
            length = int(content_length)
        except ValueError:
            self._send(400, {"status": "invalid_request"})
            return
        if length < 0 or length > 4096:
            self._send(413, {"status": "request_too_large"})
            return
        self.rfile.read(length)
        state.reset()
        self._send(200, {"status": "reset", "target_id": TARGET_ID, "reset_count": state.reset_count})

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
