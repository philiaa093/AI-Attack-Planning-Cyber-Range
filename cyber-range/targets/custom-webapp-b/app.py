"""
lab-webapp-b: Intentionally vulnerable web application for isolated cyber range.
DO NOT deploy outside lab environment. Contains deliberate SQLi, XSS, Path Traversal.
Vuln patterns differ from lab-webapp-a to test planner generalization.
Status: IMPLEMENTED (not VALIDATED)
"""
from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

TARGET_ID = os.environ.get("TARGET_ID", "lab-webapp-b")
PORT = int(os.environ.get("PORT", "8080"))
UPLOADS_DIR = "/app/uploads"
MAX_BODY_BYTES = 1024 * 1024


class AppState:
    def __init__(self) -> None:
        self.reset_count = 0
        self.db = self._init_db()

    def _init_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(":memory:", check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY, customer_id INTEGER, item TEXT, quantity INTEGER
            );
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY, sku TEXT, description TEXT, stock INTEGER
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, author TEXT, body TEXT
            );
            DELETE FROM orders; DELETE FROM inventory; DELETE FROM comments;
            INSERT INTO orders (customer_id, item, quantity) VALUES
                (1, 'Laptop', 2), (2, 'Mouse', 5), (1, 'Keyboard', 1);
            INSERT INTO inventory (sku, description, stock) VALUES
                ('SKU-001', 'Laptop 15in', 10),
                ('SKU-002', 'Wireless Mouse', 50),
                ('SKU-003', 'Mechanical Keyboard', 25);
        """)
        return db

    def reset(self) -> None:
        self.db.close()
        self.db = self._init_db()
        self.reset_count += 1


state = AppState()


class Handler(BaseHTTPRequestHandler):
    server_version = "LabWebAppB/1"

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

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid content length"})
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request body too large"})
            return None
        return self.rfile.read(length) if length > 0 else b""

    def do_GET(self) -> None:
        path = urlsplit(self.path).path

        if path == "/":
            self._send_html(200, "<html><body><h1>lab-webapp-b</h1><p>Cyber range target B (lab only)</p></body></html>")
            return

        if path == "/health":
            self._send_json(200, {"status": "ok", "target_id": TARGET_ID, "reset_count": state.reset_count})
            return

        # INTENTIONAL VULN: SQL injection via string concatenation (different pattern from A) — lab only
        if path == "/api/orders":
            customer_id = self._params().get("customer_id", [""])[0]
            if not customer_id:
                self._send_json(400, {"error": "missing customer_id"})
                return
            try:
                query = "SELECT * FROM orders WHERE customer_id = " + customer_id
                rows = state.db.execute(query).fetchall()
                self._send_json(200, {"orders": [dict(r) for r in rows]})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # INTENTIONAL VULN: stored XSS — renders stored comments without escaping — lab only
        if path == "/api/comments":
            rows = state.db.execute("SELECT * FROM comments ORDER BY id").fetchall()
            html_parts = []
            for r in rows:
                html_parts.append(f"<div class='comment'><b>{r['author']}</b>: {r['body']}</div>")
            html = "<html><body><h1>Comments</h1>" + "".join(html_parts) + "</body></html>"
            self._send_html(200, html)
            return

        # INTENTIONAL VULN: path traversal via direct file read — lab only
        if path == "/api/download":
            filename = self._params().get("file", [""])[0]
            if not filename:
                self._send_json(400, {"error": "missing file parameter"})
                return
            filepath = os.path.join(UPLOADS_DIR, filename)
            try:
                with open(filepath, "rb") as f:
                    content = f.read()
                self._send(200, content.decode("utf-8", errors="replace"), "application/octet-stream")
            except FileNotFoundError:
                self._send_json(404, {"error": "file not found"})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # SAFE: parameterized query
        if path == "/api/inventory":
            rows = state.db.execute("SELECT * FROM inventory").fetchall()
            self._send_json(200, {"inventory": [dict(r) for r in rows]})
            return

        self._send_json(404, {"status": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path

        if path == "/reset":
            if self._read_body() is None:
                return
            state.reset()
            self._send_json(200, {"status": "reset", "target_id": TARGET_ID, "reset_count": state.reset_count})
            return

        # INTENTIONAL VULN: stored XSS — stores raw HTML from user input — lab only
        if path == "/api/comments":
            raw = self._read_body()
            if raw is None:
                return
            try:
                data = json.loads(raw)
                author = str(data.get("author", "anonymous"))
                body = str(data.get("body", ""))
                state.db.execute("INSERT INTO comments (author, body) VALUES (?, ?)", (author, body))
                state.db.commit()
                self._send_json(201, {"status": "created"})
            except (json.JSONDecodeError, Exception) as e:
                self._send_json(400, {"error": str(e)})
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
