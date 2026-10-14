"""Temporary-root tests; never load the control server or execute a module runner."""
import ast
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboards.app.backend import research_overview as overview


def task_table():
    rows = ["# Tasks", "", "| ID | Descriptive name | Status | Dependencies |", "|---|---|---|---|"]
    for n in range(1, 36):
        status = "DEFERRED" if n in (26, 32) else "SPEC_ONLY"
        dependency = "none" if n == 1 else "all-required" if n == 35 else f"TASK-{n-1:03d}"
        rows.append(f"| TASK-{n:03d} | Task {n} | `{status}` | {dependency} |")
    return "\n".join(rows) + "\n\n## Other backlog\n| SL-01 | ignored |\n"


class ResearchOverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = self.root / "TASKS.md"
        self.tasks.write_text(task_table(), encoding="utf-8")
        self.evaluations = self.root / overview.EVALUATION_ROOT
        self.evaluations.mkdir(parents=True)

    def build(self):
        return overview.build_research_overview(self.root)

    def package(self, char="a", modify=None):
        directory = self.evaluations / ("RUN-EVAL-" + char * 32)
        directory.mkdir()
        configuration = {"protocol_sha256": "b" * 64}
        summaries = [dict(split=split, candidate_id=candidate,
                          metrics={name: dict(mean=0.5, ci=[0.1, 0.9]) for name in overview.METRICS},
                          raw_payload="SECRET_MUST_NOT_LEAK")
                     for split in overview.SPLITS for candidate in overview.CANDIDATES]
        refs = []
        for name in sorted(overview.PACKAGE_FILES - {"manifest.json"}):
            observed = configuration if name == "configuration.json" else (
                {"summaries": summaries, "raw_secret": "SECRET_MUST_NOT_LEAK"} if name == "analysis.json" else {})
            obj = dict(run_id=directory.name, source="SIMULATED_FIXTURE", observed_state=observed)
            if modify:
                modify(name, obj)
            data = json.dumps(obj).encode() if name.endswith(".json") else b"SECRET_MUST_NOT_LEAK"
            (directory / name).write_bytes(data)
            refs.append(dict(name=name, sha256=hashlib.sha256(data).hexdigest()))
        manifest = dict(run_id=directory.name, schema_version=2, source="SIMULATED_FIXTURE",
                        observed_state=dict(pipeline="COMPLETED_OFFLINE", configuration=configuration, artifacts=refs))
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return directory

    def failure(self, result):
        self.assertEqual(result["verification"]["state"], "FAILED")
        self.assertIsNone(result["metrics"])

    def test_canonical_table_metadata_and_deferred(self):
        result = self.build()
        self.assertEqual(result["state"], "OK")
        self.assertEqual([t["id"] for t in result["tasks"]], list(overview.TASK_IDS))
        self.assertEqual(result["tasks"][0]["dependencies"], [])
        self.assertEqual(result["tasks"][-1]["dependencies"], ["all-required"])
        self.assertEqual(result["tasks"][25]["status"], "DEFERRED")
        self.assertEqual(result["tasks"][31]["status"], "DEFERRED")
        self.assertEqual(result["task_source"]["sha256"], hashlib.sha256(self.tasks.read_bytes()).hexdigest())
        self.assertTrue(result["task_source"]["modified_at_utc"].endswith("Z"))
        self.assertFalse(result["integration"]["fully_connected"])
        self.assertFalse(result["integration"]["execution_enabled"])

    def test_source_changes_are_read_fresh(self):
        before = self.build()
        self.tasks.write_text(task_table().replace("Task 1 | `SPEC_ONLY`", "Task 1 | `IMPLEMENTED`"), encoding="utf-8")
        after = self.build()
        self.assertNotEqual(before["task_source"]["sha256"], after["task_source"]["sha256"])
        self.assertEqual(after["tasks"][0]["status"], "IMPLEMENTED")

    def test_malformed_table_rejects_without_partial_rows(self):
        original = task_table()
        cases = [original.replace("| TASK-010", "| TASK-009"),
                 original.replace("| TASK-010", "| TASK-036"),
                 original.replace("| TASK-010", "TASK-010"),
                 original.replace("`SPEC_ONLY`", "`READY`", 1),
                 original.replace("Task 1 |", "<script> |", 1),
                 original.replace("| TASK-001 |\n", "| TASK-999 |\n"),
                 original.replace("| TASK-001 |\n", "| TASK-001, TASK-001 |\n"),
                 original.replace("| TASK-001 |\n", "| TASK-002 |\n"),
                 original.replace("`DEFERRED`", "`IMPLEMENTED`", 1),
                 original.replace("|---|---|---|---|", "bad separator"),
                 original.replace("## Other backlog", "| ID | Descriptive name | Status | Dependencies |"),
                 original.replace("| TASK-035 | Task 35 | `SPEC_ONLY` | all-required |", "")]
        for data in cases:
            with self.subTest(data=data[:120]):
                self.tasks.write_text(data, encoding="utf-8")
                result = self.build()
                self.assertEqual(result["state"], "ERROR")
                self.assertEqual(result["tasks"], [])
                self.assertTrue(result["errors"])

    def test_missing_invalid_utf8_and_oversized_source(self):
        self.tasks.unlink()
        self.assertEqual(self.build()["errors"][0]["code"], "SOURCE_MISSING")
        self.tasks.write_bytes(b"\xff")
        self.assertEqual(self.build()["state"], "ERROR")
        self.tasks.write_bytes(b"x" * (overview.MAX_TASK_BYTES + 1))
        self.assertEqual(self.build()["errors"][0]["code"], "FILE_SIZE_LIMIT")

    def test_module_presence_is_not_import_or_task_promotion(self):
        for _, path, _, _ in overview.KNOWN_MODULES:
            module = self.root / path
            module.parent.mkdir(parents=True, exist_ok=True)
            module.write_text("raise AssertionError('must never import')", encoding="utf-8")
        result = self.build()
        self.assertTrue(all(m["availability"] == "PRESENT" for m in result["modules"]))
        self.assertEqual(result["tasks"][25]["status"], "DEFERRED")
        self.assertEqual(result["tasks"][31]["status"], "DEFERRED")
        self.assertEqual(result["tasks"][31]["integration_scope"], "READ_ONLY_WEB_EXISTING")
        self.assertEqual(result["tasks"][27]["status"], "SPEC_ONLY")
        self.assertEqual(result["tasks"][0]["integration_scope"], "DOCUMENTATION_ONLY")

    def test_missing_modules_and_invalid_module_type(self):
        self.assertTrue(all(m["availability"] == "MISSING" for m in self.build()["modules"]))
        (self.root / overview.KNOWN_MODULES[0][1]).mkdir(parents=True)
        result = self.build()
        self.assertEqual(result["modules"][0]["availability"], "ERROR")
        self.assertEqual(result["state"], "PARTIAL")

    def test_valid_package_uses_verifier_and_minimal_metrics(self):
        directory = self.package()
        with patch.object(overview, "verify_evaluation_package", wraps=overview.verify_evaluation_package) as verify:
            result = self.build()
        digest = hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
        verify.assert_called_once_with(directory, digest)
        item = result["evaluations"]["packages"][0]
        self.assertEqual(item["verification"]["state"], "VERIFIED")
        self.assertEqual(item["source"]["sha256"], digest)
        self.assertEqual(item["source"]["provenance"], "SIMULATED_FIXTURE")
        self.assertEqual(item["verification"]["hash_basis"], "SELF_COMPUTED_NOT_TRUSTED_PRODUCER_PIN")
        self.assertEqual(item["verification"]["experimental_claims"], "UNRESOLVED")
        self.assertEqual(len(item["metrics"]), 4)
        self.assertEqual(set(item["metrics"][0]["values"]), set(overview.METRICS))
        self.assertNotIn("SECRET_MUST_NOT_LEAK", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_null_confidence_interval_remains_null(self):
        def modify(name, obj):
            if name == "analysis.json":
                obj["observed_state"]["summaries"][0]["metrics"]["success_rate"]["ci"] = None
        self.package(modify=modify)
        rows = self.build()["evaluations"]["packages"][0]["metrics"]
        row = next(r for r in rows if r["split"] == "validation" and r["candidate_id"] == "synthetic-review")
        self.assertIsNone(row["values"]["success_rate"]["ci_low"])

    def test_per_package_hash_failure_preserves_other_result(self):
        bad = self.package("a")
        self.package("b")
        (bad / "report.md").write_text("changed", encoding="utf-8")
        result = self.build()
        self.assertEqual(result["state"], "PARTIAL")
        self.failure(result["evaluations"]["packages"][0])
        self.assertEqual(result["evaluations"]["packages"][1]["verification"]["state"], "VERIFIED")

    def test_manifest_path_reference_and_malformed_shapes_fail(self):
        directory = self.package()
        path = directory / "manifest.json"
        original = json.loads(path.read_text())
        variants = [dict(original, observed_state=None), dict(original, source="LIVE"),
                    dict(original, run_id="OTHER"), dict(original, schema_version=1)]
        escaped = json.loads(json.dumps(original))
        escaped["observed_state"]["artifacts"][0]["name"] = "../../TASKS.md"
        variants.append(escaped)
        bad_name = json.loads(json.dumps(original))
        bad_name["observed_state"]["artifacts"][0]["name"] = []
        variants.append(bad_name)
        for obj in variants:
            path.write_text(json.dumps(obj), encoding="utf-8")
            self.failure(self.build()["evaluations"]["packages"][0])

    def test_duplicate_json_nonfinite_and_deep_json_fail(self):
        directory = self.package()
        path = directory / "manifest.json"
        for text in ('{"run_id":"a","run_id":"b"}', '{"n":NaN}', '{"n":' + '[' * 1200 + '0' + ']' * 1200 + '}'):
            path.write_text(text, encoding="utf-8")
            self.failure(self.build()["evaluations"]["packages"][0])

    def test_bad_aggregate_values_are_errors_not_zeros(self):
        invalid = (True, "SECRET_MUST_NOT_LEAK", float("nan"), float("inf"), -1, 2, 10**50)
        for n, value in enumerate(invalid):
            def modify(name, obj):
                if name == "analysis.json":
                    obj["observed_state"]["summaries"][0]["metrics"]["success_rate"]["mean"] = value
            self.package(format(n, "x"), modify)
        result = self.build()
        for item in result["evaluations"]["packages"]:
            self.failure(item)
        self.assertNotIn("SECRET_MUST_NOT_LEAK", json.dumps(result))

    def test_incomplete_duplicate_aggregate_grid_fails(self):
        def modify(name, obj):
            if name == "analysis.json":
                rows = obj["observed_state"]["summaries"]
                rows[1] = rows[0]
        self.package(modify=modify)
        self.failure(self.build()["evaluations"]["packages"][0])

    def test_missing_root_is_not_empty_success(self):
        self.evaluations.rmdir()
        result = self.build()
        self.assertEqual(result["evaluations"]["state"], "ERROR")
        self.assertEqual(result["evaluations"]["errors"][0]["code"], "SOURCE_MISSING")

    def test_unknown_names_are_not_exposed_or_read(self):
        (self.evaluations / "SECRET_MUST_NOT_LEAK").mkdir()
        result = self.build()
        self.assertEqual(result["evaluations"]["state"], "PARTIAL")
        self.assertEqual(result["evaluations"]["packages"], [])
        self.assertNotIn("SECRET_MUST_NOT_LEAK", json.dumps(result))

    def test_inventory_and_all_size_limits(self):
        directory = self.package()
        with patch.object(overview, "MAX_PACKAGES", 0):
            self.assertEqual(self.build()["evaluations"]["errors"][0]["code"], "PACKAGE_COUNT_LIMIT")
        for limit, code in (("MAX_FILE_BYTES", "FILE_SIZE_LIMIT"),
                            ("MAX_PACKAGE_BYTES", "PACKAGE_SIZE_LIMIT"),
                            ("MAX_OVERVIEW_BYTES", "OVERVIEW_SIZE_LIMIT")):
            with self.subTest(limit=limit), patch.object(overview, limit, 1):
                item = self.build()["evaluations"]["packages"][0]
                self.failure(item)
                self.assertEqual(item["verification"]["error_code"], code)
        (directory / "extra").mkdir()
        self.assertEqual(self.build()["evaluations"]["packages"][0]["verification"]["error_code"], "PACKAGE_INVENTORY_INVALID")
        (directory / "extra").rmdir()
        (directory / "report.md").unlink()
        self.failure(self.build()["evaluations"]["packages"][0])

    def test_path_traversal_and_outside_root(self):
        for path in (self.root / ".." / "TASKS.md", self.root.parent / "TASKS.md"):
            with self.assertRaises(overview.OverviewError):
                overview._read(path, self.root)

    def test_symlink_file_directory_and_ancestor_rejected(self):
        target = self.root / "real-tasks"
        self.tasks.rename(target)
        try:
            self.tasks.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"OS does not allow creating symlinks: {exc.winerror if hasattr(exc, 'winerror') else exc.errno}")
        self.assertEqual(self.build()["errors"][0]["code"], "LINK_OR_REPARSE_POINT")
        self.tasks.unlink()
        target.rename(self.tasks)
        directory = self.package()
        linked = self.evaluations / ("RUN-EVAL-" + "b" * 32)
        linked.symlink_to(directory, target_is_directory=True)
        self.failure(self.build()["evaluations"]["packages"][1])
        alias = self.root / "alias"
        alias.symlink_to(self.root / "runtime", target_is_directory=True)
        with self.assertRaises(overview.OverviewError):
            overview._checked(alias / "evaluation-runs", self.root, directory=True)

    def test_any_windows_reparse_attribute_rejected_before_read(self):
        real = Path.lstat
        def lstat(path, *args, **kwargs):
            if path == self.tasks:
                return SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400)
            return real(path, *args, **kwargs)
        with patch.object(Path, "lstat", lstat), patch.object(overview, "bounded_bytes") as read:
            self.assertEqual(self.build()["errors"][0]["code"], "LINK_OR_REPARSE_POINT")
            read.assert_not_called()

    def test_changed_during_verification_is_not_published(self):
        directory = self.package()
        verify = overview.verify_evaluation_package
        def changed(*args):
            result = verify(*args)
            (directory / "report.md").write_bytes(b"changed after verification")
            return result
        with patch.object(overview, "verify_evaluation_package", changed):
            item = self.build()["evaluations"]["packages"][0]
        self.failure(item)
        self.assertEqual(item["verification"]["error_code"], "SOURCE_CHANGED")

    def test_static_error_does_not_leak_exception(self):
        self.package()
        with patch.object(overview, "verify_evaluation_package", side_effect=ValueError("SECRET_MUST_NOT_LEAK")):
            result = self.build()
        self.failure(result["evaluations"]["packages"][0])
        self.assertNotIn("SECRET_MUST_NOT_LEAK", json.dumps(result))

    def test_reads_preserve_all_bytes_and_do_not_dispatch(self):
        self.package()
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("write")), \
                patch.object(Path, "write_text", side_effect=AssertionError("write")):
            self.assertEqual(self.build()["state"], "OK")
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_standalone_get_cors_and_method_surface(self):
        self.assertEqual([(route.path, route.methods) for route in overview.app.routes],
                         [("/api/research/overview", {"GET"})])
        with patch.object(overview, "ROOT", self.root), TestClient(overview.app) as client:
            for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
                response = client.get("/api/research/overview?root=/ignored&run_id=ignored", headers={"Origin": origin})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["state"], "OK")
                self.assertEqual(response.headers["access-control-allow-origin"], origin)
            self.assertNotIn("access-control-allow-origin", client.get("/api/research/overview", headers={"Origin": "https://example.invalid"}).headers)
            self.assertEqual(client.post("/api/research/overview").status_code, 405)
            self.assertEqual(client.get("/openapi.json").status_code, 404)
            self.assertEqual(client.options("/api/research/overview", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}).status_code, 400)
            self.tasks.unlink()
            response = client.get("/api/research/overview")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["state"], "ERROR")

    def test_unified_route_in_isolation_without_control_server_import(self):
        path = Path(__file__).absolute().parents[2] / "dashboards/app/backend/control_api.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        route = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_research_overview")
        isolated = FastAPI()
        namespace = dict(app=isolated, ROOT=self.root, Dict=dict, Any=object)
        exec(compile(ast.Module(body=[route], type_ignores=[]), str(path), "exec"), namespace)
        with TestClient(isolated) as client:
            self.assertEqual(client.get("/api/research/overview").json()["state"], "OK")


if __name__ == "__main__":
    unittest.main()
