"""Unit tests for SimulationGymEnv Gymnasium adapter (RT-04C Requirements N, O, P)."""
from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from gymnasium.utils.env_checker import check_env

from agent.memory.state.belief_state import BeliefState
from runtime.simulation.gym_adapter import SimulationGymEnv, encode_belief_state_features
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.step_result import TerminationReason


class TestSimulationGymEnv(unittest.TestCase):
    """Test suite for Farama Gymnasium adapter wrapping EpisodeEnvironment."""

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
        self.s4 = self.loader.load_from_file(self.fixtures_dir / "scenario_s4_clean.json")

    def test_gym_env_checker_conformance(self) -> None:
        """Farama Gymnasium env_checker must validate SimulationGymEnv without errors."""
        env = SimulationGymEnv(scenario=self.s1, random_seed=42)
        # Verify check_env passes
        check_env(env, skip_render_check=True)
        env.close()

    def test_n_gym_observation_contains_no_true_state(self) -> None:
        """Requirement N: Observation must be pure numeric float32 vector derived from BeliefState."""
        env = SimulationGymEnv(scenario=self.s1, random_seed=42)
        obs, info = env.reset(seed=42)

        self.assertIsInstance(obs, np.ndarray)
        self.assertEqual(obs.dtype, np.float32)
        self.assertEqual(obs.shape, (16,))
        self.assertTrue(env.observation_space.contains(obs))

        # Check step returns
        obs2, reward, terminated, truncated, info2 = env.step(0)
        self.assertIsInstance(obs2, np.ndarray)
        self.assertTrue(env.observation_space.contains(obs2))

    def test_o_gym_info_contains_no_hidden_diagnostics_by_default(self) -> None:
        """Requirement O: Gym info dict must not leak TrueState, hidden topology, or hidden secrets."""
        env = SimulationGymEnv(scenario=self.s1, random_seed=42)
        obs, info = env.reset(seed=42)

        forbidden_keys = (
            "true_state",
            "hidden_nodes",
            "hidden_topology",
            "hidden_credentials",
            "detection_model",
            "defender_state",
            "ground_truth",
            "vulnerabilities",
            "is_decoy",
            "is_blocked",
        )

        for k in forbidden_keys:
            self.assertNotIn(k, info)

        obs2, reward, terminated, truncated, step_info = env.step(0)
        for k in forbidden_keys:
            self.assertNotIn(k, step_info)

    def test_p_feature_encoding_derives_only_from_belief(self) -> None:
        """Requirement P: Feature encoding derives 100% from BeliefState."""
        # Minimal dummy belief
        dummy_data = {
            "known_hosts": {"lab-dmz-entry": {"access_level": "FOOTHOLD"}},
            "known_services": [{"host": "lab-dmz-entry", "port": 80, "protocol": "HTTP"}],
            "known_endpoints": [],
            "candidate_findings": [],
            "confirmed_findings": [],
            "access_state": {"lab-dmz-entry": "FOOTHOLD"},
            "known_credentials": [],
            "sessions": [{"session_id": "s1", "target_id": "lab-dmz-entry", "state": "ACTIVE"}],
            "observed_reachability": [],
            "detection_signals": [],
            "objective_status": {},
            "hypotheses": [],
            "provenance_refs": [],
        }
        belief = BeliefState(dummy_data)
        features = encode_belief_state_features(belief_state=belief)

        self.assertEqual(features.shape, (16,))
        self.assertEqual(features[0], 1.0)  # 1 known host
        self.assertEqual(features[1], 1.0)  # 1 known service
        self.assertEqual(features[7], 1.0)  # 1 active session
        self.assertEqual(features[10], 1.0)  # max_access FOOTHOLD (rank 1.0)

    def test_dynamic_action_masking_and_discrete_stepping(self) -> None:
        """Gym action_mask correctly identifies valid discrete proposals."""
        env = SimulationGymEnv(scenario=self.s1, max_actions=32, random_seed=42)
        obs, info = env.reset(seed=42)

        mask = info["action_mask"]
        self.assertEqual(mask.shape, (32,))
        self.assertEqual(mask.dtype, np.int8)

        # Number of 1s in mask must match admissible_actions_count
        valid_indices = int(np.sum(mask))
        self.assertEqual(valid_indices, info["admissible_actions_count"])
        self.assertGreater(valid_indices, 0)

        # Step valid index 0
        obs, reward, terminated, truncated, step_info = env.step(0)
        self.assertTrue(step_info["success"])

        # Step out-of-bounds masked index (e.g. 31)
        obs_bad, r_bad, term_bad, trunc_bad, info_bad = env.step(31)
        self.assertFalse(term_bad)
        self.assertFalse(trunc_bad)
        self.assertEqual(r_bad, -0.5)
        self.assertEqual(info_bad["rejection_reason"], "ACTION_INDEX_OUT_OF_BOUNDS_OR_MASKED")

    def test_structured_proposal_stepping(self) -> None:
        """SimulationGymEnv accepts structured dict proposals directly."""
        env = SimulationGymEnv(scenario=self.s1, random_seed=42)
        env.reset(seed=42)

        # Structured proposal
        obs, reward, terminated, truncated, info = env.step(
            {"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"}
        )
        self.assertTrue(info["success"])
        self.assertEqual(info["action_id"], "ACTION-RECON-001")
        self.assertEqual(info["target_id"], "lab-dmz-entry")

    def test_provisional_reward_and_evaluator_view(self) -> None:
        """Provisional mechanical reward signals and evaluator view separation."""
        env = SimulationGymEnv(scenario=self.s4, random_seed=42)
        env.reset(seed=42)

        # Clean STOP
        obs, reward, terminated, truncated, info = env.step({"action_id": "ACTION-STOP-001"})
        self.assertTrue(terminated)
        self.assertEqual(info["termination_reason"], "PLANNER_STOP")
        self.assertEqual(reward, 0.0)

        # Evaluator view is accessible separately
        eval_view = env.get_evaluator_view()
        self.assertFalse(eval_view.is_objective_achieved())

    def test_e_hidden_target_count_and_ids_do_not_leak_through_action_mask(self) -> None:
        """Test E: Hidden target count and IDs cannot be inferred from Gym action mapping or mask."""
        # S1 has 3 nodes, S2 has 4 nodes, S4 has 2 nodes
        self.assertEqual(len(self.s1.hidden_nodes), 3)
        self.assertEqual(len(self.s2.hidden_nodes), 4)
        self.assertEqual(len(self.s4.hidden_nodes), 2)

        env1 = SimulationGymEnv(scenario=self.s1, random_seed=42)
        env2 = SimulationGymEnv(scenario=self.s2, random_seed=42)
        env4 = SimulationGymEnv(scenario=self.s4, random_seed=42)

        _, info1 = env1.reset(seed=42)
        _, info2 = env2.reset(seed=42)
        _, info4 = env4.reset(seed=42)

        mask1 = info1["action_mask"]
        mask2 = info2["action_mask"]
        mask4 = info4["action_mask"]

        # Hard Invariant: At t=0, visible targets are identical (only entry seed lab-dmz-entry)
        # Therefore, action mapping and mask MUST NOT leak differing hidden node counts
        self.assertEqual(len(env1._current_admissible_proposals), len(env2._current_admissible_proposals))
        self.assertEqual(len(env1._current_admissible_proposals), len(env4._current_admissible_proposals))
        self.assertEqual(int(np.sum(mask1)), int(np.sum(mask2)))
        self.assertEqual(int(np.sum(mask1)), int(np.sum(mask4)))

        # Verify NO hidden target appears in any admissible proposal at t=0
        hidden_targets = {"lab-internal-app", "lab-db-crown", "lab-decoy-honeypot", "lab-internal-isolated"}
        for env in (env1, env2, env4):
            for prop in env._current_admissible_proposals:
                tgt = str(prop.get("target_id") or "")
                for ht in hidden_targets:
                    self.assertNotIn(ht, tgt, f"Hidden target {ht} leaked into Gym proposal mapping: {prop}")

        env1.close()
        env2.close()
        env4.close()


if __name__ == "__main__":
    unittest.main()
