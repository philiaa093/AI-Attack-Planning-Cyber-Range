"""Offline checks for bounded history pages and worker-thread endpoints."""
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from dashboards.app.backend import control_api
from dashboards.app.backend.run_history import RunIndex
from runtime.evidence.evidence_readonly import verify_records


class HistoryPaginationTests(unittest.TestCase):
    def test_page_matches_full_history_and_only_verifies_visible_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for number in range(6):
                run = root / (f"RUN-{number}" if number else "TEST-HIDDEN")
                run.mkdir()
                (run / "report.json").write_text(json.dumps({
                    "run_id": run.name, "created_at_utc": f"2026-10-16T00:00:0{number}Z",
                    "state": "COMPLETED", "actual_mode": "RULE",
                }), encoding="utf-8")
            index = RunIndex(run_roots=[root])
            full = index.list_runs(planner="RULE", include_test_runs=False)
            with patch('dashboards.app.backend.run_history.verify_records', wraps=verify_records) as verify:
                page = index.list_runs(planner="RULE", include_test_runs=False, limit=2, offset=2)
                self.assertEqual(page.total_count, 5)
                self.assertEqual(page.runs, full.runs[2:4])
                self.assertEqual(verify.call_count, 2)
            self.assertEqual(index.list_runs(limit=2, offset=99).runs, [])

    def test_api_validates_pagination_and_offloads_blocking_reads(self):
        with TestClient(control_api.app) as client:
            for query in ('limit=0', 'limit=101', 'limit=bad', 'offset=-1'):
                self.assertEqual(client.get('/api/runs/history?' + query).status_code, 422)
        for endpoint in (control_api.get_runs_history, control_api.get_system_status, control_api.get_range_status):
            self.assertFalse(inspect.iscoroutinefunction(endpoint))


if __name__ == '__main__':
    unittest.main()
