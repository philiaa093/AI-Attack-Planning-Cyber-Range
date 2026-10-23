"""Contracts tests for True State Model (RT-04A).

Verifies Draft 2020-12 closed schema conformance, model distinction from Belief State,
fail-closed rejection of unknown properties, and deterministic serialization.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.validation.validate_scaffold import validate_shape, load_json
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.true_state import (
    TrueState,
    NodeTrueState,
    SimulatedSession,
    CredentialTruth,
    ReachabilityEdge,
    ObjectiveTruth,
    DefenderState,
)
from agent.memory.state.belief_state import project_belief_state


ROOT = Path(__file__).resolve().parents[2]
TRUE_STATE_SCHEMA_PATH = ROOT / "runtime/simulation/contracts/true-state.schema.json"
FIXTURES_DIR = ROOT / "runtime/simulation/fixtures/scenarios"


class TrueStateContractTests(unittest.TestCase):
    """Test TrueState model, schema validation, and separation from Belief State."""

    def setUp(self) -> None:
        errors: list[str] = []
        self.schema = load_json(TRUE_STATE_SCHEMA_PATH, errors)
        self.assertEqual(errors, [])
        self.assertIsInstance(self.schema, dict)
        self.loader = ScenarioLoader()

    def test_true_state_schema_is_closed_draft_2020_12_object(self) -> None:
        """Requirement: true-state.schema.json is a closed Draft 2020-12 object."""
        self.assertEqual(self.schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema.get("type"), "object")
        self.assertIs(self.schema.get("additionalProperties"), False)
        self.assertTrue(len(self.schema.get("required", [])) >= 9)

    def test_initial_true_state_from_s1_validates_schema(self) -> None:
        """Requirement C: Initial TrueState derived from S1 scenario validates schema cleanly."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        true_state = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)
        state_dict = true_state.to_dict()

        errors = validate_shape(state_dict, self.schema)
        self.assertEqual(errors, [])
        self.assertEqual(true_state.current_step, 0)
        self.assertEqual(true_state.scenario_id, "SCN-SIM-001")
        self.assertEqual(true_state.defender_state.detection_state, "QUIET")
        self.assertFalse(true_state.is_objective_achieved())

    def test_true_state_is_distinct_from_belief_state(self) -> None:
        """Requirement C: TrueState model does not inherit from or subclass BeliefState."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        true_state = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)

        # Belief State projection produces a dict conforming to state.schema.json ($defs/belief_state)
        belief_state = project_belief_state([])

        self.assertIsInstance(true_state, TrueState)
        self.assertNotIsInstance(true_state, dict)
        self.assertIsInstance(belief_state, dict)

        # TrueState must not be a subclass of any planner/belief class
        self.assertNotIn("BeliefState", [b.__name__ for b in TrueState.__mro__])

        # Verify key differences in state representations
        true_dict = true_state.to_dict()
        # True state has node_states, defender_state, objective_truth
        self.assertIn("node_states", true_dict)
        self.assertIn("defender_state", true_dict)
        self.assertIn("objective_truth", true_dict)
        # Belief state does not have hidden defender_state or true objective_truth
        self.assertNotIn("defender_state", belief_state)
        self.assertNotIn("objective_truth", belief_state)

    def test_true_state_rejects_unknown_root_property(self) -> None:
        """Requirement B: Unknown root properties in TrueState fail schema validation."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        true_state = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)
        state_dict = true_state.to_dict()
        state_dict["unauthorized_ground_truth"] = True

        errors = validate_shape(state_dict, self.schema)
        self.assertTrue(any("unauthorized_ground_truth" in e or "unknown property" in e for e in errors))

    def test_true_state_rejects_invalid_session_state(self) -> None:
        """Requirement B: Invalid session states fail validation fail-closed."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        true_state = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)
        state_dict = true_state.to_dict()
        state_dict["active_sessions"]["sess-bad"] = {
            "session_id": "sess-bad",
            "node_id": "lab-dmz-entry",
            "access_level": "USER",
            "established_at_step": 1,
            "session_state": "UNRECOGNIZED_STATE",
        }

        # Model instantiation fails closed
        with self.assertRaises(ValueError) as ctx:
            TrueState.from_dict(state_dict)
        self.assertIn("Invalid session_state", str(ctx.exception))

    def test_true_state_rejects_negative_step_and_noise(self) -> None:
        """Requirement B: Negative current_step fails schema validation."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        true_state = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)
        state_dict = true_state.to_dict()
        state_dict["current_step"] = -1

        errors = validate_shape(state_dict, self.schema)
        self.assertTrue(any("below minimum" in e for e in errors))

    def test_true_state_deterministic_serialization(self) -> None:
        """Requirement K: Same TrueState serializes bit-for-bit identically."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        true_state = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)

        hashes = {true_state.deterministic_hash() for _ in range(10)}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len(next(iter(hashes))), 64)

    def test_true_state_from_dict_roundtrip(self) -> None:
        """Requirement K: TrueState roundtrip from dict preserves exact data."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        original = scenario.create_initial_true_state(run_id="RUN-TEST-001", seed=42)
        state_dict = original.to_dict()
        restored = TrueState.from_dict(state_dict)

        self.assertEqual(original.deterministic_hash(), restored.deterministic_hash())
        self.assertEqual(original.scenario_id, restored.scenario_id)
        self.assertEqual(len(original.node_states), len(restored.node_states))


if __name__ == "__main__":
    unittest.main()
