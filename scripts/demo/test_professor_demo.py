"""Kiểm tra stdlib, HTTP fixture loopback; không phải Docker/provider receipts."""
import contextlib
from dataclasses import replace
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_professor_demo as demo
from runtime.discovery_gate import DispatchResponse


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.root = demo.OUTPUT / ("TEST-" + uuid.uuid4().hex)
        self.run_id = "RUN-TEST-" + uuid.uuid4().hex
        self.rec = demo.new_recorder(self.root / "evidence", self.run_id)
        self.hits = []
        hits = self.hits

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                body = (b'<a href="/renamed-from-observation">next</a><form method="POST" action="/never-submit"><input name="csrf"></form>'
                        if self.path == "/" else b"<html>Observed resource</html>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.sink = io.StringIO()

    def gate(self, pages=1):
        gate = demo.make_gate(self.rec, self.origin, pages)
        return gate

    def assess(self, gate=None, **kwargs):
        with contextlib.redirect_stdout(self.sink):
            return demo.assess(gate or self.gate(), self.rec, demo.approval_for(self.run_id), **kwargs)

    def test_safe_one_page_fixture(self):
        with patch("runtime.observed_planner._call_real_provider", side_effect=AssertionError("provider must not run")):
            result = self.assess(preview=True)
        self.assertEqual(result["discovery"]["resources"], 1)
        self.assertEqual(result["discovery"]["forms_submitted"], 0)
        self.assertEqual(result["planner_provenance"]["actual_mode"], "RULE")
        self.assertEqual(self.hits, ["/"])
        self.assertEqual(result["state_summary"]["remaining_budget"]["actions"], 15)
        self.assertEqual(result["state_summary"]["remaining_budget"]["requests"], 0)
        self.assertEqual(result["proposal_decision"]["target_dispatches"], 0)

    def test_observed_renamed_route_and_two_request_ordering(self):
        result = self.assess(self.gate(2))
        self.assertEqual(self.hits, ["/", "/renamed-from-observation"])
        self.assertEqual(result["discovery"]["requests"], 2)
        self.assertEqual(result["discovery"]["forms_submitted"], 0)
        self.assertTrue(demo.EvidenceVerifier.verify_directory(self.rec.directory).ordering_ok)

    def test_verifier_failure_halts_before_planner(self):
        real = demo.EvidenceVerifier.verify_directory(self.rec.directory)
        failed = replace(real, passed=False, ordering_ok=False)
        with patch.object(demo.EvidenceVerifier, "verify_directory", return_value=failed), \
             patch.object(demo.ObservedStatePlanner, "propose", side_effect=AssertionError("planner must halt")), \
             self.assertRaisesRegex(demo.DemoBlocked, "CORE_EVIDENCE_VERIFIER_ORDERING"):
            self.assess(self.gate(2))

    def test_deny_zero_http(self):
        with contextlib.redirect_stdout(self.sink), \
             patch("runtime.discovery_gate.http.client.HTTPConnection", side_effect=AssertionError("no network")):
            result = demo.deny_case(self.gate(), self.rec)
        self.assertEqual(result["decision"], "DENIED")
        self.assertEqual(result["network_dispatch_delta"], 0)
        self.assertEqual(self.hits, [])
        self.assertTrue(demo.verify(self.rec)["passed"])

    def test_missing_approval_zero_http(self):
        gate = self.gate()
        with patch("runtime.discovery_gate.http.client.HTTPConnection", side_effect=AssertionError("no network")):
            response = gate.dispatch(demo.DiscoveryRequest(self.run_id, demo.TARGET, demo.ACTION, self.origin + "/"))
            self.assertEqual(response.refusal_reason, "MISSING_APPROVAL")
            with self.assertRaisesRegex(demo.DemoBlocked, "MISSING_OR_INVALID"):
                demo.assess(gate, self.rec, None)
        self.assertEqual(self.hits, [])

    def test_provider_absent_explicit_fallback(self):
        with patch("runtime.observed_planner._call_real_provider", side_effect=AssertionError("Internet provider forbidden")):
            result = self.assess(planner_mode="llm-unavailable", fallback=True)
        self.assertEqual(result["planner_provenance"]["requested_mode"], "LLM")
        self.assertEqual(result["planner_provenance"]["actual_mode"], "RULE")
        self.assertEqual(result["planner_provenance"]["fallback_reason"], "MOCK_PROVIDER_RETURNED_EMPTY")
        self.assertIn("PROVIDER_NOT_CALLED_OFFLINE_DEMO", self.sink.getvalue())

    def test_provider_absent_without_fallback_halts(self):
        with self.assertRaisesRegex(demo.DemoBlocked, "PLANNER_HALTED"):
            self.assess(planner_mode="llm-unavailable", fallback=False)
        self.assertEqual(self.hits, ["/"])

    def test_intent_failure_zero_http(self):
        self.rec.inject_intent_failure()
        with self.assertRaisesRegex(demo.DemoBlocked, "EVIDENCE_NOT_DURABLE"), \
             patch("runtime.discovery_gate.http.client.HTTPConnection", side_effect=AssertionError("no network")):
            self.assess(self.gate(2))
        self.assertEqual(self.hits, [])

    def test_result_failure_stops_next_request(self):
        self.rec.inject_result_failure()
        with self.assertRaisesRegex(demo.DemoBlocked, "EVIDENCE_NOT_DURABLE"):
            self.assess(self.gate(2))
        self.assertEqual(self.hits, ["/"])

    def test_runtime_unavailable_halts(self):
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaisesRegex(demo.DemoBlocked, "DISCOVERY_RESPONSE_ERROR"):
            self.assess(self.gate(2))
        self.assertEqual(self.hits, [])

    def test_exclusive_directory_and_receipt_redaction(self):
        with self.assertRaises(demo.EvidenceFailure):
            demo.new_recorder(self.rec.directory, self.run_id)
        demo.write_receipt(self.root, {"password": "sensitive-fixture-value"})
        text = (self.root / "summary.json").read_text(encoding="utf-8")
        self.assertNotIn("sensitive-fixture-value", text)
        self.assertEqual(json.loads(text)["password"], "[REDACTED]")
        with self.assertRaises(FileExistsError):
            demo.write_receipt(self.root, {})

    def test_receipt_write_failure_nonzero(self):
        with patch.object(demo, "write_receipt", side_effect=OSError("fixture failure")), \
             contextlib.redirect_stdout(self.sink):
            code = demo.main(["--mode", "deny-demo"])
        self.assertEqual(code, 2)
        self.assertIn("WRITE_FAILED", self.sink.getvalue())

    def test_dry_run_without_approval_no_health(self):
        with patch.object(demo, "docker", return_value=""), \
             patch.object(demo, "service_snapshot", return_value={}), \
             patch.object(demo, "inspect_runtime"), \
             patch.object(demo.CentralizedSafetyGate, "dispatch", side_effect=AssertionError("no HTTP")), \
             contextlib.redirect_stdout(self.sink):
            self.assertEqual(demo.main(["--dry-run"]), 2)
        self.assertIn("NOT_CHECKED", self.sink.getvalue())

    def test_preflight_health_no_assessment(self):
        response = DispatchResponse(200, {}, "", 0, False, "SUCCESS", True, demo.ORIGIN + "/health")
        with patch.object(demo, "docker", return_value=""), \
             patch.object(demo, "service_snapshot", return_value={}), patch.object(demo, "inspect_runtime"), \
             patch.object(demo.CentralizedSafetyGate, "dispatch", return_value=response) as dispatch, \
             patch.object(demo, "assess", side_effect=AssertionError("no assessment")), \
             patch.object(demo, "verify", return_value={"passed": True, "fixture": True}), \
             contextlib.redirect_stdout(self.sink):
            self.assertEqual(demo.main(["--dry-run", "--approve-read-only"]), 0)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.args[0].url, demo.ORIGIN + "/health")

    def test_start_stop_ownership_and_preserve_volume(self):
        running = {"Id": "preexisting", "State": {"Running": True}}
        stopped = {"Id": "owned", "State": {"Running": False}}
        after = {demo.TARGET: running, "gateway-ecommerce": {"Id": "owned", "State": {"Running": True}}}
        owned = {}
        with patch.object(demo, "service_snapshot", side_effect=[{demo.TARGET: running, "gateway-ecommerce": stopped}, after]), \
             patch.object(demo, "compose") as compose:
            demo.start_services(owned)
        self.assertEqual(owned, {"gateway-ecommerce": "owned"})
        compose.assert_called_once_with("start", "gateway-ecommerce")
        with patch.object(demo, "service_snapshot", return_value=after), \
             patch.object(demo, "docker", side_effect=["", json.dumps([stopped]), ""]) as docker:
            result = demo.stop_owned(owned)
        self.assertEqual(result, "OWNED_SERVICES_STOPPED_VOLUME_PRESERVED")
        self.assertEqual(docker.call_args_list[0].args, ("stop", "--time", "10", "owned"))
        self.assertEqual(docker.call_args_list[-1].args, ("volume", "inspect", "cyber-range_ecommerce-data"))

    def test_receipts_byte_identical_after_stop_owned(self):
        demo.write_receipt(self.root, {"run_id": self.run_id, "evidence_refs": []})
        before = demo.file_hashes(self.root)
        row = {"Id": "owned", "State": {"Running": True}}
        stopped = {"Id": "owned", "State": {"Running": False}}
        with patch.object(demo, "service_snapshot", return_value={demo.TARGET: row}), \
             patch.object(demo, "docker", side_effect=["", json.dumps([stopped]), ""]):
            demo.stop_owned({demo.TARGET: "owned"})
        demo.check_files(self.root, before)
        self.assertEqual(demo.file_hashes(self.root), before)

    def test_duplicate_run_id_does_not_change_first_run(self):
        fixed_id = uuid.uuid4()
        with patch.object(demo.uuid, "uuid4", return_value=fixed_id), contextlib.redirect_stdout(self.sink):
            self.assertEqual(demo.main(["--mode", "deny-demo"]), 0)
            directory = demo.OUTPUT / ("RUN-DEMO-" + fixed_id.hex)
            before = demo.file_hashes(directory)
            self.assertEqual(demo.main(["--mode", "deny-demo"]), 2)
        self.assertEqual(before, demo.file_hashes(directory))

    def test_stale_receipt_rejected(self):
        directory = self.root / self.run_id
        directory.mkdir()
        demo.write_receipt(directory, {"run_id": "RUN-OLD", "evidence_refs": []})
        with self.assertRaisesRegex(demo.DemoBlocked, "STALE_RECEIPT"):
            demo.check_receipt(directory, self.run_id)

    def test_failure_keeps_incomplete_diagnostic_receipt(self):
        with patch.object(demo, "docker", side_effect=demo.DemoBlocked("FIXTURE_RUNTIME_UNAVAILABLE")), \
             contextlib.redirect_stdout(self.sink):
            before = set(demo.OUTPUT.glob("RUN-DEMO-*"))
            self.assertEqual(demo.main(["--approve-read-only"]), 2)
        directory, = set(demo.OUTPUT.glob("RUN-DEMO-*")) - before
        result = demo.check_receipt(directory, directory.name)
        self.assertEqual(result["completion_state"], "INCOMPLETE")
        self.assertEqual(result["demo_outcome"], "BLOCKED")
        self.assertTrue(result["evidence_refs"])
        self.assertTrue((directory / "post-run-verification.json").is_file())

    def test_post_stop_receipt_read_failure_blocks(self):
        original = demo.check_files
        def unavailable(directory, expected):
            if "pipeline-summary.json" in expected:
                raise FileNotFoundError("fixture: receipt unavailable")
            return original(directory, expected)
        with patch.object(demo, "check_files", side_effect=unavailable), contextlib.redirect_stdout(self.sink):
            before = set(demo.OUTPUT.glob("RUN-DEMO-*"))
            self.assertEqual(demo.main(["--mode", "deny-demo", "--stop-owned"]), 2)
        directory, = set(demo.OUTPUT.glob("RUN-DEMO-*")) - before
        result = demo.check_receipt(directory, directory.name)
        self.assertEqual(result["completion_state"], "INCOMPLETE")
        self.assertEqual(result["receipts_preserved"], "NO")
        self.assertIn("READY_FOR_DEMO: NO", self.sink.getvalue())

    def test_cleanup_identity_drift_not_stopped(self):
        with patch.object(demo, "service_snapshot", return_value={demo.TARGET: {"Id": "changed"}}), \
             patch.object(demo, "docker", side_effect=AssertionError("must not stop")):
            with self.assertRaisesRegex(demo.DemoBlocked, "CLEANUP_OWNERSHIP"):
                demo.stop_owned({demo.TARGET: "original"})


if __name__ == "__main__":
    unittest.main()
