"""Bounded run budgets, explicit active approval, and truthful verification metadata."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from dashboards.app.backend.event_sink import EventSink
from dashboards.app.backend.models import StartRunRequest
from dashboards.app.backend.run_manager import RunManager, _run_gate
from runtime.safety.discovery_gate import load_canonical_action_allowlist


class RunBudgetVerificationTests(unittest.TestCase):
    def test_security_counts_match_live_history_and_summary_without_counting_observations(self):
        from dashboards.app.backend.run_history import RunIndex
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "RUN-COUNTS"
            folder.mkdir()
            findings = [{"finding_id": str(i), "classification": classification}
                        for i, classification in enumerate(("NEGATIVE", "OBSERVATION", "SIGNAL", "CANDIDATE"))]
            (folder / "report.json").write_text(json.dumps({"run_id": folder.name, "findings": findings}), encoding="utf-8")
            manager = RunManager(Path(directory))
            result = manager.get_run_findings(folder.name)
            self.assertEqual(len(result.items), 4)
            self.assertEqual(result.findings_count, 2)
            self.assertEqual(RunIndex(run_roots=[Path(directory)]).get_run(folder.name).findings_count, 2)
            self.assertEqual(manager.get_run_summary(folder.name).findings_count, 2)
            manager._active_run_id = folder.name
            self.assertEqual(manager.get_run_summary(folder.name).findings_count, 2)

    def test_separate_budgets_and_explicit_active_scope(self):
        gate = _run_gate(StartRunRequest(max_decisions=3, max_requests=120, max_pages=30))
        self.assertEqual((gate.budget_tracker.max_requests, gate.budget_tracker.max_pages), (120, 30))
        self.assertNotIn("ACTION-WEB-001", gate.effective_actions)
        approved = _run_gate(StartRunRequest(approve_active_verification=True))
        self.assertTrue({"ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003"} <= approved.effective_actions)
        preview = _run_gate(StartRunRequest(approve_active_verification=True, preview_one_page=True))
        self.assertEqual((preview.budget_tracker.max_requests, preview.budget_tracker.max_pages), (1, 1))
        self.assertNotIn("ACTION-WEB-001", preview.effective_actions)

    def test_active_opt_in_cannot_override_canonical_policy(self):
        allowed = load_canonical_action_allowlist() - {"ACTION-WEB-001"}
        with patch("runtime.safety.discovery_gate.load_canonical_action_allowlist", return_value=allowed):
            gate = _run_gate(StartRunRequest(approve_active_verification=True))
        self.assertNotIn("ACTION-WEB-001", gate.effective_actions)

    def test_budget_input_bounds(self):
        for invalid in ({"max_requests": 0}, {"max_requests": 501}, {"max_pages": -1},
                        {"max_pages": 101}, {"max_decisions": 101}, {"max_requests": True},
                        {"max_requests": "120"}, {"approve_active_verification": "yes"}):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                StartRunRequest(**invalid)

    def test_current_tool_is_proposed_until_dispatch_and_result_is_separate(self):
        manager = RunManager()
        sink = EventSink()
        payload = {"action_id": "ACTION-WEB-001", "tool": "SafeInputVerificationExecutor", "family": "SQL_INJECTION"}
        manager._on_runtime_event({"type": "PLANNER_PROPOSED", "payload": payload}, sink)
        self.assertEqual(manager.get_snapshot()[1].current_execution["status"], "PROPOSED")
        self.assertIsNone(manager.get_snapshot()[1].last_verification)
        manager._on_runtime_event({"type": "ACTION_DISPATCH_STARTED", "action_id": "ACTION-WEB-001", "payload": payload}, sink)
        self.assertEqual(manager.get_snapshot()[1].current_execution["status"], "RUNNING")
        manager._on_runtime_event({"type": "VERIFICATION_COMPLETED", "action_id": "ACTION-WEB-001",
                                   "payload": {**payload, "classification": "SIGNAL"}}, sink)
        self.assertEqual(manager.get_snapshot()[1].last_verification["classification"], "SIGNAL")

    def test_findings_keep_tool_resource_reason_and_require_verified_references(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "RUN-FIXTURE-VERIFICATION"
            folder = Path(directory) / run_id
            folder.mkdir()
            finding = {"finding_id": "F-1", "family": "SQL_INJECTION", "classification": "NEGATIVE",
                       "verification_action": "ACTION-WEB-001", "resource_ref": "/products", "input_ref": "q",
                       "reason": "No anomaly observed", "result_evidence_refs": ["EV-1"],
                       "limitations": ["Bounded test only"], "confidence": 0.6}
            report_path = folder / "report.json"
            report_path.write_text(json.dumps({"run_id": run_id, "findings": [finding]}), encoding="utf-8")
            manager = RunManager(Path(directory))
            with patch.object(manager, "_verified_evidence", return_value=(folder, SimpleNamespace(state="VERIFIED"),
                                                                          [(folder, {"evidence_id": "EV-1"})])):
                result = manager.get_run_findings(run_id).items[0]
            self.assertEqual((result.classification, result.severity), ("NEGATIVE", "INFO"))
            self.assertEqual((result.tool, result.resource_ref, result.input_ref), ("SafeInputVerificationExecutor", "/products", "q"))
            self.assertEqual(result.detail, "No anomaly observed")
            self.assertEqual(result.evidence_refs, ["EV-1"])
            finding["classification"] = "VERIFIED_IN_LAB"
            report_path.write_text(json.dumps({"run_id": run_id, "findings": [finding]}), encoding="utf-8")
            for state, records, expected in (("NOT_VERIFIED", [], "INCONCLUSIVE"),
                                              ("VERIFIED", [(folder, {"evidence_id": "EV-1"})], "VERIFIED_IN_LAB")):
                with patch.object(manager, "_verified_evidence", return_value=(folder, SimpleNamespace(state=state), records)):
                    self.assertEqual(manager.get_run_findings(run_id).items[0].classification, expected)

            finding.update({"family": "PATH_TRAVERSAL", "verification_action": "ACTION-WEB-003",
                            "input_ref": "q", "classification": "VERIFIED_IN_LAB"})
            report_path.write_text(json.dumps({"run_id": run_id, "findings": [finding]}), encoding="utf-8")
            with patch.object(manager, "_verified_evidence", return_value=(folder, SimpleNamespace(state="VERIFIED"),
                                                                          [(folder, {"evidence_id": "EV-1"})])):
                self.assertEqual(manager.get_run_findings(run_id).items[0].classification, "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
