"""Contract tests for RT-03A — Generic TTP Action Contract.

Validates:
  A. Generic Enterprise action fixtures validate schema.
  B. Legacy action fixtures continue to validate or are clearly classified for compatibility.
  D. Preconditions are structured data, not arbitrary code/eval.
  E. Costs are non-negative.
  F. Operational noise cost has bounded numeric semantics.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from actions.catalog.action_registry import (
    ActionDefinition,
    get_action_registry,
)
from scripts.validation.validate_scaffold import ROOT, validate_shape

ACTION_SCHEMA_PATH = ROOT / "agent/planner/contracts/action.schema.json"
CATALOG_PATH = ROOT / "actions/catalog/action-catalog.json"


class ActionContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(ACTION_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.registry = get_action_registry(CATALOG_PATH)

    def test_action_schema_is_closed_draft_2020_12_object(self):
        """Schema itself must be closed Draft 2020-12 root object."""
        self.assertEqual(self.schema.get("$schema"), "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema.get("type"), "object")
        self.assertIs(self.schema.get("additionalProperties"), False)
        # All $defs must also be closed
        for def_name, def_schema in self.schema.get("$defs", {}).items():
            with self.subTest(def_name=def_name):
                self.assertEqual(def_schema.get("type"), "object")
                self.assertIs(def_schema.get("additionalProperties"), False)

    def test_requirement_a_generic_enterprise_actions_validate_schema(self):
        """Requirement A: All generic Enterprise action definitions validate schema cleanly."""
        enterprise_actions = self.registry.get_enterprise_actions()
        self.assertGreaterEqual(len(enterprise_actions), 8, "Must have at least 8 MVP capabilities")

        for action in enterprise_actions:
            with self.subTest(action_id=action.action_id):
                payload = action.to_dict()
                errors = validate_shape(payload, self.schema)
                self.assertEqual(errors, [], f"Schema validation failed for {action.action_id}: {errors}")
                self.assertIn(action.classification, ("ENTERPRISE_TTP", "PLANNER_INTERNAL"))

    def test_requirement_b_legacy_actions_compatibility_and_classification(self):
        """Requirement B: Legacy actions validate schema and are classified as LEGACY_WEB_COMPAT."""
        legacy_actions = self.registry.get_legacy_actions()
        self.assertGreater(len(legacy_actions), 0)

        for action in legacy_actions:
            with self.subTest(action_id=action.action_id):
                payload = action.to_dict()
                errors = validate_shape(payload, self.schema)
                self.assertEqual(errors, [], f"Schema validation failed for legacy {action.action_id}: {errors}")
                self.assertEqual(action.classification, "LEGACY_WEB_COMPAT")

    def test_requirement_d_preconditions_are_structured_data(self):
        """Requirement D: Preconditions must be structured data, forbidding arbitrary code/eval."""
        for action in self.registry.get_all_actions():
            with self.subTest(action_id=action.action_id):
                pre = action.preconditions
                # Preconditions must be PreconditionContract dataclass instance, not a code string
                self.assertFalse(isinstance(pre, str), "Preconditions must not be string")
                self.assertIsInstance(pre.target_visible, bool)
                self.assertIsInstance(pre.host_observed, bool)
                self.assertIsInstance(pre.service_observed, bool)
                self.assertIsInstance(pre.finding_confirmed, bool)
                self.assertIn(pre.min_access_level, ("NONE", "FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM"))
                self.assertIsInstance(pre.require_active_session, bool)
                self.assertIsInstance(pre.require_valid_credential, bool)
                self.assertIsInstance(pre.require_reachability, bool)
                self.assertIsInstance(pre.objective_not_achieved, bool)
                self.assertIsInstance(pre.allowed_phases, tuple)

        # Ensure schema rejects arbitrary strings or eval fields in preconditions
        bad_precondition_payload = {
            "action_id": "ACTION-TEST-001",
            "action_class": "RECON",
            "preconditions": {
                "eval_expression": "lambda s: True",  # FORBIDDEN
            },
        }
        errors = validate_shape(bad_precondition_payload, self.schema)
        self.assertTrue(any("unknown property eval_expression" in e for e in errors))

    def test_requirement_e_costs_are_non_negative(self):
        """Requirement E: step_cost must be non-negative integer."""
        for action in self.registry.get_all_actions():
            with self.subTest(action_id=action.action_id):
                self.assertIsInstance(action.step_cost, int)
                self.assertGreaterEqual(action.step_cost, 0, f"Negative step_cost in {action.action_id}")

        # Negative cost rejected by schema
        bad_cost = {
            "action_id": "ACTION-TEST-001",
            "action_class": "RECON",
            "step_cost": -1,
        }
        errors = validate_shape(bad_cost, self.schema)
        self.assertTrue(any("below minimum" in e for e in errors))

    def test_requirement_f_noise_cost_bounded_numeric_semantics(self):
        """Requirement F: Operational noise_cost has bounded non-negative numeric semantics."""
        for action in self.registry.get_all_actions():
            with self.subTest(action_id=action.action_id):
                self.assertIsInstance(action.noise_cost, (int, float))
                self.assertGreaterEqual(action.noise_cost, 0.0, f"Negative noise_cost in {action.action_id}")

        # Negative noise cost rejected by schema
        bad_noise = {
            "action_id": "ACTION-TEST-001",
            "action_class": "RECON",
            "noise_cost": -0.5,
        }
        errors = validate_shape(bad_noise, self.schema)
        self.assertTrue(any("below minimum" in e for e in errors))

    def test_schema_rejects_unknown_root_property(self):
        """Action contract root object is closed: unknown properties fail validation."""
        valid_action = self.registry.get_enterprise_actions()[0].to_dict()
        valid_action["arbitrary_unknown_key"] = "forbidden"
        errors = validate_shape(valid_action, self.schema)
        self.assertTrue(any("unknown property arbitrary_unknown_key" in e for e in errors))

    def test_mitre_attack_metadata_is_validated_when_present(self):
        """MITRE ATT&CK reference metadata must conform to closed schema."""
        bad_mitre = {
            "action_id": "ACTION-TEST-001",
            "action_class": "RECON",
            "mitre_attack": {
                "tactic": "Discovery",
                "technique_id": "INVALID-ID",  # Must match ^T[0-9]{4}(\.[0-9]{3})?$
            },
        }
        errors = validate_shape(bad_mitre, self.schema)
        self.assertTrue(any("pattern mismatch" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
