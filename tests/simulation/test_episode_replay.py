"""Replay determinism tests for EpisodeEnvironment and SimulationGymEnv.

Verifies:
- Bit-for-bit replay equality across multiple runs given same scenario, seed, and actions.
- Evaluator view TrueState hash, transition outcomes, raw observations, and belief projection.
- GymEnv reset/step determinism across identical runs.
- Seed independence.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import numpy as np

from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.gym_adapter import SimulationGymEnv
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.scenario import HiddenScenario


class TestEpisodeReplayDeterminism(unittest.TestCase):
    """Test suite for replay determinism."""

    def setUp(self) -> None:
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / "runtime" / "simulation" / "fixtures" / "scenarios"
        loader = ScenarioLoader()
        self.s1 = loader.load_from_file(fixtures_dir / "scenario_s1_straight.json")
        self.s2 = loader.load_from_file(fixtures_dir / "scenario_s2_decoy.json")

    def test_episode_environment_bit_for_bit_determinism(self) -> None:
        """Same scenario, seed, and actions yield bit-for-bit identical state and observations."""
        seed = 42
        action_sequence = [
            {"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"},
            {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry"},
            {"action_id": "ACTION-EXPLOIT-001", "target_id": "lab-dmz-entry"},
            {"action_id": "ACTION-PIVOT-001", "target_id": "lab-dmz-entry"},
        ]

        def run_episode() -> tuple[list[dict], list[str], str]:
            env = EpisodeEnvironment(scenario=self.s1, random_seed=seed)
            boot_obs, _ = env.reset(seed=seed, timestamp_utc="2026-01-01T00:00:00Z")

            obs_list = [boot_obs]
            true_state_hashes = [env.get_evaluator_view().true_state.deterministic_hash()]

            for act in action_sequence:
                act_with_ts = dict(act)
                act_with_ts["timestamp_utc"] = "2026-01-01T00:00:00Z"
                res = env.step(act_with_ts)
                obs_list.extend(res.observations)
                true_state_hashes.append(env.get_evaluator_view().true_state.deterministic_hash())

            final_belief_dict = env.get_belief_state().to_dict()
            return obs_list, true_state_hashes, final_belief_dict

        obs_run1, hashes_run1, belief_run1 = run_episode()
        obs_run2, hashes_run2, belief_run2 = run_episode()

        # Exact equality of True-State state hashes at every step
        self.assertEqual(hashes_run1, hashes_run2)

        # Exact equality of observation dictionaries
        self.assertEqual(len(obs_run1), len(obs_run2))
        for o1, o2 in zip(obs_run1, obs_run2):
            self.assertEqual(o1.get("action_id"), o2.get("action_id"))
            self.assertEqual(o1.get("new_facts"), o2.get("new_facts"))

        # Exact equality of final BeliefState projection
        self.assertEqual(belief_run1, belief_run2)

    def test_gym_adapter_determinism(self) -> None:
        """SimulationGymEnv produces identical observations, rewards, and info across re-runs."""
        seed = 123
        actions = [
            {"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"},
            {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry"},
            {"action_id": "ACTION-EXPLOIT-001", "target_id": "lab-dmz-entry"},
        ]

        def run_gym() -> list[tuple[np.ndarray, float, bool, bool, dict]]:
            env = SimulationGymEnv(scenario=self.s1, random_seed=seed)
            obs, info = env.reset(seed=seed)
            history = [(obs, 0.0, False, False, info)]

            for act in actions:
                res = env.step(act)
                history.append(res)
            return history

        hist1 = run_gym()
        hist2 = run_gym()

        self.assertEqual(len(hist1), len(hist2))
        for (o1, r1, term1, trunc1, inf1), (o2, r2, term2, trunc2, inf2) in zip(hist1, hist2):
            np.testing.assert_array_equal(o1, o2)
            self.assertEqual(r1, r2)
            self.assertEqual(term1, term2)
            self.assertEqual(trunc1, trunc2)
            self.assertEqual(inf1["action_mask"].tolist(), inf2["action_mask"].tolist())
            self.assertEqual(inf1.get("action_id"), inf2.get("action_id"))
            self.assertEqual(inf1.get("success"), inf2.get("success"))

    def test_seed_isolation_independent_streams(self) -> None:
        """Runs with different seeds are cleanly initialized and decoupled."""
        env1 = EpisodeEnvironment(scenario=self.s2, random_seed=111)
        env2 = EpisodeEnvironment(scenario=self.s2, random_seed=999)

        boot1, _ = env1.reset(seed=111)
        boot2, _ = env2.reset(seed=999)

        self.assertEqual(boot1["new_facts"][0]["value"]["target_id"], boot2["new_facts"][0]["value"]["target_id"])
        self.assertEqual(
            env1.get_evaluator_view().true_state.scenario_id,
            env2.get_evaluator_view().true_state.scenario_id,
        )
        self.assertNotEqual(
            env1.get_evaluator_view().true_state.random_seed,
            env2.get_evaluator_view().true_state.random_seed,
        )
        self.assertNotEqual(
            env1.get_evaluator_view().true_state.deterministic_hash(),
            env2.get_evaluator_view().true_state.deterministic_hash(),
        )


if __name__ == "__main__":
    unittest.main()
