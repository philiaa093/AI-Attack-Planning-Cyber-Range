import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.validation import validate_scaffold


class ValidatorTests(unittest.TestCase):
    def test_current_repo_validates(self):
        self.assertEqual(validate_scaffold.validate(), [])

    def test_mutated_status_fails_without_repo_change(self):
        data = {"status": "NOT_A_STATUS"}
        self.assertNotIn(data["status"], validate_scaffold.STATUSES)

    def test_forbidden_field_fails_without_repo_change(self):
        data = {"command": "rm -rf"}
        self.assertIn("command", {key for _, key, _ in validate_scaffold.walk_keys(data)})

    def test_exact_guide_manifest(self):
        self.assertEqual(len(validate_scaffold.GUIDES), 17)
        self.assertNotIn("18-extra.md", validate_scaffold.GUIDES)

    def test_exact_task_manifest(self):
        self.assertEqual(len(validate_scaffold.TASK_SPECS), 35)
        self.assertIn("TASK-035-final-foundation-audit.md", validate_scaffold.TASK_SPECS)

    def test_exact_runbook_manifest(self):
        self.assertEqual(len(validate_scaffold.RUNBOOKS), 10)

    def test_exact_adr_manifest(self):
        self.assertEqual(len(validate_scaffold.ADRS), 12)

    def test_exact_report_manifests(self):
        self.assertEqual(len(validate_scaffold.CHAPTERS), 11)
        self.assertEqual(len(validate_scaffold.APPENDICES), 6)

    def test_complete_scaffold_placeholder_manifest(self):
        self.assertEqual(len(validate_scaffold.SCAFFOLD_PLACEHOLDER_DIRS), 62)
        for relative in validate_scaffold.SCAFFOLD_PLACEHOLDER_DIRS:
            readme = Path(validate_scaffold.ROOT) / relative / "README.md"
            self.assertTrue(readme.is_file(), relative)
            text = readme.read_text(encoding="utf-8")
            self.assertIn("> Status: SPEC_ONLY", text)
            self.assertIn("No runtime", text)

    def test_missing_placeholder_is_reported(self):
        relative = "cyber-range/network"
        readme = Path(validate_scaffold.ROOT) / relative / "README.md"
        original_is_file = Path.is_file

        def is_file(path):
            return False if path == readme else original_is_file(path)

        errors = []
        with mock.patch.object(Path, "is_file", is_file):
            validate_scaffold.validate_scaffold_placeholders(errors)
        self.assertIn(f"missing SPEC_ONLY placeholder: {relative}/README.md", errors)

    def test_local_link_rejects_backslash(self):
        self.assertEqual(validate_scaffold._link_target(r"docs\\README.md")[0], "invalid")

    def test_local_link_rejects_absolute(self):
        self.assertEqual(validate_scaffold._link_target("/etc/passwd")[0], "invalid")
        self.assertEqual(validate_scaffold._link_target("C:/secret")[0], "invalid")

    def test_external_link_only_is_classified(self):
        self.assertEqual(validate_scaffold._link_target("https://example.test/a")[0], "external")

    def test_status_vocabulary_is_closed(self):
        self.assertEqual(validate_scaffold.STATUSES, {"SPEC_ONLY", "TBD", "UNRESOLVED", "IMPLEMENTED", "VALIDATED", "DEFERRED", "BLOCKED"})

    def test_no_results_guard_is_exact(self):
        expected = "# 09 Results\n\nStatus: SPEC_ONLY\n\nNo experimental results are available.\nDo not populate this chapter until experiment evidence exists.\n"
        self.assertEqual((Path(validate_scaffold.ROOT) / "report/chapters/09-results.md").read_text(encoding="utf-8"), expected)

    def test_walk_keys_is_recursive(self):
        self.assertEqual(list(validate_scaffold.walk_keys({"outer": {"inner": 1}}))[-1][1], "inner")

    def test_validator_does_not_mutate_fixture(self):
        data = {"status": "SPEC_ONLY"}
        before = data.copy()
        self.assertEqual(validate_scaffold.validate_shape(data, {"type": "object"}), [])
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
