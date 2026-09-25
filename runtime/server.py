"""HTTP server for one fixed local lab target."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .targets import TARGETS, Target, route

TARGET_ID = os.environ.get("TARGET_ID", "lab-clean-001")
PORT = int(os.environ.get("PORT", "8080"))

if TARGET_ID not in TARGETS:
    raise ValueError("unknown target")

state = Target(TARGET_ID)


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
        method = "POST" if self.path.startswith("/action?") else "GET"
        observation = route(state, method, self.path)
        self._send(observation.status, observation.body)

    def do_POST(self) -> None:
        length = self.headers.get("Content-Length", "0")
        try:
            if int(length) != 0:
                self._send(400, {"status": "body_not_allowed"})
                return
        except ValueError:
            self._send(400, {"status": "invalid_request"})
            return
        observation = route(state, "POST", self.path)
        self._send(observation.status, observation.body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
