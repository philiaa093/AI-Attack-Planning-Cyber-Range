"""Unit and integration tests for Structured Runtime Events, SSE streaming, and EventSink."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from dashboards.app.backend.control_api import app, event_sink, run_manager
from dashboards.app.backend.event_sink import EventSink
from dashboards.app.backend.models import (
    AgentEvent,
    AgentState,
    AgentStatus,
    EvidenceStatus,
    RangeState,
    RunStatus,
    SafetyStatus,
    StepState,
)
import scripts.demo.run_professor_demo as demo
from runtime.orchestration.autonomous_runner import AutonomousRunner
from runtime.safety.discovery_gate import ApprovalToken, CentralizedSafetyGate, KillSwitch, BudgetTracker, TokenBucketRateLimiter
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder


class TestRuntimeEvents(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        event_sink.clear()
        self.test_output = demo.OUTPUT / ("TEST-EVENTS-" + uuid.uuid4().hex[:8])

        if run_manager._active_thread and run_manager._active_thread.is_alive():
            run_manager._active_thread.join(timeout=2.0)

        with run_manager._lock:
            run_manager._active_run_id = None
            run_manager._active_thread = None
            run_manager._active_gate = None
            run_manager._active_recorder = None
            run_manager._active_runner = None
            run_manager._run_status = RunStatus(state=AgentState.IDLE)
            run_manager._agent_status = AgentStatus(state=AgentState.IDLE)
            run_manager._safety_status = SafetyStatus()
            run_manager._evidence_status = EvidenceStatus()
            for step in run_manager._pipeline_status.steps:
                run_manager._pipeline_status.steps[step] = StepState.NOT_RUN

    def tearDown(self):
        if run_manager._active_thread and run_manager._active_thread.is_alive():
            run_manager._active_thread.join(timeout=2.0)
        event_sink.clear()

    def test_event_sink_broadcasts_to_multiple_subscribers(self):
        """Verify EventSink broadcasts each event to all active subscribers without queue stealing."""
        sink = EventSink()

        async def run_test():
            q1_events = []
            q2_events = []

            async def sub1():
                async for ev in sink.subscribe():
                    q1_events.append(ev)
                    if len(q1_events) == 3:
                        break

            async def sub2():
                async for ev in sink.subscribe():
                    q2_events.append(ev)
                    if len(q2_events) == 3:
                        break

            # Start subscriber tasks
            t1 = asyncio.create_task(sub1())
            t2 = asyncio.create_task(sub2())
            await asyncio.sleep(0.01)

            # Publish 3 events
            for i in range(3):
                sink.publish({"run_id": "RUN-BROADCAST-TEST", "type": f"EVENT_{i}", "payload": {"index": i}})

            await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)
            self.assertEqual(len(q1_events), 3)
            self.assertEqual(len(q2_events), 3)
            self.assertEqual([e["type"] for e in q1_events], ["EVENT_0", "EVENT_1", "EVENT_2"])
            self.assertEqual([e["type"] for e in q2_events], ["EVENT_0", "EVENT_1", "EVENT_2"])

        asyncio.run(run_test())

    def test_event_history_survives_client_reconnect(self):
        """Verify recent event history is retained and immediately retrievable on reconnect."""
        sink = EventSink()
        run_id = "RUN-HIST-" + uuid.uuid4().hex[:8]

        for i in range(10):
            sink.publish({
                "run_id": run_id,
                "type": f"STEP_{i}",
                "payload": {"step": i},
            })

        history = sink.get_history(run_id=run_id, limit=20)
        self.assertEqual(len(history), 10)
        self.assertEqual(history[0]["type"], "STEP_0")
        self.assertEqual(history[-1]["type"], "STEP_9")

    def test_pipeline_updates_from_runtime_events(self):
        """Verify RunManager updates its pipeline and agent snapshots based on real runtime events."""
        run_id = "RUN-PIPE-TEST"
        with run_manager._lock:
            run_manager._active_run_id = run_id
            for step in run_manager._pipeline_status.steps:
                run_manager._pipeline_status.steps[step] = StepState.NOT_RUN

        # 1. PLANNER_STARTED -> PLAN = RUNNING
        run_manager._on_runtime_event({"run_id": run_id, "type": "PLANNER_STARTED"}, event_sink)
        _, agent_s, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["PLAN"], StepState.RUNNING)
        self.assertEqual(agent_s.state, AgentState.RUNNING)

        # 2. PLANNER_PROPOSED -> PLAN = PASS
        run_manager._on_runtime_event({
            "run_id": run_id,
            "type": "PLANNER_PROPOSED",
            "action_id": "ACTION-RECON-001",
            "payload": {"action_id": "ACTION-RECON-001", "target_id": "lab-ecommerce", "actual_mode": "RULE"},
        }, event_sink)
        _, agent_s, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["PLAN"], StepState.PASS)
        self.assertEqual(agent_s.current_action, "ACTION-RECON-001")
        self.assertEqual(agent_s.actual_mode, "RULE")

        # 3. SAFETY_EVALUATION_STARTED -> SAFETY = RUNNING
        run_manager._on_runtime_event({"run_id": run_id, "type": "SAFETY_EVALUATION_STARTED"}, event_sink)
        _, _, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["SAFETY"], StepState.RUNNING)

        # 4. SAFETY_PERMITTED -> SAFETY = PASS
        run_manager._on_runtime_event({"run_id": run_id, "type": "SAFETY_PERMITTED"}, event_sink)
        _, _, safety_s, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["SAFETY"], StepState.PASS)
        self.assertGreaterEqual(safety_s.permits_count, 1)

        # 5. ACTION_DISPATCH_STARTED -> EXECUTE = RUNNING
        run_manager._on_runtime_event({"run_id": run_id, "type": "ACTION_DISPATCH_STARTED"}, event_sink)
        _, _, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["EXECUTE"], StepState.RUNNING)

        # 6. ACTION_COMPLETED -> EXECUTE = PASS
        run_manager._on_runtime_event({"run_id": run_id, "type": "ACTION_COMPLETED"}, event_sink)
        _, _, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["EXECUTE"], StepState.PASS)

        # 7. OBSERVATION_RECEIVED -> OBSERVE = PASS
        run_manager._on_runtime_event({"run_id": run_id, "type": "OBSERVATION_RECEIVED"}, event_sink)
        _, _, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["OBSERVE"], StepState.PASS)

        # 8. EVIDENCE_RECORDED -> EVIDENCE = PASS
        run_manager._on_runtime_event({
            "run_id": run_id,
            "type": "EVIDENCE_RECORDED",
            "payload": {"evidence_id": "EV-TEST-123"},
        }, event_sink)
        _, _, _, ev_s, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["EVIDENCE"], StepState.PASS)
        self.assertEqual(ev_s.last_evidence_id, "EV-TEST-123")

        # 9. EVIDENCE_VERIFIED -> VERIFY = PASS
        run_manager._on_runtime_event({"run_id": run_id, "type": "EVIDENCE_VERIFIED", "payload": {"records": 5}}, event_sink)
        _, _, _, ev_s, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["VERIFY"], StepState.PASS)
        self.assertEqual(ev_s.integrity_status, "VERIFIED")

        # 10. RUN_COMPLETED -> COMPLETE = COMPLETED
        run_manager._on_runtime_event({"run_id": run_id, "type": "RUN_COMPLETED", "payload": {"stop_reason": "DONE"}}, event_sink)
        run_s, agent_s, _, _, pipe_s = run_manager.get_snapshot()
        self.assertEqual(pipe_s.steps["COMPLETE"], StepState.COMPLETED)
        self.assertEqual(run_s.state, AgentState.COMPLETED)
        self.assertEqual(agent_s.state, AgentState.COMPLETED)

    def test_deny_demo_timeline_and_zero_dispatch_invariant(self):
        """Verify deny-demo scenario produces expected timeline with zero network dispatches."""
        req = {
            "mode": "deny-demo",
            "planner": "rule",
        }
        resp = self.client.post("/api/runs", json=req)
        self.assertEqual(resp.status_code, 200)
        run_id = resp.json()["run_id"]

        # Wait for deny demo worker
        for _ in range(50):
            time.sleep(0.1)
            curr = self.client.get("/api/runs/current").json()
            if curr["run"]["state"] in ("COMPLETED", "FAILED"):
                break

        if run_manager._active_thread and run_manager._active_thread.is_alive():
            run_manager._active_thread.join(timeout=3.0)

        final_curr = self.client.get("/api/runs/current").json()
        self.assertEqual(final_curr["run"]["state"], "COMPLETED")
        self.assertEqual(final_curr["safety"]["network_dispatches"], 0)
        self.assertGreaterEqual(final_curr["safety"]["denials_count"], 1)

        # Check recorded timeline in event sink
        events = event_sink.get_history(run_id=run_id, limit=50)
        event_types = [e["type"] for e in events]

        # Invariant checks:
        self.assertIn("RUN_STARTED", event_types)
        self.assertIn("PLANNER_PROPOSED", event_types)
        self.assertIn("SAFETY_EVALUATION_STARTED", event_types)
        self.assertIn("SAFETY_DENIED", event_types)
        self.assertIn("EVIDENCE_RECORDED", event_types)
        self.assertIn("EVIDENCE_VERIFIED", event_types)
        self.assertIn("RUN_COMPLETED", event_types)

        # CRITICAL INVARIANT: NO ACTION_DISPATCHED event when denied
        self.assertNotIn("ACTION_DISPATCHED", event_types)

        # Verify run_id consistency across all events
        for e in events:
            self.assertEqual(e["run_id"], run_id)

    def test_emergency_stop_blocks_new_dispatch_events(self):
        """Verify emergency stop activates kill switch, emits EMERGENCY_STOP_ACTIVATED, and prevents dispatches."""
        req = {
            "mode": "deny-demo",
            "planner": "rule",
        }
        # Start a run
        resp = self.client.post("/api/runs", json=req)
        self.assertEqual(resp.status_code, 200)
        run_id = resp.json()["run_id"]

        # Trigger emergency stop immediately
        stop_resp = self.client.post("/api/emergency-stop")
        self.assertEqual(stop_resp.status_code, 200)
        self.assertTrue(stop_resp.json()["success"])

        if run_manager._active_thread and run_manager._active_thread.is_alive():
            run_manager._active_thread.join(timeout=3.0)

        curr = self.client.get("/api/runs/current").json()
        self.assertEqual(curr["run"]["state"], "BLOCKED")
        self.assertTrue(curr["safety"]["kill_switch_active"])

        # Check events contain EMERGENCY_STOP_ACTIVATED
        events = event_sink.get_history(run_id=run_id, limit=50)
        types = [e["type"] for e in events]
        self.assertIn("EMERGENCY_STOP_ACTIVATED", types)

        # Ensure NO action was dispatched after emergency stop
        stop_idx = types.index("EMERGENCY_STOP_ACTIVATED")
        for after_event in events[stop_idx + 1:]:
            self.assertNotEqual(after_event["type"], "ACTION_DISPATCHED")

    def test_autonomous_runner_event_hook_instrumentation(self):
        """Verify AutonomousRunner cleanly emits structured events without dashboard dependencies."""
        rec_dir = self.test_output / "autonomous-hook-test"
        run_id = "RUN-HOOK-TEST-" + uuid.uuid4().hex[:6]
        rec = demo.new_recorder(rec_dir, run_id)
        gate = demo.make_gate(rec, pages=1)
        now = time.time()
        approval = ApprovalToken("APP-HOOK-" + uuid.uuid4().hex, run_id, "lab-ecommerce", "*", now, now + 180)

        emitted_events = []

        def hook(ev):
            emitted_events.append(ev)

        # Construct runner with event_hook
        runner = AutonomousRunner(
            target_id="lab-ecommerce",
            gate=gate,
            recorder=rec,
            approval=approval,
            run_id=run_id,
            requested_planner_mode="RULE",
            max_decisions=1,
            event_hook=hook,
        )

        # Mock gate dispatch so no live Docker is required
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.durable_confirmed = True
        mock_resp.refusal_reason = None
        mock_resp.body_preview = "ok"
        gate.dispatch = MagicMock(return_value=mock_resp)

        report = runner.run()

        # Verify events were captured through the hook
        self.assertTrue(len(emitted_events) > 0)
        types = [e["type"] for e in emitted_events]

        self.assertIn("RUN_STARTED", types)
        self.assertIn("AGENT_ITERATION_STARTED", types)
        self.assertIn("PLANNER_STARTED", types)
        self.assertIn("PLANNER_PROPOSED", types)
        self.assertIn("SAFETY_EVALUATION_STARTED", types)
        self.assertIn("SAFETY_PERMITTED", types)
        self.assertIn("ACTION_COMPLETED", types)
        self.assertIn("RUN_COMPLETED", types)

        # Verify proposal payload contains no private reasoning
        for e in emitted_events:
            if e["type"] == "PLANNER_PROPOSED":
                self.assertIn("action_id", e["payload"])
                self.assertIn("target_id", e["payload"])
                self.assertNotIn("thought", e["payload"])
                self.assertNotIn("chain_of_thought", e["payload"])

        # Verify all events have consistent run_id
        for e in emitted_events:
            self.assertEqual(e["run_id"], run_id)

    def test_sse_endpoint_response_headers_and_filter(self):
        """Verify GET /api/events and /api/runs/{run_id}/events stream with text/event-stream."""
        async def mock_subscribe(run_id=None):
            yield {"event_id": "EV-SSE-1", "run_id": run_id or "RUN-1", "type": "TEST", "payload": {}}

        with patch.object(event_sink, "subscribe", side_effect=mock_subscribe):
            resp = self.client.get("/api/events")
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))

            run_id = "RUN-FILTER-" + uuid.uuid4().hex[:6]
            resp_filter = self.client.get(f"/api/runs/{run_id}/events")
            self.assertEqual(resp_filter.status_code, 200)
            self.assertTrue(resp_filter.headers["content-type"].startswith("text/event-stream"))


if __name__ == "__main__":
    unittest.main()
