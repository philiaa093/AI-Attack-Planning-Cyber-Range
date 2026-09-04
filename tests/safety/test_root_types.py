import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validation import validate_scaffold

ROOT = Path(__file__).resolve().parents[2]


class RootTypeTests(unittest.TestCase):
    def assert_data_override_fails(self, relative, replacement, expected_error):
        target = ROOT / relative
        original = validate_scaffold.load_json

        def load(path, errors):
            if path == target:
                return replacement
            return original(path, errors)

        errors = []
        with patch.object(validate_scaffold, "load_json", side_effect=load):
            if relative.startswith("configs/safety/") or relative in {
                "evidence/policy.json",
                "evaluation/ground-truth/schema-link.json",
            }:
                validate_scaffold.validate_safety(errors)
            elif relative.startswith("configs/experiments/"):
                validate_scaffold.validate_experiment_identity(errors)
            else:
                validate_scaffold.validate_structured_data(errors)
        self.assertIn(expected_error, errors)

    def test_each_safety_root_rejects_array(self):
        files = (
            "configs/safety/lab-policy.yaml",
            "configs/safety/target-allowlist.yaml",
            "configs/safety/action-allowlist.yaml",
            "configs/safety/request-budget.yaml",
            "configs/safety/rate-limit.yaml",
            "configs/safety/kill-switch.yaml",
        )
        for relative in files:
            with self.subTest(path=relative):
                self.assert_data_override_fails(relative, [], f"{relative}: root must be object")

    def test_each_safety_root_rejects_null(self):
        files = (
            "configs/safety/lab-policy.yaml",
            "configs/safety/target-allowlist.yaml",
            "configs/safety/action-allowlist.yaml",
            "configs/safety/request-budget.yaml",
            "configs/safety/rate-limit.yaml",
            "configs/safety/kill-switch.yaml",
        )
        for relative in files:
            with self.subTest(path=relative):
                self.assert_data_override_fails(relative, None, f"{relative}: root must be object")

    def test_action_catalog_rejects_non_object(self):
        self.assert_data_override_fails(
            "actions/catalog/action-catalog.json",
            [],
            "actions/catalog/action-catalog.json: root must be object",
        )

    def test_action_fixture_rejects_non_object(self):
        self.assert_data_override_fails(
            "actions/catalog/ACTION-WEB-001.json",
            None,
            "actions/catalog/ACTION-WEB-001.json: root must be object",
        )

    def test_scenario_manifest_rejects_non_object(self):
        self.assert_data_override_fails(
            "scenarios/manifests/train.json",
            [],
            "scenarios/manifests/train.json: root must be object",
        )

    def test_strict_json_rejects_non_finite_constants(self):
        with self.subTest(constant="NaN"):
            with patch.object(Path, "read_text", return_value='{"seconds": NaN}'):
                errors = []
                self.assertIsNone(validate_scaffold.load_json(ROOT / "scenarios/manifests/train.json", errors))
                self.assertTrue(any("non-finite constant NaN" in error for error in errors), errors)
        for constant in ("Infinity", "-Infinity"):
            with self.subTest(constant=constant), patch.object(Path, "read_text", return_value=f'{{"seconds": {constant}}}'):
                errors = []
                self.assertIsNone(validate_scaffold.load_json(ROOT / "scenarios/manifests/train.json", errors))
                self.assertTrue(any(f"non-finite constant {constant}" in error for error in errors), errors)

    def test_evidence_policy_rejects_array_and_null(self):
        for replacement in ([], None):
            with self.subTest(replacement=replacement):
                self.assert_data_override_fails(
                    "evidence/policy.json",
                    replacement,
                    "evidence/policy.json: root must be object",
                )

    def test_evidence_manifest_rejects_array_and_null(self):
        for replacement in ([], None):
            with self.subTest(replacement=replacement):
                self.assert_data_override_fails(
                    "evidence/manifest.json",
                    replacement,
                    "evidence/manifest.json: root must be object",
                )

    def test_ground_truth_files_reject_array_and_null(self):
        for relative in (
            "evaluation/ground-truth/schema-link.json",
            "evaluation/ground-truth/sample.json",
        ):
            for replacement in ([], None):
                with self.subTest(path=relative, replacement=replacement):
                    self.assert_data_override_fails(relative, replacement, f"{relative}: root must be object")

    def test_experiment_manifests_reject_array_and_null(self):
        for path in (ROOT / "configs/experiments").glob("*.yaml"):
            relative = path.relative_to(ROOT).as_posix()
            for replacement in ([], None):
                with self.subTest(path=relative, replacement=replacement):
                    self.assert_data_override_fails(relative, replacement, f"{relative}: root must be object")

    def test_public_endpoints_in_runtime_config_are_rejected(self):
        target = ROOT / "configs/agent/planner-default.yaml"
        original = validate_scaffold.load_json
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
            def load(path, errors, endpoint=value):
                data = original(path, errors)
                if path == target and isinstance(data, dict):
                    return {**data, "endpoint": endpoint}
                return data

            errors = []
            with self.subTest(value=value), patch.object(validate_scaffold, "load_json", side_effect=load):
                validate_scaffold.validate_safety(errors)
                self.assertTrue(any("public URL/IP/hostname in runtime config" in error for error in errors), errors)

    def test_runtime_references_key_does_not_bypass_public_url_check(self):
        target = ROOT / "configs/agent/planner-default.yaml"
        original = validate_scaffold.load_json

        def load(path, errors):
            data = original(path, errors)
            if path == target and isinstance(data, dict):
                return {**data, "references": "https://target.example.edu"}
            return data

        errors = []
        with patch.object(validate_scaffold, "load_json", side_effect=load):
            validate_scaffold.validate_safety(errors)
        self.assertTrue(any("public URL/IP/hostname in runtime config" in error for error in errors), errors)

    def test_evidence_manifest_safety_values_are_enforced(self):
        target = ROOT / "evidence/manifest.json"
        original = validate_scaffold.load_json
        for key, value in (("retention", "overwrite"), ("append_only", False), ("traceable", False)):
            def load(path, errors, field=key, replacement=value):
                data = original(path, errors)
                if path == target and isinstance(data, dict):
                    return {**data, field: replacement}
                return data

            errors = []
            with self.subTest(field=key), patch.object(validate_scaffold, "load_json", side_effect=load):
                validate_scaffold.validate_structured_data(errors)
                self.assertIn("evidence/manifest.json: unsafe retention or traceability", errors)

    def test_evidence_policy_safety_values_are_enforced(self):
        target = ROOT / "evidence/policy.json"
        original = validate_scaffold.load_json
        for key, value in (("traceable", False), ("record_schema", "wrong.schema.json")):
            def load(path, errors, field=key, replacement=value):
                data = original(path, errors)
                if path == target and isinstance(data, dict):
                    return {**data, field: replacement}
                return data

            errors = []
            with self.subTest(field=key), patch.object(validate_scaffold, "load_json", side_effect=load):
                validate_scaffold.validate_safety(errors)
                self.assertIn("evidence policy unsafe", errors)


if __name__ == "__main__":
    unittest.main()
