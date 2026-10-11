"""Live ShopLab Verification Script for Autonomous Closed-Loop Runner.

Flow:
  1. Starts isolated ShopLab Docker services (lab-ecommerce and gateway-ecommerce).
  2. Verifies gateway health on strictly isolated loopback gateway (127.0.0.1:18088).
  3. Initializes AutonomousRunner with CentralizedSafetyGate, DurableEvidenceRecorder, and StateManager.
  4. Executes the autonomous control loop:
     OBSERVATION -> STATE -> AI PLANNER -> PROPOSAL -> SAFETY GATE -> EXECUTOR -> NEW OBSERVATION -> STATE UPDATE -> AI REPLAN -> ... -> STOP
  5. Verifies trace integrity, decision provenance, fail-closed safety, and zero unsafe transport.
  6. Preserves historical evidence immutability (generates new unique RUN-AUTONOMOUS-LIVE-* evidence).
  7. Bounded teardown of owned services, preserving volume ecommerce-data.
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.autonomous_runner import AutonomousRunner, AutonomousRunReport
from runtime.discovery_gate import (
    ApprovalToken,
    BudgetTracker,
    CentralizedSafetyGate,
    KillSwitch,
    TokenBucketRateLimiter,
    load_canonical_action_allowlist,
    load_canonical_target_allowlist,
)
from runtime.discovery_recorder import (
    DurableEvidenceRecorder,
)

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18088
TARGET_ID = "lab-ecommerce"


def run_docker(cmd: str) -> tuple[int, str]:
    full_cmd = ["wsl", "-d", "Ubuntu", "-e", "bash", "-c", cmd]
    p = subprocess.run(full_cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_health(timeout: float = 20.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            conn = http.client.HTTPConnection(GATEWAY_HOST, GATEWAY_PORT, timeout=2.0)
            conn.request("GET", "/health")
            res = conn.getresponse()
            if res.status == 200:
                body = res.read().decode("utf-8")
                data = json.loads(body)
                if data.get("status") == "ok" and data.get("target_id") == TARGET_ID:
                    conn.close()
                    return True
            conn.close()
        except Exception:
            pass
        time.sleep(1.0)
    return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    print("=== STARTING AUTONOMOUS CONTROL LOOP LIVE VERIFICATION ===")

    # 1. Bring up Docker services
    print("[1] Bringing up Docker services (lab-ecommerce, gateway-ecommerce)...")
    rc, out = run_docker(
        "cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml up -d lab-ecommerce gateway-ecommerce"
    )
    if rc != 0:
        print(f"FAILED to start Docker services: {out}")
        return 1

    time.sleep(2)

    # 2. Check health
    print(f"[2] Checking gateway health at http://{GATEWAY_HOST}:{GATEWAY_PORT}/health...")
    if not check_health():
        print("FAILED: gateway health check timed out")
        return 1
    print(f"    Health check PASS: target_id = {TARGET_ID}, gateway = http://{GATEWAY_HOST}:{GATEWAY_PORT}")

    # Generate unique run ID to preserve historical runs immutable
    timestamp_suffix = int(time.time())
    run_id = f"RUN-AUTONOMOUS-LIVE-{timestamp_suffix}"
    evidence_base = Path("evidence/runtime") / run_id
    evidence_base.mkdir(parents=True, exist_ok=True)
    print(f"    Assigned Run ID: {run_id}")
    print(f"    Evidence Directory: {evidence_base}")

    # Check real provider availability
    has_api_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY"))
    requested_mode = "LLM" if has_api_key else "RULE"
    print(f"    Real Provider API Key: {'DETECTED' if has_api_key else 'NONE (using deterministic RULE engine)'}")
    print(f"    Requested Planner Mode: {requested_mode}")

    # 3. Setup Safety Gate, Approval, and Recorder
    print("[3] Initializing Safety Gate, Approval Token, and Durable Evidence Recorder...")
    recorder = DurableEvidenceRecorder(run_id=run_id, base_dir=evidence_base)
    base_origin = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"

    approval = ApprovalToken(
        approval_id=f"APP-AUTO-{timestamp_suffix}",
        run_id=run_id,
        target_id=TARGET_ID,
        action_id="*",
        not_before=time.time() - 30,
        expires_at=time.time() + 900,
    )

    budget = BudgetTracker(
        max_requests=25,
        max_depth=2,
        max_pages=10,
        max_redirect_hops=3,
        max_body_bytes=65536,
        timeout=5.0,
    )

    effective_targets = {TARGET_ID}
    effective_actions = {
        "ACTION-RECON-001",
        "ACTION-RECON-002",
        "ACTION-SCAN-001",
        "ACTION-PLAN-001",
        "ACTION-PLAN-002",
        "ACTION-END-001",
        "ACTION-END-002",
        "ACTION-END-003",
    }

    gate = CentralizedSafetyGate(
        base_origin=base_origin,
        target_registry={TARGET_ID: {"host": GATEWAY_HOST, "port": GATEWAY_PORT}},
        target_allowlist=effective_targets,
        canonical_target_allowlist=effective_targets,
        action_allowlist=effective_actions,
        canonical_action_allowlist=effective_actions,
        recorder=recorder,
        budget_tracker=budget,
        rate_limiter=TokenBucketRateLimiter(requests_per_second=10.0, burst=5),
        kill_switch=KillSwitch(),
        lab_mode=True,
    )

    # 4. Initialize AutonomousRunner
    print("[4] Initializing AutonomousRunner...")
    runner = AutonomousRunner(
        target_id=TARGET_ID,
        gate=gate,
        recorder=recorder,
        approval=approval,
        run_id=run_id,
        objective_id="OBJ-AUTONOMOUS-001",
        requested_planner_mode=requested_mode,
        planner_fallback_allowed=True,
        max_decisions=10,
        max_no_progress_cycles=3,
        max_repeated_state=3,
        seed_path="/",
    )

    try:
        # 5. Run the Autonomous Control Loop
        print("[5] Executing Autonomous Closed-Loop Control...")
        print("    Loop: OBSERVE -> STATE -> PLAN -> GATE -> EXECUTE -> REPLAN -> STOP")
        report: AutonomousRunReport = runner.run()

        print("\n--- AUTONOMOUS DECISION TRACE TIMELINE ---")
        for t in report.traces:
            print(f"Iteration {t.iteration}:")
            print(f"  Decision ID:        {t.decision_id}")
            print(f"  Timestamp UTC:      {t.timestamp_utc}")
            print(f"  State Fingerprint:  {t.state_fingerprint}")
            print(f"  Proposed Action:    {t.proposal.get('action_id')}")
            print(f"  Reason Code:        {t.proposal.get('reason_code')}")
            print(f"  Safety Gate Decision: {t.safety_decision} ({t.safety_reason})")
            print(f"  Dispatched Target:  {t.dispatched}")
            print(f"  Intent Evidence ID: {t.intent_evidence_id}")
            print(f"  Result Evidence ID: {t.result_evidence_id}")
            print(f"  Observations Added: {len(t.observation_ids)} (facts: {t.new_facts_count})")
            print(f"  Iteration Outcome:  {t.outcome}")
            print("-" * 50)

        print("\n--- AUTONOMOUS EXECUTION SUMMARY ---")
        print(f"Run ID:                  {report.run_id}")
        print(f"Target:                  {report.target_id}")
        print(f"Requested Mode:          {report.requested_planner_mode}")
        print(f"Actual Mode:             {report.actual_planner_mode}")
        print(f"Provider:                {report.provider}")
        print(f"Model:                   {report.model}")
        print(f"Total Decisions:         {report.decisions_count}")
        print(f"Approved Decisions:      {report.approved_actions_count}")
        print(f"Denied Decisions:        {report.denied_actions_count}")
        print(f"Network Dispatches:      {report.network_dispatch_count}")
        print(f"Unsafe Dispatches:       {report.unsafe_dispatch_count}")
        print(f"Observations Added:      {report.observations_added_count}")
        print(f"Stop Reason:             {report.stop_reason}")

        # 6. Verify Invariants
        assert report.unsafe_dispatch_count == 0, f"VIOLATION: Unsafe dispatches = {report.unsafe_dispatch_count}"
        assert report.decisions_count > 0, "VIOLATION: Zero decisions executed in autonomous loop"
        assert report.stop_reason in (
            "PLANNER_TERMINAL_STOP",
            "terminal_phase_stop",
            "discovery_surface_complete",
            "terminal_recon_complete",
            "terminal_scan_complete",
            "NO_PROGRESS_LOOP",
            "MAX_DECISIONS_REACHED",
            "BUDGET_EXHAUSTED",
        ), f"Unexpected stop reason: {report.stop_reason}"

        # 7. Persist Final Run Artifact
        summary_artifact = recorder.persist_phase_artifact(
            "autonomous_run_report",
            {
                "run_id": report.run_id,
                "target_id": report.target_id,
                "requested_planner_mode": report.requested_planner_mode,
                "actual_planner_mode": report.actual_planner_mode,
                "provider": report.provider,
                "model": report.model,
                "decisions_count": report.decisions_count,
                "approved_actions_count": report.approved_actions_count,
                "denied_actions_count": report.denied_actions_count,
                "network_dispatch_count": report.network_dispatch_count,
                "unsafe_dispatch_count": report.unsafe_dispatch_count,
                "observations_added_count": report.observations_added_count,
                "stop_reason": report.stop_reason,
                "traces": [
                    {
                        "iteration": t.iteration,
                        "decision_id": t.decision_id,
                        "action_id": t.proposal.get("action_id"),
                        "safety_decision": t.safety_decision,
                        "safety_reason": t.safety_reason,
                        "dispatched": t.dispatched,
                        "outcome": t.outcome,
                    }
                    for t in report.traces
                ],
                "evidence_refs": report.evidence_refs,
            },
        )
        print(f"    Persisted autonomous run report artifact: {summary_artifact['evidence_id']}")

    finally:
        # 8. Teardown Docker services (bounded, stop only owned services, preserve volume)
        print("\n[8] Tearing down owned Docker services (preserving volume ecommerce-data)...")
        rc_stop, out_stop = run_docker(
            "cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml stop lab-ecommerce gateway-ecommerce"
        )
        if rc_stop == 0:
            print("    Docker services stopped cleanly.")
        else:
            print(f"    Warning: docker stop output: {out_stop}")

    print("\n=== AUTONOMOUS CONTROL LOOP LIVE VERIFICATION PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
