"""Unit tests for Simulator TransitionEngine (RT-04B).

Validates:
1. S1 straight progression (recon -> scan -> foothold -> creds -> pivot -> crown objective).
2. S2 decoy branch (honeypot alarm trips noise to CONTAINED).
3. S3 blocked firewall path (Eligible in Belief State != Successful in Environment).
4. S4 clean control (hardened target fails exploit).
5. Copy-on-write immutability (old TrueState is untouched).
6. Upstream authorization enforcement (authorized=False rejects fail-closed).
7. Determinism: identical seed and action sequence produces identical TrueState hashes.
"""
from __future__ import annotations

import random
import unittest
from pathlib import Path

from runtime.simulation.engine.transition_engine import (
    TransitionEngine,
    TransitionResult,
)
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.scenario import HiddenScenario
from runtime.simulation.models.true_state import TrueState
from scripts.validation.validate_scaffold import ROOT

FIXTURES_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"


class TestTransitionEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = ScenarioLoader()
        self.engine = TransitionEngine()
        self.s1 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        self.s2 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s2_decoy.json")
        self.s3 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s3_blocked.json")
        self.s4 = self.loader.load_from_file(FIXTURES_DIR / "scenario_s4_clean.json")

    def test_authorization_enforcement(self) -> None:
        """Unauthorized actions must reject fail-closed without mutating TrueState."""
        init_state = self.s1.create_initial_true_state(run_id="RUN-TEST-AUTH")
        res = self.engine.transition(
            true_state=init_state,
            scenario=self.s1,
            action="ACTION-RECON-001",
            target="lab-dmz-entry",
            authorized=False,
        )
        self.assertFalse(res.success)
        self.assertIn("UNAUTHORIZED", res.reason)
        self.assertEqual(res.new_true_state, init_state)
        self.assertEqual(res.noise_delta, 0.0)

    def test_copy_on_write_immutability(self) -> None:
        """Transition execution must NOT mutate the input TrueState in place."""
        state_t0 = self.s1.create_initial_true_state(run_id="RUN-TEST-COW")
        orig_step = state_t0.current_step
        orig_noise = state_t0.defender_state.accumulated_noise
        orig_nodes = dict(state_t0.node_states)

        res = self.engine.transition(
            true_state=state_t0,
            scenario=self.s1,
            action="ACTION-RECON-001",
            target="lab-dmz-entry",
            authorized=True,
        )

        self.assertTrue(res.success)
        # Verify old state was untouched
        self.assertEqual(state_t0.current_step, orig_step)
        self.assertEqual(state_t0.defender_state.accumulated_noise, orig_noise)
        self.assertEqual(state_t0.node_states, orig_nodes)
        self.assertIsNot(state_t0, res.new_true_state)
        # Verify new state advanced
        self.assertEqual(res.new_true_state.current_step, 1)
        self.assertGreater(res.new_true_state.defender_state.accumulated_noise, orig_noise)

    def test_s1_straight_path_progression(self) -> None:
        """Step-by-step execution through S1 straight path to crown jewel."""
        state = self.s1.create_initial_true_state(run_id="RUN-S1-TEST")
        rng = random.Random(42)

        # 1. Recon on DMZ entry
        res1 = self.engine.transition(state, self.s1, "ACTION-RECON-001", "lab-dmz-entry", rng=rng)
        self.assertTrue(res1.success)
        state = res1.new_true_state
        self.assertEqual(state.current_step, 1)
        self.assertEqual(len(res1.raw_observations), 1)
        self.assertEqual(res1.raw_observations[0]["fact_type"], "SERVICE")

        # 2. Vulnerability Scan on DMZ entry
        res2 = self.engine.transition(state, self.s1, "ACTION-SCAN-001", "lab-dmz-entry", rng=rng)
        self.assertTrue(res2.success)
        state = res2.new_true_state
        self.assertEqual(state.current_step, 2)
        self.assertEqual(res2.raw_observations[0]["fact_type"], "CONFIRMED_FINDING")

        # 3. Exploit web foothold on DMZ entry
        res3 = self.engine.transition(state, self.s1, "ACTION-WEB-001", "lab-dmz-entry", rng=rng)
        self.assertTrue(res3.success)
        state = res3.new_true_state
        self.assertEqual(state.get_node_access_level("lab-dmz-entry"), "FOOTHOLD")
        self.assertTrue(state.has_active_session("lab-dmz-entry"))

        # 4. Dump credentials on DMZ entry
        res4 = self.engine.transition(state, self.s1, "ACTION-AUTH-001", "lab-dmz-entry", rng=rng)
        self.assertTrue(res4.success)
        state = res4.new_true_state
        self.assertTrue(state.credentials_truth["cred-app-svc"].discovered)

        # 5. Lateral movement to Internal App
        res5 = self.engine.transition(
            state,
            self.s1,
            "ACTION-FLOW-001",
            "lab-internal-app",
            from_node_id="lab-dmz-entry",
            credential_id="cred-app-svc",
            rng=rng,
        )
        self.assertTrue(res5.success)
        state = res5.new_true_state
        self.assertEqual(state.get_node_access_level("lab-internal-app"), "USER")
        self.assertTrue(state.has_active_session("lab-internal-app"))
        self.assertTrue(state.credentials_truth["cred-db-admin"].discovered)

        # 6. Objective execution on Crown DB
        res6 = self.engine.transition(
            state,
            self.s1,
            "ACTION-FLOW-002",
            "lab-db-crown",
            from_node_id="lab-internal-app",
            credential_id="cred-db-admin",
            rng=rng,
        )
        self.assertTrue(res6.success)
        state = res6.new_true_state
        self.assertTrue(state.is_objective_achieved())
        self.assertEqual(state.objective_truth.achieved_at_step, 6)
        self.assertEqual(state.get_node_access_level("lab-db-crown"), "PRIVILEGED")

        # 7. Stop action
        res7 = self.engine.transition(state, self.s1, "ACTION-END-001", target=None, rng=rng)
        self.assertTrue(res7.success)
        state = res7.new_true_state
        self.assertEqual(state.current_step, 7)

    def test_s3_blocked_firewall_eligible_not_successful(self) -> None:
        """S3 demonstrates Eligible != Successful: direct pivot is blocked by firewall."""
        state = self.s3.create_initial_true_state(run_id="RUN-S3-TEST")
        rng = random.Random(42)

        # Establish foothold on DMZ
        res_fh = self.engine.transition(state, self.s3, "ACTION-WEB-001", "lab-dmz-entry", rng=rng)
        state = res_fh.new_true_state

        # Pivot to internal app
        res_piv = self.engine.transition(
            state, self.s3, "ACTION-FLOW-001", "lab-internal-app", from_node_id="lab-dmz-entry", rng=rng
        )
        state = res_piv.new_true_state
        self.assertEqual(state.get_node_access_level("lab-internal-app"), "USER")

        # Direct pivot from internal app to crown DB (BLOCKED BY FIREWALL in S3)
        res_direct = self.engine.transition(
            state,
            self.s3,
            "ACTION-FLOW-001",
            "lab-db-crown",
            from_node_id="lab-internal-app",
            credential_id="cred-db-admin",
            rng=rng,
        )
        # Must FAIL in environment even if planner wanted to try it
        self.assertFalse(res_direct.success)
        state = res_direct.new_true_state
        self.assertFalse(state.is_objective_achieved())
        self.assertEqual(state.get_node_access_level("lab-db-crown"), "NONE")
        self.assertEqual(len(res_direct.raw_observations), 1)
        self.assertIn("FIREWALL", str(res_direct.raw_observations[0]["value"]))

        # Alternate path via jump box
        res_jump = self.engine.transition(
            state,
            self.s3,
            "ACTION-FLOW-001",
            "lab-jump-box",
            from_node_id="lab-internal-app",
            credential_id="cred-jump-admin",
            rng=rng,
        )
        self.assertTrue(res_jump.success)
        state = res_jump.new_true_state
        self.assertEqual(state.get_node_access_level("lab-jump-box"), "USER")

        # Crown objective via jump box succeeds
        res_obj = self.engine.transition(
            state,
            self.s3,
            "ACTION-FLOW-002",
            "lab-db-crown",
            from_node_id="lab-jump-box",
            credential_id="cred-db-admin",
            rng=rng,
        )
        self.assertTrue(res_obj.success)
        state = res_obj.new_true_state
        self.assertTrue(state.is_objective_achieved())

    def test_s2_decoy_honeypot_trap(self) -> None:
        """S2 decoy honeypot trap trips detection threshold to CONTAINED."""
        state = self.s2.create_initial_true_state(run_id="RUN-S2-TEST")
        rng = random.Random(42)

        # Foothold on DMZ
        res1 = self.engine.transition(state, self.s2, "ACTION-WEB-001", "lab-dmz-entry", rng=rng)
        state = res1.new_true_state

        # Pivot to internal app, discovering honey token
        res2 = self.engine.transition(
            state, self.s2, "ACTION-FLOW-001", "lab-internal-app", from_node_id="lab-dmz-entry", rng=rng
        )
        state = res2.new_true_state
        self.assertTrue(state.credentials_truth["cred-honey-token"].discovered)

        # Trigger decoy trap
        res_decoy = self.engine.transition(
            state,
            self.s2,
            "ACTION-FLOW-001",
            "lab-decoy-honeypot",
            from_node_id="lab-internal-app",
            credential_id="cred-honey-token",
            rng=rng,
        )
        state = res_decoy.new_true_state
        self.assertGreaterEqual(state.defender_state.accumulated_noise, 24.0)
        self.assertEqual(state.defender_state.detection_state, "CONTAINED")
        self.assertGreaterEqual(state.defender_state.alerts_triggered, 1)

    def test_s4_clean_control_hardened_fail(self) -> None:
        """S4 clean control baseline: exploit fails deterministically."""
        state = self.s4.create_initial_true_state(run_id="RUN-S4-TEST")
        rng = random.Random(42)

        res_exploit = self.engine.transition(
            state, self.s4, "ACTION-WEB-001", "lab-dmz-entry", rng=rng
        )
        self.assertFalse(res_exploit.success)
        self.assertEqual(res_exploit.new_true_state.get_node_access_level("lab-dmz-entry"), "NONE")
        self.assertIn("TARGET_HARDENED", str(res_exploit.raw_observations[0]["value"]))

    def test_deterministic_replay(self) -> None:
        """Identical scenario, seed, and action sequence produces identical TrueState hashes."""
        state1 = self.s1.create_initial_true_state(run_id="RUN-REPLAY-1", seed=1337)
        state2 = self.s1.create_initial_true_state(run_id="RUN-REPLAY-1", seed=1337)

        res1 = self.engine.transition(state1, self.s1, "ACTION-RECON-001", "lab-dmz-entry", rng=1337)
        res2 = self.engine.transition(state2, self.s1, "ACTION-RECON-001", "lab-dmz-entry", rng=1337)

        self.assertEqual(res1.new_true_state.deterministic_hash(), res2.new_true_state.deterministic_hash())
        self.assertEqual(res1.raw_observations, res2.raw_observations)


if __name__ == "__main__":
    unittest.main()
