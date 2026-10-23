"""Unit tests for ScenarioLoader and semantic integrity validation (RT-04A)."""
from __future__ import annotations

import copy
from pathlib import Path
import unittest

from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.scenario import HiddenScenario


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "runtime/simulation/fixtures/scenarios"


class ScenarioLoaderTests(unittest.TestCase):
    """Test scenario loader and fail-closed semantic integrity checks."""

    def setUp(self) -> None:
        self.loader = ScenarioLoader()

    def test_load_all_four_scenarios_succeeds(self) -> None:
        """Verify loader successfully loads S1, S2, S3, S4."""
        for name in ("scenario_s1_straight.json", "scenario_s2_decoy.json", "scenario_s3_blocked.json", "scenario_s4_clean.json"):
            scenario = self.loader.load_from_file(FIXTURES_DIR / name)
            self.assertIsInstance(scenario, HiddenScenario)
            self.assertTrue(len(scenario.hidden_nodes) >= 2)
            self.assertEqual(scenario.get_entry_node().node_id, scenario.entry_seed)

    def test_missing_file_raises_file_not_found(self) -> None:
        """Non-existent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.loader.load_from_file(FIXTURES_DIR / "non_existent_scenario.json")

    def test_entry_seed_missing_from_nodes_fails_closed(self) -> None:
        """Semantic check: entry_seed not in hidden_nodes raises ValueError."""
        data = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json").to_dict()
        data["entry_seed"] = "node-ghost-nonexistent"
        with self.assertRaises(ValueError) as ctx:
            self.loader.load_from_dict(data)
        self.assertIn("entry_seed 'node-ghost-nonexistent' does not exist", str(ctx.exception))

    def test_objective_target_missing_from_nodes_fails_closed(self) -> None:
        """Semantic check: objective target not in hidden_nodes raises ValueError."""
        data = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json").to_dict()
        data["objective"]["target_node_id"] = "node-unreachable-phantom"
        with self.assertRaises(ValueError) as ctx:
            self.loader.load_from_dict(data)
        self.assertIn("target_node_id 'node-unreachable-phantom' does not exist", str(ctx.exception))

    def test_topology_edge_missing_node_fails_closed(self) -> None:
        """Semantic check: edge references non-existent node fails closed."""
        data = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json").to_dict()
        data["hidden_topology"]["edges"][0]["target"] = "node-disconnected"
        with self.assertRaises(ValueError) as ctx:
            self.loader.load_from_dict(data)
        self.assertIn("node-disconnected", str(ctx.exception))

    def test_duplicate_node_ids_fails_closed(self) -> None:
        """Semantic check: duplicate node_id in hidden_nodes fails closed."""
        data = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json").to_dict()
        duplicate_node = copy.deepcopy(data["hidden_nodes"][0])
        data["hidden_nodes"].append(duplicate_node)
        with self.assertRaises(ValueError) as ctx:
            self.loader.load_from_dict(data)
        self.assertIn("Duplicate node_id", str(ctx.exception))

    def test_initial_true_state_creation_and_reproducibility(self) -> None:
        """Requirement K & 11: Initial TrueState creation is deterministic across seeds."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        state1 = scenario.create_initial_true_state(run_id="RUN-REPLAY-001", seed=100)
        state2 = scenario.create_initial_true_state(run_id="RUN-REPLAY-001", seed=100)
        self.assertEqual(state1.deterministic_hash(), state2.deterministic_hash())

        # State at t=0 has no actions
        self.assertEqual(len(state1.action_history), 0)
        # Entry node has initial state
        self.assertIn("lab-dmz-entry", state1.node_states)


if __name__ == "__main__":
    unittest.main()
