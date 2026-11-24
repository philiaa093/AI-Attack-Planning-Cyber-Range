"""Tests for planner INCONCLUSIVE termination prevention, GNS3 authenticated workflow,
POST/form verification support, and expanded rule/template coverage.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from dashboards.app.backend.models import StartRunRequest
from dashboards.app.backend.run_manager import _run_gate
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.lab.capability_registry import (
    CapabilityRegistry,
    PassiveSurfaceAnalyzer,
    SafeInputVerificationExecutor,
    SafeReflectionVerificationExecutor,
)
from runtime.discovery.discovery_engine import InventoryItem, InventoryStore
from runtime.lab.external_scanners import TEMPLATES, FAMILIES
from runtime.lab.workflow_lab import WorkflowLab
from runtime.lab.workflow_lab import GNS3WorkflowControl
from runtime.planners.observed_planner import ObservedStatePlanner
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.safety.discovery_gate import (
    ApprovalToken,
    BudgetTracker,
    CentralizedSafetyGate,
    DiscoveryRequest,
    TokenBucketRateLimiter,
)
from scripts.validation.validate_scaffold import ROOT


class InconclusiveAndPlannerReverificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target_id = "lab-ecommerce"
        self.objective_id = "OBJ-TEST-001"
        self.planner = ObservedStatePlanner(self.target_id, self.objective_id, requested_mode="RULE")

    def test_inconclusive_candidate_enters_reverification_cycle(self) -> None:
        """Candidate with INCONCLUSIVE outcome is scheduled for reverification."""
        state = {
            "phase": "RECON",
            "remaining_budget": {"actions": 10},
            "previous_actions": ["ACTION-RECON-001", "ACTION-RECON-002", "ACTION-SCAN-001"],
            "discovered_endpoints": ["/api/resource"],
            "observed_facts": [
                {"fact_type": "ENDPOINT", "value": "/api/resource"},
                {"fact_type": "PARAMETER", "subject": "/api/resource", "value": "item_id"},
                {"fact_type": "ACTION_OUTCOME", "subject": "ACTION-WEB-001:/api/resource:item_id", "value": "INCONCLUSIVE"},
            ],
        }
        proposal = self.planner.propose(state).proposal
        self.assertEqual(proposal["action_id"], "ACTION-WEB-001")
        self.assertEqual(proposal["resource_ref"], "/api/resource")
        self.assertEqual(proposal["parameter_name"], "item_id")
        self.assertEqual(proposal["reason_code"], "reverify_inconclusive_candidate")

    def test_inconclusive_prevents_normal_termination_and_halts_with_003(self) -> None:
        """Planner never concludes with ACTION-END-001 while INCONCLUSIVE candidates remain."""
        # 3 attempts already performed for this item, all INCONCLUSIVE
        state = {
            "phase": "RECON",
            "remaining_budget": {"actions": 10},
            "previous_actions": ["ACTION-RECON-001", "ACTION-RECON-002", "ACTION-SCAN-001"],
            "discovered_endpoints": ["/api/resource"],
            "observed_facts": [
                {"fact_type": "ENDPOINT", "value": "/api/resource"},
                {"fact_type": "PARAMETER", "subject": "/api/resource", "value": "item_id"},
                {"fact_type": "ACTION_OUTCOME", "subject": "ACTION-WEB-001:/api/resource:item_id", "value": "INCONCLUSIVE"},
                {"fact_type": "ACTION_OUTCOME", "subject": "ACTION-WEB-001:/api/resource:item_id", "value": "INCONCLUSIVE"},
                {"fact_type": "ACTION_OUTCOME", "subject": "ACTION-WEB-001:/api/resource:item_id", "value": "INCONCLUSIVE"},
            ],
        }
        res = self.planner.propose(state)
        self.assertNotEqual(res.proposal["action_id"], "ACTION-END-001")
        self.assertEqual(res.proposal["action_id"], "ACTION-END-003")
        self.assertEqual(res.proposal["reason_code"], "unresolved_inconclusive_surface")


class GNS3AuthenticatedWorkflowTests(unittest.TestCase):
    def test_start_run_request_accepts_gns3_authenticated_workflow(self) -> None:
        """StartRunRequest validates authenticated workflow on GNS3 target origin."""
        req = StartRunRequest(
            mode="autonomous",
            approve_active_verification=True,
            approve_authenticated_workflow=True,
            target="lab-ecommerce",
            target_origin="http://10.0.0.2:8080",
            max_requests=250,
        )
        self.assertTrue(req.approve_authenticated_workflow)
        self.assertEqual(req.target_origin, "http://10.0.0.2:8080")
        self.assertEqual(_run_gate(req).budget_tracker.timeout, 15.0)

    def test_workflow_lab_gns3_lifecycle_without_docker_dependency(self) -> None:
        """GNS3 lifecycle records only management operations confirmed by the control plane."""
        recorder = Mock()
        recorder.persist_phase_artifact.return_value = {"evidence_id": "EV-TEST-1"}
        control = Mock()
        control.snapshot.return_value = "a" * 64
        control.restore.return_value = "a" * 64
        with patch("runtime.lab.workflow_lab.GNS3WorkflowControl", return_value=control), \
             WorkflowLab("RUN-DASH-" + "1" * 32, recorder, is_gns3=True,
                         target_origin="http://10.0.0.2:8080") as lab:
                self.assertTrue(lab.active)
                self.assertTrue(lab.is_gns3)
                admin_username = f"rt_{lab.key}_c"
                lab.promote(admin_username)

        self.assertFalse(lab.active)
        recorded_phases = [call[0][0] for call in recorder.persist_phase_artifact.call_args_list]
        self.assertIn("workflow_snapshot_intent", recorded_phases)
        self.assertIn("workflow_snapshot", recorded_phases)
        self.assertIn("workflow_control_ready", recorded_phases)
        self.assertIn("workflow_admin_provisioned", recorded_phases)
        self.assertIn("workflow_restored", recorded_phases)
        control.health.assert_called_once_with()
        control.promote.assert_called_once_with(lab.run_id, admin_username)
        control.restore.assert_called_once_with(lab.run_id)

    def test_gns3_control_requires_private_matching_host_and_environment_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CONTROL_AUTH_UNAVAILABLE"):
                GNS3WorkflowControl("http://10.0.0.2:8080")
        env = {
            "SHOPLAB_GNS3_CONTROL_TOKEN": "x" * 32,
            "SHOPLAB_GNS3_CONTROL_URL": "http://8.8.8.8:8081",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CONTROL_INVALID"):
                GNS3WorkflowControl("http://10.0.0.2:8080")


class PostFormSupportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = Mock()
        self.recorder.persist_intent.return_value = {"evidence_id": "EV-INTENT"}
        self.recorder.persist_result.return_value = {"evidence_id": "EV-RESULT"}
        self.recorder.persist_phase_artifact.return_value = {"evidence_id": "EV-PHASE"}
        self.recorder.artifacts = [{"evidence_id": "EV-RESULT-1", "type": "result"}]
        self.approval = ApprovalToken("APP-1", "RUN-POST-1", "lab-ecommerce", "*", 0, 9999999999)
        self.gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            target_allowlist={"lab-ecommerce"},
            action_allowlist={"ACTION-WEB-001", "ACTION-WEB-002", "ACTION-SCAN-001"},
            recorder=self.recorder,
            lab_mode=True,
            rate_limiter=TokenBucketRateLimiter(1000, 1000),
            budget_tracker=BudgetTracker(max_requests=100),
        )

    def test_gate_allows_post_with_form_for_active_verification(self) -> None:
        """Safety Gate permits POST method with form fields for approved active verification."""
        req = DiscoveryRequest(
            run_id="RUN-POST-1",
            target_id="lab-ecommerce",
            action_id="ACTION-WEB-001",
            url="http://127.0.0.1:18088/catalog/search",
            method="POST",
            form={"query": "test_probe"},
            approval=self.approval,
        )
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as conn:
            mock_res = Mock(status=200, getheaders=lambda: [("Content-Type", "text/html")])
            mock_res.read.return_value = b"<html>ok</html>"
            conn.return_value.getresponse.return_value = mock_res

            resp = self.gate.dispatch(req)
            self.assertEqual(resp.outcome, "SUCCESS")
            # Verify body was urlencoded in POST request
            conn.return_value.request.assert_called_once()
            call_args = conn.return_value.request.call_args
            self.assertEqual(call_args[0][0], "POST")
            self.assertEqual(call_args[1]["body"], b"query=test_probe")
            self.assertEqual(call_args[1]["headers"]["Content-Type"], "application/x-www-form-urlencoded")

    def test_runner_preflight_accepts_only_observed_post_form_target_and_input(self) -> None:
        inventory = InventoryStore()
        inventory.record_item(InventoryItem(
            canonical_url="http://127.0.0.1:18088/form-page",
            path="/form-page",
            method="GET",
            source_observation_id="OBS-FORM-001",
            parent_url=None,
            depth=0,
            status_code=200,
            content_type="text/html",
            body_bytes=100,
            truncated=False,
            forms=[{
                "action": "http://127.0.0.1:18088/form-submit",
                "method": "POST",
                "inputs": [{"name": "message", "type": "text"}],
                "is_same_origin": True,
            }],
            links_found=[],
            redirect_to=None,
            discovered_at_utc="2026-11-24T00:00:00Z",
            redacted=True,
        ))
        runner = object.__new__(AutonomousRunner)
        runner.target_id = "lab-ecommerce"
        runner.gate = self.gate
        runner.approval = self.approval
        runner.recorder = self.recorder
        runner.inventory = inventory
        runner.scanner_executor = None
        before = self.gate.network_dispatch_count

        decision = runner._evaluate_safety({
            "target_id": "lab-ecommerce",
            "action_id": "ACTION-WEB-001",
            "resource_ref": "/form-submit",
            "parameter_name": "message",
        })
        self.assertEqual(decision, ("APPROVED", "SAFETY_GATE_PASSED"))
        self.assertEqual(self.gate.network_dispatch_count, before)

        decision = runner._evaluate_safety({
            "target_id": "lab-ecommerce",
            "action_id": "ACTION-WEB-001",
            "resource_ref": "/form-submit",
            "parameter_name": "invented",
        })
        self.assertEqual(decision, ("DENIED", "UNOBSERVED_INPUT"))
        self.assertEqual(self.gate.network_dispatch_count, before)

    def test_passive_analyzer_generates_candidate_finding_for_post_forms(self) -> None:
        """PassiveSurfaceAnalyzer generates CANDIDATE_FINDING for inputs in POST forms without polluting GET PARAMETER facts."""
        inv = InventoryStore()
        inv_item = InventoryItem(
            canonical_url="http://127.0.0.1:18088/contact",
            path="/contact",
            method="GET",
            source_observation_id="OBS-1",
            parent_url=None,
            depth=1,
            status_code=200,
            content_type="text/html",
            body_bytes=500,
            truncated=False,
            forms=[{
                "action": "/contact/submit",
                "method": "POST",
                "inputs": [{"name": "message", "type": "textarea"}],
            }],
            links_found=[],
            redirect_to=None,
            discovered_at_utc="2026-10-10T00:00:00Z",
            redacted=True,
        )
        inv.record_item(inv_item)

        analyzer = PassiveSurfaceAnalyzer()
        res = analyzer.execute(
            proposal={"target_id": "lab-ecommerce"},
            gate=self.gate,
            recorder=self.recorder,
            run_id="RUN-POST-1",
            target_id="lab-ecommerce",
            inventory=inv,
            approval=self.approval,
        )
        cand_facts = [f for f in res.new_facts if f.get("fact_type") == "CANDIDATE_FINDING" and f.get("value") == "post_form_input_message"]
        self.assertTrue(len(cand_facts) >= 1)
        self.assertEqual(cand_facts[0]["value"], "post_form_input_message")

        # Verify planner extracts POST form candidate and proposes verification
        planner = ObservedStatePlanner(target_id="lab-ecommerce", requested_mode="RULE")
        state = {
            "objective_id": "OBJ-1",
            "remaining_budget": {"actions": 5},
            "previous_actions": ["ACTION-RECON-001", "ACTION-RECON-002", "ACTION-SCAN-001"],
            "discovered_endpoints": ["http://127.0.0.1:18088/contact/submit"],
            "observed_facts": res.new_facts + [
                {"fact_type": "ENDPOINT", "subject": "http://127.0.0.1:18088/contact/submit", "value": "http://127.0.0.1:18088/contact/submit"}
            ],
        }
        plan_res = planner.propose(state)
        self.assertIn(plan_res.proposal["action_id"], ("ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003"))
        self.assertEqual(plan_res.proposal["parameter_name"], "message")

    def test_reflection_probe_does_not_report_negative_on_incomplete_http_response(self) -> None:
        inventory = InventoryStore()
        response = Mock(
            outcome="FAILURE",
            refusal_reason=None,
            durable_confirmed=True,
            status_code=403,
            error_message=None,
            truncated=False,
            body="forbidden",
            headers={"Content-Type": "text/html"},
        )
        with patch.object(self.gate, "dispatch", return_value=response):
            result = SafeReflectionVerificationExecutor().execute(
                proposal={
                    "action_id": "ACTION-WEB-002",
                    "target_id": "lab-ecommerce",
                    "resource_ref": "/login",
                    "parameter_name": "username",
                    "evidence_refs": [],
                },
                gate=self.gate,
                recorder=self.recorder,
                run_id="RUN-POST-1",
                target_id="lab-ecommerce",
                inventory=inventory,
                approval=self.approval,
            )
        self.assertEqual(result.classification, "INCONCLUSIVE")
        self.assertEqual(result.outcome, "FAILURE")


class RuleAndTemplateExpansionTests(unittest.TestCase):
    def test_nuclei_template_expansion_includes_xss(self) -> None:
        """TEMPLATES in external_scanners includes lab-xss-reflection."""
        self.assertIn("lab-xss-reflection", TEMPLATES)
        self.assertEqual(TEMPLATES["lab-xss-reflection"], "xss")
        self.assertEqual(FAMILIES["xss"], "SCRIPT_INJECTION")

        # Verify YAML template file exists and parses as valid JSON/YAML
        template_file = ROOT / "tools" / "scanners" / "templates" / "lab-xss-reflection.yaml"
        self.assertTrue(template_file.is_file())
        data = json.loads(template_file.read_text(encoding="utf-8"))
        self.assertEqual(data["id"], "lab-xss-reflection")
        self.assertEqual(data["info"]["tags"], "xss")


if __name__ == "__main__":
    unittest.main()
