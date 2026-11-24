"""Unit tests for SafeBusinessLogicVerificationExecutor (ACTION-LOGIC-001)
and ObservedStatePlanner business logic proposal integration.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from runtime.discovery.discovery_engine import InventoryItem, InventoryStore
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.lab.capability_registry import (
    ACTION_EXECUTION_DETAILS,
    CapabilityRegistry,
    SafeBusinessLogicVerificationExecutor,
)
from runtime.planners.observed_planner import ObservedStatePlanner, PLANNABLE_ACTIONS
from runtime.safety.discovery_gate import (
    ApprovalToken,
    BudgetTracker,
    CentralizedSafetyGate,
    DiscoveryRequest,
    DispatchResponse,
    TokenBucketRateLimiter,
)


class BusinessLogicExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.evidence_dir = Path(self.tmp_dir.name)
        self.recorder = DurableEvidenceRecorder(run_id="RUN-TEST-001", base_dir=self.evidence_dir)
        self.approval = ApprovalToken(
            approval_id="APP-TEST-LOGIC-001",
            run_id="RUN-TEST-001",
            target_id="lab-ecommerce",
            action_id="*",
            not_before=0.0,
            expires_at=9999999999.0,
        )
        self.gate = CentralizedSafetyGate(
            base_origin="http://10.0.0.2:8080",
            target_registry={"lab-ecommerce": {"target_id": "lab-ecommerce"}},
            target_allowlist={"lab-ecommerce"},
            action_allowlist={"ACTION-LOGIC-001", "ACTION-RECON-002"},
            canonical_target_allowlist={"lab-ecommerce"},
            canonical_action_allowlist={"ACTION-LOGIC-001", "ACTION-RECON-002"},
            recorder=self.recorder,
            rate_limiter=TokenBucketRateLimiter(requests_per_second=100.0, burst=10),
            budget_tracker=BudgetTracker(max_requests=50),
            lab_mode=True,
        )
        self.executor = SafeBusinessLogicVerificationExecutor()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _create_mock_inventory(self, resource: str = "/cart/add", param: str = "quantity") -> InventoryStore:
        inv = InventoryStore()
        inv_item = InventoryItem(
            canonical_url=f"http://10.0.0.2:8080{resource}",
            path=resource,
            method="GET",
            source_observation_id="OBS-1",
            parent_url=None,
            depth=1,
            status_code=200,
            content_type="text/html",
            body_bytes=500,
            truncated=False,
            forms=[{
                "action": resource,
                "method": "POST",
                "inputs": [
                    {"name": param, "type": "number", "value": "1"},
                    {"name": "_csrf_token", "type": "hidden", "value": "token123"},
                ],
            }],
            links_found=[],
            redirect_to=None,
            discovered_at_utc="2026-10-10T00:00:00Z",
            redacted=True,
        )
        inv.record_item(inv_item)
        return inv

    def test_registry_registration_and_action_details(self) -> None:
        """ACTION-LOGIC-001 is registered in CapabilityRegistry and ACTION_EXECUTION_DETAILS."""
        registry = CapabilityRegistry()
        executor = registry.get_executor("ACTION-LOGIC-001")
        self.assertIsInstance(executor, SafeBusinessLogicVerificationExecutor)
        self.assertTrue(registry.is_executable("ACTION-LOGIC-001"))

        self.assertIn("ACTION-LOGIC-001", ACTION_EXECUTION_DETAILS)
        details = ACTION_EXECUTION_DETAILS["ACTION-LOGIC-001"]
        self.assertEqual(details["family"], "BUSINESS_LOGIC")
        self.assertIn("ACTION-LOGIC-001", PLANNABLE_ACTIONS)

    def test_logic_executor_negative_boundary_rejected(self) -> None:
        """When target rejects negative quantity with 400 Bad Request, outcome is NEGATIVE."""
        inv = self._create_mock_inventory("/cart/add", "quantity")

        def mock_dispatch(req: DiscoveryRequest) -> DispatchResponse:
            if req.method == "GET":
                return DispatchResponse(
                    status_code=200,
                    headers={"content-type": "text/html", "set-cookie": "session=sess123; Path=/"},
                    body='<form method="POST" action="/cart/add"><input name="quantity" value="1"/><input name="_csrf_token" value="abc"/></form>',
                    raw_bytes_len=100,
                    truncated=False,
                    outcome="SUCCESS",
                    durable_confirmed=True,
                    canonical_url=req.url,
                )
            # POST probe
            q_val = req.form.get("quantity")
            if q_val == "-1":
                return DispatchResponse(
                    status_code=400,
                    headers={"content-type": "text/html"},
                    body="Invalid quantity: must be positive integer",
                    raw_bytes_len=40,
                    truncated=False,
                    outcome="FAILURE",
                    durable_confirmed=True,
                    canonical_url=req.url,
                )
            return DispatchResponse(
                status_code=200,
                headers={"content-type": "text/html"},
                body="Cart updated",
                raw_bytes_len=12,
                truncated=False,
                outcome="SUCCESS",
                durable_confirmed=True,
                canonical_url=req.url,
            )

        self.gate.dispatch = mock_dispatch

        res = self.executor.execute(
            proposal={"resource_ref": "/cart/add", "parameter_name": "quantity"},
            gate=self.gate,
            recorder=self.recorder,
            run_id="RUN-TEST-001",
            target_id="lab-ecommerce",
            inventory=inv,
            approval=self.approval,
        )

        self.assertEqual(res.outcome, "SUCCESS")
        self.assertEqual(res.classification, "NEGATIVE")
        self.assertEqual(len(res.findings), 1)
        finding = res.findings[0]
        self.assertEqual(finding.family, "BUSINESS_LOGIC")
        self.assertEqual(finding.classification, "NEGATIVE")
        self.assertIn("validates parameter quantity", finding.reason)

    def test_logic_executor_verified_flaw_on_accepted_underflow(self) -> None:
        """When target accepts negative quantity with 302 and no error, outcome is VERIFIED_IN_LAB."""
        inv = self._create_mock_inventory("/cart/add", "quantity")

        def mock_dispatch(req: DiscoveryRequest) -> DispatchResponse:
            if req.method == "GET":
                return DispatchResponse(
                    status_code=200,
                    headers={"content-type": "text/html"},
                    body='<form method="POST" action="/cart/add"><input name="quantity" value="1"/></form>',
                    raw_bytes_len=100,
                    truncated=False,
                    outcome="SUCCESS",
                    durable_confirmed=True,
                    canonical_url=req.url,
                )
            return DispatchResponse(
                status_code=302,
                headers={"location": "/cart"},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="SUCCESS",
                durable_confirmed=True,
                canonical_url=req.url,
            )

        self.gate.dispatch = mock_dispatch

        res = self.executor.execute(
            proposal={"resource_ref": "/cart/add", "parameter_name": "quantity"},
            gate=self.gate,
            recorder=self.recorder,
            run_id="RUN-TEST-001",
            target_id="lab-ecommerce",
            inventory=inv,
            approval=self.approval,
        )

        self.assertEqual(res.outcome, "SUCCESS")
        self.assertEqual(res.classification, "VERIFIED_IN_LAB")
        self.assertEqual(res.findings[0].classification, "VERIFIED_IN_LAB")
        self.assertIn("flaw verified: target accepted negative value", res.findings[0].reason)

    def test_logic_executor_server_error_signal(self) -> None:
        """When target crashes with HTTP 500 on boundary probe, outcome is SIGNAL."""
        inv = self._create_mock_inventory("/cart/add", "quantity")

        def mock_dispatch(req: DiscoveryRequest) -> DispatchResponse:
            if req.method == "GET":
                return DispatchResponse(
                    status_code=200,
                    headers={},
                    body='<form method="POST" action="/cart/add"><input name="quantity" value="1"/></form>',
                    raw_bytes_len=100,
                    truncated=False,
                    outcome="SUCCESS",
                    durable_confirmed=True,
                    canonical_url=req.url,
                )
            return DispatchResponse(
                status_code=500,
                headers={},
                body="Internal Server Error: unhandled ValueError",
                raw_bytes_len=45,
                truncated=False,
                outcome="FAILURE",
                durable_confirmed=True,
                canonical_url=req.url,
            )

        self.gate.dispatch = mock_dispatch

        res = self.executor.execute(
            proposal={"resource_ref": "/cart/add", "parameter_name": "quantity"},
            gate=self.gate,
            recorder=self.recorder,
            run_id="RUN-TEST-001",
            target_id="lab-ecommerce",
            inventory=inv,
            approval=self.approval,
        )

        self.assertEqual(res.outcome, "SUCCESS")
        self.assertEqual(res.classification, "SIGNAL")
        self.assertIn("HTTP 500", res.findings[0].reason)

    def test_logic_executor_idempotency_deduplication(self) -> None:
        """When duplicate checkout tokens redirect to identical order, outcome is NEGATIVE (idempotent)."""
        inv = self._create_mock_inventory("/checkout", "idempotency_key")

        def mock_dispatch(req: DiscoveryRequest) -> DispatchResponse:
            if req.method == "GET":
                return DispatchResponse(
                    status_code=200,
                    headers={},
                    body='<form method="POST" action="/checkout"><input name="idempotency_key" value=""/></form>',
                    raw_bytes_len=100,
                    truncated=False,
                    outcome="SUCCESS",
                    durable_confirmed=True,
                    canonical_url=req.url,
                )
            return DispatchResponse(
                status_code=302,
                headers={"location": "/orders/42"},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="SUCCESS",
                durable_confirmed=True,
                canonical_url=req.url,
            )

        self.gate.dispatch = mock_dispatch

        res = self.executor.execute(
            proposal={"resource_ref": "/checkout", "parameter_name": "idempotency_key"},
            gate=self.gate,
            recorder=self.recorder,
            run_id="RUN-TEST-001",
            target_id="lab-ecommerce",
            inventory=inv,
            approval=self.approval,
        )

        self.assertEqual(res.outcome, "SUCCESS")
        self.assertEqual(res.classification, "NEGATIVE")
        self.assertIn("Idempotency verified", res.findings[0].reason)

    def test_logic_executor_broken_idempotency_flaw(self) -> None:
        """When duplicate checkout tokens redirect to different orders, outcome is VERIFIED_IN_LAB."""
        inv = self._create_mock_inventory("/checkout", "idempotency_key")
        order_counter = [1]

        def mock_dispatch(req: DiscoveryRequest) -> DispatchResponse:
            if req.method == "GET":
                return DispatchResponse(
                    status_code=200,
                    headers={},
                    body='<form method="POST" action="/checkout"><input name="idempotency_key" value=""/></form>',
                    raw_bytes_len=100,
                    truncated=False,
                    outcome="SUCCESS",
                    durable_confirmed=True,
                    canonical_url=req.url,
                )
            loc = f"/orders/{order_counter[0]}"
            order_counter[0] += 1
            return DispatchResponse(
                status_code=302,
                headers={"location": loc},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="SUCCESS",
                durable_confirmed=True,
                canonical_url=req.url,
            )

        self.gate.dispatch = mock_dispatch

        res = self.executor.execute(
            proposal={"resource_ref": "/checkout", "parameter_name": "idempotency_key"},
            gate=self.gate,
            recorder=self.recorder,
            run_id="RUN-TEST-001",
            target_id="lab-ecommerce",
            inventory=inv,
            approval=self.approval,
        )

        self.assertEqual(res.outcome, "SUCCESS")
        self.assertEqual(res.classification, "VERIFIED_IN_LAB")
        self.assertIn("Broken idempotency verified", res.findings[0].reason)

    def test_planner_proposes_action_logic_for_cart_and_checkout(self) -> None:
        """Planner automatically proposes ACTION-LOGIC-001 for cart/checkout/quantity inputs."""
        planner = ObservedStatePlanner("lab-ecommerce", "OBJ-001", requested_mode="RULE")
        state = {
            "phase": "RECON",
            "remaining_budget": {"actions": 8},
            "previous_actions": ["ACTION-RECON-001", "ACTION-RECON-002", "ACTION-SCAN-001"],
            "discovered_endpoints": ["/cart/add"],
            "observed_facts": [
                {"fact_type": "CANDIDATE_FINDING", "subject": "/cart/add", "value": "post_form_input_quantity"},
            ],
        }
        res = planner.propose(state)
        self.assertEqual(res.proposal["action_id"], "ACTION-LOGIC-001")
        self.assertEqual(res.proposal["resource_ref"], "/cart/add")
        self.assertEqual(res.proposal["parameter_name"], "quantity")
        self.assertTrue(res.proposal["hypothesis_id"].startswith("HYPO-LOGIC-"))


if __name__ == "__main__":
    unittest.main()
