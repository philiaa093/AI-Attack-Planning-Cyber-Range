"""Unit tests for EpisodeEnvironment (RT-04C Requirements C, D, E, F, G, H, I, J, K, L, M)."""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.memory.state.belief_state import BeliefState
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch
from runtime.simulation.environment import EpisodeEnvironment, create_default_safety_gate
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.step_result import TerminationReason


class TestEpisodeEnvironment(unittest.TestCase):
    """Test suite for canonical EpisodeEnvironment lifecycle."""

    def setUp(self) -> None:
        self.fixtures_dir = (
            Path(__file__).parent.parent.parent
            / "runtime"
            / "simulation"
            / "fixtures"
            / "scenarios"
        )
        self.loader = ScenarioLoader()
        self.s1 = self.loader.load_from_file(self.fixtures_dir / "scenario_s1_straight.json")
        self.s2 = self.loader.load_from_file(self.fixtures_dir / "scenario_s2_decoy.json")
        self.s3 = self.loader.load_from_file(self.fixtures_dir / "scenario_s3_blocked.json")
        self.s4 = self.loader.load_from_file(self.fixtures_dir / "scenario_s4_clean.json")

    def test_c_step_uses_constraint_evaluator(self) -> None:
        """Requirement C: ActionConstraintEvaluator must evaluate belief preconditions."""
        env = EpisodeEnvironment(scenario=self.s1, random_seed=42)

        # Attacker tries ACTION-WEB-001 immediately without scanning
        # ACTION-WEB-001 requires CONFIRMED_FINDING on target
        res = env.step(proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertFalse(res.success)
        self.assertIsNotNone(res.eligibility)
        self.assertFalse(res.eligibility.eligible)
        self.assertFalse(res.terminated)

    def test_d_step_uses_safety_gate(self) -> None:
        """Requirement D: CentralizedSafetyGate must intercept disallowed targets and actions."""
        # Restricted safety gate that permits ACTION-SCAN-001, but NOT ACTION-RECON-001
        restricted_gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            canonical_target_allowlist=frozenset({"lab-dmz-entry"}),
            canonical_action_allowlist=frozenset({"ACTION-SCAN-001"}),
            target_allowlist=frozenset({"lab-dmz-entry"}),
            action_allowlist=frozenset({"ACTION-SCAN-001"}),
            kill_switch=KillSwitch(),
            lab_mode=True,
        )
        env = EpisodeEnvironment(scenario=self.s1, safety_gate=restricted_gate)

        # Action RECON is eligible on lab-dmz-entry, but disallowed by safety gate!
        res = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertFalse(res.success)
        self.assertTrue(any("ACTION_NOT_IN_ALLOWLIST" in r for r in res.reasons))

    def test_e_step_uses_simulation_executor(self) -> None:
        """Requirement E: Steps execute through SimulationExecutor updating TrueState and BeliefState."""
        env = EpisodeEnvironment(scenario=self.s1, random_seed=42)
        res = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(res.success)
        self.assertEqual(len(res.observations), 1)
        self.assertIn("lab-dmz-entry", res.belief_state.known_hosts)

    def test_f_belief_updates_only_from_canonical_observations(self) -> None:
        """Requirement F: BeliefState must mutate ONLY through ingested canonical observations."""
        env = EpisodeEnvironment(scenario=self.s1, random_seed=42)
        belief_t0 = env.get_belief_state()
        self.assertEqual(len(belief_t0.known_services), 0)

        # RECON on lab-dmz-entry emits SERVICE observation
        res = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertEqual(len(res.belief_state.known_services), 1)

        # Ensure provenance points to the observation ID emitted
        obs_id = res.observations[0]["observation_id"]
        service = res.belief_state.known_services[0]
        self.assertIn(obs_id, service["provenance"])

    def test_g_stop_terminates_with_planner_stop(self) -> None:
        """Requirement G: ACTION-STOP-001 must cleanly terminate episode with PLANNER_STOP."""
        env = EpisodeEnvironment(scenario=self.s4, random_seed=42)
        res = env.step(proposal={"action_id": "ACTION-STOP-001"})
        self.assertTrue(res.terminated)
        self.assertFalse(res.truncated)
        self.assertEqual(res.termination_reason, TerminationReason.PLANNER_STOP)
        self.assertEqual(env.termination_reason, TerminationReason.PLANNER_STOP)

        # Further steps should return no-op
        res2 = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(res2.terminated)
        self.assertIn("EPISODE_ALREADY_FINISHED", res2.reasons)

    def test_h_kill_switch_prevents_transitions(self) -> None:
        """Requirement H: Active kill switch must halt episode with SAFETY_KILL_SWITCH."""
        kill_switch = KillSwitch()
        safety_gate = create_default_safety_gate(self.s1, kill_switch=kill_switch)
        env = EpisodeEnvironment(scenario=self.s1, safety_gate=safety_gate)

        # Activate kill switch
        kill_switch.activate()

        res = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertFalse(res.success)
        self.assertTrue(res.terminated)
        self.assertEqual(res.termination_reason, TerminationReason.SAFETY_KILL_SWITCH)
        self.assertEqual(env.step_count, 0)

    def test_i_budget_exhaustion_truncates(self) -> None:
        """Requirement I: Exhausting action budget must truncate episode with BUDGET_EXHAUSTED."""
        env = EpisodeEnvironment(scenario=self.s1, max_budget=2, random_seed=42)

        # Step 1: uses 1 budget
        r1 = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r1.success)
        self.assertFalse(r1.truncated)

        # Step 2: uses 1 budget (remaining reaches 0)
        r2 = env.step(proposal={"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r2.success)
        self.assertTrue(r2.truncated)
        self.assertEqual(r2.termination_reason, TerminationReason.BUDGET_EXHAUSTED)

        # Step 3: rejected because budget exhausted
        r3 = env.step(proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertFalse(r3.success)
        self.assertTrue(r3.truncated)
        self.assertEqual(r3.termination_reason, TerminationReason.BUDGET_EXHAUSTED)

    def test_i_max_steps_truncates(self) -> None:
        """Requirement I (cont): Reaching max_steps must truncate episode with MAX_STEPS."""
        env = EpisodeEnvironment(scenario=self.s1, max_steps=1, max_budget=20, random_seed=42)

        r1 = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r1.success)
        self.assertTrue(r1.truncated)
        self.assertEqual(r1.termination_reason, TerminationReason.MAX_STEPS)

    def test_j_s1_objective_completion(self) -> None:
        """Requirement J: S1 straight progression reaches OBJECTIVE_ACHIEVED."""
        env = EpisodeEnvironment(scenario=self.s1, random_seed=42, max_steps=20, max_budget=20)

        # 1. RECON
        r1 = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r1.success)

        # 2. SCAN
        r2 = env.step(proposal={"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r2.success)

        # 3. FOOTHOLD
        r3 = env.step(proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r3.success)

        # 4. CREDENTIAL ACCESS
        r4 = env.step(proposal={"action_id": "ACTION-AUTH-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r4.success)

        # 5. PIVOT to internal app
        r5 = env.step(
            proposal={
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-internal-app",
                "from_node_id": "lab-dmz-entry",
                "credential_id": "cred-app-svc",
            }
        )
        self.assertTrue(r5.success)

        # 6. OBJECTIVE on database
        r6 = env.step(
            proposal={
                "action_id": "ACTION-FLOW-002",
                "target_id": "lab-db-crown",
                "from_node_id": "lab-internal-app",
                "credential_id": "cred-db-admin",
            }
        )
        self.assertTrue(r6.success)
        self.assertTrue(r6.terminated)
        self.assertFalse(r6.truncated)
        self.assertEqual(r6.termination_reason, TerminationReason.OBJECTIVE_ACHIEVED)

        # Evaluator view reflects objective achievement
        eval_view = env.get_evaluator_view()
        self.assertTrue(eval_view.is_objective_achieved())

    def test_k_s2_decoy_not_labeled_to_planner(self) -> None:
        """Requirement K: Decoy markers and honey-token validity are NOT labeled to Planner."""
        env = EpisodeEnvironment(scenario=self.s2, random_seed=42)

        # 1. RECON on entry
        env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        # 2. FOOTHOLD on entry
        r2 = env.step(proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r2.success)

        # 3. PIVOT to internal app (revealing honey token and db admin credentials)
        r3 = env.step(
            proposal={
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-internal-app",
                "from_node_id": "lab-dmz-entry",
                "credential_id": "cred-app-svc",
            }
        )
        self.assertTrue(r3.success)

        belief = env.get_belief_state()
        # Planner sees credential as valid handle, NOT labeled as honey-token
        for c in belief.known_credentials:
            self.assertNotIn("is_decoy", c)
            self.assertNotEqual(c.get("validity_state"), "HONEY_TOKEN")

        # 4. Pivot into decoy host
        r4 = env.step(
            proposal={
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-decoy-honeypot",
                "from_node_id": "lab-internal-app",
                "credential_id": "cred-honey-token",
            }
        )
        self.assertTrue(r4.success)

        # Attacker belief does NOT have decoy marker on host
        self.assertIn("lab-decoy-honeypot", env.get_belief_state().known_hosts)
        host_info = env.get_belief_state().known_hosts["lab-decoy-honeypot"]
        self.assertNotIn("is_decoy", host_info)

        # True state defender alerted / contained
        eval_view = env.get_evaluator_view()
        self.assertIn(eval_view.get_detection_state(), ("ALERTED", "CONTAINED"))

    def test_l_s3_blocked_route_remains_recoverable(self) -> None:
        """Requirement L: Blocked firewall route fails safely; replan via alternate route succeeds."""
        env = EpisodeEnvironment(scenario=self.s3, random_seed=42)

        # RECON, FOOTHOLD on entry
        env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        r_fh = env.step(proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r_fh.success)

        # Pivot to internal app
        r_piv = env.step(
            proposal={
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-internal-app",
                "from_node_id": "lab-dmz-entry",
                "credential_id": "cred-app-svc",
            }
        )
        self.assertTrue(r_piv.success)

        # Attacker tries direct pivot to crown DB (blocked by firewall in S3)
        r_fail = env.step(
            proposal={
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-db-crown",
                "from_node_id": "lab-internal-app",
                "credential_id": "cred-db-admin",
            }
        )
        self.assertFalse(r_fail.success)
        self.assertFalse(r_fail.terminated)  # Episode continues!

        # Replan: Pivot via jump-box
        r_jump = env.step(
            proposal={
                "action_id": "ACTION-FLOW-001",
                "target_id": "lab-jump-box",
                "from_node_id": "lab-internal-app",
                "credential_id": "cred-jump-admin",
            }
        )
        self.assertTrue(r_jump.success)

        # Jump-box to crown database
        r_crown = env.step(
            proposal={
                "action_id": "ACTION-FLOW-002",
                "target_id": "lab-db-crown",
                "from_node_id": "lab-jump-box",
                "credential_id": "cred-db-admin",
            }
        )
        self.assertTrue(r_crown.success)
        self.assertTrue(r_crown.terminated)
        self.assertEqual(r_crown.termination_reason, TerminationReason.OBJECTIVE_ACHIEVED)

    def test_m_s4_clean_control_no_objective(self) -> None:
        """Requirement M: S4 clean control system cannot reach objective; STOP terminates cleanly."""
        env = EpisodeEnvironment(scenario=self.s4, random_seed=42)

        # Probe entry
        r1 = env.step(proposal={"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r1.success)

        # Scan reveals no exploitable finding
        r2 = env.step(proposal={"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry"})
        self.assertTrue(r2.success)
        self.assertEqual(len(r2.belief_state.confirmed_findings), 0)

        # Attacker attempts foothold anyway -> fails
        r3 = env.step(proposal={"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        self.assertFalse(r3.success)

        # Clean STOP
        r_stop = env.step(proposal={"action_id": "ACTION-STOP-001"})
        self.assertTrue(r_stop.terminated)
        self.assertEqual(r_stop.termination_reason, TerminationReason.PLANNER_STOP)

        eval_view = env.get_evaluator_view()
        self.assertFalse(eval_view.is_objective_achieved())


if __name__ == "__main__":
    unittest.main()
