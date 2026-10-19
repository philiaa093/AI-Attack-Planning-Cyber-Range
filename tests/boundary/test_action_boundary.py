"""Boundary tests for RT-03A — Generic TTP Action Contract.

Validates:
  C. Enterprise actions do not contain fixed target IDs/IP/hostnames.
  G. Expected effects do NOT directly mutate Belief State (Hard Invariant).
  H. Closed session does not satisfy precondition requiring active session in contract semantics.
  I. Action definitions do not reference Ground Truth.
  J. Action definitions do not leak hidden target inventory.
  K. Planner-facing metadata is strictly target-neutral.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from actions.catalog.action_registry import (
    ActionDefinition,
    evaluate_precondition_contract,
    get_action_registry,
    scan_action_for_target_leakage,
)
from agent.memory.state.belief_state import BeliefState
from scripts.validation.validate_scaffold import ROOT

CATALOG_PATH = ROOT / "actions/catalog/action-catalog.json"


class ActionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.registry = get_action_registry(CATALOG_PATH)

    def test_requirement_c_enterprise_actions_contain_no_hardcoded_targets_or_ips(self):
        """Requirement C: Generic Enterprise actions have zero fixed target IDs, IPs, or lab hostnames."""
        for action in self.registry.get_enterprise_actions():
            with self.subTest(action_id=action.action_id):
                # Target ID must not be present
                self.assertIsNone(
                    action.target_id,
                    f"Enterprise action {action.action_id} must have target_id=None",
                )
                # Leakage scan must be clean
                leakages = scan_action_for_target_leakage(action)
                self.assertEqual(
                    leakages,
                    [],
                    f"Target leakage detected in {action.action_id}: {leakages}",
                )

    def test_requirement_g_expected_effects_do_not_mutate_belief_state(self):
        """Requirement G: HARD INVARIANT: expected_effects in action definition cannot mutate BeliefState.

        Live path must strictly be: Proposal -> Safety Gate -> Executor -> Canonical Observation -> Belief Projection.
        """
        initial_facts = [
            {
                "fact_id": "FACT-INIT-001",
                "fact_type": "HOST",
                "subject": "10.0.1.5",
                "value": "observed",
                "confidence": 1.0,
                "provenance": {"source_kind": "OBSERVATION"},
            }
        ]
        belief_state = BeliefState.from_facts(initial_facts)
        state_dict_before = belief_state.to_dict()

        # Examine every action's expected_effects
        for action in self.registry.get_all_actions():
            effects = action.expected_effects
            # 1. Effects object must not have mutation methods
            self.assertFalse(hasattr(effects, "apply_to"))
            self.assertFalse(hasattr(effects, "mutate_state"))
            self.assertFalse(hasattr(effects, "apply_observation"))

            # 2. Directly inspecting or accessing expected_effects does not alter belief_state
            _ = effects.potential_facts
            _ = effects.potential_access_level
            _ = effects.potential_session_transition

        # State projection must remain strictly identical
        self.assertEqual(
            belief_state.to_dict(),
            state_dict_before,
            "Belief state was mutated by action definition interactions!",
        )

    def test_requirement_h_closed_session_does_not_satisfy_active_session_precondition(self):
        """Requirement H: Current vs Historical Access.

        An action requiring an active session (require_active_session=True)
        must REJECT a target where all sessions are CLOSED, even if historical
        proven_access_level is PRIVILEGED or SYSTEM.
        """
        # Find an action requiring active session (e.g. ACTION-HOSTRECON-001 or ACTION-PRIVESC-001)
        recon_action = self.registry.get_action("ACTION-HOSTRECON-001")
        self.assertIsNotNone(recon_action)
        self.assertTrue(recon_action.preconditions.require_active_session)

        # Build BeliefState where target 'srv-01' has historical PRIVILEGED access,
        # but the session was CLOSED.
        closed_session_facts = [
            {
                "fact_id": "F-HOST-01",
                "fact_type": "HOST",
                "subject": "srv-01",
                "value": "srv-01.corp",
                "confidence": 1.0,
                "provenance": {"source_kind": "OBSERVATION"},
            },
            {
                "fact_id": "F-ACCESS-01",
                "fact_type": "ACCESS",
                "subject": "srv-01",
                "value": "PRIVILEGED",  # Historical high access proven!
                "confidence": 1.0,
                "provenance": {"source_kind": "OBSERVATION"},
            },
            {
                "fact_id": "F-SESS-01",
                "fact_type": "SESSION",
                "subject": "sess-alpha-01",
                "value": {
                    "session_id": "sess-alpha-01",
                    "target_id": "srv-01",
                    "access_level": "PRIVILEGED",
                    "state": "CLOSED",  # But session is now CLOSED!
                },
                "confidence": 1.0,
                "provenance": {"source_kind": "OBSERVATION"},
            },
        ]
        belief_state = BeliefState.from_facts(closed_session_facts)

        # Verify host info shows historical PRIVILEGED access
        host_info = belief_state.known_hosts.get("srv-01")
        self.assertIsNotNone(host_info)
        self.assertEqual(host_info.get("access_level"), "PRIVILEGED")
        self.assertEqual(belief_state.access_state.get("srv-01"), "PRIVILEGED")

        # Verify session is CLOSED
        sessions_by_id = {s["session_id"]: s for s in belief_state.sessions}
        session_info = sessions_by_id.get("sess-alpha-01")
        self.assertIsNotNone(session_info)
        self.assertEqual(session_info.get("state"), "CLOSED")

        # Evaluate precondition contract
        satisfied, reasons = evaluate_precondition_contract(
            recon_action,
            belief_state,
            target_id="srv-01",
        )

        # MUST FAIL because require_active_session is True and session is CLOSED
        self.assertFalse(satisfied, "Closed session must not satisfy active execution capability")
        self.assertTrue(any("active=0" in r for r in reasons))

        # Now add an ACTIVE session and verify it succeeds
        active_session_facts = closed_session_facts + [
            {
                "fact_id": "F-SESS-02",
                "fact_type": "SESSION",
                "subject": "sess-alpha-02",
                "value": {
                    "session_id": "sess-alpha-02",
                    "target_id": "srv-01",
                    "access_level": "UNPRIVILEGED",
                    "state": "ACTIVE",
                },
                "confidence": 1.0,
                "provenance": {"source_kind": "OBSERVATION"},
            }
        ]
        active_belief = BeliefState.from_facts(active_session_facts)
        satisfied_active, _ = evaluate_precondition_contract(
            recon_action,
            active_belief,
            target_id="srv-01",
        )
        self.assertTrue(satisfied_active, "Active session must satisfy active execution capability")

    def test_requirement_i_action_definitions_do_not_reference_ground_truth(self):
        """Requirement I: Action catalog contains zero Ground Truth references or defender-private keys."""
        raw_catalog_text = CATALOG_PATH.read_text(encoding="utf-8")
        forbidden_terms = ["ground_truth", "ground-truth", "truth_records", "expected_detection", "answer_key"]
        for term in forbidden_terms:
            with self.subTest(term=term):
                self.assertNotIn(term, raw_catalog_text.lower())

    def test_requirement_j_action_definitions_do_not_leak_hidden_targets(self):
        """Requirement J: Action definitions define general capabilities and leak no hidden inventory."""
        for action in self.registry.get_enterprise_actions():
            with self.subTest(action_id=action.action_id):
                # Preconditions must not hardcode specific target IDs
                pre_dict = action.to_dict().get("preconditions", {})
                self.assertNotIn("target_id", pre_dict)
                self.assertNotIn("host_id", pre_dict)
                self.assertNotIn("ip_address", pre_dict)

    def test_requirement_k_planner_facing_metadata_is_target_neutral(self):
        """Requirement K: Action names, descriptions, and metadata are strictly target-neutral."""
        for action in self.registry.get_enterprise_actions():
            with self.subTest(action_id=action.action_id):
                # Name should not have target instance
                self.assertNotRegex(action.name, r"lab-[a-z0-9-]+")
                # Description should be generic capability explanation
                self.assertNotRegex(action.description, r"lab-[a-z0-9-]+")
                self.assertNotRegex(action.description, r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


if __name__ == "__main__":
    unittest.main()
