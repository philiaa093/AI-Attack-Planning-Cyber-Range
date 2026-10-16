"""Offline reporting regressions; temporary records only, no target/provider I/O."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dashboards.app.backend.run_history import RunIndex
from dashboards.app.backend.run_manager import RunManager
import scripts.demo.run_professor_demo as demo


class HistoryTruthfulnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "RUN-REPORT-001"
        self.run.mkdir()
        self.index = RunIndex(run_roots=[self.root])

    def report(self, **fields):
        (self.run / "report.json").write_text(json.dumps(fields), encoding="utf-8")

    def record(self, **changes):
        payload = self.run / "result-fixture.json"
        payload.write_text('{"source":"SIMULATED_FIXTURE"}', encoding="utf-8")
        record = dict(evidence_id="EV-1", run_id=self.run.name, path=str(payload),
                      sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),
                      created_at_utc="2026-10-13T00:00:00Z", source="UNIT_TEST",
                      redacted=True, expected_state="RECORDED", observed_state="RECORDED",
                      derived_from=[])
        record.update(changes)
        (self.run / "record-fixture.json").write_text(json.dumps(record), encoding="utf-8")
        return payload

    def test_absent_metadata_never_becomes_completed_rule_or_zero(self):
        self.record()
        item = self.index.get_run(self.run.name)
        self.assertEqual(item.state, "INCOMPLETE")
        self.assertEqual(item.planner_actual, "UNKNOWN")
        self.assertEqual(item.planner_verification, "UNKNOWN")
        self.assertIsNone(item.duration_ms)
        self.assertIsNone(item.network_dispatches)
        self.assertEqual(item.verified_evidence_count, 1)

    def test_summary_without_records_cannot_verify_evidence(self):
        self.report(state="COMPLETED", network_dispatch_count=0, verified_evidence_count=100)
        item = self.index.get_run(self.run.name)
        self.assertEqual(item.network_dispatches, 0)
        self.assertIsNone(item.verified_evidence_count)
        self.assertEqual(item.evidence_integrity, "NOT_VERIFIED")

    def test_tampered_payload_fails_closed_without_repair(self):
        payload = self.record()
        self.assertEqual(self.index.list_runs(limit=25).runs[0].evidence_integrity, "VERIFIED")
        payload.write_text("changed", encoding="utf-8")
        before = payload.read_bytes()
        item = self.index.get_run(self.run.name)
        self.assertEqual(item.evidence_integrity, "FAILED")
        self.assertIsNone(item.verified_evidence_count)
        self.assertEqual(payload.read_bytes(), before)
        self.assertEqual(self.index.list_runs(limit=25).runs[0].evidence_integrity, "FAILED")

    def test_cross_run_and_missing_reference_rejected(self):
        for changes in (dict(run_id="RUN-OTHER"), dict(derived_from=["EV-MISSING"])):
            self.record(**changes)
            self.assertEqual(self.index.get_run(self.run.name).evidence_integrity, "FAILED")

    def test_outside_payload_is_not_read(self):
        outside = self.root / "outside.json"
        outside.write_text("outside", encoding="utf-8")
        self.record(path=str(outside))
        self.assertEqual(self.index.get_run(self.run.name).evidence_integrity, "FAILED")

    def test_duplicate_record_identity_rejected(self):
        self.record()
        (self.run / "record-duplicate.json").write_bytes((self.run / "record-fixture.json").read_bytes())
        self.assertEqual(self.index.get_run(self.run.name).evidence_integrity, "FAILED")

    def test_invalid_counts_remain_unknown_and_duration_requires_execution_times(self):
        self.report(network_dispatch_count=True, permits_count=-1, created_at_utc="2026-10-13T00:00:00Z")
        item = self.index.get_run(self.run.name)
        self.assertIsNone(item.network_dispatches)
        self.assertIsNone(item.permits)
        self.assertIsNone(item.duration_ms)

    def test_reversed_execution_times_are_not_a_measured_zero_duration(self):
        self.report(started_at_utc="2026-10-13T00:00:10Z", ended_at_utc="2026-10-13T00:00:00Z")
        self.assertIsNone(self.index.get_run(self.run.name).duration_ms)

    def test_comparison_and_export_have_no_unmeasured_zero_or_safety_guarantee(self):
        self.report(network_dispatch_count=0)
        comparison = self.index.compare_runs(self.run.name, self.run.name)
        metrics = {row.metric: row for row in comparison.metrics}
        self.assertIsNone(metrics["duration_ms"].delta)
        self.assertIsNone(metrics["iterations"].run_a_value)
        self.assertEqual(metrics["network_dispatches"].delta, 0)
        self.assertEqual(comparison.comparison_kind, "DESCRIPTIVE_ONLY")
        self.assertIn("UNRESOLVED", comparison.safety_diff["policy_adherence"])
        for fmt in ("json", "csv"):
            output, _ = self.index.export_comparison(self.run.name, self.run.name, fmt)
            self.assertNotIn("100% Zero-bypass", output)

    def test_nested_provenance_is_reported_without_provider_e2e_claim(self):
        self.report(planner_provenance=dict(requested_mode="LLM", actual_mode="LLM", provider="fixture-provider"))
        item = self.index.get_run(self.run.name)
        self.assertEqual(item.planner_verification, "LLM_PROVIDER_RECORDED")

    def test_missing_timeline_does_not_fabricate_start_or_completion(self):
        self.assertEqual(self.index.get_run_timeline(self.run.name).events, [])
        self.report(traces=[dict(action_id="ACTION-PLAN-003")])
        events = self.index.get_run_timeline(self.run.name).events
        self.assertEqual([e.type for e in events], ["TRACE_RECORDED"])
        self.assertEqual(events[0].timestamp_utc, "")

    def test_configured_key_is_not_provider_verification(self):
        manager = RunManager(output_root=self.root / "readiness")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fixture-key"}), \
                patch.object(demo, "docker", side_effect=demo.DemoBlocked("offline")):
            result = manager.get_demo_readiness()
        self.assertEqual(result.details["llm_status"], "CONFIGURED")
        self.assertIn("E2E NOT VERIFIED", result.details["llm_provenance_disclosure"])
