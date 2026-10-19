"""Boundary tests for RT-02B Belief State Projection.

Enforces:
1. Planner direct mutation prevention (Belief State is read-only projection).
2. Self-confirming belief attack regression prevention (PLANNER_INFERENCE cannot self-confirm).
3. Plaintext secret and raw subprocess isolation.
4. Zero-knowledge boundary: no oracle leakage from scenarios or safety allowlists.
5. Ground Truth isolation: Evaluation domain truth never leaks into Belief State.
6. Discovery-driven visibility: Hypotheses never unlock target visibility.
"""
from __future__ import annotations

import copy
import json
import unittest

from agent.memory.state.belief_state import BeliefState, project_belief_state
from agent.memory.state.state_manager import StateManager
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.planners.planner_adapter import PlannerStateAdapter
from runtime.planners.planner_interface import project_visible_targets


class TestBeliefStateBoundary(unittest.TestCase):
    def setUp(self) -> None:
        self.run_id = "RUN-BOUNDARY-001"
        self.scenario_id = "SCN-001"
        self.objective_id = "OBJ-001"
        self.action_id = "ACTION-SCAN-001"

    def test_01_belief_state_is_immutable_projection(self) -> None:
        """BeliefState returns deep copies; planner mutation cannot alter internal state."""
        facts = [
            {
                "fact_id": "FACT-HOST-01",
                "fact_type": "HOST",
                "subject": "lab-target-01",
                "value": "10.0.1.10",
                "confidence": 1.0,
                "source_observation_id": "OBS-01",
            },
            {
                "fact_id": "FACT-ACCE-01",
                "fact_type": "ACCESS",
                "subject": "lab-target-01",
                "value": "USER",
                "confidence": 1.0,
                "source_observation_id": "OBS-01",
            },
        ]
        belief = BeliefState.from_facts(facts)

        # Attempt to mutate returned collections
        hosts = belief.known_hosts
        hosts["lab-target-01"]["access_level"] = "SYSTEM"
        hosts["fake-host"] = {"host": "fake-host"}

        access = belief.access_state
        access["lab-target-01"] = "SYSTEM"

        # Verify internal belief state was NOT mutated
        self.assertEqual(belief.get_host_access("lab-target-01"), "USER")
        self.assertEqual(belief.known_hosts["lab-target-01"]["access_level"], "USER")
        self.assertFalse(belief.is_host_known("fake-host"))

    def test_02_self_confirming_belief_attack_regression(self) -> None:
        """Regression test for self-confirming belief attack: PLANNER_INFERENCE cannot create truth.

        Attacker scenario:
        A malicious or hallucinating planner produces inferred observations claiming:
        1. An arbitrary target host exists.
        2. It holds valid admin credentials.
        3. It elevated to SYSTEM privilege.
        4. It established an ACTIVE root session.
        5. It has reachability to an internal database.
        6. It achieved the mission objective.

        Security Assertion:
        ALL inferred facts must be quarantined to `hypotheses`.
        Authoritative belief state must remain completely unchanged.
        """
        sm = StateManager(self.run_id, self.scenario_id, self.objective_id)

        # Baseline: empty state
        initial_belief = sm.get_belief_state()
        self.assertEqual(len(initial_belief.known_hosts), 0)
        self.assertEqual(len(initial_belief.known_credentials), 0)
        self.assertEqual(len(initial_belief.sessions), 0)
        self.assertEqual(len(initial_belief.observed_reachability), 0)

        # Adversarial planner inference observation
        adversarial_obs = {
            "observation_id": "OBS-ATTACK-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "source_kind": "PLANNER_INFERENCE",
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-ADV-01",
                    "fact_type": "HOST",
                    "subject": "lab-critical-dc",
                    "value": "10.0.0.1",
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-ADV-02",
                    "fact_type": "CREDENTIAL",
                    "subject": "CORP.LOCAL",
                    "value": {
                        "credential_id": "CRED-ADV-01",
                        "principal": "EnterpriseAdmin",
                        "credential_kind": "KERBEROS_TGT",
                        "observed_scope": "CORP.LOCAL",
                        "validity_state": "VALID",
                    },
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-ADV-03",
                    "fact_type": "ACCESS",
                    "subject": "lab-critical-dc",
                    "value": "SYSTEM",
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-ADV-04",
                    "fact_type": "SESSION",
                    "subject": "lab-critical-dc",
                    "value": {
                        "session_id": "SESS-ADV-01",
                        "target_id": "lab-critical-dc",
                        "access_level": "SYSTEM",
                        "state": "ACTIVE",
                    },
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-ADV-05",
                    "fact_type": "REACHABILITY",
                    "subject": "lab-dmz -> lab-critical-dc",
                    "value": {"from_host": "lab-dmz", "to_host": "lab-critical-dc", "protocol": "rdp"},
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-ADV-06",
                    "fact_type": "OBJECTIVE",
                    "subject": "OBJ-DOMAIN-COMPROMISE",
                    "value": "ACHIEVED",
                    "confidence": 1.0,
                },
            ],
        }

        sm.apply_observation(adversarial_obs)
        belief = sm.get_belief_state()

        # Boundary assertions: Zero authoritative belief state changes
        self.assertFalse(belief.is_host_known("lab-critical-dc"))
        self.assertEqual(belief.get_host_access("lab-critical-dc"), "NONE")
        self.assertEqual(len(belief.known_credentials), 0)
        self.assertEqual(len(belief.sessions), 0)
        self.assertEqual(len(belief.observed_reachability), 0)
        self.assertNotIn("OBJ-DOMAIN-COMPROMISE", belief.objective_status)

        # Hypotheses quarantine: All 6 facts captured as hypothesis ONLY
        self.assertEqual(len(belief.hypotheses), 6)
        for h in belief.hypotheses:
            self.assertIn("OBS-ATTACK-001", h["provenance"])

    def test_03_inference_cannot_open_visibility_boundary(self) -> None:
        """Inferred target facts cannot expand planner target visibility."""
        sm = StateManager(self.run_id, self.scenario_id, self.objective_id)
        sm.apply_observation({
            "observation_id": "OBS-INFER-VIS",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "source_kind": "PLANNER_INFERENCE",
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-INFER-VIS-1",
                    "fact_type": "TARGET",
                    "subject": "lab-hidden-crown-jewel",
                    "value": "discovered",
                    "confidence": 0.99,
                },
                {
                    "fact_id": "FACT-INFER-VIS-2",
                    "fact_type": "HOST",
                    "subject": "lab-hidden-database",
                    "value": "10.0.99.1",
                    "confidence": 0.99,
                },
            ],
        })

        visible = project_visible_targets(sm.get_state(), initial_seed="lab-entry-gateway")
        self.assertEqual(visible, frozenset({"lab-entry-gateway"}))
        self.assertNotIn("lab-hidden-crown-jewel", visible)
        self.assertNotIn("lab-hidden-database", visible)

    def test_04_no_oracle_leakage_of_safety_allowlists(self) -> None:
        """Full safety target allowlist is never leaked into Belief State."""
        # Simulated scenario: safety gate knows full allowlist
        safety_allowlist = ["lab-target-a", "lab-target-b", "lab-clean-001", "lab-internal-sql"]

        sm = StateManager(self.run_id, self.scenario_id, self.objective_id)
        # Only observe lab-target-a
        sm.apply_observation({
            "observation_id": "OBS-LEGIT-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "source_kind": "DISCOVERY",
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-LEGIT-001",
                "fact_type": "TARGET",
                "subject": "lab-target-a",
                "value": "discovered",
                "confidence": 1.0,
            }],
        })

        belief = sm.get_belief_state()
        self.assertTrue(belief.is_host_known("lab-target-a"))

        # Unobserved allowlist entries MUST remain completely unknown
        for unobserved in ("lab-target-b", "lab-clean-001", "lab-internal-sql"):
            self.assertFalse(belief.is_host_known(unobserved))
            self.assertNotIn(unobserved, belief.known_hosts)

    def test_05_ground_truth_rejection(self) -> None:
        """Belief State rejects Ground Truth keys and values."""
        bad_fact = {
            "fact_id": "FACT-GT-LEAK",
            "fact_type": "HOST",
            "subject": "lab-target-gt",
            "value": {
                "ip": "10.0.0.5",
                "ground_truth": "EVALUATION_PRIVATE_DATA",
                "expected_vulnerabilities": ["CVE-2021-44228"],
            },
            "confidence": 1.0,
            "source_observation_id": "OBS-01",
        }
        belief_dict = project_belief_state([bad_fact])
        serialized = json.dumps(belief_dict)
        self.assertNotIn("ground_truth", serialized)
        self.assertNotIn("EVALUATION_PRIVATE_DATA", serialized)
        self.assertNotIn("expected_vulnerabilities", serialized)


if __name__ == "__main__":
    unittest.main()
