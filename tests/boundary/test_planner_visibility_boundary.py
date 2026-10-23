"""Boundary tests for RT-01B: Planner Visibility Boundary (Fog-of-War).

Enforces:
  Invariant 1: Safety Scope != Planner-Visible Scope (Planner Visibility is a strict subset of Safety Scope).
  Invariant 2: Initial Fog of War (t=0) — Planner is initialized strictly with initial entry seed.
  Invariant 3: Discovery-Driven Visibility — Targets enter planner visibility ONLY via canonical observation facts.
  Invariant 4: Zero Pre-Discovery Leakage — Hidden targets never leak into PlanningInput, candidate lists, or LLM prompts.
  Invariant 5: Safety Gate Final Authority — Planner-visible != authorized; safety gate strictly evaluates and can deny.
  Invariant 6: Anti-Invention — Proposals for unobserved/unseen targets fail validation.
  Invariant 7: Deprecated Alias Compatibility — allowed_target_ids emits warning and aliases visible_target_ids.
"""
from __future__ import annotations

import ast
import json
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import MagicMock

from agent.memory.state.state_manager import StateManager
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.planners.llm_planner import LLMPlanner, ContextLimits
from runtime.planners.observed_planner import ObservedStatePlanner
from runtime.planners.planner_interface import (
    PlanningInput,
    PlanProposal,
    StateSnapshot,
    project_visible_targets,
)
from runtime.planners.rule_based_planner import RuleBasedPlanner, Rule
from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
)
from runtime.state.knowledge_state_store import StoreContext
from scripts.validation.validate_scaffold import ROOT


CONTEXT = StoreContext("RUN-BOUND-VIS-001", "SES-001", "EP-001")
ACTION = "ACTION-RECON-001"
REVIEW_ACTION = "ACTION-PLAN-003"


def create_snapshot(facts=None, phase="RECON", target="lab-entry-01"):
    base_state = {
        "schema_version": "1.0",
        "run_id": CONTEXT.run_id,
        "scenario_id": "SCN-001",
        "objective_id": "OBJ-001",
        "phase": phase,
        "remaining_budget": {"actions": 10, "requests": 50, "seconds": 3600.0},
        "observed_facts": facts or [],
        "previous_actions": [],
    }
    return StateSnapshot.from_state(base_state, context=CONTEXT)


class PlannerVisibilityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry_seed = "lab-entry-01"
        self.hidden_targets = {"lab-internal-01", "lab-core-01", "lab-decoy-01"}
        self.safety_scope = {self.entry_seed} | self.hidden_targets

    def test_01_initial_fog_of_war_entry_seed_only(self) -> None:
        """Invariant 1 & 2: At t=0, planner visibility contains ONLY entry seed, never hidden targets."""
        snapshot = create_snapshot()
        projected = project_visible_targets(snapshot, initial_seed=self.entry_seed)

        self.assertEqual(projected, frozenset({self.entry_seed}))
        self.assertNotIn("lab-internal-01", projected)
        self.assertNotIn("lab-core-01", projected)
        self.assertNotIn("lab-decoy-01", projected)

        # Invariant: Safety Scope != Planner-Visible Scope
        self.assertNotEqual(projected, frozenset(self.safety_scope))
        self.assertTrue(projected.issubset(self.safety_scope))

        # PlanningInput construction at t=0
        p_input = PlanningInput(
            state=snapshot,
            allowed_action_ids={ACTION},
            visible_target_ids=projected,
        )
        self.assertEqual(p_input.visible_target_ids, frozenset({self.entry_seed}))
        for hidden in self.hidden_targets:
            self.assertNotIn(hidden, p_input.visible_target_ids)

    def test_02_zero_pre_discovery_leakage_in_prompts_and_candidates(self) -> None:
        """Invariant 4: Hidden targets never leak into PlanningInput, candidate loops, or LLM prompts."""
        # State contains candidate findings, but target is NOT in visible_target_ids
        unseen_fact = {
            "fact_id": "FACT-HIDDEN-01",
            "fact_type": "CANDIDATE_FINDING",
            "subject": "lab-internal-01",
            "value": "hidden_login_surface",
            "confidence": 0.5,
            "source_observation_id": "OBS-001",
        }
        visible_fact = {
            "fact_id": "FACT-VISIBLE-01",
            "fact_type": "CANDIDATE_FINDING",
            "subject": self.entry_seed,
            "value": "entry_service_found",
            "confidence": 0.5,
            "source_observation_id": "OBS-002",
        }
        snapshot = create_snapshot(facts=[unseen_fact, visible_fact], phase="ANALYSIS")

        # PlanningInput at t=0 has only entry seed
        p_input = PlanningInput(
            state=snapshot,
            allowed_action_ids={REVIEW_ACTION},
            visible_target_ids={self.entry_seed},
        )

        # Test RuleBasedPlanner candidate filtering
        rule_planner = RuleBasedPlanner()
        decision = rule_planner.plan(p_input)
        self.assertIsNotNone(decision.proposal)
        plan = decision.proposal.to_dict()
        self.assertEqual(plan["target_id"], self.entry_seed)
        self.assertNotEqual(plan["target_id"], "lab-internal-01")

        # Test LLMPlanner candidate filtering and context prompt isolation
        calls: list[str] = []

        class MockProvider:
            def complete(self, prompt_text: str):
                calls.append(prompt_text)
                # Parse context from prompt text to verify hidden target is absent
                data = json.loads(prompt_text)
                content = json.loads(data["input"][0]["content"])
                return json.dumps({
                    "status": "completed",
                    "output": [{
                        "type": "function_call",
                        "name": "submit_review_decision",
                        "arguments": json.dumps({
                            "input_revision": content["control"]["input_revision"],
                            "decision": "REVIEW_EVIDENCE",
                            "candidate_version": content["candidates"][0]["candidate_version"],
                            "reason_code": "REVIEW_REQUIRED",
                        }),
                    }],
                })

        provider = MockProvider()
        llm = LLMPlanner(provider=provider, count_tokens=lambda text: len(text) // 4)
        llm.plan(p_input)

        self.assertEqual(len(calls), 1)
        raw_prompt = calls[0]
        # Invariant: Hidden target ID must NOT appear anywhere in the LLM payload
        self.assertNotIn("lab-internal-01", raw_prompt)
        self.assertNotIn("lab-core-01", raw_prompt)
        self.assertIn(self.entry_seed, raw_prompt)

    def test_03_discovery_driven_visibility_unlock(self) -> None:
        """Invariant 3: Target enters visibility only when canonical observation fact is present."""
        # 1. State before discovery
        s0 = create_snapshot(facts=[])
        vis0 = project_visible_targets(s0, initial_seed=self.entry_seed)
        self.assertEqual(vis0, frozenset({self.entry_seed}))
        self.assertNotIn("lab-internal-01", vis0)

        # 2. Add canonical discovery fact: TARGET discovered
        discovery_fact = {
            "fact_id": "FACT-DISC-001",
            "fact_type": "TARGET",
            "subject": self.entry_seed,
            "value": "lab-internal-01",
            "confidence": 1.0,
            "source_observation_id": "OBS-DISC-01",
        }
        s1 = create_snapshot(facts=[discovery_fact])
        vis1 = project_visible_targets(s1, initial_seed=self.entry_seed)

        # Invariant: Discovery fact unlocked visibility
        self.assertEqual(vis1, frozenset({self.entry_seed, "lab-internal-01"}))
        self.assertIn("lab-internal-01", vis1)
        # Undiscovered targets remain hidden
        self.assertNotIn("lab-core-01", vis1)
        self.assertNotIn("lab-decoy-01", vis1)

        # 3. Add canonical discovery fact via SERVICE host
        service_fact = {
            "fact_id": "FACT-DISC-002",
            "fact_type": "SERVICE",
            "subject": "lab-core-01:8080",
            "value": "http",
            "confidence": 1.0,
            "source_observation_id": "OBS-DISC-02",
        }
        s2 = create_snapshot(facts=[discovery_fact, service_fact])
        vis2 = project_visible_targets(s2, initial_seed=self.entry_seed)
        self.assertEqual(vis2, frozenset({self.entry_seed, "lab-internal-01", "lab-core-01"}))

    def test_04_safety_gate_remains_independent_authority(self) -> None:
        """Invariant 5: Planner-visible != authorized; Safety Gate strictly enforces policy."""
        # Target is visible to planner
        visible_targets = {self.entry_seed, "lab-internal-01"}

        # Safety Gate does NOT allow lab-internal-01 (revoked or not allowlisted)
        gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            target_registry={
                self.entry_seed: {"host": "127.0.0.1", "port": 18088},
                "lab-internal-01": {"host": "127.0.0.1", "port": 18089},
            },
            target_allowlist={self.entry_seed},  # Only entry is allowlisted in gate!
            canonical_target_allowlist={self.entry_seed},
            action_allowlist={"ACTION-RECON-002"},
            lab_mode=True,
        )

        approval = ApprovalToken(
            approval_id="APP-REVOKED-01",
            run_id=CONTEXT.run_id,
            target_id="lab-internal-01",
            action_id="ACTION-RECON-002",
            not_before=0,
            expires_at=2000000000,
        )

        req = DiscoveryRequest(
            run_id=CONTEXT.run_id,
            target_id="lab-internal-01",
            action_id="ACTION-RECON-002",
            url="http://127.0.0.1:18089/admin",
            approval=approval,
        )

        # Dispatch MUST be denied by safety gate with zero network dispatches
        resp = gate.dispatch(req)
        self.assertEqual(resp.outcome, "DENIED")
        self.assertEqual(resp.refusal_reason, "TARGET_NOT_ALLOWLISTED")
        self.assertEqual(gate.network_dispatch_count, 0)

    def test_05_anti_invention_and_unseen_target_rejection(self) -> None:
        """Invariant 6: Proposals for unobserved / invented targets are rejected before gate."""
        snapshot = create_snapshot()
        p_input = PlanningInput(
            state=snapshot,
            allowed_action_ids={ACTION},
            visible_target_ids={self.entry_seed},
        )

        # Attempt to propose an invented target
        class InventingPlanner(RuleBasedPlanner):
            def _plan(self, req):
                from runtime.planners.planner_interface import PlanningDecision
                prop = PlanProposal.from_dict({
                    "plan_id": "PLAN-021-" + "a" * 64,
                    "objective_id": "OBJ-001",
                    "action_id": ACTION,
                    "target_id": "lab-invented-01",
                    "reason_code": "invented_target",
                    "confidence": 0.5,
                })
                return PlanningDecision(
                    context=req.state.context,
                    input_revision=req.state.revision,
                    requested_mode="RULE",
                    actual_mode="RULE",
                    proposal=prop,
                )

        planner = InventingPlanner()
        with self.assertRaisesRegex(ValueError, "proposal outside candidate scope"):
            planner.plan(p_input)

        # ObservedStatePlanner rejection check
        obs_planner = ObservedStatePlanner(target_id=self.entry_seed, visible_targets={self.entry_seed})
        parsed, err = obs_planner._parse_provider_json(json.dumps({
            "schema_version": "1.0",
            "plan_id": "PLAN-001",
            "objective_id": "OBJ-001",
            "action_id": "ACTION-RECON-001",
            "target_id": "lab-invented-01",
            "reason_code": "hallucination",
            "confidence": 0.5,
        }))
        self.assertIsNone(parsed)
        self.assertEqual(err, "UNAUTHORIZED_TARGET_lab-invented-01")

    def test_06_autonomous_runner_fog_of_war_lifecycle(self) -> None:
        """Invariant 1 & 3: AutonomousRunner maintains fog-of-war at t=0 and expands only on observation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_root = os.environ.get("APPROVED_EVIDENCE_ROOT")
            os.environ["APPROVED_EVIDENCE_ROOT"] = tmp_dir
            try:
                gate = CentralizedSafetyGate(
                    base_origin="http://127.0.0.1:18088",
                    target_registry={
                        self.entry_seed: {"host": "127.0.0.1", "port": 18088},
                        "lab-internal-01": {"host": "127.0.0.1", "port": 18089},
                    },
                    target_allowlist=self.safety_scope,
                    canonical_target_allowlist=self.safety_scope,
                    action_allowlist={"ACTION-RECON-001", "ACTION-RECON-002", "ACTION-END-001"},
                    lab_mode=True,
                )

                recorder = DurableEvidenceRecorder(run_id="RUN-BOUND-TEST")
                approval = ApprovalToken(
                    approval_id="APP-BOUND-01",
                    run_id="RUN-BOUND-TEST",
                    target_id=self.entry_seed,
                    action_id="*",
                    not_before=0,
                    expires_at=2000000000,
                )

                runner = AutonomousRunner(
                    target_id=self.entry_seed,
                    run_id="RUN-BOUND-TEST",
                    gate=gate,
                    recorder=recorder,
                    approval=approval,
                    max_decisions=5,
                )

                # At t=0, runner.visible_targets has ONLY entry seed
                self.assertEqual(runner.visible_targets, {self.entry_seed})
                self.assertEqual(runner.planner.visible_targets, {self.entry_seed})
                # Gate has full safety scope
                self.assertEqual(runner.gate.effective_targets, self.safety_scope)
                self.assertNotEqual(runner.visible_targets, runner.gate.effective_targets)

                # Simulate discovery observation ingestion
                discovery_obs = {
                    "observation_id": "OBS-DISC-99",
                    "run_id": runner.run_id,
                    "action_id": "ACTION-RECON-002",
                    "timestamp_utc": "2026-10-10T12:00:00Z",
                    "outcome": "SUCCESS",
                    "new_facts": [
                        {
                            "fact_id": "FACT-DISC-99",
                            "fact_type": "TARGET",
                            "subject": self.entry_seed,
                            "value": "lab-internal-01",
                            "confidence": 1.0,
                        }
                    ],
                }

                runner._ingest_and_update_visibility(discovery_obs)

                # Visibility is now unlocked for lab-internal-01
                self.assertIn("lab-internal-01", runner.visible_targets)
                self.assertIn("lab-internal-01", runner.planner.visible_targets)
                # Still does not contain unobserved targets
                self.assertNotIn("lab-core-01", runner.visible_targets)
                self.assertNotIn("lab-decoy-01", runner.visible_targets)

            finally:
                if old_root is not None:
                    os.environ["APPROVED_EVIDENCE_ROOT"] = old_root
                else:
                    os.environ.pop("APPROVED_EVIDENCE_ROOT", None)

    def test_07_deprecated_allowed_target_ids_compatibility_and_warning(self) -> None:
        """Invariant 7: allowed_target_ids emits DeprecationWarning and acts as alias to visible_target_ids."""
        snapshot = create_snapshot()

        # Warning emitted on accessing allowed_target_ids
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")
            req = PlanningInput(
                state=snapshot,
                allowed_action_ids={ACTION},
                allowed_target_ids={self.entry_seed},
            )
            val = req.allowed_target_ids

            self.assertEqual(val, frozenset({self.entry_seed}))
            self.assertEqual(req.visible_target_ids, frozenset({self.entry_seed}))
            dep_warnings = [w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)]
            self.assertTrue(len(dep_warnings) >= 1)
            self.assertIn("allowed_target_ids is deprecated", str(dep_warnings[0].message))

    def test_08_observed_state_planner_no_allowlist_default(self) -> None:
        """Invariant 8: ObservedStatePlanner does not load canonical target allowlist when instantiated."""
        planner = ObservedStatePlanner(target_id=self.entry_seed)
        # Default visibility is strictly {target_id}, never repo-wide allowlist
        self.assertEqual(planner.visible_targets, {self.entry_seed})
        self.assertNotIn("lab-internal-01", planner.visible_targets)
        self.assertNotIn("lab-core-01", planner.visible_targets)
        self.assertNotIn("lab-ecommerce", planner.visible_targets if self.entry_seed != "lab-ecommerce" else set())


if __name__ == "__main__":
    unittest.main()
