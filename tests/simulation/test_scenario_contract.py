"""Contracts tests for Hidden Simulator Scenario Model (RT-04A).

Verifies Draft 2020-12 closed schema conformance, validation of S1–S4 fixtures,
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
from runtime.simulation.models.scenario import HiddenScenario


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "runtime/simulation/contracts/scenario.schema.json"
FIXTURES_DIR = ROOT / "runtime/simulation/fixtures/scenarios"


class ScenarioContractTests(unittest.TestCase):
    """Test scenario schema structure, validation of S1-S4 fixtures, and closed object constraints."""

    def setUp(self) -> None:
        errors: list[str] = []
        self.schema = load_json(SCHEMA_PATH, errors)
        self.assertEqual(errors, [])
        self.assertIsInstance(self.schema, dict)
        self.loader = ScenarioLoader(SCHEMA_PATH)

    def test_schema_is_closed_draft_2020_12_object(self) -> None:
        """Requirement: Schema itself must be closed Draft 2020-12 object."""
        self.assertEqual(self.schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema.get("type"), "object")
        self.assertIs(self.schema.get("additionalProperties"), False)
        self.assertTrue(len(self.schema.get("required", [])) >= 10)

    def test_s1_straight_scenario_validates_cleanly(self) -> None:
        """Requirement A: S1 Straight fixture passes schema validation with zero errors."""
        s1_path = FIXTURES_DIR / "scenario_s1_straight.json"
        self.assertTrue(s1_path.is_file(), f"Missing S1 fixture: {s1_path}")
        errors: list[str] = []
        data = load_json(s1_path, errors)
        self.assertEqual(errors, [])
        shape_errors = validate_shape(data, self.schema)
        self.assertEqual(shape_errors, [])
        scenario = self.loader.load_from_file(s1_path)
        self.assertEqual(scenario.scenario_id, "SCN-SIM-001")
        self.assertEqual(scenario.entry_seed, "lab-dmz-entry")
        self.assertEqual(len(scenario.hidden_nodes), 3)

    def test_s2_decoy_scenario_validates_cleanly(self) -> None:
        """Requirement A: S2 Decoy fixture passes schema validation with zero errors."""
        s2_path = FIXTURES_DIR / "scenario_s2_decoy.json"
        self.assertTrue(s2_path.is_file(), f"Missing S2 fixture: {s2_path}")
        errors: list[str] = []
        data = load_json(s2_path, errors)
        self.assertEqual(errors, [])
        shape_errors = validate_shape(data, self.schema)
        self.assertEqual(shape_errors, [])
        scenario = self.loader.load_from_file(s2_path)
        self.assertEqual(scenario.scenario_id, "SCN-SIM-002")
        decoy_nodes = [n for n in scenario.hidden_nodes if n.is_decoy]
        self.assertEqual(len(decoy_nodes), 1)
        self.assertEqual(decoy_nodes[0].node_id, "lab-decoy-honeypot")

    def test_s3_blocked_replan_scenario_validates_cleanly(self) -> None:
        """Requirement A: S3 Blocked fixture passes schema validation with zero errors."""
        s3_path = FIXTURES_DIR / "scenario_s3_blocked.json"
        self.assertTrue(s3_path.is_file(), f"Missing S3 fixture: {s3_path}")
        errors: list[str] = []
        data = load_json(s3_path, errors)
        self.assertEqual(errors, [])
        shape_errors = validate_shape(data, self.schema)
        self.assertEqual(shape_errors, [])
        scenario = self.loader.load_from_file(s3_path)
        self.assertEqual(scenario.scenario_id, "SCN-SIM-003")
        blocked_edges = [e for e in scenario.hidden_topology.edges if e.is_blocked]
        self.assertEqual(len(blocked_edges), 1)
        self.assertEqual(blocked_edges[0].edge_id, "edge-app-to-db-blocked")

    def test_s4_clean_control_scenario_validates_cleanly(self) -> None:
        """Requirement A: S4 Clean Control fixture passes schema validation with zero errors."""
        s4_path = FIXTURES_DIR / "scenario_s4_clean.json"
        self.assertTrue(s4_path.is_file(), f"Missing S4 fixture: {s4_path}")
        errors: list[str] = []
        data = load_json(s4_path, errors)
        self.assertEqual(errors, [])
        shape_errors = validate_shape(data, self.schema)
        self.assertEqual(shape_errors, [])
        scenario = self.loader.load_from_file(s4_path)
        self.assertEqual(scenario.scenario_id, "SCN-SIM-004")
        # Entry node has 0 vulnerabilities
        entry = scenario.get_entry_node()
        self.assertEqual(len(entry.vulnerabilities), 0)

    def test_schema_rejects_unknown_root_property(self) -> None:
        """Requirement B: Unknown root properties fail validation (closed schema)."""
        data = load_json(FIXTURES_DIR / "scenario_s1_straight.json", [])
        data["unauthorized_property"] = "leaked_eval"
        errors = validate_shape(data, self.schema)
        self.assertTrue(any("unauthorized_property" in e or "unknown property" in e for e in errors))

    def test_schema_rejects_unknown_node_property(self) -> None:
        """Requirement B: Unknown node properties fail validation (closed node schema)."""
        data = load_json(FIXTURES_DIR / "scenario_s1_straight.json", [])
        data["hidden_nodes"][0]["attacker_backdoor"] = "root_shell"
        errors = validate_shape(data, self.schema)
        self.assertTrue(any("attacker_backdoor" in e or "unknown property" in e for e in errors))

    def test_schema_rejects_invalid_node_kind(self) -> None:
        """Requirement B: Invalid node kinds fail closed."""
        data = load_json(FIXTURES_DIR / "scenario_s1_straight.json", [])
        data["hidden_nodes"][0]["node_kind"] = "INTERNET_PUBLIC_CLOUD"
        errors = validate_shape(data, self.schema)
        self.assertTrue(len(errors) > 0)

    def test_schema_rejects_negative_noise(self) -> None:
        """Requirement B: Negative noise values fail closed."""
        data = load_json(FIXTURES_DIR / "scenario_s1_straight.json", [])
        data["transitions"][0]["noise_delta"] = -5.0
        errors = validate_shape(data, self.schema)
        self.assertTrue(any("below minimum" in e for e in errors))

    def test_schema_rejects_probability_above_one(self) -> None:
        """Requirement B: Transition probabilities > 1.0 fail closed."""
        data = load_json(FIXTURES_DIR / "scenario_s1_straight.json", [])
        data["transitions"][0]["success_probability"] = 1.5
        errors = validate_shape(data, self.schema)
        self.assertTrue(any("above maximum" in e for e in errors))

    def test_deterministic_scenario_serialization(self) -> None:
        """Requirement K: Same scenario representation serializes bit-for-bit identically."""
        scenario = self.loader.load_from_file(FIXTURES_DIR / "scenario_s1_straight.json")
        hashes = {scenario.deterministic_hash() for _ in range(10)}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len(next(iter(hashes))), 64)


if __name__ == "__main__":
    unittest.main()
