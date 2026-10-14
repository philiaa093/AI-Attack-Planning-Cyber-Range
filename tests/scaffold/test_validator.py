import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.validation import validate_scaffold


class ValidatorTests(unittest.TestCase):
    def test_frozen_source_link_requires_exact_handoff_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "reports/TASK-015-offline-handoff.md"
            source = root / "runtime/discovery/discovery_report_importer.py"
            report.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            report.write_text("[source](../runtime/discovery_report_importer.py)")
            with mock.patch.object(validate_scaffold, "ROOT", root):
                errors = []
                validate_scaffold.validate_markdown_links(errors)
                self.assertEqual(len(errors), 1)
                source.write_text("# fixture")
                errors = []
                validate_scaffold.validate_markdown_links(errors)
                self.assertEqual(errors, [])
                report.rename(report.with_name("other-handoff.md"))
                errors = []
                validate_scaffold.validate_markdown_links(errors)
                self.assertEqual(len(errors), 1)

    def test_current_repo_validates(self):
        self.assertEqual(validate_scaffold.validate(), [])

    def dependency_fixture(self):
        rows = [f"| TASK-{n:03d} | Task | SPEC_ONLY | {'none' if n == 1 else f'TASK-{n-1:03d}'} |" for n in range(1, 36)]
        names = {name[:5]: name for name in validate_scaffold.SL_SPECS}
        rows += [f"| [SL-{n:02d}](docs/task-specs/{names[f'SL-{n:02d}']}) | TASK-011 | SPEC_ONLY | {'Không' if n == 1 else f'SL-{n-1:02d}'} | Scope |" for n in range(1, 13)]
        return "\n".join(rows)

    def dependency_errors(self, text, specs=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TASKS.md").write_text(text, encoding="utf-8")
            spec_dir = root / "docs/task-specs"
            spec_dir.mkdir(parents=True)
            for name, content in (specs or {}).items():
                (spec_dir / name).write_text(content, encoding="utf-8")
            errors = []
            with mock.patch.object(validate_scaffold, "ROOT", root):
                validate_scaffold.validate_dependencies(errors)
            return errors

    def test_dependency_tables_read_correct_columns(self):
        self.assertEqual(self.dependency_errors(self.dependency_fixture()), [])

    def test_canonical_dependencies_reject_unknown_self_and_forward(self):
        for dependency in ("TASK-999", "TASK-002", "TASK-003"):
            with self.subTest(dependency=dependency):
                text = self.dependency_fixture().replace("| TASK-002 | Task | SPEC_ONLY | TASK-001 |", f"| TASK-002 | Task | SPEC_ONLY | {dependency} |")
                self.assertTrue(any("invalid dependency TASK-002" in e for e in self.dependency_errors(text)))

    def test_task_ids_remain_complete_and_unique(self):
        text = self.dependency_fixture()
        first = text.splitlines()[0]
        for malformed in (text.replace(first, ""), text + "\n" + first):
            self.assertIn("TASKS.md dependency IDs incomplete or duplicated", self.dependency_errors(malformed))

    def test_sl_ids_remain_complete_and_unique(self):
        text = self.dependency_fixture()
        first = next(line for line in text.splitlines() if line.startswith("| [SL-01]"))
        for malformed in (text.replace(first, ""), text + "\n" + first):
            self.assertIn("TASKS.md SL dependency IDs incomplete or duplicated", self.dependency_errors(malformed))

    def test_sl_dependencies_reject_unknown_self_and_forward(self):
        for dependency in ("SL-99", "SL-02", "SL-03"):
            with self.subTest(dependency=dependency):
                text = self.dependency_fixture().replace("| SPEC_ONLY | SL-01 | Scope |", f"| SPEC_ONLY | {dependency} | Scope |")
                self.assertTrue(any("invalid SL dependency SL-02" in e for e in self.dependency_errors(text)))

    def test_sl_rejects_unknown_canonical_reference_and_wrong_link(self):
        for malformed in (self.dependency_fixture().replace("TASK-011 | SPEC_ONLY", "TASK-999 | SPEC_ONLY"), self.dependency_fixture().replace("docs/task-specs/SL-01-baseline-checks.md", "docs/task-specs/SL-02-storage-lifecycle.md")):
            self.assertTrue(self.dependency_errors(malformed))

    def test_spec_dependencies_are_limited_to_dependencies_section(self):
        name = "SL-02-storage-lifecycle.md"
        spec = "# Spec\n\n## Dependencies\nSL-01; TASK-011\n\n## Inputs\nSL-99\n"
        self.assertEqual(self.dependency_errors(self.dependency_fixture(), {name: spec}), [])
        for dependency in ("SL-02", "SL-03", "SL-99", "TASK-999"):
            with self.subTest(dependency=dependency):
                self.assertTrue(self.dependency_errors(self.dependency_fixture(), {name: spec.replace("SL-01; TASK-011", dependency)}))

    def test_spec_dependency_link_is_bound_to_id(self):
        spec = "# Spec\n## Dependencies\n[SL-01](SL-02-storage-lifecycle.md)\n"
        self.assertTrue(self.dependency_errors(self.dependency_fixture(), {"SL-02-storage-lifecycle.md": spec}))

    def test_exact_task_and_sl_manifest_reject_missing_and_extra(self):
        expected = validate_scaffold.TASK_SPECS | validate_scaffold.SL_SPECS
        self.assertEqual(len(expected), 47)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = root / "docs/task-specs"
            specs.mkdir(parents=True)
            for name in expected:
                (specs / name).write_text("# Spec\n", encoding="utf-8")
            with mock.patch.object(validate_scaffold, "ROOT", root):
                errors = []
                validate_scaffold._exact_dir(errors, "docs/task-specs", expected)
                self.assertEqual(errors, [])
                for name in ("TASK-001-foundation-validator.md", "SL-01-baseline-checks.md"):
                    with mock.patch.object(Path, "glob", return_value=[p for p in specs.iterdir() if p.name != name]):
                        errors = []
                        validate_scaffold._exact_dir(errors, "docs/task-specs", expected)
                    self.assertIn(f"docs/task-specs: missing required file {name}", errors)
                for name in ("TASK-036-extra.md", "SL-13-extra.md"):
                    (specs / name).write_text("# Extra\n", encoding="utf-8")
                errors = []
                validate_scaffold._exact_dir(errors, "docs/task-specs", expected)
                self.assertEqual(len(errors), 2)

    def test_task_headings_reject_missing_extra_and_reordered(self):
        headings = validate_scaffold.TASK_HEADINGS
        valid = "# Spec\n" + "\n".join(f"## {h}" for h in headings)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec.md"
            for text, accepted in ((valid, True), (valid.replace("## Purpose", "## Extra"), False), (valid + "\n## Extra", False), (valid.replace("## Status\n## Purpose", "## Purpose\n## Status"), False)):
                path.write_text(text, encoding="utf-8")
                errors = []
                with mock.patch.object(validate_scaffold, "ROOT", path.parent):
                    validate_scaffold._check_markdown(path, errors, headings)
                self.assertEqual(not errors, accepted)

    def test_sl_identity_and_status_are_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = root / "docs/task-specs"
            specs.mkdir(parents=True)
            path = specs / "SL-01-baseline-checks.md"
            for heading, status, expected_error in (
                ("SL-01", "BLOCKED", None),
                ("SL-02", "BLOCKED", "exact SL ID mismatch"),
                ("SL-01", "NOT_A_STATUS", "invalid SL status marker"),
            ):
                path.write_text(f"# {heading} — Fixture\n## Status\n`{status}`\n", encoding="utf-8")
                errors = []
                with mock.patch.object(validate_scaffold, "ROOT", root):
                    validate_scaffold.validate_ids_and_status(errors)
                relevant = [e for e in errors if "SL-01-baseline-checks.md" in e]
                if expected_error is None:
                    self.assertEqual(relevant, [])
                else:
                    self.assertTrue(any(expected_error in e for e in relevant))

    def test_dependency_prose_does_not_create_edges(self):
        spec = "# Spec\n## Dependencies\nSL-01; TASK-011. SL-03 tích hợp sau, không tạo dependency vòng.\n"
        self.assertEqual(self.dependency_errors(self.dependency_fixture(), {"SL-02-storage-lifecycle.md": spec}), [])

    def test_markdown_links_reject_missing_and_escaping_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.md"
            path.write_text("# Fixture\n[missing](missing.md)\n[escape](../outside.md)\n", encoding="utf-8")
            errors = []
            with mock.patch.object(validate_scaffold, "ROOT", root):
                validate_scaffold.validate_markdown_links(errors)
            self.assertEqual(len(errors), 2)
            self.assertTrue(all("broken or escaping local link" in e for e in errors))

    def test_artifact_rejection_is_not_relaxed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.pyc").write_bytes(b"fixture")
            errors = []
            with mock.patch.object(validate_scaffold, "ROOT", root):
                validate_scaffold.validate_ast_and_artifacts(errors)
            self.assertIn("forbidden artifact bad.pyc", errors)

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
        self.assertEqual(len(validate_scaffold.ADRS), 13)

    def test_exact_report_manifests(self):
        self.assertEqual(len(validate_scaffold.CHAPTERS), 11)
        self.assertEqual(len(validate_scaffold.APPENDICES), 6)

    def test_complete_scaffold_placeholder_manifest(self):
        self.assertEqual(len(validate_scaffold.SCAFFOLD_PLACEHOLDER_DIRS), 57)
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
        self.assertEqual((Path(validate_scaffold.ROOT) / "docs/thesis/chapters/09-results.md").read_text(encoding="utf-8"), expected)

    def test_walk_keys_is_recursive(self):
        self.assertEqual(list(validate_scaffold.walk_keys({"outer": {"inner": 1}}))[-1][1], "inner")

    def test_validator_does_not_mutate_fixture(self):
        data = {"status": "SPEC_ONLY"}
        before = data.copy()
        self.assertEqual(validate_scaffold.validate_shape(data, {"type": "object"}), [])
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
