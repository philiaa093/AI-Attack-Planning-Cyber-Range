"""Live Docker verification script for ShopLab and Gateway runtime."""
from __future__ import annotations

import http.client
import json
import re
import subprocess
import sys
import time
import uuid
from urllib.parse import urlencode

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18088


def run_docker(cmd: str) -> tuple[int, str]:
    full_cmd = ["wsl", "-d", "Ubuntu", "-e", "bash", "-c", cmd]
    p = subprocess.run(full_cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


class LiveClient:
    def __init__(self, host=GATEWAY_HOST, port=GATEWAY_PORT):
        self.host = host
        self.port = port
        self.cookies: dict[str, str] = {}

    def request(self, method: str, path: str, body: dict | str | None = None, headers: dict | None = None) -> tuple[int, dict, str]:
        req_headers = dict(headers or {})
        req_body = None
        if isinstance(body, dict):
            req_body = urlencode(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif isinstance(body, str):
            req_body = body.encode("utf-8")

        if req_body is not None:
            req_headers["Content-Length"] = str(len(req_body))

        if self.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            req_headers["Cookie"] = cookie_str

        conn = http.client.HTTPConnection(self.host, self.port, timeout=10)
        conn.request(method, path, body=req_body, headers=req_headers)
        res = conn.getresponse()
        status = res.status

        # Collect headers, updating cookies
        res_headers = {}
        for k, v in res.getheaders():
            lk = k.lower()
            res_headers[lk] = v
            if lk == "set-cookie":
                for part in v.split(";"):
                    part = part.strip()
                    if "=" in part:
                        ck, cv = part.split("=", 1)
                        if ck in ("session", "role", "username"):
                            if cv:
                                self.cookies[ck] = cv
                            elif ck in self.cookies:
                                del self.cookies[ck]

        payload = res.read().decode("utf-8", errors="ignore")
        conn.close()
        return status, res_headers, payload

    def extract_csrf(self, html: str) -> str:
        for marker in ("name='csrf_token' value='", 'name="csrf_token" value="'):
            if marker in html:
                start = html.find(marker) + len(marker)
                quote = marker[-1]
                end = html.find(quote, start)
                return html[start:end]
        return ""

    def register(self, username: str, password: str = "Password123!@#", email: str = "") -> int:
        if not email:
            email = f"{username}@demo.lab"
        status, _, body = self.request("GET", "/register")
        csrf = self.extract_csrf(body)
        status, _, _ = self.request("POST", "/register", {"username": username, "password": password, "email": email, "csrf_token": csrf})
        return status

    def login(self, username: str, password: str = "Password123!@#") -> int:
        status, _, body = self.request("GET", "/login")
        csrf = self.extract_csrf(body)
        status, _, _ = self.request("POST", "/login", {"username": username, "password": password, "csrf_token": csrf})
        return status


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    results = {}
    print("=== STARTING LIVE DOCKER VERIFICATION ===")

    # Ensure required demo services are up
    print("[0] Ensuring lab-ecommerce and gateway-ecommerce are up...")
    rc, out = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml up -d lab-ecommerce gateway-ecommerce")
    assert rc == 0, f"compose up failed: {out}"
    time.sleep(2)

    # 1. LIVE HEALTH
    c = LiveClient()
    status, _, body = c.request("GET", "/health")
    assert status == 200, f"Expected 200, got {status}"
    health_data = json.loads(body)
    assert health_data.get("status") == "ok", f"Health not ok: {health_data}"
    assert health_data.get("target_id") == "lab-ecommerce", f"Unexpected target_id: {health_data}"
    results["health"] = "PASS"
    print("[1] Health check: PASS")

    # 2. FULL PRODUCT E2E (Client A)
    client_a = LiveClient()
    user_a = f"alice_{uuid.uuid4().hex[:6]}"
    reg_status = client_a.register(user_a)
    assert reg_status == 302, f"Register failed: {reg_status}"
    login_status = client_a.login(user_a)
    assert login_status == 302, f"Login failed: {login_status}"
    assert "session" in client_a.cookies, "Missing session cookie for Alice"
    results["register_login_a"] = "PASS"

    # Catalog & Product
    status, _, body = client_a.request("GET", "/products")
    assert status == 200 and "ShopLab" in body, "Catalog failed"
    status, _, body = client_a.request("GET", "/products/1")
    assert status == 200 and "Laptop" in body, "Product 1 failed"
    csrf = client_a.extract_csrf(body)

    # Cart Add
    status, _, _ = client_a.request("POST", "/cart/add", {"product_id": "1", "quantity": "1", "csrf_token": csrf})
    assert status == 302, f"Cart add failed: {status}"

    # View Cart & Checkout
    status, _, body = client_a.request("GET", "/cart")
    assert status == 200 and "Laptop" in body, "Cart view failed"
    csrf = client_a.extract_csrf(body)
    status, _, body = client_a.request("POST", "/checkout", {
        "shipping_name": "Alice Live",
        "shipping_address": "123 Docker Lane",
        "shipping_city": "Container City",
        "shipping_postal": "11111",
        "csrf_token": csrf,
    })
    assert status == 200 and "Order Placed Successfully" in body, f"Checkout failed: {status}"
    order_match = re.search(r"Order #(\d+)", body)
    assert order_match, f"Order ID not found in checkout response: {body}"
    order_id_a = order_match.group(1)
    results["checkout_a"] = "PASS"

    # Orders List & Detail
    status, _, body = client_a.request("GET", "/orders")
    assert status == 200 and f"/orders/{order_id_a}" in body, f"Order list missing order {order_id_a}"
    status, _, body = client_a.request("GET", f"/orders/{order_id_a}")
    assert status == 200 and "$1299.99" in body, "Order detail failed"

    # Invoice Download
    inv_match = re.search(r"file=(INV-[A-F0-9]{32}\.txt)", body)
    assert inv_match, f"Invoice link not found in order {order_id_a}: {body}"
    inv_file_a = inv_match.group(1)
    status, _, inv_body = client_a.request("GET", f"/download/invoice?file={inv_file_a}")
    assert status == 200 and "ShopLab — Lab / Simulated Order Receipt" in inv_body, "Invoice download failed"
    assert "$1299.99" in inv_body, "Invoice content mismatch"
    results["invoice_a"] = "PASS"

    # Review
    status, _, body = client_a.request("GET", "/products/1")
    csrf = client_a.extract_csrf(body)
    review_text = f"Live docker verified laptop {uuid.uuid4().hex[:6]}"
    status, _, _ = client_a.request("POST", "/reviews", {
        "product_id": "1",
        "rating": "5",
        "body": review_text,
        "csrf_token": csrf,
    })
    assert status == 302, f"Review submission failed: {status}"
    status, _, body = client_a.request("GET", "/products/1")
    assert review_text in body, "Review not displayed on product"
    results["review_a"] = "PASS"
    print(f"[2] Full Product E2E for Client A (Order #{order_id_a}): PASS")

    # 3. TWO CLIENT SESSIONS & IDOR ISOLATION
    client_b = LiveClient()
    user_b = f"bob_{uuid.uuid4().hex[:6]}"
    reg_b = client_b.register(user_b)
    assert reg_b == 302, f"Bob register failed: {reg_b}"
    login_b = client_b.login(user_b)
    assert login_b == 302, f"Bob login failed: {login_b}"
    assert client_a.cookies["session"] != client_b.cookies["session"], "Sessions not isolated"

    # Bob cart is isolated (empty)
    status, _, body = client_b.request("GET", "/cart")
    assert "Your cart is empty" in body, "Bob cart not empty"

    # Bob orders Product 2
    status, _, body = client_b.request("GET", "/products/2")
    csrf_b = client_b.extract_csrf(body)
    client_b.request("POST", "/cart/add", {"product_id": "2", "quantity": "1", "csrf_token": csrf_b})
    status, _, body = client_b.request("GET", "/cart")
    csrf_b = client_b.extract_csrf(body)
    status, _, body = client_b.request("POST", "/checkout", {
        "shipping_name": "Bob Live",
        "shipping_address": "456 Gateway Ave",
        "shipping_city": "Docker Town",
        "shipping_postal": "22222",
        "csrf_token": csrf_b,
    })
    assert status == 200 and "Order Placed Successfully" in body, "Bob checkout failed"
    order_match_b = re.search(r"Order #(\d+)", body)
    assert order_match_b, f"Order ID not found in Bob checkout response: {body}"
    order_id_b = order_match_b.group(1)

    # Cross-order IDOR check: Bob cannot access Alice's Order
    status, _, _ = client_b.request("GET", f"/orders/{order_id_a}")
    assert status == 404, f"IDOR check failed: expected 404, got {status}"

    # Cross-invoice IDOR check: Bob cannot access Alice's invoice
    status, _, _ = client_b.request("GET", f"/download/invoice?file={inv_file_a}")
    assert status == 404, f"Invoice IDOR check failed: expected 404, got {status}"

    # Normal user cannot access /admin
    status, _, _ = client_a.request("GET", "/admin")
    assert status == 403, f"Admin check failed: expected 403, got {status}"

    # Missing CSRF fails
    status, _, _ = client_a.request("POST", "/cart/add", {"product_id": "1", "quantity": "1"})
    assert status == 403, f"Missing CSRF check failed: expected 403, got {status}"
    results["two_sessions"] = "PASS"
    print(f"[3] Two Client Sessions & IDOR Isolation (Alice #{order_id_a} vs Bob #{order_id_b}): PASS")

    # 4. CONTAINER RESTART TEST
    print("[4] Testing real container restart...")
    rc, out = run_docker("docker restart cyber-range-lab-ecommerce-1")
    assert rc == 0, f"docker restart failed: {out}"
    time.sleep(2)

    # Verify data survives restart
    status, _, body = client_a.request("GET", "/orders")
    assert status == 200 and f"/orders/{order_id_a}" in body, f"Order {order_id_a} missing after container restart"
    status, _, body = client_a.request("GET", "/products/1")
    assert review_text in body, "Review missing after container restart"
    status, _, inv_body = client_a.request("GET", f"/download/invoice?file={inv_file_a}")
    assert status == 200 and "$1299.99" in inv_body, "Invoice failed after restart"
    results["container_restart"] = "PASS"
    print("[4] Container Restart persistence: PASS")

    # 5. CONTAINER REPLACEMENT TEST
    print("[5] Testing real container replacement (same volume)...")
    rc, orig_cid = run_docker("docker inspect cyber-range-lab-ecommerce-1 --format '{{.Id}}'")
    rc, out = run_docker("docker rm -f cyber-range-lab-ecommerce-1")
    assert rc == 0, f"docker rm failed: {out}"

    rc, out = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml up -d --no-deps lab-ecommerce")
    assert rc == 0, f"compose up lab-ecommerce failed: {out}"
    time.sleep(2)

    rc, new_cid = run_docker("docker inspect cyber-range-lab-ecommerce-1 --format '{{.Id}}'")
    assert new_cid != orig_cid, f"Container was not replaced! Same ID: {new_cid}"
    print(f"  Container replaced: {orig_cid[:12]} -> {new_cid[:12]}")

    # Verify durable state survives container replacement
    status, _, body = client_a.request("GET", "/orders")
    assert status == 200 and f"/orders/{order_id_a}" in body, f"Order {order_id_a} missing after container replacement"
    status, _, body = client_a.request("GET", "/products/1")
    assert review_text in body, "Review missing after container replacement"
    status, _, inv_body = client_a.request("GET", f"/download/invoice?file={inv_file_a}")
    assert status == 200 and "$1299.99" in inv_body, "Invoice failed after replacement"
    results["container_replacement"] = "PASS"
    print("[5] Container Replacement persistence: PASS")

    # 6. FAILURE TEST — TARGET DOWN
    print("[6] Testing failure scenario (target down)...")
    rc, out = run_docker("docker stop cyber-range-lab-ecommerce-1")
    assert rc == 0, f"docker stop failed: {out}"
    time.sleep(1)

    status, _, body = c.request("GET", "/health")
    assert status == 502, f"Expected 502 when target down, got {status}"
    assert "lab-ecommerce" not in body, f"Leaked internal target hostname in error: {body}"

    # Restart target and verify recovery
    rc, out = run_docker("docker start cyber-range-lab-ecommerce-1")
    assert rc == 0, f"docker start failed: {out}"
    time.sleep(2)

    status, _, body = c.request("GET", "/health")
    assert status == 200 and json.loads(body).get("status") == "ok", "Recovery failed"
    results["failure_target_down"] = "PASS"
    print("[6] Failure test (target down -> 502 -> recovery): PASS")

    # 7. RESTORE TO BASELINE TEST
    print("[7] Testing restore to baseline...")
    # Stop target container
    rc, out = run_docker("docker stop cyber-range-lab-ecommerce-1")
    assert rc == 0, f"docker stop failed: {out}"

    # Run restore script in ephemeral container mounted to volume
    restore_cmd = (
        "docker run --rm --entrypoint python -v cyber-range_ecommerce-data:/app/data "
        "cyber-range-lab-ecommerce:latest "
        "-c 'from app import restore_baseline; restore_baseline(\"/app/data\")'"
    )
    rc, out = run_docker(restore_cmd)
    assert rc == 0, f"Restore failed: {out}"

    # Start target container
    rc, out = run_docker("docker start cyber-range-lab-ecommerce-1")
    assert rc == 0, f"docker start failed: {out}"
    time.sleep(2)

    # Health is OK
    status, _, body = c.request("GET", "/health")
    assert status == 200, f"Health after restore failed: {status}"

    # Old sessions of Alice and Bob are invalidated (403)
    status, _, _ = client_a.request("GET", "/orders")
    assert status == 403, f"Expected old session to be rejected with 403, got {status}"

    # Login anew and verify baseline products exist and orders are wiped
    client_c = LiveClient()
    user_c = f"charlie_{uuid.uuid4().hex[:6]}"
    client_c.register(user_c)
    client_c.login(user_c)
    status, _, body = client_c.request("GET", "/orders")
    assert "No orders yet" in body, f"Expected clean orders list, got {body}"

    status, _, body = client_c.request("GET", "/products/1")
    assert review_text not in body, "Review was not reset"
    results["restore_baseline"] = "PASS"
    print("[7] Restore to baseline & session invalidation: PASS")

    # 8. BOUNDED TEARDOWN
    print("[8] Testing bounded teardown...")
    rc, out = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml stop lab-ecommerce gateway-ecommerce")
    assert rc == 0, f"docker compose stop failed: {out}"

    # Check that containers are stopped
    rc, out_running = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml ps --status running -q")
    assert not out_running.strip(), f"Containers still running: {out_running}"
    rc, out_all = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml ps -a")
    assert "cyber-range-lab-ecommerce-1" in out_all and "cyber-range-gateway-ecommerce-1" in out_all, "Owned containers not in ps -a"

    # Volume still exists
    rc, out = run_docker("docker volume ls -q -f name=cyber-range_ecommerce-data")
    assert "cyber-range_ecommerce-data" in out, "Volume unexpectedly deleted"
    results["teardown"] = "PASS"
    print("[8] Bounded teardown: PASS")

    print("\n=== ALL LIVE DOCKER RUNTIME VERIFICATIONS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
