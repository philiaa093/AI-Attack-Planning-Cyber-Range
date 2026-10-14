"""Independent review regressions: metadata and custody, with temporary files only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dashboards.app.backend.run_history import RunIndex
from dashboards.app.backend.run_manager import RunManager
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.evidence.evidence_package import EvidenceManifest, EvidencePackageError, EvidenceVerifier, LabReportBuilder
from runtime.evidence.evidence_readonly import MAX_FILE_BYTES, bounded_bytes


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "RUN-REVIEW-001"
        self.run.mkdir()
        self.index = RunIndex(run_roots=[self.root])
        self.manager = RunManager(output_root=self.root)

    def report(self, **fields):
        (self.run / "report.json").write_text(json.dumps(fields), encoding="utf-8")

    def record(self, *, target=None, run_id=None, refs=None):
        target = target or self.run / "artifact.json"
        target.write_text('{"source":"SIMULATED_FIXTURE"}', encoding="utf-8")
        record = dict(evidence_id="EV-REVIEW", run_id=run_id or self.run.name,
                      path=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      created_at_utc="2026-10-13T00:00:00Z", source="UNIT_TEST", redacted=True,
                      expected_state="RECORDED", observed_state="RECORDED", derived_from=refs or [])
        (self.run / "record-review.json").write_text(json.dumps(record), encoding="utf-8")

    def test_malformed_metadata_does_not_break_other_runs_or_exports(self):
        good = self.root / "RUN-GOOD"
        good.mkdir()
        for value in (17, None, [], {}):
            with self.subTest(value=value):
                self.report(requested_mode=value, traces=[{"timestamp_utc": value}], findings=[17])
                self.assertEqual(self.index.list_runs().total_count, 2)
                self.assertIsNotNone(self.index.get_run(self.run.name))
                self.assertIsNotNone(self.index.compare_runs(self.run.name, good.name))
                self.index.export_comparison(self.run.name, good.name, "json")
                self.index.export_comparison(self.run.name, good.name, "csv")
                timeline = self.index.get_run_timeline(self.run.name)
                self.assertTrue(all(type(e.timestamp_utc) is str for e in timeline.events))

    def test_cross_run_report_and_payload_are_rejected(self):
        self.report(run_id="RUN-OTHER", traces=[{"action_id": "ACTION-PLAN-003"}])
        self.assertEqual(self.index._get_action_sequence(self.run.name), [])
        outside = self.root / "RUN-OTHER"
        outside.mkdir()
        self.record(target=outside / "artifact.json")
        self.assertTrue(self.manager.get_run_evidence_detail(self.run.name, "EV-REVIEW") is None)
        self.assertNotEqual(self.manager.get_run_evidence(self.run.name).integrity_status, "VERIFIED")

    def test_matching_hash_does_not_hide_wrong_run_schema_or_reference(self):
        for changes in (dict(run_id="RUN-OTHER"), dict(refs=["EV-MISSING"])):
            self.record(**changes)
            self.assertIsNone(self.manager.get_run_evidence_detail(self.run.name, "EV-REVIEW"))
        self.record()
        rec_file = self.run / "record-review.json"
        rec = json.loads(rec_file.read_text())
        rec["source"] = "UNSUPPORTED"
        rec_file.write_text(json.dumps(rec))
        self.assertIsNone(self.manager.get_run_evidence_detail(self.run.name, "EV-REVIEW"))

    def test_valid_run_local_evidence_remains_readable(self):
        self.record()
        evidence = self.manager.get_run_evidence(self.run.name)
        self.assertEqual(evidence.integrity_status, "VERIFIED")
        self.assertEqual(evidence.verified_count, 1)
        self.assertTrue(self.manager.get_run_evidence_detail(self.run.name, "EV-REVIEW").verified)

    def test_relative_approved_root_uses_the_same_boundary(self):
        self.record()
        with patch("os.getcwd", return_value=str(self.root.parent)):
            index = RunIndex(run_roots=[Path(self.root.name)])
            manager = RunManager(output_root=Path(self.root.name))
        self.assertEqual(index.find_run_dir(self.run.name), self.run)
        self.assertEqual(index.list_runs().total_count, 1)
        self.assertTrue(manager.get_run_evidence_detail(self.run.name, "EV-REVIEW").verified)

    def test_malformed_run_is_isolated_at_the_in_memory_http_api(self):
        from fastapi.testclient import TestClient
        from dashboards.app.backend.control_api import app
        self.report(requested_mode=17, traces=[{"timestamp_utc": []}], findings=[17])
        with patch("dashboards.app.backend.control_api.run_index", self.index):
            client = TestClient(app)
            for path in ("/api/runs/history", f"/api/runs/{self.run.name}/timeline"):
                self.assertEqual(client.get(path).status_code, 200)

    def test_oversized_report_and_artifact_are_rejected(self):
        self.record()
        (self.run / "artifact.json").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        self.assertTrue(self.manager.get_run_evidence_detail(self.run.name, "EV-REVIEW") is None)
        (self.run / "report.json").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        self.assertEqual(self.index._get_action_sequence(self.run.name), [])

    def test_linked_ancestor_rejected_by_read_listing_and_lookup(self):
        actual = self.root / "actual"
        actual.mkdir()
        alias = self.root / "alias"
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(actual), str(alias))
            self.addCleanup(lambda: alias.rmdir() if alias.exists() else None)
        else:
            alias.symlink_to(actual, target_is_directory=True)
        root = alias / "nested"
        root.mkdir()
        run = root / "RUN-LINK"
        run.mkdir()
        payload = run / "data.json"
        payload.write_text("{}")
        with self.assertRaises(ValueError):
            bounded_bytes(payload, run)
        index = RunIndex(run_roots=[root])
        self.assertIsNone(index.find_run_dir(run.name))
        self.assertEqual(index.list_runs().runs, [])

    def test_dispatch_is_independent_of_permission_and_strictly_typed(self):
        for value, expected in ((None, None), ("false", None), (0, None), (False, False), (True, True)):
            self.report(traces=[{"safety_decision": "PERMITTED", "dispatched": value}])
            step = self.index._get_action_sequence(self.run.name)[0]
            self.assertIs(step.dispatched, expected)
            self.assertIsNone(step.outcome)
        (self.run / "report.json").unlink()
        (self.run / "decision-review.json").write_text(json.dumps(dict(
            run_id=self.run.name, decision="PERMITTED", proposal={"action_id": "ACTION-PLAN-003"})))
        step = self.index._get_action_sequence(self.run.name)[0]
        self.assertIsNone(step.dispatched)
        self.assertIsNone(step.outcome)
        self.assertIsNone(step.target_id)

    def test_summary_keeps_missing_measurements_and_stop_statuses(self):
        for stop, status in ((None, "INCOMPLETE"), ("MANUAL_STOP", "STOPPED"),
                             ("KILL_SWITCH_ACTIVATED", "BLOCKED"), ("unexpected", "INCOMPLETE")):
            self.report(stop_reason=stop)
            summary = self.manager.get_run_summary(self.run.name)
            self.assertEqual(summary.status, status)
            self.assertEqual(summary.planner, "UNKNOWN")
            self.assertIsNone(summary.decisions_count)
            self.assertIsNone(summary.network_dispatches)
            self.assertIsNone(summary.facts_count)
        self.report(state="FAILED", network_dispatch_count=0)
        self.assertEqual(self.manager.get_run_summary(self.run.name).status, "FAILED")
        self.assertEqual(self.manager.get_run_summary(self.run.name).network_dispatches, 0)


class PublicationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def recorder(self):
        recorder = DurableEvidenceRecorder("RUN-PUBLISH", base_dir=self.root / "evidence",
                                           approved_root=self.root, source="UNIT_TEST",
                                           exclusive_creation=True)
        recorder.persist_phase_artifact("metadata", {"source": "SIMULATED_FIXTURE"},
                                        expected_state="RECORDED", observed_state="RECORDED")
        return recorder

    def test_empty_report_only_and_manifest_only_do_not_verify(self):
        for files in ({}, {"report.json": "{}"}, {"manifest.json": "{}"}):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, content in files.items():
                    (root / name).write_text(content)
                self.assertFalse(EvidenceVerifier.verify_directory(root).passed)

    def test_second_manifest_publication_preserves_original_bytes(self):
        recorder = self.recorder()
        EvidenceManifest.build_manifest(recorder.directory, recorder.run_id)
        path = recorder.directory / "manifest.json"
        before = path.read_bytes()
        with self.assertRaises(EvidencePackageError):
            EvidenceManifest.build_manifest(recorder.directory, recorder.run_id)
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(EvidenceVerifier.verify_directory(recorder.directory).passed)

    def test_manifest_with_omitted_records_does_not_verify(self):
        recorder = self.recorder()
        EvidenceManifest.build_manifest(recorder.directory, recorder.run_id)
        path = recorder.directory / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["records"] = []
        manifest["records_count"] = 0
        path.write_text(json.dumps(manifest))
        self.assertFalse(EvidenceVerifier.verify_directory(recorder.directory).passed)

    def test_second_report_and_collision_preserve_original_bytes(self):
        recorder = self.recorder()
        report = dict(run_id=recorder.run_id)
        md, js = LabReportBuilder.build_report(report, recorder.directory)
        before = {p.name: p.read_bytes() for p in (md, js)}
        with self.assertRaises(EvidencePackageError):
            LabReportBuilder.build_report(report, recorder.directory)
        self.assertEqual({p.name: p.read_bytes() for p in (md, js)}, before)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.md").write_bytes(b"existing")
            with self.assertRaises(EvidencePackageError):
                LabReportBuilder.build_report(report, root)
            self.assertEqual((root / "report.md").read_bytes(), b"existing")
            self.assertFalse((root / "report.json").exists())

    def test_partial_publication_is_retained_on_write_failure(self):
        recorder = self.recorder()
        real_fsync = os.fsync
        calls = 0
        def fail_second(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated fsync failure")
            return real_fsync(fd)
        with patch("runtime.evidence.evidence_package.os.fsync", side_effect=fail_second):
            with self.assertRaises(OSError):
                LabReportBuilder.build_report(dict(run_id=recorder.run_id), recorder.directory)
        self.assertTrue((recorder.directory / "report.json").exists())
        self.assertTrue((recorder.directory / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
