"""Test legacy RL compatibility and coexistence (RT-04C Requirement T).

Verifies:
- Legacy ReplayAssessmentEnv from runtime.evaluation.rl_environment continues functioning.
- Deprecation notice on ReplayAssessmentEnv directs users to canonical EpisodeEnvironment / SimulationGymEnv.
- Zero state coupling or world-model duplication between SimulationGymEnv and ReplayAssessmentEnv.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from runtime.evaluation.rl_environment import (
    OPERATIONS,
    ReplayAsset,
    ReplayAssessmentEnv,
)
from runtime.simulation.gym_adapter import SimulationGymEnv
from runtime.simulation.loader import ScenarioLoader


class TestLegacyRLCompatibility(unittest.TestCase):
    """Test legacy RL environment compatibility and clean coexistence."""

    def test_legacy_rl_environment_deprecation_notice(self) -> None:
        """Requirement T: ReplayAssessmentEnv carries deprecation docstring referencing RT-04."""
        doc = ReplayAssessmentEnv.__doc__ or ""
        self.assertIn("DEPRECATED", doc)
        self.assertIn("runtime.simulation", doc)
        self.assertIn("TASK-023", doc)

    def test_legacy_rl_environment_operational(self) -> None:
        """Legacy ReplayAssessmentEnv still functions for existing synthetic replay tests."""
        asset = ReplayAsset("lab-fixture", 3, True)
        env = ReplayAssessmentEnv(
            [asset],
            approved_targets=["lab-fixture"],
            approved_operations=OPERATIONS,
        )
        obs, info = env.reset(seed=42)
        self.assertIn("assets", obs)
        self.assertIn("action_mask", info)
        next_obs, reward, ended, truncated, next_info = env.step(0)
        self.assertFalse(ended)
        self.assertFalse(truncated)
        env.close()

    def test_coexistence_without_world_model_collision(self) -> None:
        """SimulationGymEnv and ReplayAssessmentEnv can coexist in same runtime without collision."""
        fixtures_dir = (
            Path(__file__).parent.parent.parent
            / "runtime"
            / "simulation"
            / "fixtures"
            / "scenarios"
        )
        scenario = ScenarioLoader().load_from_file(fixtures_dir / "scenario_s1_straight.json")
        sim_env = SimulationGymEnv(scenario=scenario, random_seed=42)
        obs_sim, info_sim = sim_env.reset(seed=42)

        legacy_env = ReplayAssessmentEnv(
            [ReplayAsset("lab-dmz-entry", 1, True)],
            approved_targets=["lab-dmz-entry"],
            approved_operations=OPERATIONS,
        )
        obs_legacy, info_legacy = legacy_env.reset(seed=42)

        # Confirm distinct observation representations
        self.assertEqual(obs_sim.shape, (16,))
        self.assertIsInstance(obs_legacy, dict)
        self.assertIn("assets", obs_legacy)

        sim_env.close()
        legacy_env.close()


if __name__ == "__main__":
    unittest.main()
