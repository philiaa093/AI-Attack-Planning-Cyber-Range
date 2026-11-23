"""Offline API-contract tests for the GNS3/vSphere provider."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping
import unittest

from runtime.lab.providers import JsonResponse, RedirectDenyHandler, UrllibJsonTransport
from runtime.lab.providers.gns3_vsphere import GNS3VSphereRangeProvider
from runtime.lab.range_provider import RangeProviderError, validate_provider_contract
from runtime.lab.remote_range_config import parse_remote_range_config


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: Any


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: Any = None,
        timeout: float = 10.0,
    ) -> JsonResponse:
        self.requests.append(RecordedRequest(method, url, dict(headers or {}), body))
        if url.endswith("/api/session"):
            return JsonResponse(201, "session-id", {})
        if "/api/vcenter/vm/" in url and url.endswith("/power") and method == "GET":
            return JsonResponse(200, "POWERED_ON", {})
        if "/v2/projects/" in url and "/nodes/" in url and method == "GET":
            return JsonResponse(200, {"status": "started"}, {})
        if url.endswith("/health"):
            return JsonResponse(200, {"status": "ok"}, {})
        if "/control/v1/" in url:
            return JsonResponse(200, {"status": "ok", "blocked_routes": []}, {})
        if url.endswith("/RevertToCurrentSnapshot_Task"):
            return JsonResponse(202, {"type": "Task", "value": "task-1"}, {})
        if "/Task/" in url and url.endswith("/info"):
            return JsonResponse(200, {"state": "success"}, {})
        if url.endswith("/api/v1/discovery"):
            return JsonResponse(200, {"status": "ok", "services": []}, {})
        return JsonResponse(204, None, {})


class FailingStartTransport(FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def request(self, method: str, url: str, **kwargs: Any) -> JsonResponse:
        if not self.failed and method == "POST" and url.endswith("/start"):
            self.failed = True
            self.requests.append(RecordedRequest(method, url, dict(kwargs.get("headers") or {}), kwargs.get("body")))
            return JsonResponse(500, {"error": "synthetic failure"}, {})
        return super().request(method, url, **kwargs)


class FailingTaskTransport(FakeTransport):
    def request(self, method: str, url: str, **kwargs: Any) -> JsonResponse:
        if "/Task/" in url and url.endswith("/info"):
            self.requests.append(RecordedRequest(method, url, dict(kwargs.get("headers") or {}), kwargs.get("body")))
            return JsonResponse(200, {"state": "error", "error": {"message": "must-not-leak"}}, {})
        return super().request(method, url, **kwargs)


class TestRemoteRangeProvider(unittest.TestCase):
    def setUp(self) -> None:
        raw = json.loads(
            (ROOT / "configs" / "lab" / "remote-range.example.json").read_text(encoding="utf-8")
        )
        self.config = parse_remote_range_config(raw)
        self.environ = {
            "RANGE_CONTROL_TOKEN": "control-token-" + "x" * 40,
            "GNS3_USERNAME": "gns3-user",
            "GNS3_PASSWORD": "gns3-password",
            "VSPHERE_USERNAME": "vsphere-user",
            "VSPHERE_PASSWORD": "vsphere-password",
        }
        self.transport = FakeTransport()
        self.provider = GNS3VSphereRangeProvider(
            self.config,
            transport=self.transport,
            environ=self.environ,
            timeout=1.0,
        )

    def test_provider_contract_and_sanitized_metadata(self) -> None:
        validate_provider_contract(self.provider)
        self.assertTrue(self.provider.capabilities.external_infrastructure)
        metadata = self.provider.metadata
        self.assertEqual(metadata["provider_kind"], "GNS3_VSPHERE")
        self.assertNotIn("password", json.dumps(metadata).lower())
        self.assertNotIn(self.environ["RANGE_CONTROL_TOKEN"], json.dumps(metadata))

    def test_authenticated_transport_denies_redirects(self) -> None:
        handler = RedirectDenyHandler()
        redirected = handler.redirect_request(None, None, 302, "Found", {}, "https://other.invalid")
        self.assertIsNone(redirected)

    def test_transport_denies_host_outside_config_before_network(self) -> None:
        transport = UrllibJsonTransport(allowed_hosts=frozenset({"approved.example.invalid"}))
        with self.assertRaises(RangeProviderError) as ctx:
            transport.request("GET", "https://other.example.invalid/health")
        self.assertEqual(ctx.exception.code, "REMOTE_DESTINATION_DENIED")

    def test_start_health_stop_use_only_fixed_api_paths(self) -> None:
        endpoints = self.provider.start()
        self.assertEqual(set(endpoints), set(self.config.targets))
        health = self.provider.health_check_all()
        self.assertTrue(all(health.values()))
        self.provider.stop()

        urls = [request.url for request in self.transport.requests]
        self.assertTrue(any("/v2/projects/" in url and url.endswith("/open") for url in urls))
        self.assertTrue(any("/api/vcenter/vm/" in url and "action=stop" in url for url in urls))
        for secret in self.environ.values():
            self.assertFalse(any(secret in url for url in urls))

    def test_data_plane_policy_denies_before_transport(self) -> None:
        before = len(self.transport.requests)
        response = self.provider.dispatch_bounded_request(
            "lab-enterprise-dmz",
            "POST",
            "/control/v1/reset",
            body={},
        )
        self.assertEqual(response["error"], "DATA_PLANE_ACTION_DENIED")
        self.assertEqual(len(self.transport.requests), before)

        response = self.provider.dispatch_bounded_request(
            "unknown-target",
            "GET",
            "/health",
        )
        self.assertEqual(response["error"], "UNKNOWN_TARGET")
        self.assertEqual(len(self.transport.requests), before)

    def test_bounded_dispatch_and_control_route(self) -> None:
        response = self.provider.dispatch_bounded_request(
            "lab-enterprise-dmz",
            "GET",
            "/api/v1/discovery",
        )
        self.assertEqual(response["http_status"], 200)
        self.provider.block_route("lab-enterprise-internal", "primary")
        control_request = self.transport.requests[-1]
        self.assertTrue(control_request.url.endswith("/control/v1/routes/block"))
        self.assertEqual(control_request.headers["Authorization"], f"Bearer {self.environ['RANGE_CONTROL_TOKEN']}")

    def test_restore_uses_fixed_current_snapshot_operation(self) -> None:
        self.provider.reset_all()
        snapshot_requests = [
            request for request in self.transport.requests
            if request.url.endswith("/RevertToCurrentSnapshot_Task")
        ]
        self.assertEqual(len(snapshot_requests), len(self.config.targets))
        self.assertTrue(all(request.body == {"suppressPowerOn": True} for request in snapshot_requests))
        task_requests = [
            request for request in self.transport.requests
            if "/Task/task-1/info" in request.url
        ]
        self.assertEqual(len(task_requests), len(self.config.targets))

    def test_restore_task_failure_halts_without_power_on(self) -> None:
        transport = FailingTaskTransport()
        provider = GNS3VSphereRangeProvider(
            self.config,
            transport=transport,
            environ=self.environ,
            timeout=1.0,
        )
        with self.assertRaises(RangeProviderError) as ctx:
            provider.reset_all()
        self.assertEqual(ctx.exception.code, "VSPHERE_SNAPSHOT_REVERT_TASK_FAILED")
        snapshot_index = next(
            index for index, request in enumerate(transport.requests)
            if request.url.endswith("/RevertToCurrentSnapshot_Task")
        )
        self.assertFalse(
            any("/power?action=start" in request.url for request in transport.requests[snapshot_index + 1:])
        )

    def test_missing_secret_fails_before_network(self) -> None:
        with self.assertRaises(RangeProviderError) as ctx:
            GNS3VSphereRangeProvider(
                self.config,
                transport=self.transport,
                environ={},
            )
        self.assertEqual(ctx.exception.code, "REMOTE_SECRET_MISSING")
        self.assertEqual(self.transport.requests, [])

    def test_partial_start_rolls_back_powered_vms(self) -> None:
        transport = FailingStartTransport()
        provider = GNS3VSphereRangeProvider(
            self.config,
            transport=transport,
            environ=self.environ,
            timeout=1.0,
        )
        with self.assertRaises(RangeProviderError) as ctx:
            provider.start()
        self.assertEqual(ctx.exception.code, "GNS3_NODE_START_FAILED")
        self.assertTrue(
            any("/power?action=stop" in request.url for request in transport.requests),
            "Partial start must attempt bounded vSphere rollback",
        )


if __name__ == "__main__":
    unittest.main()
