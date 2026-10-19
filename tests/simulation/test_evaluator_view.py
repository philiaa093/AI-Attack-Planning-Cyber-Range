"""Tests for ScenarioEvaluationView (RT-04A).

Verifies the read-only contract for evaluation engines and scoring harnesses.
"""
from __future__ import annotations

from pathlib import Path
import unittest

from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.evaluator_view import ScenarioEvaluationView
from runtime.simulation.models.true_state import SimulatorActionRecord
from agent.memory.state.belief_state import project_belief_state


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "runtime/simulation/fixtures/scenarios"


class ScenarioEvaluationViewTests(unittest.TestCase):
    """Test read-only evaluation view contract."""

    def setUp(self) -> None:
        self.loader = ScenarioLoader()
        self.scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        self.true_state = self.scenario.create_initial_true_state(run_id="RUN-EVAL-TEST", seed=42)

    def test_evaluator_view_read_only_access(self) -> None:
        """Verify evaluation view exposes read-only queries accurately."""
        # Belief state where agent only knows about lab-dmz-entry
        mock_facts = [
            {
                "fact_id": "fact-host-01",
                "fact_type": "HOST",
                "subject": "lab-dmz-entry",
                "value": {"host": "lab-dmz-entry", "ip": "10.0.1.10", "access_level": "NONE"},
                "confidence": 1.0,
                "source_observation_id": "obs-001",
            }
        ]
        belief = project_belief_state(mock_facts)

        actions = (
            SimulatorActionRecord(
                step=1,
                action_id="ACTION-RECON-001",
                target_node_id="lab-dmz-entry",
                success=True,
                noise_delta=0.5,
                timestamp_utc="2026-10-17T12:00:00Z",
            ),
        )

        view = ScenarioEvaluationView(
            true_state=self.true_state,
            belief_state=belief,
            action_history=actions,
        )

        self.assertFalse(view.is_objective_achieved())
        self.assertEqual(view.get_detection_state(), "QUIET")
        self.assertEqual(view.get_accumulated_noise(), 0.0)
        self.assertEqual(view.get_reachability_edges_count(), 2)

        known_in_belief = view.get_discovered_node_ids_in_belief()
        self.assertIn("lab-dmz-entry", known_in_belief)
        self.assertNotIn("lab-internal-app", known_in_belief)
        self.assertNotIn("lab-db-crown", known_in_belief)

        summary = view.get_alignment_summary()
        self.assertEqual(summary["scenario_id"], "SCN-SIM-001")
        self.assertEqual(summary["total_actions_taken"], 1)
        self.assertEqual(summary["belief_known_count"], 1)


if __name__ == "__main__":
    unittest.main()
