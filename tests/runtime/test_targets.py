import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("runtime_targets", Path(__file__).resolve().parents[2] / "runtime" / "targets.py")
_module = importlib.util.module_from_spec(_spec)
import sys
sys.modules["runtime_targets"] = _module
_spec.loader.exec_module(_module)
Target = _module.Target


class TargetTests(unittest.TestCase):
    def test_fixed_vulnerability_observations(self):
        cases = {
            "lab-sqli-001": "ACTION-WEB-001",
            "lab-xss-001": "ACTION-WEB-002",
            "lab-path-001": "ACTION-WEB-003",
        }
        for target_id, action_id in cases.items():
            with self.subTest(target_id=target_id):
                observation = Target(target_id).observe(action_id)
                self.assertEqual(observation.status, 200)
                self.assertTrue(observation.body["vulnerable"])
                self.assertEqual(observation.body["status"], "detected")

    def test_clean_control_never_reports_fixed_fixtures(self):
        target = Target("lab-clean-001")
        for action_id in ("ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003"):
            with self.subTest(action_id=action_id):
                observation = target.observe(action_id)
                self.assertFalse(observation.body["vulnerable"])
                self.assertEqual(observation.body["status"], "not_detected")

    def test_reset_is_deterministic(self):
        target = Target("lab-sqli-001")
        self.assertEqual(target.health().body["reset_count"], 0)
        self.assertEqual(target.reset().body["reset_count"], 1)
        self.assertEqual(target.health().body["reset_count"], 1)


if __name__ == "__main__":
    unittest.main()
