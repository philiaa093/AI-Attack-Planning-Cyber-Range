"""Unit and Integration tests for Run History, Timeline Replay, and Experiment Comparison."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from dashboards.app.backend.control_api import app, run_index
from dashboards.app.backend.run_history import RunIndex


class TestRunHistory(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_list_runs_history(self):
        """Verify GET /api/runs/history scans filesystem and returns valid RunHistoryResponse."""
        resp = self.client.get("/api/runs/history")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("runs", data)
        self.assertIn("total_count", data)
        self.assertGreaterEqual(data["total_count"], 1)

        # Inspect first run structure
        first = data["runs"][0]
        self.assertIn("run_id", first)
        self.assertIn("planner_requested", first)
        self.assertIn("planner_actual", first)
        self.assertIn("planner_verification", first)
        self.assertIn("control_mode", first)
        self.assertIn("state", first)
        self.assertIn("network_dispatches", first)
        self.assertIn("evidence_count", first)

    def test_list_runs_with_filters(self):
        """Verify query filters for planner, control_mode, and search query."""
        resp = self.client.get("/api/runs/history?planner=RULE")
        self.assertEqual(resp.status_code, 200)
        for r in resp.json()["runs"]:
            self.assertTrue(
                "RULE" in r["planner_requested"].upper()
                or "RULE" in r["planner_actual"].upper()
                or "RULE" in r["planner_verification"].upper()
            )

        resp_search = self.client.get("/api/runs/history?search=RUN")
        self.assertEqual(resp_search.status_code, 200)
        self.assertGreaterEqual(resp_search.json()["total_count"], 1)

    def test_get_run_detail(self):
        """Verify GET /api/runs/{run_id} returns exact run metadata."""
        list_resp = self.client.get("/api/runs/history")
        runs = list_resp.json()["runs"]
        self.assertTrue(len(runs) > 0)
        target_id = runs[0]["run_id"]

        detail_resp = self.client.get(f"/api/runs/{target_id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail = detail_resp.json()
        self.assertEqual(detail["run_id"], target_id)
        self.assertIn("planner_verification", detail)

    def test_get_run_timeline(self):
        """Verify GET /api/runs/{run_id}/timeline returns chronologically ordered replay events."""
        target_id = "RUN-TIMELINE-FIXTURE"
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            run_dir = root / target_id
            run_dir.mkdir()
            (run_dir / "events.jsonl").write_text(json.dumps(dict(
                event_id="EVT-FIXTURE-1", run_id=target_id, type="RUN_STARTED",
                timestamp_utc="2026-10-13T00:00:00Z", payload={},
            )) + "\n", encoding="utf-8")
            from unittest.mock import patch
            with patch.object(run_index, "roots", [root]):
                timeline_resp = self.client.get(f"/api/runs/{target_id}/timeline")
        self.assertEqual(timeline_resp.status_code, 200)
        data = timeline_resp.json()
        self.assertEqual(data["run_id"], target_id)
        self.assertIn("events", data)
        self.assertGreaterEqual(len(data["events"]), 1)

        # Invariant: Step indices are sequential and chronologically structured
        indices = [ev["step_index"] for ev in data["events"]]
        self.assertEqual(indices, list(range(1, len(data["events"]) + 1)))

        # Invariant: Every event has typed metadata and title
        first_ev = data["events"][0]
        self.assertIn("event_id", first_ev)
        self.assertIn("type", first_ev)
        self.assertIn("title", first_ev)
        self.assertIn("description", first_ev)

    def test_compare_runs(self):
        """Verify GET /api/runs/compare computes side-by-side metrics and academic summary."""
        list_resp = self.client.get("/api/runs/history")
        runs = list_resp.json()["runs"]
        run_a = runs[0]["run_id"]
        run_b = runs[1]["run_id"] if len(runs) > 1 else runs[0]["run_id"]

        comp_resp = self.client.get(f"/api/runs/compare?run_a={run_a}&run_b={run_b}")
        self.assertEqual(comp_resp.status_code, 200)
        comp = comp_resp.json()

        self.assertEqual(comp["run_a"]["run_id"], run_a)
        self.assertEqual(comp["run_b"]["run_id"], run_b)
        self.assertIn("metrics", comp)
        self.assertIn("action_sequence_a", comp)
        self.assertIn("action_sequence_b", comp)
        self.assertIn("findings_overlap", comp)
        self.assertIn("safety_diff", comp)

        # Invariant: Neutral academic phrasing
        verdict = comp["summary_verdict"]
        self.assertTrue("Observed" in verdict or "Measured" in verdict or "Recorded" in verdict)

    def test_export_comparison_json_and_csv(self):
        """Verify GET /api/runs/compare/export returns valid JSON and CSV downloads."""
        list_resp = self.client.get("/api/runs/history")
        run_a = list_resp.json()["runs"][0]["run_id"]

        # Export JSON
        resp_json = self.client.get(f"/api/runs/compare/export?run_a={run_a}&run_b={run_a}&format=json")
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.headers.get("content-type"), "application/json")
        data = resp_json.json()
        self.assertIn("metrics", data)

        # Export CSV
        resp_csv = self.client.get(f"/api/runs/compare/export?run_a={run_a}&run_b={run_a}&format=csv")
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn("text/csv", resp_csv.headers.get("content-type", ""))
        self.assertIn("EXPERIMENT RUN COMPARISON", resp_csv.text)
        self.assertIn("ACTION SEQUENCE COMPARISON", resp_csv.text)

    def test_path_traversal_protection(self):
        """Verify path traversal attacks are rejected with HTTP 400 Bad Request."""
        # 1. Invalid run_id with dot-dots
        resp = self.client.get("/api/runs/..%2F..%2Fetc%2Fpasswd")
        self.assertIn(resp.status_code, (400, 404))

        # 2. Invalid timeline path
        resp_tl = self.client.get("/api/runs/invalid..name/timeline")
        self.assertEqual(resp_tl.status_code, 400)

        # 3. Invalid compare path
        resp_cmp = self.client.get("/api/runs/compare?run_a=valid-run&run_b=../../../etc")
        self.assertEqual(resp_cmp.status_code, 400)

    def test_corrupt_run_directory_resilience(self):
        """Verify that malformed/corrupted run folders do not crash the RunIndex."""
        temp_dir = Path(tempfile.mkdtemp(prefix="test_corrupt_run_"))
        try:
            corrupt_run = temp_dir / "RUN-CORRUPT-TEST-001"
            corrupt_run.mkdir()
            (corrupt_run / "report.json").write_text("{invalid json format...", encoding="utf-8")

            custom_index = RunIndex(run_roots=[temp_dir])
            result = custom_index.list_runs()
            self.assertEqual(result.total_count, 1)
            self.assertEqual(result.runs[0].run_id, "RUN-CORRUPT-TEST-001")
            self.assertEqual(result.runs[0].state, "INCOMPLETE")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_run_history_survival_across_backend_restart(self):
        """Verify historical runs are preserved across restarts via filesystem scanning."""
        fresh_index = RunIndex()
        res = fresh_index.list_runs()
        self.assertGreaterEqual(res.total_count, 1)
        first_id = res.runs[0].run_id
        fetched = fresh_index.get_run(first_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.run_id, first_id)


if __name__ == "__main__":
    unittest.main()
