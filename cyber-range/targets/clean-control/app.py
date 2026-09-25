"""
lab-clean-control: Secure web application for isolated cyber range.
Baseline control — contains NO intentional vulnerabilities.
Used to measure false positive rate of security scanning tools.
Status: IMPLEMENTED (not VALIDATED)
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

TARGET_ID = os.environ.get("TARGET_ID", "lab-clean-control")
PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = pathlib.Path("/app/data").resolve()
MAX_BODY_BYTES = 1024 * 1024
MAX_BODY_BYTES = 1024 * 1024


class AppState:
    def __init__(self) -> None:
        self.reset_count = 0
        self.db = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY, name TEXT, description TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY, name TEXT
            );
            DELETE FROM items; DELETE FROM categories;
            INSERT INTO categories (name) VALUES ('Electronics'), ('Books'), ('Clothing');
            INSERT INTO items (name, description) VALUES
                ('Notebook', 'A5 ruled notebook'),
                ('Pen', 'Blue ballpoint pen'),
                ('Eraser', 'White rubber eraser');
        """)
        return db

    def reset(self) -> None:
        self.db.close()
        self.db = self._init_db()
        self.reset_count += 1


state = AppState()


class Handler(BaseHTTPRequestHandler):
    server_version = "LabCleanControl/1"

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
        path = urlsplit(self.path).path

        if path == "/":
            self._send_html(200, "<html><body><h1>lab-clean-control</h1><p>Secure baseline (lab only)</p></body></html>")
            return

        if path == "/health":
            self._send_json(200, {"status": "ok", "target_id": TARGET_ID, "reset_count": state.reset_count})
            return

        # SECURE: parameterized query — no SQLi
        if path == "/api/items/search":
            q = self._params().get("q", [""])[0]
            rows = state.db.execute(
                "SELECT * FROM items WHERE name LIKE ?", (f"%{q}%",)
            ).fetchall()
            self._send_json(200, {"results": [dict(r) for r in rows]})
            return

        # SECURE: escaped output — no XSS
        if path == "/search":
            q = self._params().get("q", [""])[0]
            safe_q = html_escape(q)
            html = f"<html><body><h1>Search results for: {safe_q}</h1><p>No results.</p></body></html>"
            self._send_html(200, html)
            return

        # SECURE: path normalization + containment check — no path traversal
        if path == "/files":
            name = self._params().get("name", [""])[0]
            if not name:
                self._send_json(400, {"error": "missing name parameter"})
                return
            requested = (DATA_DIR / name).resolve()
            if DATA_DIR not in requested.parents and requested != DATA_DIR:
                self._send_json(403, {"error": "forbidden"})
                return
            try:
                with open(requested, "r") as f:
                    self._send(200, f.read(), "text/plain")
            except FileNotFoundError:
                self._send_json(404, {"error": "file not found"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # SECURE: parameterized query
        if path == "/api/categories":
            rows = state.db.execute("SELECT * FROM categories").fetchall()
            self._send_json(200, {"categories": [dict(r) for r in rows]})
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

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
