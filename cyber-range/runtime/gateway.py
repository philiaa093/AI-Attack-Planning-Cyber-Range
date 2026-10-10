"""Loopback-published HTTP gateway into one isolated lab target."""
from __future__ import annotations

import os
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urljoin, urlsplit

TARGET_HOST = os.environ.get("TARGET_HOST", "")
TARGET_PORT = int(os.environ.get("TARGET_PORT", "8080"))
PORT = int(os.environ.get("PORT", "8080"))
MAX_BODY = 1024 * 1024
ALLOWED_UPSTREAMS = frozenset({
    "lab-webapp-a", "lab-webapp-b", "lab-clean-control", "lab-ecommerce",
})


def validate_upstream(host: str, port: int) -> None:
    if host not in ALLOWED_UPSTREAMS or port != 8080:
        raise ValueError("Gateway upstream must be an allowlisted internal lab target")


def validate_path(path: str) -> None:
    if not isinstance(path, str) or len(path) > 8192:
        raise ValueError("Invalid request path")
    decoded = path
    for _ in range(4):
        if (not decoded.startswith("/") or decoded.startswith("//")
                or "\\" in decoded
                or any(ord(char) < 32 or ord(char) == 127 for char in decoded)):
            raise ValueError("Only bounded origin-form request paths are allowed")
        parsed = urlsplit(decoded)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise ValueError("Invalid request path authority or fragment")
        next_value = unquote(decoded, errors="strict")
        if next_value == decoded:
            return
        decoded = next_value
    raise ValueError("Excessively encoded request path")


def safe_location(location: str, request_path: str) -> str:
    if not location or any(ord(char) < 32 or ord(char) == 127 for char in location):
        raise ValueError("Invalid redirect location")
    if "\\" in location:
        raise ValueError("Invalid redirect location")
    origin = f"http://{TARGET_HOST}:{TARGET_PORT}"
    parsed = urlsplit(urljoin(origin + request_path, location))
    if (parsed.scheme != "http" or parsed.hostname != TARGET_HOST
            or parsed.port != TARGET_PORT or parsed.username is not None
            or parsed.password is not None or parsed.fragment):
        raise ValueError("Redirect outside the configured lab target")
    relative = parsed.path or "/"
    if parsed.query:
        relative += "?" + parsed.query
    validate_path(relative)
    return relative


class Gateway(BaseHTTPRequestHandler):
    def _proxy(self) -> None:
        try:
            validate_upstream(TARGET_HOST, TARGET_PORT)
        except ValueError:
            self.send_error(503)
            return
        try:
            validate_path(self.path)
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1 or "Transfer-Encoding" in self.headers:
                raise ValueError("Ambiguous request framing")
            raw_length = lengths[0] if lengths else "0"
            if not raw_length.isascii() or not raw_length.isdigit():
                raise ValueError("Invalid content length")
            length = int(raw_length)
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        if length > MAX_BODY:
            self.send_error(413)
            return
        self.connection.settimeout(5)
        try:
            body = self.rfile.read(length) if length else None
        except (OSError, TimeoutError):
            self.send_error(408)
            return
        if body is not None and len(body) != length:
            self.send_error(400)
            return
        headers = {}
        for key in ("Content-Type", "Cookie", "Accept", "X-CSRF-Token"):
            values = self.headers.get_all(key, [])
            if len(values) > 1:
                self.send_error(400)
                return
            if values:
                headers[key] = values[0]
        connection = HTTPConnection(TARGET_HOST, TARGET_PORT, timeout=5)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY:
                self.send_error(502)
                return
            response_headers = []
            raw_headers = response.getheaders()
            if sum(key.lower() == "location" for key, _ in raw_headers) > 1:
                raise ValueError("Ambiguous redirect location")
            hop_headers = {
                token.strip().lower()
                for key, value in raw_headers if key.lower() == "connection"
                for token in value.split(",")
            }
            for key, value in raw_headers:
                if any(ord(char) < 32 or ord(char) == 127 for char in value):
                    raise ValueError("Invalid upstream response header")
                if key.lower() in hop_headers:
                    continue
                if key.lower() == "location":
                    value = safe_location(value, self.path)
                if key.lower() in {
                    "content-type", "set-cookie", "location", "cache-control",
                    "content-security-policy", "x-content-type-options",
                    "x-frame-options", "referrer-policy",
                }:
                    response_headers.append((key, value))
            self.send_response(response.status)
            for key, value in response_headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_error(502)
        finally:
            connection.close()

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    validate_upstream(TARGET_HOST, TARGET_PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Gateway).serve_forever()
