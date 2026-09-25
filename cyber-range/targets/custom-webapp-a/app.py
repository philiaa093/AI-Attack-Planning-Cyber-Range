"""
lab-webapp-a: Intentionally vulnerable web application for isolated cyber range.
DO NOT deploy outside lab environment. Contains deliberate SQLi, XSS, Path Traversal.
Status: IMPLEMENTED (not VALIDATED)
"""
from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

TARGET_ID = os.environ.get("TARGET_ID", "lab-webapp-a")
PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = "/app/data"
MAX_BODY_BYTES = 1024 * 1024


class AppState:
    def __init__(self) -> None:
        self.reset_count = 0
        self.db = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, name TEXT, email TEXT
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, name TEXT, price REAL
            );
            DELETE FROM users; DELETE FROM products;
            INSERT INTO users (name, email) VALUES
                ('alice', 'alice@lab.invalid'),
                ('bob', 'bob@lab.invalid'),
                ('charlie', 'charlie@lab.invalid');
            INSERT INTO products (name, price) VALUES
                ('Widget', 9.99), ('Gadget', 19.99), ('Doohickey', 4.99);
        """)
        return db

    def reset(self) -> None:
        self.db.close()
        self.db = self._init_db()
        self.reset_count += 1


state = AppState()


class Handler(BaseHTTPRequestHandler):
    server_version = "LabWebAppA/1"

    def _send(self, status: int, body: str, content_type: str = "application/json") -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, status: int, obj: dict) -> None:
        self._send(status, json.dumps(obj, sort_keys=True))

    def _send_html(self, status: int, html: str) -> None:
        self._send(status, html, "text/html; charset=utf-8")

    def _params(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.path).query)

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path

        if path == "/":
            self._send_html(200, "<html><body><h1>lab-webapp-a</h1><p>Cyber range target (lab only)</p></body></html>")
            return

        if path == "/health":
            self._send_json(200, {"status": "ok", "target_id": TARGET_ID, "reset_count": state.reset_count})
            return

        # INTENTIONAL VULN: SQL injection via string concatenation — lab only
        if path == "/api/users/search":
            q = self._params().get("q", [""])[0]
            try:
                query = f"SELECT * FROM users WHERE name LIKE '%{q}%'"
                rows = state.db.execute(query).fetchall()
                self._send_json(200, {"results": [dict(r) for r in rows]})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # INTENTIONAL VULN: reflected XSS — lab only
        if path == "/search":
            q = self._params().get("q", [""])[0]
            html = f"<html><body><h1>Search results for: {q}</h1><p>No results.</p></body></html>"
            self._send_html(200, html)
            return

        # INTENTIONAL VULN: path traversal via unsanitized join — lab only
        if path == "/files":
            name = self._params().get("name", [""])[0]
            if not name:
                self._send_json(400, {"error": "missing name parameter"})
                return
            filepath = os.path.join(DATA_DIR, name)
            try:
                with open(filepath, "r") as f:
                    self._send(200, f.read(), "text/plain")
            except FileNotFoundError:
                self._send_json(404, {"error": "file not found"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # SAFE: parameterized query
        if path == "/api/products":
            rows = state.db.execute("SELECT * FROM products").fetchall()
            self._send_json(200, {"products": [dict(r) for r in rows]})
            return

        self._send_json(404, {"status": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/reset":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(400, {"error": "invalid content length"})
                return
            if length < 0 or length > MAX_BODY_BYTES:
                self._send_json(413, {"error": "request body too large"})
                return
            if length > 0:
                self.rfile.read(length)
            state.reset()
            self._send_json(200, {"status": "reset", "target_id": TARGET_ID, "reset_count": state.reset_count})
            return
        self._send_json(404, {"status": "not_found"})

    def do_PUT(self) -> None:
        self._send_json(405, {"status": "method_not_allowed"})

    def do_DELETE(self) -> None:
        self._send_json(405, {"status": "method_not_allowed"})

    def do_PATCH(self) -> None:
        self._send_json(405, {"status": "method_not_allowed"})

    def do_HEAD(self) -> None:
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS, POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
