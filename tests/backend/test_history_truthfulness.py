"""Offline reporting regressions; temporary records only, no target/provider I/O."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dashboards.app.backend.run_history import RunIndex
from dashboards.app.backend.models import AgentState
from dashboards.app.backend.run_manager import RunManager
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.lab import control_support as lab


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

    def test_current_terminal_run_integrity_matches_list_and_detail(self):
        manager = RunManager(output_root=self.root)
        index = RunIndex(run_roots=[self.root], run_manager=manager)
        manager._run_status.run_id = self.run.name
        manager._run_status.state = AgentState.RUNNING
        payload = self.record()
        self.assertEqual(index.get_run(self.run.name).evidence_integrity, "NOT_VERIFIED")
        manager._run_status.state = AgentState.FAILED
        manager._run_status.stop_reason = "fixture failure"
        for state, count in [("VERIFIED", 1), ("FAILED", None)]:
            for row in (index.get_run(self.run.name), index.list_runs(limit=1).runs[0], index.list_runs().runs[0]):
                self.assertEqual((row.evidence_integrity, row.verified_evidence_count), (state, count))
                self.assertEqual(row.stop_reason, "fixture failure")
            payload.write_text("changed", encoding="utf-8")

    def test_surface_groups_only_verified_discovery_and_links_actual_records(self):
        directory = self.run / "assessment"
        recorder = DurableEvidenceRecorder(self.run.name, directory, approved_root=self.root)
        manager = RunManager(output_root=self.root)
        def record(action, url, method="GET"):
            return recorder.persist_phase_artifact("result", {
                "run_id": self.run.name, "action_id": action, "url": url, "method": method,
                "outcome": "SUCCESS", "status_code": 200,
            })["evidence_id"]
        first = record("ACTION-RECON-002", "http://LOCALHOST:80/products?q=one")
        second = record("ACTION-RECON-002", "http://localhost/products?q=two#hidden")
        head = record("ACTION-RECON-002", "http://localhost/products", "HEAD")
        record("ACTION-SCAN-002", "http://localhost/scanner")
        record("ACTION-WEB-001", "http://localhost/verification")
        record("ACTION-RECON-002", "http://user@localhost/private")
        self.report(findings=[{"category": "SURFACE_DISCOVERY", "title": "Unverified legacy endpoint"}])
        (directory / "result-orphan.json").write_text(json.dumps({
            "run_id": self.run.name, "action_id": "ACTION-RECON-002", "method": "GET",
            "outcome": "SUCCESS", "status_code": 200, "url": "http://localhost/orphan",
        }), encoding="utf-8")
        findings = manager.get_run_findings(self.run.name)
        self.assertEqual(findings.findings_count, 0)
        self.assertEqual(len(findings.items), 2)
        get, head_item = findings.items
        self.assertEqual(get.resource_ref, "http://localhost/products")
        self.assertCountEqual(get.evidence_refs, [first, second])
        self.assertEqual(head_item.evidence_refs, [head])
        self.assertNotEqual(get.finding_id, head_item.finding_id)
        payload = next(path for path in directory.glob("result-*.json") if path.name != "result-orphan.json")
        payload.write_text("{}", encoding="utf-8")
        self.assertEqual(manager.get_run_findings(self.run.name).items, [])

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

    def test_old_provider_halt_is_failed_without_rewriting_report(self):
        self.report(state="COMPLETED", pipeline_control_completed=True,
                    requested_planner_mode="LLM", actual_planner_mode="NONE",
                    stop_reason="provider_unavailable_halt:FALLBACK_NOT_ALLOWED:PROVIDER_ERROR_TimeoutError")
        path = self.run / "report.json"
        before = path.read_bytes()
        item = self.index.get_run(self.run.name)
        self.assertEqual(item.state, "FAILED")
        self.assertEqual(item.planner_actual, "NONE")
        self.assertEqual(path.read_bytes(), before)

    def test_missing_timeline_does_not_fabricate_start_or_completion(self):
        self.assertEqual(self.index.get_run_timeline(self.run.name).events, [])
        self.report(traces=[dict(action_id="ACTION-PLAN-003")])
        events = self.index.get_run_timeline(self.run.name).events
        self.assertEqual([e.type for e in events], ["TRACE_RECORDED"])
        self.assertEqual(events[0].timestamp_utc, "")

    def test_inconclusive_stop_is_not_described_as_clean(self):
        event = dict(event_id="EVT-1", run_id=self.run.name, type="RUN_COMPLETED",
                     timestamp_utc="2026-11-24T00:00:00Z",
                     payload={"stop_reason": "unresolved_inconclusive_surface"})
        (self.run / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        description = self.index.get_run_timeline(self.run.name).events[0].description
        self.assertIn("unresolved_inconclusive_surface", description)
        self.assertNotIn("cleanly", description)

    def test_configured_key_is_not_provider_verification(self):
        manager = RunManager(output_root=self.root / "readiness")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fixture-key"}), \
                patch.object(lab, "docker", side_effect=lab.DemoBlocked("offline")):
            result = manager.get_demo_readiness()
        self.assertEqual(result.details["llm_status"], "CONFIGURED")
        self.assertIn("E2E NOT VERIFIED", result.details["llm_provenance_disclosure"])
