"""Recorder Preflight Tests (E01-E07) for SL-08.

Mandatory prerequisite before any live ShopLab dispatch:
  E01: intent write success -> request may proceed.
  E02: intent write failure -> zero network dispatch.
  E03: decision write failure -> zero network dispatch.
  E04: result write failure -> exactly current request may have occurred, but no subsequent request.
  E05: recorder directory unavailable -> fail closed.
  E06: short/partial write -> fail closed.
  E07: redacted receipt contains no cookie/session/CSRF/raw credentials.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
)
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
)


class MockServer:
    """Ephemeral loopback HTTP server tracking exact requests received."""

    def __init__(self) -> None:
        self.request_count = 0
        self.last_path = ""
        self.last_headers: dict[str, str] = {}

        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parent.request_count += 1
                parent.last_path = self.path
                parent.last_headers = dict(self.headers)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>OK</h1></body></html>")

            def log_message(self, format: str, *args: object) -> None:
                pass  # Silence output during tests

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)


class RecorderPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_server = MockServer()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.evidence_dir = Path(self.temp_dir.name) / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        self.target_id = "lab-ecommerce"
        self.action_id = "ACTION-RECON-002"
        self.run_id = "RUN-PREFLIGHT-001"
        self.base_origin = f"http://127.0.0.1:{self.mock_server.port}"

        self.target_registry = {
            self.target_id: {"host": "127.0.0.1", "port": self.mock_server.port}
        }
        self.target_allowlist = {self.target_id}
        self.action_allowlist = {self.action_id}

        self.approval = ApprovalToken(
            approval_id="APP-001",
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            not_before=time.time() - 10,
            expires_at=time.time() + 300,
        )

    def tearDown(self) -> None:
        self.mock_server.close()
        self.temp_dir.cleanup()

    def _make_gate(self, recorder: DurableEvidenceRecorder) -> CentralizedSafetyGate:
        return CentralizedSafetyGate(
            base_origin=self.base_origin,
            target_registry=self.target_registry,
            target_allowlist=self.target_allowlist,
            action_allowlist=self.action_allowlist,
            recorder=recorder,
            lab_mode=True,
        )

    def test_e01_intent_success_request_proceeds(self) -> None:
        """E01: intent write success -> request may proceed."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        gate = self._make_gate(recorder)

        req = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/",
            approval=self.approval,
        )

        resp = gate.dispatch(req)

        self.assertEqual(gate.network_dispatch_count, 1)
        self.assertEqual(self.mock_server.request_count, 1)
        self.assertTrue(resp.durable_confirmed)
        self.assertEqual(resp.outcome, "SUCCESS")
        self.assertEqual(resp.status_code, 200)

        # Confirm artifacts exist on disk
        artifacts = list(self.evidence_dir.glob("*.json"))
        self.assertGreaterEqual(len(artifacts), 4)  # intent, record-intent, result, record-result

    def test_e02_intent_write_failure_zero_dispatch(self) -> None:
        """E02: intent write failure -> zero network dispatch."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        recorder.inject_intent_failure(True)
        gate = self._make_gate(recorder)

        req = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/",
            approval=self.approval,
        )

        resp = gate.dispatch(req)

        self.assertEqual(gate.network_dispatch_count, 0)
        self.assertEqual(self.mock_server.request_count, 0)
        self.assertFalse(resp.durable_confirmed)
        self.assertEqual(resp.refusal_reason, "INTENT_EVIDENCE_WRITE_FAILED")

    def test_e03_decision_write_failure_zero_dispatch(self) -> None:
        """E03: decision write failure -> zero network dispatch."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        recorder.inject_decision_failure(True)
        gate = self._make_gate(recorder)

        req = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/",
            approval=self.approval,
        )

        resp = gate.dispatch(req)

        self.assertEqual(gate.network_dispatch_count, 0)
        self.assertEqual(self.mock_server.request_count, 0)
        self.assertFalse(resp.durable_confirmed)
        self.assertEqual(resp.refusal_reason, "INTENT_EVIDENCE_WRITE_FAILED")

    def test_e04_result_write_failure_stops_subsequent_dispatch(self) -> None:
        """E04: result write failure -> exactly current request may have occurred, but no subsequent request."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        recorder.inject_result_failure(True)
        gate = self._make_gate(recorder)

        req1 = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/",
            approval=self.approval,
        )

        resp1 = gate.dispatch(req1)

        # Exactly 1 request occurred
        self.assertEqual(gate.network_dispatch_count, 1)
        self.assertEqual(self.mock_server.request_count, 1)
        self.assertFalse(resp1.durable_confirmed)
        self.assertEqual(resp1.refusal_reason, "RESULT_EVIDENCE_WRITE_FAILED")

        # Gate must be halted: scheduling subsequent request must be refused with ZERO dispatch!
        req2 = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/catalog",
            approval=self.approval,
        )

        resp2 = gate.dispatch(req2)
        # Dispatch count remains strictly 1!
        self.assertEqual(gate.network_dispatch_count, 1)
        self.assertEqual(self.mock_server.request_count, 1)
        self.assertFalse(resp2.durable_confirmed)
        self.assertEqual(resp2.refusal_reason, "HALTED_DUE_TO_EVIDENCE_FAILURE")

    def test_e05_recorder_directory_unavailable_fail_closed(self) -> None:
        """E05: recorder directory unavailable -> fail closed."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        recorder.inject_dir_error(True)
        gate = self._make_gate(recorder)

        req = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/",
            approval=self.approval,
        )

        resp = gate.dispatch(req)

        self.assertEqual(gate.network_dispatch_count, 0)
        self.assertEqual(self.mock_server.request_count, 0)
        self.assertFalse(resp.durable_confirmed)

    def test_e06_short_partial_write_fail_closed(self) -> None:
        """E06: short/partial write -> fail closed."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        recorder.inject_partial_write(True)
        gate = self._make_gate(recorder)

        req = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/",
            approval=self.approval,
        )

        resp = gate.dispatch(req)

        self.assertEqual(gate.network_dispatch_count, 0)
        self.assertEqual(self.mock_server.request_count, 0)
        self.assertFalse(resp.durable_confirmed)

    def test_e07_redacted_receipt_contains_no_secrets(self) -> None:
        """E07: redacted receipt contains no cookie/session/CSRF/raw credentials."""
        recorder = DurableEvidenceRecorder(run_id=self.run_id, base_dir=self.evidence_dir)
        gate = self._make_gate(recorder)

        synthetic_session = "SYNTHETIC_SESSION_TOKEN_XYZ_987654"
        synthetic_csrf = "SYNTHETIC_CSRF_ABC_123456"
        synthetic_password = "SUPER_SECRET_PASSWORD_999"

        req = DiscoveryRequest(
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"{self.base_origin}/search?session={synthetic_session}&csrf_token={synthetic_csrf}&password={synthetic_password}",
            headers={
                "Cookie": f"session={synthetic_session}",
                "X-CSRF-Token": synthetic_csrf,
                "Authorization": f"Bearer {synthetic_session}",
            },
            approval=self.approval,
        )

        resp = gate.dispatch(req)
        self.assertTrue(resp.durable_confirmed)

        # Inspect all persisted files in evidence directory
        evidence_files = list(self.evidence_dir.glob("*.json"))
        self.assertGreater(len(evidence_files), 0)

        for ef in evidence_files:
            content = ef.read_text(encoding="utf-8")
            self.assertNotIn(synthetic_session, content)
            self.assertNotIn(synthetic_csrf, content)
            self.assertNotIn(synthetic_password, content)


if __name__ == "__main__":
    unittest.main()
