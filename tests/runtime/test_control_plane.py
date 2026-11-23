"""Focused RT-06P tests for management/data plane separation."""
from __future__ import annotations

import http.client
import json
import secrets
import threading
import unittest
from http.server import ThreadingHTTPServer

from runtime.lab.enterprise_range.control import ControlPlaneHandler
from runtime.lab.enterprise_range.services import (
    DMZServiceHandler,
    InternalServiceHandler,
    TargetState,
    _validate_relay_request,
)


class TestEnterpriseControlPlane(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.token = secrets.token_urlsafe(32)
        cls.state = TargetState("lab-enterprise-internal", "ZONE_INTERNAL")

        class BoundControl(ControlPlaneHandler):
            target_state = cls.state
            control_token = cls.token

        class BoundData(InternalServiceHandler):
            target_state = cls.state

        cls.control_server = ThreadingHTTPServer(("127.0.0.1", 0), BoundControl)
        cls.data_server = ThreadingHTTPServer(("127.0.0.1", 0), BoundData)
        cls.control_thread = threading.Thread(target=cls.control_server.serve_forever, daemon=True)
        cls.data_thread = threading.Thread(target=cls.data_server.serve_forever, daemon=True)
        cls.control_thread.start()
        cls.data_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        for server in (cls.control_server, cls.data_server):
            server.shutdown()
            server.server_close()
        cls.control_thread.join(timeout=2.0)
        cls.data_thread.join(timeout=2.0)

    def setUp(self) -> None:
        self.state.reset()

    def _request(
        self,
        port: int,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        token: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        encoded = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        headers: dict[str, str] = {}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(encoded))
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        try:
            conn.request(method, path, body=encoded, headers=headers)
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            conn.close()

    def test_control_plane_requires_bearer_token_without_echo(self) -> None:
        port = self.control_server.server_address[1]
        for token in (None, "wrong-secret-value-that-must-not-echo"):
            with self.subTest(token=token):
                status, payload = self._request(port, "GET", "/control/v1/health", token=token)
                self.assertEqual(status, 403)
                self.assertEqual(payload["error"], "CONTROL_AUTH_REQUIRED")
                if token:
                    self.assertNotIn(token, json.dumps(payload))

    def test_control_lifecycle_and_route_operations(self) -> None:
        port = self.control_server.server_address[1]
        status, health = self._request(port, "GET", "/control/v1/health", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(health["target_id"], "lab-enterprise-internal")

        status, blocked = self._request(
            port,
            "POST",
            "/control/v1/routes/block",
            {"route": "primary"},
            self.token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(blocked["blocked_routes"], ["primary"])

        status, unblocked = self._request(
            port,
            "POST",
            "/control/v1/routes/unblock",
            {"route": "primary"},
            self.token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(unblocked["blocked_routes"], [])

        before = self.state.reset_count
        status, reset = self._request(port, "POST", "/control/v1/reset", {}, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(reset["reset_count"], before + 1)

    def test_data_plane_has_no_lifecycle_or_admin_routes(self) -> None:
        port = self.data_server.server_address[1]
        for path in ("/reset", "/api/v1/admin/block_route", "/api/v1/admin/unblock_route"):
            with self.subTest(path=path):
                status, payload = self._request(port, "POST", path, {"route": "primary"})
                self.assertEqual(status, 404)
                self.assertEqual(payload["error"], "NOT_FOUND")

    def test_relay_cannot_reach_control_plane(self) -> None:
        requests = (
            {
                "target_host": "internal-service",
                "target_port": 9090,
                "method": "POST",
                "path": "/control/v1/reset",
            },
            {
                "target_host": "internal-service",
                "target_port": 8080,
                "method": "POST",
                "path": "/control/v1/reset",
            },
        )
        for request in requests:
            with self.subTest(request=request):
                normalized, rejection = _validate_relay_request("lab-enterprise-dmz", request)
                self.assertIsNone(normalized)
                self.assertIsNotNone(rejection)
                self.assertIn(rejection[1], {"RELAY_DESTINATION_DENIED", "RELAY_ACTION_DENIED"})


class TestDataPlaneResetRemoval(unittest.TestCase):
    def test_dmz_reset_is_not_a_data_plane_operation(self) -> None:
        state = TargetState("lab-enterprise-dmz", "ZONE_DMZ")

        class BoundDMZ(DMZServiceHandler):
            target_state = state

        server = ThreadingHTTPServer(("127.0.0.1", 0), BoundDMZ)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2.0)
        try:
            conn.request("POST", "/reset", body=b"{}", headers={"Content-Length": "2"})
            response = conn.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 404)
            self.assertEqual(payload["error"], "NOT_FOUND")
        finally:
            conn.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
