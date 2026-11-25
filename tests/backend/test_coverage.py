"""Coverage is a projection of verified run evidence, not inferred success."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from fastapi.testclient import TestClient

from dashboards.app.backend.coverage import build_coverage
from dashboards.app.backend.event_sink import EventSink
from dashboards.app.backend.models import AgentState, StartRunRequest
from dashboards.app.backend.run_manager import RunManager, _run_gate, _scan_redaction_ready
from dashboards.app.backend.run_history import RunIndex
from dashboards.app.backend.scanner_analysis import analyze_alert, record_post_scan_analysis
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.lab.authenticated_workflow import WORKFLOW_CHECK_CONTEXT
from runtime.lab.capability_registry import CapabilityExecutionResult
from runtime.orchestration.autonomous_runner import AutonomousRunReport, AutonomousRunner
from runtime.safety.discovery_gate import ApprovalToken, CentralizedSafetyGate, DiscoveryRequest


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "RUN-COVERAGE-001"
        self.recorder = DurableEvidenceRecorder(self.run.name, self.run / "assessment",
                                                approved_root=self.root, source="UNIT_TEST")

    def record(self, kind, **payload):
        return self.recorder.persist_phase_artifact(kind, {"run_id": self.run.name, **payload})

    def test_verified_partial_coverage_separates_legacy_and_new_checks(self):
        self.record("dashboard_run_scope", execution_scope="combined", authenticated_workflow_approved=True,
                    active_verification_approved=True, external_scanners=["nuclei"])
        self.record("scanner_result", tool="nuclei", status="COMPLETED", coverage="PARTIAL",
                    refused_requests=0, candidate_count=0, seed_coverage={"observed_seed_count": 3,
                    "requested_seed_count": 2, "successful_seed_count": 2, "not_requested_seed_count": 1})
        self.record("workflow_check", check="login_a", status="PASS")
        route, method, role, auth_state, case, negative, expected = WORKFLOW_CHECK_CONTEXT["peer_cannot_read_order"]
        self.record("workflow_check", check="peer_cannot_read_order", status="PASS", route=route,
                    method=method, role=role, auth_state=auth_state, case=case, negative=negative,
                    expected=expected, http_status=404)
        for classification in ("INCONCLUSIVE", "NEGATIVE"):
            self.record("action_web_001_verification", action_id="ACTION-WEB-001", resource="/products",
                        parameter="q", classification=classification, reason="Fixture result")
        coverage = build_coverage(self.run, self.run.name)
        self.assertEqual(coverage["integrity"], "VERIFIED")
        self.assertEqual(coverage["workflow"]["recorded_checks"], 2)
        rows = {row["check"]: row for row in coverage["matrix"]}
        self.assertEqual(rows["login_a"]["status"], "UNKNOWN")
        self.assertEqual(rows["peer_cannot_read_order"]["status"], "PASS")
        self.assertEqual(rows["peer_cannot_read_order"]["http_status"], 404)
        self.assertEqual(rows["guest_admin_denied"]["status"], "NOT_RECORDED")
        self.assertEqual(len(coverage["legacy_workflow_checks"]), 1)
        scanners = {item["tool"]: item for item in coverage["scanners"]}
        self.assertEqual(scanners["zap-active"]["reason"], "NOT_SELECTED")
        self.assertEqual(scanners["nuclei"]["seed_coverage"]["not_requested_seed_count"], 1)
        self.assertEqual(coverage["verifications"][0]["attempts"], 2)
        self.assertEqual(coverage["verifications"][0]["classification"], "NEGATIVE")

    def test_skipped_scanner_uses_only_a_matching_verified_batch(self):
        selected = ["zap-active", "nuclei"]
        self.record("dashboard_run_scope", external_scanners=selected)
        error = dict(run_id=self.run.name, tool="zap-active", status="ERROR",
                     reason="SCANNER_BUDGET_EXHAUSTED", coverage="INCOMPLETE")
        ref = self.record("scanner_result", **error)["evidence_id"]
        batch = dict(run_id=self.run.name, results=[{**error, "evidence_id": ref}], result_evidence_refs=[ref])
        self.recorder.persist_phase_artifact("scanner_batch", batch, derived_from=[ref])
        self.record("scanner_result", tool="nuclei", status="NOT_RUN", coverage="NOT_TESTED",
                    reason="provider_unavailable_halt")
        def skipped_reason():
            coverage = build_coverage(self.run, self.run.name)
            return next(row["reason"] for row in coverage["scanners"] if row["tool"] == "nuclei")
        self.assertEqual(skipped_reason(), "SCANNER_BUDGET_EXHAUSTED")
        # A second batch makes attribution ambiguous.
        self.recorder.persist_phase_artifact("scanner_batch", batch, derived_from=[ref])
        self.assertEqual(skipped_reason(), "provider_unavailable_halt")

    def test_no_scope_or_records_does_not_invent_skipped_reasons(self):
        empty = build_coverage(self.run, self.run.name)
        self.assertEqual(empty["integrity"], "NOT_VERIFIED")
        self.assertEqual(empty["matrix"], [])
        self.record("workflow_check", check="login_a", status="PASS")
        coverage = build_coverage(self.run, self.run.name)
        self.assertIsNone(coverage["scope"])
        self.assertEqual(coverage["scanners"][0]["status"], "UNKNOWN")
        self.assertEqual(coverage["matrix"][0]["status"], "UNKNOWN")

    def test_passive_zap_alerts_are_projected_separately_from_candidates(self):
        digest = "a" * 64
        alerts = [
            {"alert_index": index, "rule_id": rule, "severity": severity,
             "urls": [[1, [[2, 3]]], [1, [[4, 5]]]], "otherinfo": "PRIVATE_SENTINEL"}
            for index, (rule, severity) in enumerate(
                (("10038-1", "medium"), ("10020-1", "medium"), ("10021", "low")))
        ]
        review = self.recorder.persist_phase_artifact("zap_review", {
            "run_id": self.run.name, "tool": "zap-passive", "format_version": 2,
            "report_state": "AVAILABLE", "report_sha256": digest, "alerts": alerts,
        }, source="TOOL_ADAPTER", observed_state="AVAILABLE")
        result = {"run_id": self.run.name, "tool": "zap-passive", "status": "COMPLETED",
                  "report_sha256": digest, "candidate_count": 0}
        self.recorder.persist_phase_artifact("scanner_result", result, derived_from=[review["evidence_id"]])
        coverage = build_coverage(self.run, self.run.name)
        self.assertEqual(coverage["scanners"][0]["candidate_count"], 0)
        self.assertEqual(coverage["scanner_reviews"], [{
            "tool": "zap-passive", "status": "AVAILABLE",
            "source": {"artifact": "zap_review", "evidence_id": review["evidence_id"]},
            "alerts": [{"alert_index": row["alert_index"], "rule_id": row["rule_id"],
                        "severity": row["severity"], "instances": 2} for row in alerts],
        }])

        # A review for a different report cannot provide this scanner's alert metadata.
        self.recorder.persist_phase_artifact("scanner_result", {**result, "report_sha256": "b" * 64},
                                             derived_from=[review["evidence_id"]])
        self.assertEqual(build_coverage(self.run, self.run.name)["scanner_reviews"][0]["status"], "UNAVAILABLE")

    def test_active_zap_and_nuclei_share_the_review_shape_and_keep_missing_distinct(self):
        digest = "b" * 64
        self.record("scanner_result", tool="nuclei", status="COMPLETED", candidate_count=0)
        self.assertEqual(build_coverage(self.run, self.run.name)["scanner_reviews"], [
            {"tool": "nuclei", "status": "NOT_RECORDED", "alerts": [], "source": None},
        ])
        for tool, artifact, row in (
            ("zap-active", "zap_review", {"urls": [[1, []]], "rule_id": "10021", "severity": "low"}),
            ("nuclei", "nuclei_review", {"instances": 2, "rule_id": "lab-xss-reflection", "severity": "informational"}),
        ):
            review = self.recorder.persist_phase_artifact(artifact, {
                "run_id": self.run.name, "tool": tool, "format_version": 2 if tool == "zap-active" else 1,
                "report_state": "AVAILABLE", "report_sha256": digest,
                "alerts": [{"alert_index": 0, **row}],
            }, source="TOOL_ADAPTER", observed_state="AVAILABLE")
            self.recorder.persist_phase_artifact("scanner_result", {
                "run_id": self.run.name, "tool": tool, "status": "COMPLETED", "report_sha256": digest,
            }, derived_from=[review["evidence_id"]])
        zap, nuclei = build_coverage(self.run, self.run.name)["scanner_reviews"]
        self.assertEqual((zap["tool"], zap["status"], zap["source"]["artifact"]),
                         ("zap-active", "AVAILABLE", "zap_review"))
        self.assertEqual((nuclei["tool"], nuclei["status"], nuclei["source"]["artifact"]),
                         ("nuclei", "AVAILABLE", "nuclei_review"))
        self.assertEqual(zap["alerts"], [{"alert_index": 0, "rule_id": "10021", "severity": "low", "instances": 1}])
        self.assertEqual(nuclei["alerts"], [{"alert_index": 0, "rule_id": "lab-xss-reflection",
                                            "severity": "informational", "instances": 2}])

    def test_ai_review_of_verified_alerts_preserves_source_and_observations(self):
        from dashboards.app.backend.control_api import app
        from runtime.lab.control_support import verify

        reply = {"interpretation": "Fixture meaning", "uncertainty": "Headers unavailable",
                 "evidence_check": "Inspect the saved response headers"}
        for tool, rule in (("zap-passive", "10021"), ("zap-active", "12345"), ("nuclei", "fixture-rule")):
            zap = tool.startswith("zap")
            row = {"urls": [[1, []]]} if zap else {"instances": 1}
            ref = self.recorder.persist_phase_artifact("zap_review" if zap else "nuclei_review", {
                "run_id": self.run.name, "tool": tool, "format_version": 2 if zap else 1,
                "report_state": "AVAILABLE", "report_sha256": "a" * 64, "raw": "PRIVATE_FIXTURE",
                "alerts": [{"alert_index": 0, "rule_id": rule, "severity": "low", **row}],
            }, source="TOOL_ADAPTER", observed_state="AVAILABLE")["evidence_id"]
            self.recorder.persist_phase_artifact("scanner_result", {"run_id": self.run.name, "tool": tool,
                "status": "COMPLETED", "report_sha256": "a" * 64, "candidate_count": 0}, derived_from=[ref])
        before = build_coverage(self.run, self.run.name)
        with patch("dashboards.app.backend.scanner_analysis._call_real_provider",
                   return_value=(json.dumps(reply), None, {"model_returned": "fixture-model"})) as provider:
            client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 51000))
            url = f"/api/runs/{self.run.name}/coverage/analysis/nuclei/{ref}/0"
            origin = {"origin": "http://127.0.0.1:5173"}
            with patch("dashboards.app.backend.control_api.run_index", RunIndex(run_roots=[self.root])):
                self.assertEqual(client.post(url).status_code, 403)
                self.assertEqual(client.post(url.replace("nuclei/", "zap-passive/"), headers=origin).status_code, 404)
                self.assertEqual(client.post(url, headers=origin).json()["evidence_check"], reply["evidence_check"])
                cached = client.get(f"/api/runs/{self.run.name}/coverage").json()
                self.assertEqual(cached["scanner_reviews"][-1]["alerts"][0]["analysis"]["model"], "fixture-model")
                self.assertEqual(client.post(url, headers=origin).json()["interpretation"], reply["interpretation"])
            self.assertEqual(before, build_coverage(self.run, self.run.name))
            record_post_scan_analysis(self.run, self.recorder, None, lambda: False)
            self.assertEqual(provider.call_count, 4)
            for call in provider.call_args_list:
                inputs = json.loads(call.args[1])
                self.assertFalse(set(inputs) - {"tool", "rule_id", "severity", "instances", "report_status", "rule_definition"})
                self.assertNotIn("PRIVATE_FIXTURE", call.args[1])
        after = build_coverage(self.run, self.run.name)
        self.assertEqual(after["integrity"], "VERIFIED")
        self.assertTrue(verify(self.recorder)["passed"])
        self.assertEqual(before["scanners"], after["scanners"])
        for review in after["scanner_reviews"]:
            advice = review["alerts"][0]["analysis"]
            self.assertEqual(advice["model"], "fixture-model")
            self.assertTrue(advice["analysis_evidence_id"].startswith("EV-SCANNER_ANALYSIS-"))

    def test_ai_review_handles_missing_rule_provider_and_malformed_answers(self):
        review = {"tool": "zap-active", "status": "PARTIAL"}
        alert = {"rule_id": "10021", "instances": 1, "severity": None}
        with patch("dashboards.app.backend.scanner_analysis._call_real_provider") as provider:
            self.assertEqual(analyze_alert(review, {**alert, "rule_id": None}, None)["status"], "MISSING_RULE")
            provider.assert_not_called()
            provider.return_value = (None, "MISSING_API_KEY", {})
            self.assertEqual(analyze_alert(review, alert, None)["status"], "PROVIDER_UNAVAILABLE")
            provider.return_value = ('{"action":"run"}', None, {})
            self.assertEqual(analyze_alert(review, alert, None)["status"], "INVALID_RESPONSE")

    def test_legacy_path_result_requires_path_like_input(self):
        self.record("action_web_003_verification", action_id="ACTION-WEB-003", resource="/products",
                    parameter="q", classification="VERIFIED_IN_LAB", reason="Legacy result")
        result = build_coverage(self.run, self.run.name)
        self.assertEqual(result["verifications"][0]["classification"], "INCONCLUSIVE")
        self.assertEqual(result["verifications"][0]["reason"], "PATH_INPUT_NOT_OBSERVED")

    def test_tamper_or_conflicting_scope_fails_closed_without_repair(self):
        artifact = self.record("dashboard_run_scope", authenticated_workflow_approved=False,
                               external_scanners=[])
        self.record("dashboard_run_scope", authenticated_workflow_approved=True,
                    external_scanners=[])
        self.assertEqual(build_coverage(self.run, self.run.name)["integrity"], "FAILED")
        payload = Path(artifact["payload_path"])
        payload.write_text('{"changed":true}', encoding="utf-8")
        before = payload.read_bytes()
        result = build_coverage(self.run, self.run.name)
        self.assertEqual(result["integrity"], "FAILED")
        self.assertEqual(result["matrix"], [])
        self.assertEqual(payload.read_bytes(), before)

    def test_coverage_endpoint_uses_scoped_run_index(self):
        from dashboards.app.backend.control_api import app
        self.record("dashboard_run_scope", authenticated_workflow_approved=False, external_scanners=[])
        with patch("dashboards.app.backend.control_api.run_index", RunIndex(run_roots=[self.root])):
            client = TestClient(app)
            response = client.get(f"/api/runs/{self.run.name}/coverage")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["integrity"], "VERIFIED")
            self.assertEqual(response.json()["workflow"]["status"], "NOT_SELECTED")
            self.assertEqual(client.get("/api/runs/RUN-MISSING/coverage").status_code, 404)
            self.assertEqual(client.get("/api/runs/invalid!id/coverage").status_code, 400)


class SeparateExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_id = "RUN-COVERAGE-WORKFLOW"
        self.run = self.root / self.run_id
        self.run.mkdir()
        self.manager = RunManager(output_root=self.root)
        self.manager._active_dir = self.run
        self.manager._active_run_id = self.run_id
        self.sink = EventSink()

    def request(self, **overrides):
        fields = dict(mode="autonomous", planner="rule", target="lab-ecommerce",
                      target_origin="http://127.0.0.1:18088", max_requests=200,
                      execution_scope="workflow", approve_read_only=False,
                      approve_authenticated_workflow=True)
        fields.update(overrides)
        return StartRunRequest(**fields)

    def _run_scanner_report_fixture(self, include_web, interrupted=False, planner="rule"):
        run_id = self.run_id
        recorder = DurableEvidenceRecorder(run_id, self.run / "assessment", approved_root=self.root)
        actions = ["ACTION-SCAN-002"] + (["ACTION-WEB-001"] if include_web else [])

        class FakeLab:
            def __init__(self, _run_id, rec, **kwargs):
                self.recorder = rec
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.recorder.persist_phase_artifact("workflow_restored", {"run_id": run_id})

        class FakeWebExecutor:
            def execute(self, proposal, recorder, **kwargs):
                artifact = recorder.persist_phase_artifact("action_web_001_verification", {
                    "run_id": run_id, "action_id": "ACTION-WEB-001", "resource": "/products",
                    "parameter": "q", "classification": "NEGATIVE", "reason": "Fixture result"})
                return CapabilityExecutionResult(action_id="ACTION-WEB-001", target_id="lab-ecommerce",
                    outcome="SUCCESS", classification="NEGATIVE", result_evidence_id=artifact["evidence_id"])

        def create_runner(**kwargs):
            runner = AutonomousRunner(**kwargs)
            runner.inventory = SimpleNamespace(items={"/products": SimpleNamespace(
                canonical_url="http://127.0.0.1:18088/products?q=fixture", path="/products?q=fixture",
                refusal_reason=None, forms=[])})
            runner.capability_registry.register("ACTION-WEB-001", FakeWebExecutor())
            proposals = iter(actions)
            def propose(_state):
                action = next(proposals)
                return SimpleNamespace(proposal={"action_id": action, "target_id": "lab-ecommerce",
                    "resource_ref": "/products", "parameter_name": "q"},
                    mode_provenance={"actual_mode": "RULE"})
            runner.planner.propose = propose
            return runner

        def scan(_tool, relay, *args):
            if interrupted:
                raise RuntimeError("SCANNER_BUDGET_EXHAUSTED")
            seed = relay.urls()[0]
            relay.executed_urls.add(seed)
            relay.successful_urls.add(seed)
            relay.gate.network_dispatch_count += 1
            site = [{"host": "lab-ecommerce", "alerts": [{"alert": "Missing header", "pluginid": "10021",
                     "riskcode": "1", "confidence": "2", "instances": [{"uri": seed}]}]}]
            return json.dumps({"version": "fixture", "report": {"site": site}}).encode()

        request = self.request(execution_scope="scan", planner=planner, approve_authenticated_workflow=False,
                               approve_active_verification=True,
                               external_scanners=["zap-passive", "nuclei"] if interrupted else ["zap-passive"],
                               max_decisions=len(actions))
        with patch("runtime.lab.workflow_lab.WorkflowLab", FakeLab), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner", side_effect=create_runner), \
             patch("runtime.lab.external_scanners.preflight", return_value={}), \
             patch("runtime.lab.external_scanners.isolated_scan", side_effect=scan):
            self.manager._worker(run_id, request, self.run, self.sink)
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.COMPLETED)
        report = json.loads((self.run / "report.json").read_text(encoding="utf-8"))
        return report, build_coverage(self.run, run_id)

    def test_llm_run_includes_analysis_even_without_candidates(self):
        reply = {"interpretation": "Possible header issue", "uncertainty": "Missing headers",
                 "evidence_check": "Inspect saved header fields"}
        with patch("dashboards.app.backend.scanner_analysis._call_real_provider",
                   return_value=(json.dumps(reply), None, {"model_returned": "fixture"})) as provider:
            report, coverage = self._run_scanner_report_fixture(False, planner="llm")
        provider.assert_called_once()
        alert = coverage["scanner_reviews"][0]["alerts"][0]
        self.assertIn(alert["analysis"]["analysis_evidence_id"], report["evidence_refs"])
        self.assertEqual(report["scanner_results"][0]["candidate_count"], 0)
        self.assertEqual(coverage["scan_isolation"]["restore"], "RECORDED")

    def test_new_report_keeps_batch_reason_for_unstarted_scanner(self):
        report, coverage = self._run_scanner_report_fixture(include_web=False, interrupted=True)
        for rows in (report["scanner_results"], coverage["scanners"]):
            skipped = next(row for row in rows if row["tool"] == "nuclei")
            self.assertEqual((skipped["status"], skipped["reason"]), ("NOT_RUN", "SCANNER_BUDGET_EXHAUSTED"))
        self.assertNotEqual(report["stop_reason"], "SCANNER_BUDGET_EXHAUSTED")

    def test_passive_scanner_report_and_coverage_do_not_claim_internal_verification(self):
        report, coverage = self._run_scanner_report_fixture(include_web=False)
        self.assertEqual(report["active_verifications_count"], 0)
        self.assertEqual(coverage["integrity"], "VERIFIED")
        self.assertEqual(coverage["verifications"], [])
        scanner = next(item for item in coverage["scanners"] if item["tool"] == "zap-passive")
        self.assertEqual(scanner["status"], "COMPLETED")
        self.assertEqual(scanner["seed_coverage"]["requested_seed_count"], 1)
        self.assertEqual(coverage["scan_isolation"]["restore"], "RECORDED")

    def test_mixed_scanner_and_web_report_matches_verified_coverage(self):
        report, coverage = self._run_scanner_report_fixture(include_web=True)
        self.assertEqual(report["active_verifications_count"], 1)
        self.assertEqual(coverage["integrity"], "VERIFIED")
        self.assertEqual(len(coverage["verifications"]), 1)
        self.assertEqual(coverage["verifications"][0]["action"], "ACTION-WEB-001")
        self.assertEqual(coverage["verifications"][0]["attempts"], 1)
        self.assertEqual(next(item for item in coverage["scanners"]
                              if item["tool"] == "zap-passive")["status"], "COMPLETED")

    def test_independent_approvals_do_not_enable_other_scope(self):
        workflow = self.request()
        actions = _run_gate(workflow).effective_actions
        self.assertIn("ACTION-AUTH-001", actions)
        self.assertNotIn("ACTION-WEB-001", actions)
        self.assertNotIn("ACTION-SCAN-002", actions)
        scan = self.request(execution_scope="scan", approve_authenticated_workflow=False,
                            approve_active_verification=True, external_scanners=["nuclei"])
        actions = _run_gate(scan).effective_actions
        self.assertIn("ACTION-SCAN-002", actions)
        self.assertNotIn("ACTION-AUTH-001", actions)
        with self.assertRaises(ValidationError):
            self.request(approve_authenticated_workflow=False)
        with self.assertRaises(ValidationError):
            self.request(approve_active_verification=True)
        with self.assertRaises(ValidationError):
            self.request(execution_scope="scan")

    def test_only_known_isolated_lab_origins_are_accepted(self):
        for origin in ("http://127.0.0.1:18088", "http://10.0.0.2:8080"):
            with self.subTest(origin=origin):
                self.assertEqual(self.request(target_origin=origin).target_origin, origin)
                self.assertEqual(self.request(execution_scope="scan", approve_authenticated_workflow=False,
                                              target_origin=origin).target_origin, origin)
        for origin in ("http://192.168.1.2:8080", "http://10.0.0.20:8080",
                       "http://10.0.0.2:8080/path", "http://127.0.0.1:18089"):
            for scope in ("workflow", "scan"):
                with self.subTest(origin=origin, scope=scope), self.assertRaises(ValidationError):
                    self.request(execution_scope=scope, target_origin=origin,
                                 approve_authenticated_workflow=scope == "workflow")
        with self.assertRaises(ValidationError):
            self.request(target="lab-gns3", target_origin="http://10.0.0.2:8080")
        deny_demo = StartRunRequest(mode="deny-demo", target="lab-gns3",
                                    target_origin="http://192.168.1.2:8080")
        self.assertEqual(deny_demo.mode, "deny-demo")

    def test_mutated_target_is_refused_before_run_creation_and_worker_side_effects(self):
        request = self.request()
        request.target_origin = "http://192.168.1.2:8080"
        with patch("runtime.lab.workflow_lab.WorkflowLab") as lab, \
             patch("runtime.lab.control_support.new_recorder") as recorder, \
             patch("dashboards.app.backend.run_manager.AutonomousRunner") as runner:
            response = self.manager.start_run(request, self.sink)
            self.assertFalse(response.success)
            self.assertEqual(response.message, "ISOLATED_LAB_TARGET_UNSUPPORTED")
            self.assertIsNone(self.manager._active_thread)
            self.manager._worker(self.run_id, request, self.run, self.sink)
        lab.assert_not_called()
        recorder.assert_not_called()
        runner.assert_not_called()
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.FAILED)

    def test_web_labs_require_scan_scope_and_matching_loopback_origin(self):
        for target, port in (("lab-webapp-a", 18085), ("lab-webapp-b", 18086)):
            origin = f"http://127.0.0.1:{port}"
            scan = self.request(target=target, target_origin=origin, execution_scope="scan",
                                approve_authenticated_workflow=False, approve_active_verification=True,
                                external_scanners=["zap-active", "nuclei"])
            self.assertEqual(_run_gate(scan).effective_targets, {target})
            self.assertIn("ACTION-SCAN-002", _run_gate(scan).effective_actions)
            for wrong in ("http://10.0.0.2:8080", "http://127.0.0.1:18088", origin + "/other"):
                with self.subTest(target=target, origin=wrong), self.assertRaises(ValidationError):
                    self.request(target=target, target_origin=wrong, execution_scope="scan",
                                 approve_authenticated_workflow=False)
            for scope in ("workflow", "combined"):
                with self.subTest(target=target, scope=scope), self.assertRaises(ValidationError):
                    self.request(target=target, target_origin=origin, execution_scope=scope)

    def test_web_lab_cleanup_happens_before_terminal_event_and_coverage(self):
        lifecycle = []
        run_id = self.run_id
        class FakeLab:
            def __init__(self, _id, recorder, target, origin, **kwargs):
                self.recorder = recorder
                self_target = target
                self_origin = origin
                lifecycle.append((self_target, self_origin))
            def __enter__(self):
                lifecycle.append("isolated")
            def __exit__(self, *args):
                lifecycle.append("removed")
                self.recorder.persist_phase_artifact("scan_lab_restored", {"run_id": run_id})
        class FakeRunner:
            def __init__(self, **kwargs):
                self.hook = kwargs["event_hook"]
                self.scanner_executor = None
            def run(self):
                self.hook({"type": "RUN_COMPLETED", "payload": {"stop_reason": "fixture"}})
                return AutonomousRunReport(run_id, "lab-webapp-a", "RULE", "RULE", "rule_engine", "none",
                                           0, 0, 0, 0, 0, 0, "fixture", [], {}, [])
        recorder = DurableEvidenceRecorder(run_id, self.run / "assessment", approved_root=self.root)
        request = self.request(target="lab-webapp-a", target_origin="http://127.0.0.1:18085",
                               execution_scope="scan", approve_authenticated_workflow=False,
                               approve_read_only=True)
        original_event = self.manager._on_runtime_event
        def capture(event, sink):
            if event["type"] == "RUN_COMPLETED":
                self.assertIn("removed", lifecycle)
            original_event(event, sink)
        with patch("runtime.lab.web_scan_lab.WebScanLab", FakeLab), \
             patch("runtime.lab.workflow_lab.WorkflowLab") as shoplab, \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner", FakeRunner), \
             patch.object(self.manager, "_on_runtime_event", side_effect=capture):
            self.manager._worker(run_id, request, self.run, self.sink)
        shoplab.assert_not_called()
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.COMPLETED,
                         self.manager.get_snapshot()[0].error)
        coverage = build_coverage(self.run, run_id)
        self.assertEqual(coverage["scan_isolation"]["restore"], "RECORDED")
        self.assertEqual(coverage["workflow"]["status"], "NOT_SELECTED")

    def test_web_lab_without_approval_never_creates_containers(self):
        request = self.request(target="lab-webapp-b", target_origin="http://127.0.0.1:18086",
                               execution_scope="scan", approve_authenticated_workflow=False,
                               approve_read_only=False)
        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        with patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.web_scan_lab.WebScanLab") as isolated:
            self.manager._worker(self.run_id, request, self.run, self.sink)
        isolated.assert_not_called()
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.FAILED)
        self.assertEqual(self.manager.get_snapshot()[3].integrity_status, "VERIFIED")

    def test_non_isolated_scan_refuses_post_before_network(self):
        scan = self.request(execution_scope="scan", approve_authenticated_workflow=False,
                            approve_active_verification=True)
        gate = _run_gate(scan)
        approval = ApprovalToken("APP-FIXTURE", self.run_id, "lab-ecommerce", "*", time.time() - 1, time.time() + 60)
        request = DiscoveryRequest(self.run_id, "lab-ecommerce", "ACTION-WEB-002",
                                   "http://127.0.0.1:18088/cart/add", method="POST",
                                   form={"quantity": "1"}, approval=approval)
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as transport:
            response = gate.dispatch(request)
        self.assertEqual(response.outcome, "DENIED")
        self.assertEqual(response.refusal_reason, "SCAN_READ_ONLY_METHOD_REQUIRED")
        self.assertEqual(gate.network_dispatch_count, 0)
        transport.assert_not_called()
        request.method = "GET"
        request.form = {}
        with patch.object(CentralizedSafetyGate, "dispatch", return_value="delegated") as parent:
            self.assertEqual(gate.dispatch(request), "delegated")
        parent.assert_called_once_with(request)

    def test_unsafe_html_redaction_blocks_scan_before_creation_or_snapshot(self):
        request = self.request(execution_scope="scan", approve_authenticated_workflow=False)
        with patch("dashboards.app.backend.run_manager._scan_redaction_ready", return_value=False), \
             patch("runtime.lab.workflow_lab.WorkflowLab") as lab, \
             patch("dashboards.app.backend.run_manager.AutonomousRunner") as runner:
            response = self.manager.start_run(request, self.sink)
        self.assertFalse(response.success)
        self.assertEqual(response.message, "SCAN_REDACTION_UNSAFE")
        self.assertIsNone(self.manager._active_thread)
        lab.assert_not_called()
        runner.assert_not_called()

    def test_redaction_probe_requires_hidden_values_to_disappear(self):
        with patch("runtime.evidence.discovery_recorder.redact_secrets", side_effect=lambda value: value):
            self.assertFalse(_scan_redaction_ready())
        with patch("runtime.evidence.discovery_recorder.redact_secrets", return_value={}):
            self.assertFalse(_scan_redaction_ready())
        with patch("runtime.evidence.discovery_recorder.redact_secrets", side_effect=RuntimeError("fixture")):
            self.assertFalse(_scan_redaction_ready())
        with patch("runtime.evidence.discovery_recorder.redact_secrets", return_value={"body_snippet": "[BODY_SNIPPET_OMITTED]"}):
            self.assertTrue(_scan_redaction_ready())

    def test_scan_starts_when_real_redaction_probe_passes(self):
        self.assertTrue(_scan_redaction_ready())
        request = self.request(execution_scope="scan", approve_authenticated_workflow=False)
        with patch("dashboards.app.backend.run_manager.threading.Thread") as thread:
            response = self.manager.start_run(request, self.sink)
        self.assertTrue(response.success)
        thread.return_value.start.assert_called_once()

    def test_scan_blocks_if_recorder_redactor_is_replaced(self):
        request = self.request(execution_scope="scan", approve_authenticated_workflow=False)
        with patch("runtime.evidence.discovery_recorder.redact_secrets", side_effect=lambda value: value), \
             patch("dashboards.app.backend.run_manager.threading.Thread") as thread, \
             patch("runtime.lab.control_support.new_recorder") as recorder, \
             patch("runtime.lab.workflow_lab.WorkflowLab") as lab:
            response = self.manager.start_run(request, self.sink)
            self.assertFalse(response.success)
            self.assertEqual(response.message, "SCAN_REDACTION_UNSAFE")
            self.manager._worker(self.run_id, request, self.run, self.sink)
        thread.assert_not_called()
        recorder.assert_not_called()
        lab.assert_not_called()
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.FAILED)

    def test_scan_captures_profile_and_request_when_redaction_check_passes(self):
        profile = object()
        self.manager.model_profiles = SimpleNamespace(snapshot=lambda: profile)
        request = self.request(execution_scope="scan", approve_authenticated_workflow=False, planner="llm")
        with patch("dashboards.app.backend.run_manager._scan_redaction_ready", return_value=True), \
             patch("dashboards.app.backend.run_manager.threading.Thread") as thread:
            response = self.manager.start_run(request, self.sink)
        self.assertTrue(response.success)
        worker_request, captured_profile = thread.call_args.kwargs["args"][1], thread.call_args.kwargs["args"][-1]
        self.assertIs(captured_profile, profile)
        request.target_origin = "http://192.168.1.2:8080"
        self.assertEqual(worker_request.target_origin, "http://127.0.0.1:18088")

    def test_scan_worker_receives_profile_when_redaction_check_passes(self):
        profile = object()
        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        request = self.request(execution_scope="scan", approve_authenticated_workflow=False, planner="llm")
        with patch("dashboards.app.backend.run_manager._scan_redaction_ready", return_value=True), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.workflow_lab.WorkflowLab", side_effect=RuntimeError("fixture stop")), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner") as runner:
            self.manager._worker(self.run_id, request, self.run, self.sink, profile)
        self.assertIs(runner.call_args.kwargs["planner_provider_config"], profile)

    def test_workflow_only_restores_before_completion_and_does_not_create_runner(self):
        lifecycle = []
        class FakeLab:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                lifecycle.append("enter")
                return self
            def __exit__(self, *args):
                lifecycle.append("restored")

        class FakeWorkflow:
            def __init__(self, *args):
                pass
            def execute(self):
                lifecycle.append("workflow")
                return {"status": "COMPLETED", "checks": [], "failed_checks": 0, "network_dispatches": 0}

        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        original_event = self.manager._on_runtime_event
        def capture(event, sink):
            if event["type"] in ("WORKFLOW_COMPLETED", "RUN_COMPLETED"):
                self.assertIn("restored", lifecycle)
            original_event(event, sink)

        with patch("runtime.lab.workflow_lab.WorkflowLab", FakeLab), \
             patch("runtime.lab.authenticated_workflow.AuthenticatedWorkflow", FakeWorkflow), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner") as runner, \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.control_support.verify", return_value={"records": 1}), \
             patch.object(self.manager, "_on_runtime_event", side_effect=capture):
            self.manager._worker(self.run_id, self.request(), self.run, self.sink)
        runner.assert_not_called()
        self.assertEqual(lifecycle, ["enter", "workflow", "restored"])
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.COMPLETED)
        report = json.loads((self.run / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["actual_planner_mode"], "NONE")
        self.assertEqual(report["scanner_results"], [])
        self.assertTrue(report["workflow_result"]["original_volume_restored"])

    def test_restore_failure_cannot_report_completed(self):
        class FailingLab:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                raise RuntimeError("RESTORE_FAILED")
        class FakeWorkflow:
            def __init__(self, *args):
                pass
            def execute(self):
                return {"status": "COMPLETED", "checks": [], "failed_checks": 0, "network_dispatches": 0}

        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        with patch("runtime.lab.workflow_lab.WorkflowLab", FailingLab), \
             patch("runtime.lab.authenticated_workflow.AuthenticatedWorkflow", FakeWorkflow), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner") as runner, \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.control_support.verify", return_value={"records": 1}):
            self.manager._worker(self.run_id, self.request(), self.run, self.sink)
        runner.assert_not_called()
        self.assertEqual(self.manager.get_snapshot()[0].state, AgentState.FAILED)
        events = self.sink.get_history(run_id=self.run_id, limit=100)
        self.assertNotIn("RUN_COMPLETED", [event["type"] for event in events])

    def test_scan_failure_preserves_observed_results_without_guessing_missing_results(self):
        run_id = self.run_id
        class FailingRestore:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                raise RuntimeError("RESTORE_FAILED")
        class FakeRunner:
            def __init__(self, **kwargs):
                self.scanner_executor = SimpleNamespace(results=[{"tool": "zap-passive", "status": "COMPLETED"}])
            def run(self):
                return AutonomousRunReport(run_id, "lab-ecommerce", "RULE", "RULE", "rule_engine", "none",
                                           0, 0, 0, 0, 0, 0, "fixture", [], {}, [])
        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        request = self.request(execution_scope="scan", approve_authenticated_workflow=False,
                               approve_active_verification=True, external_scanners=["zap-passive", "nuclei"])
        with patch("dashboards.app.backend.run_manager._scan_redaction_ready", return_value=True), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.workflow_lab.WorkflowLab", FailingRestore), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner", FakeRunner):
            self.manager._worker(self.run_id, request, self.run, self.sink)
        report = json.loads((self.run / "report.json").read_text(encoding="utf-8"))
        results = {item["tool"]: item for item in report["scanner_results"]}
        self.assertEqual(results["zap-passive"]["status"], "COMPLETED")
        self.assertEqual(results["nuclei"]["status"], "UNKNOWN")
        self.assertEqual(results["nuclei"]["reason"], "RUN_FAILED")

    def test_scan_only_restores_without_running_workflow_and_records_skipped_scanner(self):
        run_id = self.run_id
        lifecycle = []
        class FakeLab:
            def __init__(self, _run_id, recorder, **kwargs):
                self.recorder = recorder
            def __enter__(self):
                lifecycle.append("isolation_started")
                return self
            def __exit__(self, *args):
                lifecycle.append("restored")
                self.recorder.persist_phase_artifact("workflow_restored", {"run_id": run_id})
        class FakeRunner:
            def __init__(self, **kwargs):
                self.scanner_executor = None
                self.hook = kwargs["event_hook"]
            def run(self):
                lifecycle.append("scan")
                self.hook({"type": "RUN_COMPLETED", "payload": {"stop_reason": "budget_exhausted"}})
                return AutonomousRunReport(run_id, "lab-ecommerce", "RULE", "RULE", "rule_engine", "none",
                                           0, 0, 0, 0, 0, 0, "budget_exhausted", [], {}, [])

        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        req = self.request(execution_scope="scan", approve_authenticated_workflow=False,
                           approve_active_verification=True, external_scanners=["nuclei"])
        with patch("runtime.lab.workflow_lab.WorkflowLab", FakeLab), \
             patch("runtime.lab.authenticated_workflow.AuthenticatedWorkflow") as workflow, \
             patch("dashboards.app.backend.run_manager.AutonomousRunner", FakeRunner), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.control_support.verify", return_value={"records": 2}):
            self.manager._worker(self.run_id, req, self.run, self.sink)
        workflow.assert_not_called()
        self.assertEqual(lifecycle, ["isolation_started", "scan", "restored"])
        result = build_coverage(self.run, self.run_id)
        scanner = next(item for item in result["scanners"] if item["tool"] == "nuclei")
        self.assertEqual(scanner["status"], "NOT_RUN")
        self.assertEqual(scanner["reason"], "budget_exhausted")
        self.assertEqual(result["workflow"]["reason"], "WORKFLOW_NOT_APPROVED")
        self.assertEqual(result["scan_isolation"]["restore"], "RECORDED")

    def test_stop_during_workflow_restores_before_terminal_state(self):
        lifecycle = []
        class FakeLab:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                lifecycle.append("restored")
        class StoppedWorkflow:
            def __init__(self, gate, *args):
                self.gate = gate
            def execute(self):
                self.gate.kill_switch.activate()
                return {"status": "COMPLETED", "checks": [], "failed_checks": 0, "network_dispatches": 0}

        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        with patch("runtime.lab.workflow_lab.WorkflowLab", FakeLab), \
             patch("runtime.lab.authenticated_workflow.AuthenticatedWorkflow", StoppedWorkflow), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.control_support.verify", return_value={"records": 1}):
            self.manager._worker(self.run_id, self.request(), self.run, self.sink)
        self.assertEqual(lifecycle, ["restored"])
        events = self.sink.get_history(run_id=self.run_id, limit=100)
        self.assertIn("RUN_STOPPED", [event["type"] for event in events])
        self.assertNotIn("RUN_COMPLETED", [event["type"] for event in events])
        report = json.loads((self.run / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["state"], "STOPPED")

    def test_legacy_scan_without_workflow_also_restores_isolation(self):
        run_id = self.run_id
        lifecycle = []
        class FakeLab:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                lifecycle.append("isolation_started")
                return self
            def __exit__(self, *args):
                lifecycle.append("restored")
        class FakeRunner:
            def __init__(self, **kwargs):
                self.scanner_executor = None
                self.hook = kwargs["event_hook"]
            def run(self):
                lifecycle.append("scan")
                self.hook({"type": "RUN_COMPLETED", "payload": {"stop_reason": "done"}})
                return AutonomousRunReport(run_id, "lab-ecommerce", "RULE", "RULE", "rule_engine", "none",
                                           0, 0, 0, 0, 0, 0, "done", [], {}, [])

        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        request = self.request(execution_scope="combined", approve_authenticated_workflow=False, approve_read_only=True)
        with patch("runtime.lab.workflow_lab.WorkflowLab", FakeLab), \
             patch("runtime.lab.authenticated_workflow.AuthenticatedWorkflow") as workflow, \
             patch("dashboards.app.backend.run_manager._scan_redaction_ready", return_value=True), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner", FakeRunner), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.control_support.verify", return_value={"records": 1}):
            self.manager._worker(self.run_id, request, self.run, self.sink)
        self.assertEqual(lifecycle, ["isolation_started", "scan", "restored"])
        workflow.assert_not_called()

    def test_scan_evidence_failure_never_emits_early_completion(self):
        run_id = self.run_id
        lifecycle = []
        class FakeLab:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                lifecycle.append("restored")
        class FakeRunner:
            def __init__(self, **kwargs):
                self.scanner_executor = None
                self.hook = kwargs["event_hook"]
            def run(self):
                self.hook({"type": "RUN_COMPLETED", "payload": {"stop_reason": "done"}})
                return AutonomousRunReport(run_id, "lab-ecommerce", "RULE", "RULE", "rule_engine", "none",
                                           0, 0, 0, 0, 0, 0, "done", [], {}, [])

        recorder = DurableEvidenceRecorder(self.run_id, self.run / "assessment", approved_root=self.root)
        req = self.request(execution_scope="scan", approve_authenticated_workflow=False, approve_read_only=True)
        with patch("runtime.lab.workflow_lab.WorkflowLab", FakeLab), \
             patch("dashboards.app.backend.run_manager._scan_redaction_ready", return_value=True), \
             patch("dashboards.app.backend.run_manager.AutonomousRunner", FakeRunner), \
             patch("runtime.lab.control_support.new_recorder", return_value=recorder), \
             patch("runtime.lab.control_support.verify", side_effect=RuntimeError("VERIFY_FAILED")):
            self.manager._worker(self.run_id, req, self.run, self.sink)
        events = self.sink.get_history(run_id=self.run_id, limit=100)
        self.assertNotIn("RUN_COMPLETED", [event["type"] for event in events])
        self.assertIn("RUN_FAILED", [event["type"] for event in events])
        self.assertEqual(lifecycle, ["restored"])
        report = json.loads((self.run / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["state"], "FAILED")


if __name__ == "__main__":
    unittest.main()
