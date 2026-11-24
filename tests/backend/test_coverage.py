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

    def test_no_scope_or_records_does_not_invent_skipped_reasons(self):
        empty = build_coverage(self.run, self.run.name)
        self.assertEqual(empty["integrity"], "NOT_VERIFIED")
        self.assertEqual(empty["matrix"], [])
        self.record("workflow_check", check="login_a", status="PASS")
        coverage = build_coverage(self.run, self.run.name)
        self.assertIsNone(coverage["scope"])
        self.assertEqual(coverage["scanners"][0]["status"], "UNKNOWN")
        self.assertEqual(coverage["matrix"][0]["status"], "UNKNOWN")

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

    def _run_scanner_report_fixture(self, include_web):
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
            seed = relay.urls()[0]
            relay.executed_urls.add(seed)
            relay.successful_urls.add(seed)
            relay.gate.network_dispatch_count += 1
            return json.dumps({"version": "fixture", "report": {"site": []}}).encode()

        request = self.request(execution_scope="scan", approve_authenticated_workflow=False,
                               approve_active_verification=True, external_scanners=["zap-passive"],
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
