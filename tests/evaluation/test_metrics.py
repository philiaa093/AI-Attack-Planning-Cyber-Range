import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation" / "metrics"))
from formulas import (
    _ratio,
    f1,
    false_positive_rate,
    goal_success_rate,
    planning_validity_rate,
    precision,
    recall,
    redundant_action_rate,
    replanning_success_rate,
)


class MetricTests(unittest.TestCase):
    def test_metrics(self):
        self.assertEqual(precision(3, 1), 0.75)
        self.assertEqual(recall(3, 1), 0.75)
        self.assertEqual(f1(3, 1, 1), 0.75)
        self.assertEqual(false_positive_rate(1, 3), 0.25)

    def test_zero_denominators_are_na(self):
        self.assertIsNone(_ratio(0, 0))
        self.assertIsNone(precision(0, 0))
        self.assertIsNone(recall(0, 0))
        self.assertIsNone(f1(0, 0, 0))
        self.assertIsNone(false_positive_rate(0, 0))
        self.assertIsNone(goal_success_rate(0, 0))

    def test_additional_rates_use_safe_ratio(self):
        self.assertEqual(goal_success_rate(3, 4), 0.75)
        self.assertEqual(planning_validity_rate(3, 4), 0.75)
        self.assertEqual(replanning_success_rate(3, 4), 0.75)
        self.assertEqual(redundant_action_rate(1, 4), 0.25)
        self.assertIsNone(planning_validity_rate(0, 0))
        self.assertIsNone(replanning_success_rate(0, 0))
        self.assertIsNone(redundant_action_rate(0, 0))

    def test_counts_reject_bool_and_negative(self):
        for bad in (True, False, -1):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _ratio(bad, 1)
                with self.assertRaises(ValueError):
                    goal_success_rate(1, bad)

    def test_ground_truth_isolation(self):
        forbidden = ("ground_truth", "ground-truth", "expected_detection", "truth_records")
        roots = (ROOT / "configs/agent", ROOT / "configs/llm", ROOT / "configs/rl", ROOT / "actions")
        for directory in roots:
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}:
                    text = path.read_text(encoding="utf-8").lower()
                    self.assertFalse(any(token in text for token in forbidden), path)

    def test_experiment_identity_and_scenarios(self):
        scenarios = {
            json.loads(path.read_text(encoding="utf-8"))["scenario_id"]
            for path in (ROOT / "scenarios/manifests").glob("*.json")
        }
        experiment_ids = set()
        for path in (ROOT / "configs/experiments").glob("*.yaml"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertRegex(manifest["experiment_id"], r"^EXP-[0-9]{4}$")
            self.assertNotIn(manifest["experiment_id"], experiment_ids)
            self.assertTrue(set(manifest["scenario_ids"]) <= scenarios)
            experiment_ids.add(manifest["experiment_id"])

    def test_evidence_traceability_contract(self):
        schema = json.loads((ROOT / "agent/planner/contracts/evidence.schema.json").read_text(encoding="utf-8"))
        self.assertTrue({"evidence_id", "run_id", "path", "sha256", "created_at_utc"} <= set(schema["required"]))
        policy = json.loads((ROOT / "evidence/policy.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "evidence/manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(policy["append_only"] and policy["traceable"])
        self.assertEqual(manifest["retention"], "append_only")


if __name__ == "__main__":
    unittest.main()
