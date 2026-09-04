import copy
import json
import unittest
from pathlib import Path

from scripts.validation.validate_scaffold import (
    ACTION_IDS,
    _runtime_string_is_public,
    safety_contract_errors,
    walk_keys,
)

ROOT = Path(__file__).resolve().parents[2]


class SafetyTests(unittest.TestCase):
    def load(self, relative):
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def safety_values(self):
        return {
            "policy": self.load("configs/safety/lab-policy.yaml"),
            "targets": self.load("configs/safety/target-allowlist.yaml"),
            "actions": self.load("configs/safety/action-allowlist.yaml"),
            "budget": self.load("configs/safety/request-budget.yaml"),
            "rate": self.load("configs/safety/rate-limit.yaml"),
            "kill": self.load("configs/safety/kill-switch.yaml"),
        }

    def test_safe_defaults(self):
        self.assertEqual(safety_contract_errors(**self.safety_values()), [])

    def test_env_defaults_exact(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("LAB_MODE=true", text)
        self.assertIn("PUBLIC_TARGETS=false", text)
        self.assertIn("ALLOW_ARBITRARY_SHELL=false", text)
        self.assertIn("ALLOW_DYNAMIC_ACTIONS=false", text)

    def test_budget_rate_and_kill_switch(self):
        values = self.safety_values()
        self.assertEqual(
            (values["budget"]["max_actions"], values["budget"]["max_requests"], values["budget"]["max_rps"]),
            (100, 2000, 5),
        )
        self.assertEqual((values["rate"]["requests_per_second"], values["rate"]["burst"]), (5, 1))
        self.assertTrue(values["kill"]["halts_new_actions"] and values["kill"]["preserve_evidence"])

    def test_unknown_target_is_not_allowlisted(self):
        values = self.safety_values()
        self.assertNotIn("public.example", values["targets"]["allowed_target_ids"])

    def test_unknown_action_is_not_allowlisted(self):
        values = self.safety_values()
        self.assertEqual(set(values["actions"]["allowed_action_ids"]), ACTION_IDS)
        self.assertNotIn("ACTION-UNKNOWN-999", values["actions"]["allowed_action_ids"])

    def assert_mutation_fails(self, group, key, value, message):
        values = copy.deepcopy(self.safety_values())
        values[group][key] = value
        self.assertIn(message, safety_contract_errors(**values))

    def test_mutated_budget_is_rejected(self):
        self.assert_mutation_fails("budget", "max_actions", 0, "request budget unsafe")

    def test_mutated_rate_is_rejected(self):
        self.assert_mutation_fails("rate", "burst", 99, "rate limit unsafe")

    def test_mutated_kill_switch_is_rejected(self):
        self.assert_mutation_fails("kill", "enabled", False, "kill switch unsafe")

    def test_mutated_target_allowlist_is_rejected(self):
        values = copy.deepcopy(self.safety_values())
        values["targets"]["allowed_target_ids"].append("public.example")
        self.assertIn("target allowlist unsafe", safety_contract_errors(**values))

    def test_mutated_action_allowlist_is_rejected(self):
        values = copy.deepcopy(self.safety_values())
        values["actions"]["allowed_action_ids"].append("ACTION-UNKNOWN-999")
        self.assertIn("action allowlist unsafe", safety_contract_errors(**values))

    def test_mutated_action_class_map_is_rejected(self):
        values = copy.deepcopy(self.safety_values())
        values["actions"]["action_classes"]["ACTION-WEB-001"] = "RECON"
        self.assertIn("action allowlist unsafe", safety_contract_errors(**values))

    def test_arbitrary_command_variants_are_walked(self):
        data = {"nested": [{"shell_command": "x", "raw_exploit_command": "y", "arbitrary_command": "z"}]}
        self.assertEqual(
            {key for _, key, _ in walk_keys(data)} - {"nested"},
            {"shell_command", "raw_exploit_command", "arbitrary_command"},
        )

    def test_public_ip_is_recognized(self):
        self.assertTrue(_runtime_string_is_public("8.8.8.8"))

    def test_public_url_is_recognized(self):
        self.assertTrue(_runtime_string_is_public("https://public.example"))

    def test_public_dns_names_are_recognized(self):
        self.assertTrue(_runtime_string_is_public("target.example.edu"))
        self.assertTrue(_runtime_string_is_public("target.example.co.uk"))

    def test_public_endpoint_forms_are_recognized(self):
        for value in (
            "target.example.edu:443",
            "target.example.edu.",
            "8.8.8.8:53",
            "[2001:4860:4860::8888]:443",
            "ftp://target.example.edu",
            "//target.example.edu",
            "ssh:target.example.edu",
            "ftp:target.example.edu",
            "target.example.edu/api",
            "target.example.edu?x=1",
            "target.example.edu#fragment",
            "8.8.8.8/api",
            r"\\target.example.edu\share",
        ):
            with self.subTest(value=value):
                self.assertTrue(_runtime_string_is_public(value))

    def test_local_schema_paths_are_not_hostnames(self):
        self.assertFalse(_runtime_string_is_public("agent/planner/contracts/state.schema.json"))
        self.assertFalse(_runtime_string_is_public("actions/catalog/action-catalog.json"))


if __name__ == "__main__":
    unittest.main()
