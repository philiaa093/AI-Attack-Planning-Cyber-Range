"""Unit and Integration tests for Dashboard Control API and RunManager."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from dashboards.app.backend.control_api import app, run_manager, range_controller, event_sink
from dashboards.app.backend.models import AgentState, RangeState, StepState


class TestControlAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        event_sink.clear()

    def test_get_status(self):
        """Verify GET /api/status returns structured SystemStatus without crashing."""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["api"], "healthy")
        self.assertIn("range", data)
        self.assertIn("run", data)
        self.assertIn("agent", data)
        self.assertIn("safety", data)
        self.assertIn("evidence", data)
        self.assertIn("pipeline", data)

        # Range must report structured status
        self.assertIn(data["range"]["status"], [s.value for s in RangeState])
        self.assertEqual(data["range"]["target_id"], "lab-ecommerce")

    def test_get_range_status(self):
        """Verify GET /api/range/status returns genuine Docker/services state."""
        resp = self.client.get("/api/range/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("checked_at_utc", data)

    def test_range_stop_when_no_owned_services(self):
        """Verify POST /api/range/stop is a safe no-op when no services are owned."""
        resp = self.client.post("/api/range/stop")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["message"], "No owned services to stop")

    def test_preflight_real_validation(self):
        """Verify POST /api/demo/preflight returns genuine check items and blockers."""
        resp = self.client.post("/api/demo/preflight")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("passed", data)
        self.assertIn("outcome", data)
        self.assertIsInstance(data["checks"], list)
        self.assertIsInstance(data["blockers"], list)
        self.assertTrue(len(data["checks"]) > 0)

        check_names = [c["name"] for c in data["checks"]]
        self.assertIn("DOCKER_AVAILABLE", check_names)
        self.assertIn("CANONICAL_POLICY", check_names)

    def test_event_sink_thread_safety(self):
        """Verify EventSink handles concurrent multi-threaded publishing."""
        run_id = "RUN-TEST-" + uuid.uuid4().hex
        threads = []

        def publisher(idx):
            for i in range(10):
                event_sink.publish({
                    "run_id": run_id,
                    "type": f"TEST_EVENT_{idx}_{i}",
                    "payload": {"idx": idx, "i": i},
                })

        for t_idx in range(5):
            t = threading.Thread(target=publisher, args=(t_idx,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        history = event_sink.get_history(run_id=run_id, limit=100)
        self.assertEqual(len(history), 50)

    def test_deny_demo_execution_flow(self):
        """Verify POST /api/runs with mode='deny-demo' executes zero-dispatch safety denial."""
        req_payload = {
            "mode": "deny-demo",
            "planner": "rule",
            "allow_fallback": True,
            "target": "lab-ecommerce",
            "approve_read_only": True,
        }
        resp = self.client.post("/api/runs", json=req_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        run_id = data["run_id"]

        # Wait briefly for background worker to complete deny case
        for _ in range(50):
            time.sleep(0.1)
            curr = self.client.get("/api/runs/current").json()
            if curr["run"]["state"] in ("COMPLETED", "FAILED"):
                break

        final_curr = self.client.get("/api/runs/current").json()
        self.assertEqual(final_curr["run"]["state"], "COMPLETED")
        self.assertEqual(final_curr["run"]["stop_reason"], "DENY_DEMO_COMPLETED")
        self.assertEqual(final_curr["safety"]["network_dispatches"], 0)
        self.assertGreaterEqual(final_curr["safety"]["denials_count"], 1)

    def test_prevent_duplicate_active_runs(self):
        """Verify system forbids starting a new run while another run is active."""
        req_payload = {
            "mode": "deny-demo",
            "planner": "rule",
        }
        with run_manager._lock:
            run_manager._run_status.state = AgentState.RUNNING
            run_manager._active_run_id = "RUN-ACTIVE-TEST"

        try:
            resp = self.client.post("/api/runs", json=req_payload)
            self.assertEqual(resp.status_code, 409)
            self.assertIn("Another run is currently active", resp.json()["detail"])
        finally:
            with run_manager._lock:
                run_manager._run_status.state = AgentState.IDLE
                run_manager._active_run_id = None

    def test_emergency_stop_halts_active_state(self):
        """Verify POST /api/emergency-stop activates kill switch and halts dispatches."""
        resp = self.client.post("/api/emergency-stop")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

        # Check status reflects blocked/kill switch
        curr = self.client.get("/api/runs/current").json()
        self.assertEqual(curr["run"]["state"], "BLOCKED")
        self.assertEqual(curr["run"]["stop_reason"], "EMERGENCY_KILL_SWITCH_ACTIVATED")

    def test_evidence_and_findings_endpoints(self):
        """Verify GET /api/runs/{run_id}/evidence, /findings, /summary against real run data."""
        # Check if there is an existing run in demo-output
        sample_runs = list(run_manager.output_root.glob("RUN-*"))
        if not sample_runs:
            return  # Skip if no runs recorded yet

        run_id = sample_runs[0].name
        # 1. Evidence list
        ev_resp = self.client.get(f"/api/runs/{run_id}/evidence")
        self.assertEqual(ev_resp.status_code, 200)
        ev_data = ev_resp.json()
        self.assertIn("items", ev_data)
        self.assertIn("integrity_status", ev_data)
        self.assertGreaterEqual(ev_data["evidence_count"], 1)

        # 2. Evidence detail
        first_ev_id = ev_data["items"][0]["evidence_id"]
        det_resp = self.client.get(f"/api/runs/{run_id}/evidence/{first_ev_id}")
        self.assertEqual(det_resp.status_code, 200)
        det_data = det_resp.json()
        self.assertEqual(det_data["evidence_id"], first_ev_id)
        self.assertTrue(det_data["verified"])
        self.assertIsNotNone(det_data["content"])

        # 3. Findings list
        fnd_resp = self.client.get(f"/api/runs/{run_id}/findings")
        self.assertEqual(fnd_resp.status_code, 200)
        fnd_data = fnd_resp.json()
        self.assertIn("items", fnd_data)
        self.assertIn("findings_count", fnd_data)

        # 4. Run Summary
        sum_resp = self.client.get(f"/api/runs/{run_id}/summary")
        self.assertEqual(sum_resp.status_code, 200)
        sum_data = sum_resp.json()
        self.assertEqual(sum_data["run_id"], run_id)
        self.assertIn("integrity_status", sum_data)
        self.assertIn("network_dispatches", sum_data)

    def test_path_traversal_protection(self):
        """Verify strict path traversal protection across all run inspection endpoints."""
        traversal_payloads = [
            "..",
            "../..",
            "..%2F..",
            "....//....//",
            "C:\\Windows\\System32",
            "/etc/passwd",
            "RUN-ID/../../secret",
        ]
        for bad_id in traversal_payloads:
            r1 = self.client.get(f"/api/runs/{bad_id}/evidence")
            self.assertIn(r1.status_code, (400, 404))

            r2 = self.client.get(f"/api/runs/{bad_id}/findings")
            self.assertIn(r2.status_code, (400, 404))

            r3 = self.client.get(f"/api/runs/{bad_id}/summary")
            self.assertIn(r3.status_code, (400, 404))

            r4 = self.client.get(f"/api/runs/{bad_id}/evidence/{bad_id}")
            self.assertIn(r4.status_code, (400, 404))

        # Unknown but valid syntax run_id should 404
        r_unk = self.client.get("/api/runs/RUN-NONEXISTENT-999999/evidence")
        self.assertEqual(r_unk.status_code, 404)

    def test_pause_and_resume_api_endpoints(self):
        """Verify POST /api/runs/{run_id}/pause and resume endpoints."""
        # Non-existent run -> 400 or 404
        p_resp = self.client.post("/api/runs/RUN-NONEXISTENT/pause")
        self.assertIn(p_resp.status_code, (400, 404))

        r_resp = self.client.post("/api/runs/RUN-NONEXISTENT/resume")
        self.assertIn(r_resp.status_code, (400, 404))

    def test_approval_and_rejection_api_security(self):
        """Verify POST /api/runs/{run_id}/proposals/{proposal_id}/approve and reject."""
        # Non-existent run -> 400 or 404
        app_resp = self.client.post("/api/runs/RUN-NONEXISTENT/proposals/PROP-01/approve")
        self.assertIn(app_resp.status_code, (400, 404))

        rej_resp = self.client.post(
            "/api/runs/RUN-NONEXISTENT/proposals/PROP-01/reject",
            json={"reason": "Operator denied"},
        )
        self.assertIn(rej_resp.status_code, (400, 404))

    def test_demo_readiness_endpoint(self):
        """Verify GET /api/demo/readiness separates REQUIRED vs OPTIONAL and reports honest LLM status."""
        resp = self.client.get("/api/demo/readiness")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["overall_status"], ["READY", "DEGRADED", "BLOCKED"])
        self.assertIn("summary", data)
        self.assertIn("checks", data)
        self.assertIn("details", data)

        check_map = {c["name"]: c for c in data["checks"]}
        self.assertIn("BACKEND_API", check_map)
        self.assertEqual(check_map["BACKEND_API"]["category"], "REQUIRED")
        self.assertTrue(check_map["BACKEND_API"]["passed"])

        self.assertIn("SAFETY_POLICY", check_map)
        self.assertEqual(check_map["SAFETY_POLICY"]["category"], "REQUIRED")
        self.assertTrue(check_map["SAFETY_POLICY"]["passed"])

        self.assertIn("EVIDENCE_VAULT", check_map)
        self.assertEqual(check_map["EVIDENCE_VAULT"]["category"], "REQUIRED")
        self.assertTrue(check_map["EVIDENCE_VAULT"]["passed"])

        self.assertIn("LLM_PROVIDER", check_map)
        self.assertEqual(check_map["LLM_PROVIDER"]["category"], "OPTIONAL")
        # Missing LLM key must NEVER be in blockers
        self.assertNotIn("LLM_PROVIDER", data["blockers"])

        # Details must disclose fallback and offline replay capabilities
        self.assertTrue(data["details"]["llm_fallback_ready"])
        self.assertTrue(data["details"]["offline_replay_available"])
        self.assertIn("ports", data["details"])
        self.assertEqual(data["details"]["ports"]["backend"], 8000)
        self.assertEqual(data["details"]["ports"]["frontend"], 5173)

    def test_stop_ownership_pid_reuse_protection(self):
        """Verify stop_control_center.ps1 inspects command line and skips unrelated/reused PIDs."""
        import os
        import subprocess

        session_file = ROOT / ".demo-session.json"
        my_pid = os.getpid()
        session_data = {
            "session_id": "TEST-PID-REUSE-UNIT",
            "started_at_utc": "2026-10-13T01:00:00Z",
            "backend_pid": my_pid,
            "frontend_pid": 999999,
            "project_root": str(ROOT),
            "status": "ready",
        }
        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f)

            stop_script = ROOT / "scripts" / "demo" / "stop_control_center.ps1"
            cmd = [
                "powershell",
                "-ExecutionPolicy", "Bypass",
                "-File", str(stop_script),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=20)
            self.assertEqual(res.returncode, 0)
            self.assertIn("does not match expected project backend command line", res.stdout)
            self.assertIn("SKIPPING termination to protect unrelated/reused process", res.stdout)
            self.assertFalse(session_file.exists())
        finally:
            if session_file.exists():
                session_file.unlink()


if __name__ == "__main__":
    unittest.main()
