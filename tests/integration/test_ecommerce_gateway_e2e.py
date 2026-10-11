"""End-to-end integration test of ShopLab through HTTP Gateway with persistence and restore."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from urllib.parse import urlencode

from test_ecommerce_storage import load_app

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_PATH = ROOT / "cyber-range" / "runtime" / "gateway.py"
COMPOSE_PATH = ROOT / "cyber-range" / "compose.yaml"
MANIFESTS_PATH = ROOT / "cyber-range" / "targets" / "manifests" / "targets.json"


def load_gateway():
    import importlib.util
    spec = importlib.util.spec_from_file_location("runtime_gateway", GATEWAY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gateway_mod = load_gateway()


class LiveServer:
    def __init__(self, server_cls, handler_cls, addr=("127.0.0.1", 0)):
        self.server = server_cls(addr, handler_cls)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class EcommerceGatewayE2ETests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "invoices").mkdir(parents=True, exist_ok=True)

        self.app = load_app()
        self.app.initialize_storage(str(self.data_dir))

        # Start live ShopLab HTTP server
        self.app_server = LiveServer(
            self.app.ThreadingHTTPServer,
            self.app.Handler,
            ("127.0.0.1", 0)
        )

        # Configure and start live Gateway HTTP server
        self.original_host = gateway_mod.TARGET_HOST
        self.original_port = gateway_mod.TARGET_PORT
        gateway_mod.TARGET_HOST = "127.0.0.1"
        gateway_mod.TARGET_PORT = self.app_server.port
        self.original_validate = gateway_mod.validate_upstream
        gateway_mod.validate_upstream = lambda h, p: None

        self.gw_server = LiveServer(
            gateway_mod.ThreadingHTTPServer,
            gateway_mod.Gateway,
            ("127.0.0.1", 0)
        )

    def tearDown(self):
        self.gw_server.close()
        self.app_server.close()
        self.app.close_storage()
        gateway_mod.TARGET_HOST = self.original_host
        gateway_mod.TARGET_PORT = self.original_port
        gateway_mod.validate_upstream = self.original_validate
        self.temp_dir.cleanup()

    def gw_request(self, method: str, path: str, body: dict | str | None = None, headers: dict | None = None) -> tuple[int, dict, bytes]:
        req_headers = dict(headers or {})
        req_body = None
        if isinstance(body, dict):
            req_body = urlencode(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif isinstance(body, str):
            req_body = body.encode("utf-8")

        if req_body is not None:
            req_headers["Content-Length"] = str(len(req_body))

        conn = http.client.HTTPConnection("127.0.0.1", self.gw_server.port, timeout=5)
        conn.request(method, path, body=req_body, headers=req_headers)
        res = conn.getresponse()
        status = res.status
        res_headers = {}
        cookie_list = []
        for k, v in res.getheaders():
            if k.lower() == "set-cookie":
                cookie_list.append(v)
            else:
                res_headers[k.lower()] = v
        res_headers["set-cookie"] = cookie_list
        payload = res.read()
        conn.close()
        return status, res_headers, payload

    def extract_cookie(self, headers: dict, cookie_name: str = "session") -> str | None:
        cookie_headers = headers.get("set-cookie") or []
        if isinstance(cookie_headers, str):
            cookie_headers = [cookie_headers]
        for header in cookie_headers:
            for part in header.split(";"):
                part = part.strip()
                if part.startswith(f"{cookie_name}="):
                    return part.split("=", 1)[1]
        return None

    def extract_csrf(self, html_bytes: bytes) -> str:
        text = html_bytes.decode("utf-8", errors="ignore")
        marker = "name='csrf_token' value='"
        if marker in text:
            start = text.find(marker) + len(marker)
            end = text.find("'", start)
            return text[start:end]
        marker2 = 'name="csrf_token" value="'
        if marker2 in text:
            start = text.find(marker2) + len(marker2)
            end = text.find('"', start)
            return text[start:end]
        return ""

    def register_and_login(self, username: str, password: str = "Password123!@#", email: str = "") -> str:
        if not email:
            email = f"{username}@demo.lab"
        # 1. Register
        status, h, body = self.gw_request("GET", "/register")
        sess_reg = self.extract_cookie(h, "session")
        csrf_reg = self.extract_csrf(body)
        status, h, _ = self.gw_request(
            "POST", "/register",
            {"username": username, "password": password, "email": email, "csrf_token": csrf_reg},
            headers={"Cookie": f"session={sess_reg}"} if sess_reg else {}
        )
        self.assertEqual(status, 302)

        # 2. Login
        status, h, body = self.gw_request("GET", "/login")
        sess_login = self.extract_cookie(h, "session")
        csrf_login = self.extract_csrf(body)
        status, h, _ = self.gw_request(
            "POST", "/login",
            {"username": username, "password": password, "csrf_token": csrf_login},
            headers={"Cookie": f"session={sess_login}"} if sess_login else {}
        )
        self.assertEqual(status, 302)
        sess_auth = self.extract_cookie(h, "session")
        return f"session={sess_auth}"

    # ── R01: Topology, Manifest, Compose Consistency ──────────────────────
    def test_R01_manifest_compose_consistency(self):
        compose = json.loads(COMPOSE_PATH.read_text(encoding="utf-8"))
        services = compose["services"]

        # 1. Target lab-ecommerce is internal only
        self.assertIn("lab-ecommerce", services)
        self.assertEqual(services["lab-ecommerce"]["networks"], ["lab"])
        self.assertNotIn("ports", services["lab-ecommerce"])
        self.assertEqual(services["lab-ecommerce"]["environment"]["TARGET_ID"], "lab-ecommerce")
        self.assertIn("ecommerce-data:/app/data", services["lab-ecommerce"].get("volumes", []))

        # 2. Gateway gateway-ecommerce binds loopback only
        self.assertIn("gateway-ecommerce", services)
        gw_ports = services["gateway-ecommerce"].get("ports", [])
        self.assertEqual(gw_ports, ["127.0.0.1:18088:8080"])
        self.assertEqual(services["gateway-ecommerce"]["environment"]["TARGET_HOST"], "lab-ecommerce")

        # 3. Named volume defined
        self.assertIn("ecommerce-data", compose.get("volumes", {}))

        # 4. Manifests targets.json contains lab-ecommerce
        manifest = json.loads(MANIFESTS_PATH.read_text(encoding="utf-8"))
        t_ids = {t["target_id"] for t in manifest["targets"]}
        self.assertIn("lab-ecommerce", t_ids)
        ecomm_target = next(t for t in manifest["targets"] if t["target_id"] == "lab-ecommerce")
        self.assertEqual(ecomm_target["port"], 18088)
        self.assertEqual(ecomm_target["health_path"], "/health")

        # 5. Gateway allowed upstreams contains lab-ecommerce
        self.assertIn("lab-ecommerce", gateway_mod.ALLOWED_UPSTREAMS)

    # ── R02, R03: Two-Session E2E Product Flow & Ownership Denial ──────────
    def test_R02_R03_gateway_two_session_product_flow_and_isolation(self):
        # 1. Health check through gateway
        status, _, body = self.gw_request("GET", "/health")
        self.assertEqual(status, 200)
        h_data = json.loads(body.decode("utf-8"))
        self.assertEqual(h_data["status"], "ok")
        self.assertEqual(h_data["target_id"], "lab-ecommerce")

        # 2. Register & Login User A (alice) and User B (bob) through Gateway
        cookie_a = self.register_and_login("alice_demo")
        cookie_b = self.register_and_login("bob_demo")
        self.assertNotEqual(cookie_a, cookie_b)

        # 4. User A adds Product 1 to cart through Gateway
        status, _, body = self.gw_request("GET", "/products/1", headers={"Cookie": cookie_a})
        csrf_a = self.extract_csrf(body)
        status, _, _ = self.gw_request(
            "POST", "/cart/add",
            {"product_id": "1", "quantity": "1", "csrf_token": csrf_a},
            headers={"Cookie": cookie_a}
        )
        self.assertEqual(status, 302)

        # 5. User A checks out through Gateway
        status, _, body = self.gw_request("GET", "/cart", headers={"Cookie": cookie_a})
        csrf_a = self.extract_csrf(body)
        status, _, body = self.gw_request(
            "POST", "/checkout",
            {"shipping_name": "Alice Demo", "shipping_address": "101 Lab Way", "shipping_city": "Lab City", "shipping_postal": "99999", "csrf_token": csrf_a},
            headers={"Cookie": cookie_a}
        )
        self.assertEqual(status, 200)  # Order confirmation page
        self.assertIn(b"Order Placed Successfully", body)

        # User A gets order ID
        status, _, body = self.gw_request("GET", "/orders", headers={"Cookie": cookie_a})
        self.assertEqual(status, 200)
        self.assertIn(b"/orders/1", body)

        # User A inspects order details and gets invoice filename
        status, _, body = self.gw_request("GET", "/orders/1", headers={"Cookie": cookie_a})
        self.assertEqual(status, 200)
        import re
        match = re.search(r'file=(INV-[A-F0-9]{32}\.txt)', body.decode("utf-8"))
        self.assertIsNotNone(match)
        inv_file = match.group(1)

        # User A can download own invoice
        status, _, body = self.gw_request("GET", f"/download/invoice?file={inv_file}", headers={"Cookie": cookie_a})
        self.assertEqual(status, 200)
        self.assertIn(b"ShopLab", body)

        # 6. User B cannot access User A's order or invoice (IDOR denial)
        status, _, _ = self.gw_request("GET", "/orders/1", headers={"Cookie": cookie_b})
        self.assertEqual(status, 404)

        status, _, _ = self.gw_request("GET", f"/download/invoice?file={inv_file}", headers={"Cookie": cookie_b})
        self.assertEqual(status, 404)

        # 7. Unauthenticated user cannot access order or admin
        status, _, _ = self.gw_request("GET", "/orders/1")
        self.assertEqual(status, 403)

        status, _, _ = self.gw_request("GET", "/admin", headers={"Cookie": cookie_a})
        self.assertEqual(status, 403)

        # 8. Promote User B to admin locally and verify admin flow through Gateway
        self.app_server.close()
        self.app.close_storage()
        # Find bob user ID
        import sqlite3
        con = sqlite3.connect(str(self.data_dir / "shoplab.sqlite3"))
        bob_uid = con.execute("SELECT id FROM users WHERE username='bob_demo'").fetchone()[0]
        con.close()
        self.app.set_local_role(str(self.data_dir), bob_uid, "admin")
        self.app.initialize_storage(str(self.data_dir))
        self.app_server = LiveServer(self.app.ThreadingHTTPServer, self.app.Handler, ("127.0.0.1", 0))
        gateway_mod.TARGET_PORT = self.app_server.port

        # 8a. Verify old session of Bob is invalidated upon role elevation (403)
        status, _, _ = self.gw_request("GET", "/admin", headers={"Cookie": cookie_b})
        self.assertEqual(status, 403)

        # 8b. Bob logs in again through Gateway to obtain authoritative admin session
        status, h, body = self.gw_request("GET", "/login")
        csrf_login = self.extract_csrf(body)
        sess_login = self.extract_cookie(h, "session")
        status, h, _ = self.gw_request(
            "POST", "/login",
            {"username": "bob_demo", "password": "Password123!@#", "csrf_token": csrf_login},
            headers={"Cookie": f"session={sess_login}"} if sess_login else {}
        )
        self.assertEqual(status, 302)
        sess_admin = self.extract_cookie(h, "session")
        admin_cookie = f"session={sess_admin}"

        status, _, body = self.gw_request("GET", "/admin", headers={"Cookie": admin_cookie})
        self.assertEqual(status, 200)
        self.assertIn(b"Admin Dashboard", body)

        # Admin B transitions order 1 to shipped
        csrf_b = self.extract_csrf(body)
        status, _, _ = self.gw_request(
            "POST", "/admin/orders/status",
            {"order_id": "1", "status": "shipped", "csrf_token": csrf_b},
            headers={"Cookie": admin_cookie}
        )
        self.assertEqual(status, 302)

        # Verify status updated
        status, _, body = self.gw_request("GET", "/admin/orders/1", headers={"Cookie": admin_cookie})
        self.assertEqual(status, 200)
        self.assertIn(b"shipped", body)

    # ── R05: Persistence & Container Replacement Simulation ───────────────
    def test_R05_persistence_and_replacement(self):
        # 1. Create a user and place an order
        cookie = self.register_and_login("persist_user")

        status, _, body = self.gw_request("GET", "/products/1", headers={"Cookie": cookie})
        csrf = self.extract_csrf(body)
        self.gw_request("POST", "/cart/add", {"product_id": "1", "quantity": "1", "csrf_token": csrf}, headers={"Cookie": cookie})
        status, _, body = self.gw_request("GET", "/cart", headers={"Cookie": cookie})
        csrf = self.extract_csrf(body)
        self.gw_request(
            "POST", "/checkout",
            {"shipping_name": "P User", "shipping_address": "1 St", "shipping_city": "City", "shipping_postal": "00000", "csrf_token": csrf},
            headers={"Cookie": cookie}
        )

        # 2. Stop and recreate the server process (container replacement with same volume)
        self.app_server.close()
        self.app.close_storage()

        # Re-initialize storage with existing data directory
        self.app.initialize_storage(str(self.data_dir))
        self.app_server = LiveServer(
            self.app.ThreadingHTTPServer,
            self.app.Handler,
            ("127.0.0.1", 0)
        )
        gateway_mod.TARGET_PORT = self.app_server.port

        # 3. Verify data survived restart
        status, _, body = self.gw_request("GET", "/orders", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertIn(b"/orders/1", body)

    # ── R06: Restore to Baseline ───────────────────────────────────────────
    def test_R06_restore_to_baseline(self):
        # 1. Create runtime data and session
        cookie = self.register_and_login("reset_user")

        # 2. Call restore_baseline (approved local administrative workflow)
        self.app_server.close()
        self.app.close_storage()
        self.app.restore_baseline(str(self.data_dir))
        self.app.initialize_storage(str(self.data_dir))
        self.app_server = LiveServer(
            self.app.ThreadingHTTPServer,
            self.app.Handler,
            ("127.0.0.1", 0)
        )
        gateway_mod.TARGET_PORT = self.app_server.port

        # 3. Assert old session is invalid (rejected with 403)
        status, _, body = self.gw_request("GET", "/orders", headers={"Cookie": cookie})
        self.assertEqual(status, 403)

        # 4. Service is healthy
        status, _, body = self.gw_request("GET", "/health")
        self.assertEqual(status, 200)

    # ── R07: Failure Tests ─────────────────────────────────────────────────
    def test_R07_gateway_and_service_failures(self):
        # 1. Invalid path framing -> 400
        status, _, _ = self.gw_request("GET", "/%2foutside.invalid")
        self.assertEqual(status, 400)

        # 2. Upstream unavailable -> 502
        self.app_server.close()
        status, _, _ = self.gw_request("GET", "/health")
        self.assertEqual(status, 502)


if __name__ == "__main__":
    unittest.main()
