"""Regression tests for owned-file scope and contract/receipt separation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validation import validate_scaffold as v


class ScanScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patched = patch.object(v, "ROOT", self.root)
        patched.start()
        self.addCleanup(patched.stop)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def structured_errors(self):
        errors = []
        v.validate_structured_data(errors)
        return errors

    def test_session_lifecycle_is_separate_and_fail_closed(self):
        session = dict(session_id="DEMO-SES-1234abcd", started_at_utc="2026-10-14T00:00:00Z",
                       status="DEGRADED", backend_pid=123, frontend_pid=456,
                       backend_url="http://127.0.0.1:8000", frontend_url="http://127.0.0.1:5173",
                       gateway_url="http://127.0.0.1:18088", project_root=str(self.root))
        for status in ("INITIALIZING", "READY", "DEGRADED"):
            self.assertEqual(v._session_errors({**session, "status": status}), [])
        for key, value in (("status", "VALIDATED"), ("backend_pid", True),
                           ("frontend_pid", -1), ("backend_url", "http://example.com:8000"),
                           ("frontend_url", "http://127.0.0.1:65536"),
                           ("project_root", str(self.root / "other")),
                           ("started_at_utc", "2026-10-14T00:00:00"), ("command", "bad")):
            with self.subTest(key=key):
                path = self.write(".demo-session.json", json.dumps({**session, key: value}))
                errors = []
                v.load_json(path, errors)
                self.assertTrue(errors)
        path = self.write(".demo-session.json", json.dumps(session))
        self.assertFalse(v._is_contract_data(path))
        errors = []
        v.load_json(path, errors)
        self.assertEqual(errors, [])

    def test_handoff_metadata_roles_do_not_exempt_contract_snapshots(self):
        base = "dashboards/app/handoffs/UI-20261014T134112Z-dca3d019/"
        for folder in ("source/", "before/"):
            path = self.write(base + folder + "dashboards/app/frontend/tsconfig.json", '{/* allowed */ "compilerOptions": {}}')
            errors = []
            self.assertIsNotNone(v.load_json(path, errors))
            self.assertEqual(errors, [])
            self.assertFalse(v._is_contract_data(path))
            contract = self.write(base + folder + "configs/safety/lab-policy.yaml", '{"command":"bad"}')
            self.assertTrue(v._is_contract_data(contract))
        receipt = self.write(base + "receipts.json", '{"checks":[{"command":"npm test"}]}')
        self.assertFalse(v._is_contract_data(receipt))
        self.assertTrue(v._is_contract_data(self.root / "configs/safety/receipts.json"))
        self.assertFalse(v._is_contract_data(self.root / ("runtime/gate-hygiene/UI-REPAIR-" + "a" * 32 + "/backend.receipt.json")))
        self.assertTrue(v._is_contract_data(self.root / ("runtime/gate-hygiene/UI-REPAIR-" + "a" * 32 + "/policy.json")))
        self.assertTrue(any("forbidden" in error for error in self.structured_errors()))

    def status_errors(self):
        errors = []
        v.validate_ids_and_status(errors)
        return errors

    def test_installed_dependencies_are_not_read_or_linted(self):
        dependency = "dashboards/app/frontend/node_modules/example/"
        self.write(dependency + "README.md", "[missing](absent.md)\n[site](https://example.test)")
        self.write(dependency + "package.json", "not JSON")
        self.write(dependency + "bad.py", "if")
        self.write(dependency + "tool.exe", "non-executable fixture")
        self.write(dependency + "__pycache__/bad.pyc", "fixture")
        self.write("dashboards/app/frontend/src/owned.py", "answer = 42\n")
        visited = [v.rel(path) for path in v._workspace_files()]
        self.assertEqual(visited, ["dashboards/app/frontend/src/owned.py"])
        self.assertEqual(v._all_data_files(), [])
        for check in (v.validate_markdown_links, v.validate_ast_and_artifacts):
            errors = []
            check(errors)
            self.assertEqual(errors, [])

    def test_exclusion_is_exact_and_cannot_hide_canonical_subdirectories(self):
        relatives = ["configs/node_modules/unsafe.json",
                     "agent/.venv/unsafe.json",
                     "dashboards/app/frontend/node_modules-backup/unsafe.json"]
        for relative in relatives:
            self.write(relative, '{"command": "fixture", "status": "INVALID"}')
        errors = self.structured_errors() + self.status_errors()
        for relative in relatives:
            self.assertTrue(any(e.startswith(relative + ": forbidden") for e in errors), errors)
            self.assertIn(relative + ": invalid status 'INVALID'", errors)

    def test_gitignore_cannot_disable_contract_checks(self):
        self.write(".gitignore", "configs/\n*.json\n")
        path = self.write("configs/unsafe.json", '{"raw_exploit_command": "fixture"}')
        self.assertIn(path, v._all_data_files())
        self.assertIn("configs/unsafe.json: forbidden command/payload field raw_exploit_command",
                      self.structured_errors())

    def test_unreadable_tree_cannot_silently_pass(self):
        def denied_walk(root, *, onerror, followlinks):
            self.assertEqual(root, self.root)
            self.assertFalse(followlinks)
            onerror(PermissionError("fixture: unreadable tree"))

        with patch.object(v.os, "walk", side_effect=denied_walk):
            with self.assertRaises(PermissionError):
                list(v._workspace_files())

    def test_generated_frontend_bundle_is_pruned_but_owned_binary_fails(self):
        self.write("dashboards/app/frontend/dist/bundle.exe", "fixture")
        self.write("runtime/bad.exe", "fixture")
        errors = []
        v.validate_ast_and_artifacts(errors)
        self.assertEqual(errors, ["forbidden artifact runtime/bad.exe"])

    def test_owned_python_and_cache_errors_remain_visible(self):
        self.write("runtime/invalid.py", "if")
        self.write("runtime/__pycache__/cached.pyc", "fixture")
        errors = []
        v.validate_ast_and_artifacts(errors)
        self.assertTrue(any(e.startswith("Python AST failure runtime/invalid.py") for e in errors))
        self.assertIn("forbidden artifact runtime/__pycache__/cached.pyc", errors)

    def test_reports_accept_receipt_fields_without_mutating_source(self):
        data = {"status": "HANDOFF_BLOCKED", "baseline": {"status": "DIRTY"},
                "check_receipts": [{"command": "fixture"}],
                "pending_handoff_payload": {"status": "HANDOFF_BLOCKED"}}
        path = self.write("reports/receipt.json", json.dumps(data))
        before = path.read_bytes()
        errors = self.structured_errors() + self.status_errors()
        self.assertFalse(any(e.startswith("reports/receipt.json:") for e in errors), errors)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(before), data)

    def test_report_syntax_errors_are_still_detected(self):
        self.write("reports/bad.json", "{bad}")
        self.assertTrue(any(e.startswith("reports/bad.json: invalid JSON")
                            for e in self.structured_errors()))

    def test_receipt_identity_cannot_exempt_contract_data(self):
        for prefix in ("configs", "actions", "agent", "scenarios", "evidence", "tools"):
            relative = prefix + "/fixture.json"
            self.write(relative, json.dumps({"document_type": "TASK_HANDOFF_DOCUMENTS",
                       "status": "DIRTY", "nested": {"command": "fixture"}}))
        errors = self.structured_errors() + self.status_errors()
        for prefix in ("configs", "actions", "agent", "scenarios", "evidence", "tools"):
            relative = prefix + "/fixture.json"
            self.assertIn(relative + ": forbidden command/payload field command", errors)
            self.assertIn(relative + ": invalid status 'DIRTY'", errors)

    def test_npm_fields_are_metadata_only_at_the_reserved_frontend_paths(self):
        data = '{"dependencies": {"commander": "1"}, "scripts": {"build": "fixture"}}'
        self.write("dashboards/app/frontend/package.json", data)
        self.write("dashboards/app/frontend/package-lock.json", data)
        self.write("configs/package.json", data)
        errors = self.structured_errors()
        self.assertFalse(any(e.startswith("dashboards/app/frontend/") for e in errors), errors)
        self.assertIn("configs/package.json: forbidden command/payload field commander", errors)

    def test_frontend_metadata_syntax_is_not_exempt(self):
        self.write("dashboards/app/frontend/package-lock.json", "not JSON")
        self.assertTrue(any(e.startswith("dashboards/app/frontend/package-lock.json: invalid JSON")
                            for e in self.structured_errors()))

    def test_frontend_tsconfig_comments_preserve_strings_and_line_positions(self):
        data = {"url": "https://example.test/a//b", "literal": "/* quoted */",
                "escaped": 'quote " // text', "compilerOptions": {"strict": True}}
        original = json.dumps(data, indent=2)
        content = "/* header\nsecond line */\n" + original + "\n// footer\n"
        path = self.write("dashboards/app/frontend/tsconfig.json", content)
        errors = []
        self.assertEqual(v.load_json(path, errors), data)
        self.assertEqual(errors, [])
        stripped = v._strip_json_comments(content)
        self.assertEqual(len(stripped), len(content))
        self.assertEqual([i for i, char in enumerate(stripped) if char == "\n"],
                         [i for i, char in enumerate(content) if char == "\n"])

    def test_comment_support_cannot_relax_contract_parsing(self):
        for relative in ("configs/safety/fixture.yaml", "agent/tsconfig.json",
                         "dashboards/app/frontend/package-lock.json"):
            with self.subTest(relative=relative):
                path = self.write(relative, '{/* comment */ "lab_mode": true}')
                errors = []
                self.assertIsNone(v.load_json(path, errors))
                self.assertTrue(errors)

    def test_tsconfig_still_rejects_malformed_and_nonfinite_values(self):
        for content in ('{/* unterminated', '{"value": NaN}', '{"value": Infinity}',
                        '{"value": -Infinity}', '{"value": "unterminated}', '{"x": true,}'):
            with self.subTest(content=content):
                path = self.write("dashboards/app/frontend/tsconfig.json", content)
                errors = []
                self.assertIsNone(v.load_json(path, errors))
                self.assertTrue(errors)

    def test_owned_document_links_remain_strict(self):
        self.write("docs/fixture.md", "[public](https://example.test)\n[missing](absent.md)")
        self.write("docs/references.md", "[reference](https://example.test)")
        self.write("dashboards/app/frontend/README.md", "[local](http://127.0.0.1:5173)")
        errors = []
        v.validate_markdown_links(errors)
        self.assertEqual(len(errors), 3)
        self.assertIn("docs/fixture.md: external URL outside docs/references.md", errors)
        self.assertIn("dashboards/app/frontend/README.md: external URL outside docs/references.md", errors)
        self.assertIn("docs/fixture.md: broken or escaping local link absent.md", errors)


if __name__ == "__main__":
    unittest.main()
