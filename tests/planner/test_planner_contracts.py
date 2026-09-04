import copy
import json
import unittest
from pathlib import Path

from scripts.validation.validate_scaffold import (
    ACTION_IDS,
    SCENARIO_PATTERN,
    TARGET_PATTERN,
    catalog_consistency_errors,
    scenario_consistency_errors,
)

ROOT = Path(__file__).resolve().parents[2]


class PlannerContractTests(unittest.TestCase):
    def load(self, relative):
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def catalog_entries(self):
        catalog = self.load("actions/catalog/action-catalog.json")
        return {entry["action_id"]: entry for entry in catalog["actions"]}

    def action_fixtures(self):
        return {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in (ROOT / "actions/catalog").glob("ACTION-*.json")
            if path.name != "action-catalog.json"
        }

    def allowlists(self):
        actions = self.load("configs/safety/action-allowlist.yaml")
        targets = self.load("configs/safety/target-allowlist.yaml")
        return set(actions["allowed_action_ids"]), set(targets["allowed_target_ids"])

    def scenario_manifests(self):
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (ROOT / "scenarios/manifests").glob("*.json")
        ]

    def test_action_catalog_is_exact_and_allowlisted(self):
        allowed_actions, _ = self.allowlists()
        self.assertEqual(set(self.catalog_entries()), ACTION_IDS)
        self.assertEqual(allowed_actions, ACTION_IDS)

    def test_action_fixtures_match_catalog_and_targets(self):
        _, allowed_targets = self.allowlists()
        self.assertEqual(
            catalog_consistency_errors(self.action_fixtures(), self.catalog_entries(), allowed_targets),
            [],
        )

    def test_action_fixture_unknown_targets_are_rejected(self):
        _, allowed_targets = self.allowlists()
        fixtures = copy.deepcopy(self.action_fixtures())
        fixtures["ACTION-END-002.json"]["target_id"] = "lab-clean-002"
        fixtures["ACTION-END-003.json"]["target_id"] = "lab-clean-003"
        errors = catalog_consistency_errors(fixtures, self.catalog_entries(), allowed_targets)
        self.assertIn("ACTION-END-002.json: target_id not allowlisted", errors)
        self.assertIn("ACTION-END-003.json: target_id not allowlisted", errors)

    def test_missing_action_fixture_is_rejected(self):
        _, allowed_targets = self.allowlists()
        fixtures = copy.deepcopy(self.action_fixtures())
        del fixtures["ACTION-WEB-001.json"]
        self.assertIn(
            "ACTION-WEB-001.json: required action fixture missing",
            catalog_consistency_errors(fixtures, self.catalog_entries(), allowed_targets),
        )

    def test_action_fixture_filename_id_mismatch_is_rejected(self):
        _, allowed_targets = self.allowlists()
        fixtures = copy.deepcopy(self.action_fixtures())
        fixtures["ACTION-WEB-001.json"]["action_id"] = "ACTION-WEB-002"
        self.assertTrue(catalog_consistency_errors(fixtures, self.catalog_entries(), allowed_targets))

    def test_action_fixture_class_mismatch_is_rejected(self):
        _, allowed_targets = self.allowlists()
        fixtures = copy.deepcopy(self.action_fixtures())
        fixtures["ACTION-WEB-001.json"]["action_class"] = "SCAN"
        errors = catalog_consistency_errors(fixtures, self.catalog_entries(), allowed_targets)
        self.assertIn("ACTION-WEB-001.json: action_class does not match catalog", errors)

    def test_manifests_use_bounded_actions_and_lab_targets(self):
        allowed_actions, allowed_targets = self.allowlists()
        self.assertEqual(
            scenario_consistency_errors(self.scenario_manifests(), allowed_actions, allowed_targets),
            [],
        )
        for manifest in self.scenario_manifests():
            self.assertTrue(all(TARGET_PATTERN.fullmatch(target) for target in manifest["target_ids"]))

    def test_unequal_scenario_budgets_are_rejected(self):
        actions, targets = self.allowlists()
        manifests = copy.deepcopy(self.scenario_manifests())
        manifests[0]["budgets"]["actions"] -= 1
        self.assertIn("scenario budgets differ", scenario_consistency_errors(manifests, actions, targets))

    def test_equal_oversized_scenario_budgets_are_rejected(self):
        actions, targets = self.allowlists()
        manifests = copy.deepcopy(self.scenario_manifests())
        for manifest in manifests:
            manifest["budgets"]["actions"] = 101
            manifest["budgets"]["requests"] = 2001
        errors = scenario_consistency_errors(manifests, actions, targets)
        self.assertEqual(errors.count("SCN-001: budget exceeds safety limits") + errors.count("SCN-002: budget exceeds safety limits") + errors.count("SCN-003: budget exceeds safety limits") + errors.count("SCN-004: budget exceeds safety limits"), 4)

    def test_non_finite_scenario_budgets_are_rejected(self):
        actions, targets = self.allowlists()
        for value in (float("nan"), float("inf"), float("-inf")):
            manifests = copy.deepcopy(self.scenario_manifests())
            for manifest in manifests:
                manifest["budgets"]["seconds"] = value
            errors = scenario_consistency_errors(manifests, actions, targets)
            with self.subTest(value=value):
                self.assertEqual(sum(error.endswith("budget must contain finite numbers") for error in errors), 4)

    def test_unknown_scenario_target_is_rejected(self):
        actions, targets = self.allowlists()
        manifests = copy.deepcopy(self.scenario_manifests())
        manifests[0]["target_ids"] = ["lab-unknown-001"]
        self.assertIn(f"{manifests[0]['scenario_id']}: unknown target", scenario_consistency_errors(manifests, actions, targets))

    def test_unknown_scenario_action_is_rejected(self):
        actions, targets = self.allowlists()
        manifests = copy.deepcopy(self.scenario_manifests())
        manifests[0]["allowed_actions"].append("ACTION-WEB-999")
        self.assertIn(f"{manifests[0]['scenario_id']}: unknown allowed action", scenario_consistency_errors(manifests, actions, targets))

    def test_replan_action_ids_stay_bounded(self):
        self.assertIn("ACTION-PLAN-002", ACTION_IDS)
        self.assertNotIn("ACTION-PLAN-999", ACTION_IDS)

    def test_scenario_ids_match_contract_and_are_unique(self):
        values = [manifest["scenario_id"] for manifest in self.scenario_manifests()]
        self.assertTrue(all(SCENARIO_PATTERN.fullmatch(value) for value in values))
        self.assertEqual(len(values), len(set(values)))

    def test_scenario_splits_are_partitioned(self):
        self.assertEqual({manifest["split"] for manifest in self.scenario_manifests()}, {"TRAIN", "VALIDATION", "HELD_OUT"})

    def test_action_names_are_unique(self):
        names = [entry["name"] for entry in self.catalog_entries().values()]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
