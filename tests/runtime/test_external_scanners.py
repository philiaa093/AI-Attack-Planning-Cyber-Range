"""Scanner isolation and integration checks; real Docker scans use only a local fixture."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dashboards.app.backend.models import StartRunRequest
from dashboards.app.backend.run_manager import _run_gate
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder, EvidenceFailure
from runtime.discovery.discovery_engine import HTMLMetadataParser
from runtime.lab.external_scanners import ExternalScannerExecutor, ScannerRelay, isolated_scan, load_config, preflight, parse_runtime_nuclei
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.safety.discovery_gate import ApprovalToken, BudgetTracker, CentralizedSafetyGate, TokenBucketRateLimiter


class ExternalScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.recorder = DurableEvidenceRecorder("RUN-SCANNER-TEST", self.root / "evidence", approved_root=self.root)
        self.approval = ApprovalToken("APP-TEST", "RUN-SCANNER-TEST", "lab-ecommerce", "*", time.time()-1, time.time()+600)
        self.gate = CentralizedSafetyGate("http://127.0.0.1:18088", recorder=self.recorder,
            action_allowlist={"ACTION-SCAN-002"}, target_allowlist={"lab-ecommerce"},
            rate_limiter=TokenBucketRateLimiter(1000, 10), budget_tracker=BudgetTracker(max_requests=100))
        self.inventory = SimpleNamespace(items={"/products": SimpleNamespace(
            canonical_url=self.gate.base_origin + "/products", refusal_reason=None,
            forms=[{"method": "GET", "action": "/products", "inputs": [{"name": "q"}]},
                   {"method": "POST", "action": "/products", "inputs": [{"name": "secret"}]}])})
        self.cancelled = False
        self.relay = ScannerRelay(self.gate, self.recorder, "RUN-SCANNER-TEST", "lab-ecommerce",
            self.inventory, self.approval, "ACTION-SCAN-002", lambda: self.cancelled)

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_urls_preserve_observed_values_without_inventing_select_defaults(self):
        item = self.inventory.items["/products"]
        item.canonical_url += "?category=2&q=blue+shirt&q=coat"
        item.forms[0]["inputs"].append({"name": "category", "type": "select"})
        relay = ScannerRelay(self.gate, self.recorder, "RUN-SCANNER-TEST", "lab-ecommerce",
            self.inventory, self.approval, "ACTION-SCAN-002", lambda: False)
        self.assertIn("http://lab-ecommerce/products?category=2&q=blue+shirt&q=coat", relay.urls())
        self.assertIn("http://lab-ecommerce/products?q=", relay.urls())
        self.assertFalse(any("labprobe" in url or "category=" in url and "category=2" not in url
                             for url in relay.urls()))
        self.assertTrue(all("secret" not in url for url in relay.urls()))

    def execute(self, executor):
        return executor.execute({"action_id": "ACTION-SCAN-002"}, self.gate, self.recorder,
            "RUN-SCANNER-TEST", "lab-ecommerce", self.inventory, self.approval)

    def test_observed_select_options_become_gated_baseline_seeds(self):
        parser = HTMLMetadataParser(self.gate.base_origin + "/products")
        parser.feed('<form method="GET" action="/products"><input name="q" type="search">'
                    '<select name="category"><option value="">All</option>'
                    '<option value="disabled" disabled>Disabled</option>'
                    '<optgroup disabled><option value="hidden">Hidden</option></optgroup>'
                    '<option value="2">Two</option><option value="3" selected>Three</option></select></form>')
        self.inventory.items["/products"].forms = [asdict(form) for form in parser.forms]
        options = parser.forms[0].inputs[1]["options"]
        self.assertEqual([option["value"] for option in options], ["", "2", "3"])
        relay = ScannerRelay(self.gate, self.recorder, "RUN-SCANNER-TEST", "lab-ecommerce",
            self.inventory, self.approval, "ACTION-SCAN-002", lambda: False)
        seed = "http://lab-ecommerce/products?category=3&q="
        self.assertIn(seed, relay.urls())
        response = SimpleNamespace(status_code=200, durable_confirmed=True, truncated=False, body="fixture", headers={})
        with patch.object(self.gate, "dispatch", return_value=response) as dispatch:
            self.assertEqual(relay.dispatch({"url": seed, "method": "GET"})["status"], 200)
        self.assertEqual(dispatch.call_args.args[0].url, self.gate.base_origin + "/products?category=3&q=")

    def test_select_metadata_is_bounded_and_excludes_sensitive_or_unsupported_values(self):
        parser = HTMLMetadataParser(self.gate.base_origin)
        parser.feed('<form><select name="category">' +
                    '<option value="x">X</option>' * 30 + '</select>' +
                    '<select name="token"><option value="private">Private</option></select>'
                    '<select name="multi" multiple><option value="x">X</option></select>'
                    '<select name="off" disabled><option value="x">X</option></select>'
                    '<select name="bad"><option>No value</option><option value="&#10;">Bad</option>'
                    '<option value="' + 'x' * 129 + '">Long</option></select></form>'
                    '<form method="POST"><select name="post"><option value="x">X</option></select></form>')
        fields = parser.forms[0].inputs
        self.assertEqual(len(fields[0]["options"]), 16)
        for field in fields[1:4]:
            self.assertNotIn("options", field)
        self.assertEqual(fields[4]["options"], [])
        self.assertNotIn("options", parser.forms[1].inputs[0])

    def test_scope_validation_before_dispatch(self):
        bad = [None, [], {}, {"url": "http://lab-ecommerce/products", "method": "POST"},
               {"url": "http://lab-ecommerce/products", "method": "GET", "headers": {}},
               *({"url": url, "method": "GET"} for url in (
                   "http://example.com/products", "http://lab-ecommerce:8080/products", "http://lab-ecommerce@evil/products",
                   "http://lab-ecommerce/unobserved", "http://lab-ecommerce/products?secret=a",
                   "http://lab-ecommerce/products?new=1", "http://lab-ecommerce/products#x",
                   "http://lab-ecommerce/products\r\nX:1", "file:///products", "http://lab-ecommerce/../products"))]
        with patch.object(self.gate, "dispatch") as dispatch:
            for request in bad:
                with self.subTest(request=request):
                    self.assertEqual(self.relay.dispatch(request)["status"], 403)
            dispatch.assert_not_called()
        self.assertEqual(self.relay.refusals, len(bad))

    def test_request_maps_to_gate_without_headers_or_body(self):
        response = SimpleNamespace(status_code=200, durable_confirmed=True, truncated=False,
            body="test", headers={"Set-Cookie": "token=secret", "Content-Type": "text/html"})
        with patch.object(self.gate, "dispatch", return_value=response) as dispatch:
            result = self.relay.dispatch({"url": "http://lab-ecommerce/products?q=probe", "method": "GET"})
        request = dispatch.call_args.args[0]
        self.assertEqual(request.url, "http://127.0.0.1:18088/products?q=probe")
        self.assertEqual(request.action_id, "ACTION-SCAN-002")
        self.assertEqual(request.headers, {})
        self.assertNotIn("Set-Cookie", result["headers"])

    def test_revocation_budget_stop_and_missing_approval(self):
        changes = [lambda: setattr(self, "cancelled", True), lambda: self.approval.revoke(),
                   lambda: self.gate.revoke_target("lab-ecommerce"), lambda: self.gate.kill_switch.activate(),
                   lambda: self.gate.effective_actions.clear(), lambda: setattr(self.relay, "approval", None),
                   lambda: setattr(self.gate.budget_tracker, "max_requests", 0)]
        for change in changes:
            with self.subTest(change=change), patch.object(self.gate, "dispatch") as dispatch:
                change()
                with self.assertRaises(RuntimeError):
                    self.relay.dispatch({"url": "http://lab-ecommerce/products", "method": "GET"})
                dispatch.assert_not_called()
            self.cancelled = False
            self.approval.revoked = False
            self.relay.approval = self.approval
            self.gate.effective_targets.add("lab-ecommerce")
            self.gate.effective_actions.add("ACTION-SCAN-002")
            self.gate.kill_switch = type(self.gate.kill_switch)()
            self.gate.budget_tracker.max_requests = 100

    def test_evidence_failure_prevents_network(self):
        self.recorder._inject_intent_failure = True
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            with self.assertRaises(EvidenceFailure):
                self.relay.dispatch({"url": "http://lab-ecommerce/products", "method": "GET"})
            connection.assert_not_called()
        self.assertTrue(self.gate.halted_due_to_evidence)

    def test_external_approval_is_separate_and_narrowing(self):
        self.assertNotIn("ACTION-SCAN-002", _run_gate(StartRunRequest(approve_active_verification=True)).effective_actions)
        self.assertIn("ACTION-SCAN-002", _run_gate(StartRunRequest(approve_active_verification=True,
                                                              external_scanners=["nuclei"])).effective_actions)
        for fields in ({"external_scanners": ["nuclei"]},
                       {"external_scanners": ["unknown"], "approve_active_verification": True},
                       {"external_scanners": ["nuclei", "nuclei"], "approve_active_verification": True},
                       {"external_scanners": ["zap-passive", "zap-active"], "approve_active_verification": True},
                       {"external_scanners": ["nuclei"], "approve_active_verification": True, "preview_one_page": True}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                StartRunRequest(**fields)

    def test_failed_or_empty_execution_never_reports_clean(self):
        for behavior in (RuntimeError("SCANNER_TIMEOUT"), b""):
            executor = ExternalScannerExecutor(["nuclei"])
            with patch("runtime.lab.external_scanners.preflight", return_value={}), \
                 patch("runtime.lab.external_scanners.isolated_scan", side_effect=behavior if isinstance(behavior, Exception) else None,
                       return_value=behavior):
                result = self.execute(executor)
            self.assertEqual(result.outcome, "FAILURE")
            self.assertEqual(result.classification, "INCONCLUSIVE")
            self.assertEqual(executor.results[0]["coverage"], "INCOMPLETE")
            self.assertTrue(result.result_evidence_id)

    def test_report_provenance_and_candidates_not_confirmed(self):
        raw = json.dumps({"template-id": "lab-sql-error", "type": "http", "matcher-status": True,
            "host": "http://lab-ecommerce", "matched-at": "http://lab-ecommerce/products?q=x",
            "info": {"severity": "info", "tags": ["sqli"]}}).encode()
        def scan(*args):
            self.gate.network_dispatch_count += 1
            args[1].executed_urls.add("http://lab-ecommerce/products?q=x")
            return raw
        executor = ExternalScannerExecutor(["nuclei"])
        with patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan):
            result = self.execute(executor)
        self.assertEqual(result.outcome, "SUCCESS")
        self.assertEqual(result.findings[0].classification, "CANDIDATE")
        self.assertEqual(len(executor.results[0]["report_sha256"]), 64)
        self.assertTrue(executor.results[0]["asset_hashes"])
        with self.assertRaises(ValueError):
            self.execute(executor)

    def test_runner_does_not_offer_unselected_scanner_and_stop_revokes(self):
        runner = AutonomousRunner("lab-ecommerce", self.gate, self.recorder, self.approval)
        self.assertNotIn("ACTION-SCAN-002", runner.planner.effective_actions)
        selected = AutonomousRunner("lab-ecommerce", self.gate, self.recorder, self.approval,
                                    external_scanners=("nuclei",))
        selected.request_stop()
        self.assertTrue(self.gate.kill_switch.is_active())

    def test_real_report_url_must_have_a_gated_request(self):
        for matched in ("http://example.com/products", "http://lab-ecommerce/unvisited"):
            raw = json.dumps({"matched-at": matched}).encode()
            with self.subTest(matched=matched), self.assertRaises(ValueError):
                parse_runtime_nuclei(raw, self.relay)

    def test_gate_origin_must_match_registered_loopback_gateway(self):
        for origin in ("http://127.0.0.1:9999", "http://lab-ecommerce:18088", "http://127.0.0.1:18088/path"):
            with self.subTest(origin=origin), patch.object(self.gate, "base_origin", origin):
                with self.assertRaisesRegex(RuntimeError, "SCANNER_GATE_ORIGIN_MISMATCH"):
                    self.relay.check()

    def test_default_port_canonicalization_and_result_failure(self):
        response = SimpleNamespace(status_code=200, durable_confirmed=True, truncated=False, body="ok", headers={})
        with patch.object(self.gate, "dispatch", return_value=response):
            self.relay.dispatch({"url": "http://lab-ecommerce:80/products?q=x", "method": "GET"})
        self.assertIn("http://lab-ecommerce/products?q=x", self.relay.executed_urls)
        self.recorder._inject_result_failure = True
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.getheaders.return_value = []
        connection.getresponse.return_value.read.return_value = b"ok"
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection", return_value=connection):
            with self.assertRaises(EvidenceFailure):
                self.relay.dispatch({"url": "http://lab-ecommerce/products", "method": "GET"})
        self.assertTrue(self.gate.halted_due_to_evidence)
        with self.assertRaises(EvidenceFailure):
            self.relay.check()

    def test_zap_ignores_alerts_on_requests_refused_by_relay(self):
        from runtime.lab.external_scanners import parse_runtime_zap
        report = {"site": [{"@host": "lab-ecommerce", "@name": "http://lab-ecommerce", "alerts": [{"alert": "SQL Injection", "confidence": "3",
            "instances": [{"uri": "http://lab-ecommerce/products?q=x"}, {"uri": "http://lab-ecommerce/blocked"}]}]}]}
        self.relay.executed_urls.add("http://lab-ecommerce/products?q=x")
        self.assertEqual(len(parse_runtime_zap(report, self.relay)), 1)

    def test_runner_ingests_scanner_outcome_and_cannot_repeat_batch(self):
        runner = AutonomousRunner("lab-ecommerce", self.gate, self.recorder, self.approval,
                                    external_scanners=("nuclei",))
        runner.inventory = self.inventory
        def scan(*args):
            self.gate.network_dispatch_count += 1
            return b""
        proposal = {"action_id": "ACTION-SCAN-002", "target_id": "lab-ecommerce"}
        self.assertEqual(runner._evaluate_safety(proposal)[0], "APPROVED")
        with patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan):
            trace = runner._execute_approved_action(proposal, {"actual_mode": "RULE"}, 1, "fixture")
        self.assertEqual(trace.outcome, "SUCCESS")
        self.assertIn("ACTION-SCAN-002", runner.state_manager.get_state()["previous_actions"])
        self.assertEqual(runner._evaluate_safety(proposal)[1], "SCANNER_ALREADY_EXECUTED")

    @unittest.skipUnless(os.environ.get("SCANNER_DOCKER_TESTS") == "1", "Opt-in real isolated scanner/fixture test")
    def test_real_scanners_on_local_fixture(self):
        received = []
        class Fixture(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                body = b"<html><body>SQL syntax: fixture signal, not a vulnerability</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Fixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = "http://127.0.0.1:" + str(server.server_port)
            self.gate.base_origin = origin
            self.gate.target_registry["lab-ecommerce"]["port"] = server.server_port
            self.gate.canonicalizer = type(self.gate.canonicalizer)(origin)
            self.inventory.items["/products"].canonical_url = origin + "/products"
            parser = HTMLMetadataParser(origin + "/products")
            parser.feed('<form action="/products"><input name="q" type="search">'
                        '<select name="category"><option value="2">Two</option></select></form>')
            self.inventory.items["/products"].forms = [asdict(form) for form in parser.forms]
            tool = os.environ.get("SCANNER_TEST_TOOL", "nuclei")
            result = self.execute(ExternalScannerExecutor([tool]))
            self.assertEqual(result.outcome, "SUCCESS", result.details)
            self.assertGreater(result.network_dispatch_count, 0)
            self.assertTrue(any(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query,
                                keep_blank_values=True) == {"category": ["2"], "q": [""]} for url in received))
            self.assertTrue(all(f.classification == "CANDIDATE" for f in result.findings))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    @unittest.skipUnless(os.environ.get("SCANNER_ISOLATION_TESTS") == "1", "Opt-in Docker isolation/cancellation check")
    def test_real_container_isolation_and_cancellation(self):
        identities, config = preflight(["nuclei"]), load_config()
        original_popen = subprocess.Popen
        inspected = []
        created = []
        def launch(command, *args, **kwargs):
            if command[:2] == ["docker", "run"]:
                created.append(command[command.index("--name") + 1])
            if "--network" in command and command[command.index("--network") + 1].startswith("container:"):
                bridge = command[command.index("--network") + 1].split(":", 1)[1]
                info = json.loads(subprocess.run(["docker", "inspect", bridge], capture_output=True,
                                                text=True, timeout=10, check=True).stdout)[0]
                self.assertEqual(info["HostConfig"]["NetworkMode"], "none")
                self.assertTrue(info["HostConfig"]["ReadonlyRootfs"])
                self.assertEqual(info["Config"]["User"], "1000:1000")
                self.assertIn("ALL", info["HostConfig"]["CapDrop"])
                self.assertEqual([m["Destination"] for m in info["Mounts"] if m["Type"] == "bind"], ["/scanner"])
                self.assertFalse(info["NetworkSettings"]["Networks"]["none"]["Gateway"])
                inspected.append(bridge)
            return original_popen(command, *args, **kwargs)
        response = SimpleNamespace(status_code=200, durable_confirmed=True, truncated=False,
                                   body="fixture", headers={})
        def dispatch(request):
            self.gate.network_dispatch_count += 1
            self.gate.kill_switch.activate()
            return response
        with patch("runtime.lab.external_scanners.subprocess.Popen", side_effect=launch), \
             patch.object(self.gate, "dispatch", side_effect=dispatch):
            with self.assertRaisesRegex(RuntimeError, "SCANNER_CANCELLED"):
                isolated_scan("nuclei", self.relay, identities, config)
        self.assertEqual(self.gate.network_dispatch_count, 1)
        self.assertTrue(inspected)
        for name in created:
            result = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, "Container must be removed after cancellation")


if __name__ == "__main__":
    unittest.main()
