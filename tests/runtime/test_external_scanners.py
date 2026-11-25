"""Scanner isolation and integration checks; real Docker scans use only a local fixture."""
import json
import hashlib
import io
import os
from pathlib import Path
import runpy
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
from runtime.lab.capability_registry import CapabilityExecutionResult
from runtime.lab.external_scanners import (
    ExternalScannerExecutor, ScannerRelay, isolated_scan, load_config, preflight,
    parse_runtime_nuclei, recorded_scanner_coverage,
)
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.safety.discovery_gate import ApprovalToken, BudgetTracker, CentralizedSafetyGate, TokenBucketRateLimiter
from tools.parsers import zap_parser


class RecordedScannerCoverageTests(unittest.TestCase):
    def test_coverage_and_seed_count_require_explicit_measurements(self):
        for coverage, seed, expected in (
            ("BOUNDED", {"not_requested_seed_count": 0}, ("BOUNDED", 0)),
            ("PARTIAL", {"not_requested_seed_count": 2}, ("PARTIAL", 2)),
            (None, None, (None, None)),
            ("BOUNDED", {"not_requested_seed_count": False}, ("BOUNDED", None)),
            ("UNKNOWN", {"not_requested_seed_count": -1}, (None, None)),
        ):
            with self.subTest(coverage=coverage, seed=seed):
                result = {"status": "COMPLETED", "coverage": coverage, "seed_coverage": seed}
                self.assertEqual(recorded_scanner_coverage(result), expected)

    def test_only_same_run_records_with_evidence_count_for_selected_scanners(self):
        executor = ExternalScannerExecutor(("zap-passive", "nuclei"))
        bounded = {
            "run_id": "RUN-UNIT", "status": "COMPLETED", "evidence_id": "EV-UNIT-FIXTURE",
            "coverage": "BOUNDED", "seed_coverage": {"not_requested_seed_count": 0},
        }
        executor.results.append({**bounded, "tool": "zap-passive"})
        self.assertFalse(executor.has_complete_recorded_coverage("RUN-UNIT"))

        for change in ({"run_id": "RUN-OTHER"}, {"evidence_id": None},
                       {"seed_coverage": {}}, {"coverage": "PARTIAL"}):
            with self.subTest(change=change):
                executor.results[1:] = [{**bounded, "tool": "nuclei", **change}]
                self.assertFalse(executor.has_complete_recorded_coverage("RUN-UNIT"))
        executor.results[1:] = [{**bounded, "tool": "nuclei", "evidence_id": "EV-UNIT-SECOND"}]
        self.assertTrue(executor.has_complete_recorded_coverage("RUN-UNIT"))


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
        for value in ("", "2", "3"):
            self.assertIn("http://lab-ecommerce/products?category=" + value + "&q=", relay.urls())
        self.assertEqual(relay.seed_coverage()["requested_seed_count"], 0)
        response = SimpleNamespace(status_code=200, durable_confirmed=True, truncated=False, body="fixture", headers={})
        with patch.object(self.gate, "dispatch", return_value=response) as dispatch:
            self.assertEqual(relay.dispatch({"url": seed, "method": "GET"})["status"], 200)
        self.assertEqual(dispatch.call_args.args[0].url, self.gate.base_origin + "/products?category=3&q=")
        self.assertEqual(relay.seed_coverage()["requested_seed_count"], 1)
        self.assertEqual(relay.seed_coverage()["successful_seed_count"], 1)
        self.assertEqual(relay.seed_coverage()["not_requested_seed_count"], len(relay.seed_urls) - 1)

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
        self.assertTrue(fields[0]["options_truncated"])
        for field in fields[1:4]:
            self.assertNotIn("options", field)
        self.assertEqual(fields[4]["options"], [])
        self.assertNotIn("options", parser.forms[1].inputs[0])

    def test_seed_cap_is_reported_as_unrequested_coverage(self):
        self.relay.seed_urls = {"http://lab-ecommerce/products?q=" + str(i) for i in range(105)}
        self.assertEqual(len(self.relay.urls()), 100)
        self.relay.executed_urls.update(self.relay.urls())
        self.assertEqual(self.relay.seed_coverage()["not_requested_seed_count"], 5)
        self.assertEqual(self.relay.seed_coverage()["successful_seed_count"], 0)

    def test_seed_coverage_matches_reordered_distinct_keys_only(self):
        base = "http://lab-ecommerce/products?"
        self.relay.seed_urls = {
            base + "q=&category=2", base + "category=2&q=",
            base + "q=red&%71=blue&category=2", base + "q=changed&category=2",
        }
        self.relay.executed_urls = {
            base + "category=2&q=", base + "%71=blue&category=2&q=red",
            base + "category=2&q=other",
            "http://lab-ecommerce:8080/products?q=changed&category=2",
        }
        self.relay.successful_urls = self.relay.executed_urls.copy()
        self.assertEqual(self.relay.seed_coverage(), {
            "observed_seed_count": 3, "selected_seed_count": 3,
            "requested_seed_count": 1, "successful_seed_count": 1,
            "not_requested_seed_count": 2, "options_truncated": False,
        })

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

    def test_refusals_record_only_fixed_diagnostics_and_keep_limit(self):
        requests = [("http://outside.invalid/products", "AUTHORITY"),
                    ("http://lab-ecommerce/unobserved", "UNOBSERVED_PATH"),
                    ("http://lab-ecommerce/products?unknown=private-value", "UNOBSERVED_QUERY_KEY")]
        with patch.object(self.gate, "dispatch") as dispatch:
            for url, expected in requests:
                self.assertEqual(self.relay.dispatch({"url": url, "method": "GET"})["status"], 403)
            self.relay.refusals = 31
            with self.assertRaisesRegex(RuntimeError, "SCANNER_REFUSAL_LIMIT"):
                self.relay.dispatch({"url": requests[-1][0], "method": "GET"})
            dispatch.assert_not_called()
        artifacts = [json.loads(f.read_text()) for f in (self.root / "evidence").glob("scanner_refusal-*.json")]
        self.assertEqual({d["scope_violation"] for d in artifacts}, {expected for _, expected in requests})
        self.assertTrue(all(len(d["request_sha256"]) == 64 for d in artifacts))
        self.assertNotIn("private-value", json.dumps(artifacts))

    def test_zap_worker_uses_query_insertion_points_and_observed_query_seeds_only(self):
        worker = runpy.run_path(str(Path(__file__).resolve().parents[2] / "tools/scanners/zap_worker.py"))
        urls = ["http://lab-ecommerce/products", "http://lab-ecommerce/products?q="]
        calls = []
        def respond(url, **kwargs):
            path = urllib.parse.urlsplit(url).path
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query, keep_blank_values=True)
            calls.append((path, params))
            data = ({"version": "fixture"} if path.endswith("/version/") else
                    {"urls": urls} if path.endswith("/urls/") else
                    {"scan": "1"} if path.endswith("/scan/") else
                    {"status": "100"} if path.endswith("/status/") else
                    {"recordsToScan": "0"} if path.endswith("/recordsToScan/") else {})
            return io.StringIO(json.dumps(data))
        opener = Mock()
        opener.open.side_effect = respond
        with patch("urllib.request.build_opener", return_value=opener), \
             patch("subprocess.Popen") as launch, \
             patch("sys.stdin", io.StringIO(json.dumps({"active": True, "urls": urls}))), \
             patch("sys.stdout", io.StringIO()):
            launch.return_value.poll.return_value = None
            worker["main"]()
        self.assertIn(("/JSON/ascan/action/setOptionTargetParamsInjectable/", {"Integer": ["1"]}), calls)
        self.assertIn(("/JSON/ascan/action/setOptionTargetParamsEnabledRPC/", {"Integer": ["0"]}), calls)
        scans = [params for path, params in calls if path == "/JSON/ascan/action/scan/"]
        self.assertEqual([params["url"] for params in scans], [[urls[1]]])
        self.assertTrue(all(params["method"] == ["GET"] and params["recurse"] == ["false"] for params in scans))
        self.assertEqual(len([p for p, _ in calls if p.endswith("/accessUrl/")]), len(urls))

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

    def test_zap_local_failure_does_not_skip_selected_nuclei_or_repeat_batch(self):
        for reason in ("SCANNER_REFUSAL_LIMIT", "SCANNER_TIMEOUT", "SCANNER_PROCESS_FAILED"):
            executor = ExternalScannerExecutor(["zap-active", "nuclei"])
            def scan(tool, *args):
                if tool == "zap-active":
                    raise RuntimeError(reason)
                self.gate.network_dispatch_count += 1
                return b""
            with self.subTest(reason=reason), \
                 patch("runtime.lab.external_scanners.preflight", return_value={}), \
                 patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan) as invoke:
                result = self.execute(executor)
            self.assertEqual([c.args[0] for c in invoke.call_args_list], ["zap-active", "nuclei"])
            self.assertEqual([r["status"] for r in executor.results], ["ERROR", "COMPLETED"])
            self.assertEqual(result.outcome, "FAILURE")
            self.assertEqual(result.classification, "INCONCLUSIVE")
            fact_subjects = {f["subject"] for f in result.new_facts}
            self.assertTrue({"ACTION-SCAN-002:zap-active", "ACTION-SCAN-002:nuclei"} <= fact_subjects)
            coverage = {f["subject"]: f["value"] for f in result.new_facts
                        if f["subject"].endswith(":coverage")}
            self.assertEqual(coverage.get("ACTION-SCAN-002:zap-active:coverage"), "INCOMPLETE")
            with self.assertRaisesRegex(ValueError, "SCANNER_BATCH_ALREADY_EXECUTED"):
                self.execute(executor)

    def test_global_failure_and_evidence_failure_do_not_continue_batch(self):
        for reason in ("SCANNER_CANCELLED", "SCANNER_BUDGET_EXHAUSTED", "SCANNER_TARGET_REVOKED",
                       "SCANNER_ACTION_REVOKED", "SCANNER_APPROVAL_INVALID", "SCANNER_CLEANUP_FAILED:fixture"):
            with self.subTest(reason=reason), \
                 patch("runtime.lab.external_scanners.preflight", return_value={}), \
                 patch("runtime.lab.external_scanners.isolated_scan", side_effect=RuntimeError(reason)) as invoke:
                executor = ExternalScannerExecutor(["zap-active", "nuclei"])
                self.assertEqual(self.execute(executor).outcome, "FAILURE")
                self.assertEqual(invoke.call_count, 1)
                self.assertEqual(len(executor.results), 1)
        with patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=EvidenceFailure("fixture")) as invoke:
            with self.assertRaises(EvidenceFailure):
                self.execute(ExternalScannerExecutor(["zap-active", "nuclei"]))
            self.assertEqual(invoke.call_count, 1)

    def test_next_scanner_rechecks_approval_after_local_failure(self):
        def scan(*args):
            self.approval.revoke()
            raise RuntimeError("SCANNER_REFUSAL_LIMIT")
        with patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan) as invoke:
            executor = ExternalScannerExecutor(["zap-active", "nuclei"])
            self.assertEqual(self.execute(executor).outcome, "FAILURE")
        self.assertEqual(invoke.call_count, 1)
        self.assertEqual(executor.results[-1]["reason"], "SCANNER_APPROVAL_INVALID")

    def test_cleanup_failure_is_terminal_even_after_local_scanner_error(self):
        for error in (RuntimeError("SCANNER_REFUSAL_LIMIT"), EvidenceFailure("fixture")):
            with self.subTest(error=type(error).__name__), \
                 patch.object(self.relay, "check", side_effect=error), \
                 patch("runtime.lab.external_scanners.subprocess.run",
                       return_value=SimpleNamespace(returncode=1, stderr=b"cleanup failed")):
                expected = EvidenceFailure if isinstance(error, EvidenceFailure) else RuntimeError
                message = "fixture" if isinstance(error, EvidenceFailure) else "SCANNER_CLEANUP_FAILED"
                with self.assertRaisesRegex(expected, message):
                    isolated_scan("zap-active", self.relay,
                                  {"bridge_image": {"id": "fixture"}, "zap_image": {"id": "fixture"}},
                                  {"timeout_seconds": 1})

    def test_report_provenance_and_candidates_not_confirmed(self):
        raw = json.dumps({"template-id": "lab-sql-error", "type": "http", "matcher-status": True,
            "host": "http://lab-ecommerce", "matched-at": "http://lab-ecommerce/products?q=x",
            "info": {"severity": "info", "tags": ["sqli"], "description": "PRIVATE_REPORT_TEXT"}}).encode()
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
        directory = self.root / "evidence"
        payload_path, = directory.glob("nuclei_review-*.json")
        payload = json.loads(payload_path.read_text("utf-8"))
        self.assertEqual(payload["report_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(payload["alerts"], [{"alert_index": 0, "rule_id": "lab-sql-error",
                                             "severity": "informational", "instances": 1}])
        self.assertNotIn("PRIVATE_REPORT_TEXT", payload_path.read_text("utf-8"))
        self.assertNotIn("matched-at", payload_path.read_text("utf-8"))
        review_record, = (json.loads(p.read_text()) for p in directory.glob("record-nuclei_review-*.json"))
        result_record, = (json.loads(p.read_text()) for p in directory.glob("record-scanner_result-*.json"))
        self.assertEqual(result_record["derived_from"], [review_record["evidence_id"]])
        with self.assertRaises(ValueError):
            self.execute(executor)

    def test_zap_review_evidence_retains_dispatched_order_without_raw_data(self):
        base = "http://lab-ecommerce/products"
        self.inventory.items["/products"].forms[0]["inputs"].append({"name": "page"})
        dispatched = base + "?q=PRIVATE_NEEDLE&page=2&q=second"
        reordered = base + "?page=2&q=PRIVATE_NEEDLE&q=second"
        reversed_repeat = base + "?q=second&page=2&q=PRIVATE_NEEDLE"
        report = {"site": [{"host": "lab-ecommerce", "alerts": [
            {"alert": "SQL Injection", "confidence": "2", "pluginid": "40018",
             "alertRef": "40018-2", "riskcode": "3", "instances": [
                {"uri": reordered, "evidence": "PRIVATE_REPORT_TEXT"},
                {"uri": reversed_repeat}, {"uri": reordered.replace("page=2", "page=3")},
            ]},
            {"alert": "PRIVATE_UNRECOGNIZED_ALERT", "uri": reordered, "pluginid": "10021",
             "alertRef": "PRIVATE_REF", "riskcode": 1, "riskdesc": "PRIVATE_RISK_DESC"},
        ]}]}
        raw = json.dumps({"version": "2.16.1", "report": report}).encode()

        def scan(tool, relay, *_):
            for method in ("GET", "HEAD"):
                self.assertEqual(relay.dispatch({"url": dispatched, "method": method})["status"], 200)
            self.assertEqual(relay.dispatch({"url": base + "/blocked", "method": "GET"})["status"], 403)
            return raw

        with patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan), \
             patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.getheaders.return_value = []
            response.read.return_value = b"fixture"
            result = self.execute(ExternalScannerExecutor(["zap-active"]))
        self.assertEqual(result.findings, [])
        self.assertEqual(connection.call_count, 2)
        self.assertEqual(connection.return_value.request.call_args.args[1], urllib.parse.urlsplit(dispatched).path
                         + "?" + urllib.parse.urlsplit(dispatched).query)

        evidence_dir = self.root / "evidence"
        payload_path, = evidence_dir.glob("zap_review-*.json")
        saved = payload_path.read_text("utf-8")
        payload = json.loads(saved)
        self.assertEqual(payload["report_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(payload["format_version"], 2)
        self.assertEqual(payload["dispatch_count"], 2)
        self.assertEqual([row["method"] for row in payload["requests"]], ["GET", "HEAD"])
        self.assertEqual(len(payload["alerts"]), 2)
        self.assertIsNone(payload["alerts"][1]["finding_type"])
        self.assertEqual([(row["rule_id"], row["severity"]) for row in payload["alerts"]],
                         [("40018-2", "high"), ("10021", "low")])
        expected = [
            {"alert_index": 0, "finding_type": "sqli", "exact": 0, "query_order_only": 1, "unmatched": 2},
        ]
        self.assertEqual(zap_parser.reconcile_zap_evidence(payload), expected)
        legacy = {**payload, "format_version": 1, "alerts": [
            {k: v for k, v in row.items() if k not in ("rule_id", "severity")} for row in payload["alerts"]
        ]}
        self.assertEqual(zap_parser.reconcile_zap_evidence(legacy), expected)
        tampered = {**payload, "alerts": [{**payload["alerts"][0], "severity": "PRIVATE_RISK_DESC"}]}
        with self.assertRaisesRegex(ValueError, "alert metadata"):
            zap_parser.reconcile_zap_evidence(tampered)
        with self.assertRaisesRegex(ValueError, "dispatch count"):
            zap_parser.reconcile_zap_evidence({**payload, "requests": payload["requests"][:1]})
        for text in ("/products", "PRIVATE_NEEDLE", "PRIVATE_REPORT_TEXT", "PRIVATE_UNRECOGNIZED_ALERT",
                     "PRIVATE_REF", "PRIVATE_RISK_DESC", "page="):
            self.assertNotIn(text, saved)
        review_record, = (json.loads(p.read_text()) for p in evidence_dir.glob("record-zap_review-*.json"))
        intent_record, = (json.loads(p.read_text()) for p in evidence_dir.glob("record-scanner_intent-*.json"))
        result_record, = (json.loads(p.read_text()) for p in evidence_dir.glob("record-scanner_result-*.json"))
        self.assertTrue(review_record["redacted"])
        self.assertEqual(review_record["sha256"], hashlib.sha256(payload_path.read_bytes()).hexdigest())
        self.assertEqual(review_record["derived_from"], [intent_record["evidence_id"]])
        self.assertEqual(result_record["derived_from"], [review_record["evidence_id"]])

    def test_zap_review_partial_or_missing_input_cannot_report_full_comparison(self):
        with patch.object(zap_parser, "_MAX_REVIEW_FIELDS", 1):
            capture = zap_parser.ZapReviewCapture("lab-ecommerce")
            uri = "http://lab-ecommerce/products?q=one&page=2"
            capture.record_dispatch(uri, "GET", 200)
            partial = capture.finish({"site": [{"host": "lab-ecommerce", "alerts": [
                {"alert": "SQL Injection", "confidence": 2, "uri": uri},
            ]}]}, report_received=True, dispatch_count=1)
        self.assertEqual((partial["requests_omitted"], partial["alert_urls_omitted"]), (1, 1))
        for value in (partial, capture.finish(None, report_received=False, dispatch_count=1),
                      capture.finish(None, report_received=True, dispatch_count=1)):
            with self.subTest(report_state=value["report_state"]), self.assertRaises(ValueError):
                zap_parser.reconcile_zap_evidence(value)

    def test_zap_review_write_failure_stops_before_next_scanner(self):
        persist = self.recorder.persist_phase_artifact

        def fail_review(phase, *args, **kwargs):
            if phase == "zap_review":
                raise EvidenceFailure("review storage unavailable")
            return persist(phase, *args, **kwargs)

        with patch.object(self.recorder, "persist_phase_artifact", side_effect=fail_review), \
             patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=RuntimeError("SCANNER_TIMEOUT")) as scan:
            with self.assertRaisesRegex(EvidenceFailure, "review storage unavailable"):
                self.execute(ExternalScannerExecutor(["zap-active", "nuclei"]))
        self.assertEqual(scan.call_count, 1)
        self.assertEqual(list((self.root / "evidence").glob("scanner_result-*.json")), [])

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

    def test_gate_origin_must_match_registered_private_lab_gateway(self):
        for origin in ("http://127.0.0.1:9999", "http://lab-ecommerce:18088",
                       "http://127.0.0.1:18088/path", "http://8.8.8.8:18088"):
            with self.subTest(origin=origin), patch.object(self.gate, "base_origin", origin):
                with self.assertRaisesRegex(RuntimeError, "SCANNER_GATE_ORIGIN_MISMATCH"):
                    self.relay.check()

        request = StartRunRequest(target="lab-ecommerce", target_origin="http://10.0.0.2:8080",
                                  approve_active_verification=True, external_scanners=["nuclei"])
        gate = _run_gate(request, self.recorder)
        inventory = SimpleNamespace(items={"/products": SimpleNamespace(
            canonical_url=gate.base_origin + "/products", refusal_reason=None, forms=[])})
        relay = ScannerRelay(gate, self.recorder, "RUN-SCANNER-TEST", "lab-ecommerce",
                             inventory, self.approval, "ACTION-SCAN-002", lambda: False)
        relay.check()

    def test_zap_active_scan_deduplicates_equivalent_query_shapes(self):
        from tools.scanners.zap_worker import active_scan_urls

        urls = [
            "http://lab-ecommerce/products?q=&category=2",
            "http://lab-ecommerce/products?category=3&q=phone",
            "http://lab-ecommerce/products?q=phone",
            "http://lab-ecommerce/products",
            "http://lab-ecommerce/search?q=phone",
        ]
        self.assertEqual(active_scan_urls(urls), [urls[0], urls[2], urls[4]])

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

    def test_external_scanners_do_not_increment_internal_verification_count(self):
        def scan(tool, relay, *args):
            self.gate.network_dispatch_count += 1
            seed = relay.urls()[0]
            relay.executed_urls.add(seed)
            relay.successful_urls.add(seed)
            return b"" if tool == "nuclei" else json.dumps({"version": "fixture", "report": {"site": []}}).encode()

        for selected in (("zap-passive",), ("zap-active",), ("nuclei",), ("zap-active", "nuclei")):
            with self.subTest(scanners=selected):
                runner = AutonomousRunner("lab-ecommerce", self.gate, self.recorder, self.approval,
                                          max_decisions=1, external_scanners=selected)
                runner.inventory = self.inventory
                proposal = {"action_id": "ACTION-SCAN-002", "target_id": "lab-ecommerce"}
                plan = SimpleNamespace(proposal=proposal, mode_provenance={"actual_mode": "RULE"})
                with patch.object(runner.planner, "propose", return_value=plan), \
                     patch("runtime.lab.external_scanners.preflight", return_value={}), \
                     patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan):
                    report = runner.run()
                self.assertEqual(report.decisions_count, 1)
                self.assertEqual(report.active_verifications_count, 0)
                self.assertEqual([item["tool"] for item in runner.scanner_executor.results], list(selected))
                self.assertTrue(all(item["status"] == "COMPLETED" for item in runner.scanner_executor.results))

    def test_internal_executors_still_increment_and_failures_do_not(self):
        runner = AutonomousRunner("lab-ecommerce", self.gate, self.recorder, self.approval,
                                  external_scanners=("zap-passive",))
        executor = Mock()
        executor.execute.side_effect = lambda proposal, **kwargs: CapabilityExecutionResult(
            action_id=proposal["action_id"], target_id="lab-ecommerce",
            outcome="SUCCESS", classification="INCONCLUSIVE")
        cases = (("ACTION-SCAN-002", 0), ("ACTION-WEB-001", 1), ("ACTION-SCAN-002", 1),
                 ("ACTION-WEB-002", 2), ("ACTION-WEB-003", 3), ("ACTION-LOGIC-001", 4))
        with patch.object(runner.capability_registry, "get_executor", return_value=executor):
            for index, (action, expected) in enumerate(cases, 1):
                with self.subTest(action=action, expected=expected):
                    runner._execute_approved_action({"action_id": action, "target_id": "lab-ecommerce"},
                                                    {"actual_mode": "RULE"}, index, "fixture")
                    self.assertEqual(runner.active_verifications_count, expected)
            executor.execute.side_effect = EvidenceFailure("fixture")
            with self.assertRaises(EvidenceFailure):
                runner._execute_approved_action({"action_id": "ACTION-WEB-001", "target_id": "lab-ecommerce"},
                                                {"actual_mode": "RULE"}, 7, "fixture")
            self.assertEqual(runner.active_verifications_count, 4)

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
            self.gate.budget_tracker.max_requests = 300
            self.inventory.items["/products"].canonical_url = origin + "/products"
            parser = HTMLMetadataParser(origin + "/products")
            parser.feed('<form action="/products"><input name="q" type="search">'
                        '<select name="category"><option value="2">Two</option>'
                        '<option value="3">Three</option></select></form>')
            self.inventory.items["/products"].forms = [asdict(form) for form in parser.forms]
            tool = os.environ.get("SCANNER_TEST_TOOL", "nuclei")
            selected = ["zap-active", "nuclei"] if tool == "batch" else [tool]
            result = self.execute(ExternalScannerExecutor(selected))
            self.assertEqual(result.outcome, "SUCCESS", result.details)
            self.assertEqual([r["tool"] for r in result.details["scanners"]], selected)
            self.assertGreater(result.network_dispatch_count, 0)
            self.assertTrue(any(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query,
                                keep_blank_values=True) == {"category": ["2"], "q": [""]} for url in received))
            self.assertTrue(any(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query,
                                keep_blank_values=True) == {"category": ["3"], "q": [""]} for url in received))
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
