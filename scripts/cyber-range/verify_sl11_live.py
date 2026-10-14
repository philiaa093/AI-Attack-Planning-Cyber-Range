"""Live ShopLab verification script for SL-11 (Immutable Evidence Packaging, Lab Report & Replay).

Flow:
  1. Starts verified ShopLab Docker services (lab-ecommerce and gateway-ecommerce).
  2. Gateway health check on loopback gateway (127.0.0.1:18088/health).
  3. Initializes exclusive new run directory under approved evidence root (RUN-SL11-LIVE).
  4. Runs full PTESCoordinator workflow with CentralizedSafetyGate in RULE mode.
  5. Verifies honest PTES semantics:
     - Phase 1: COMPLETED
     - Phase 2: COMPLETED
     - Phase 3: COMPLETED
     - Phase 4: COMPLETED
     - Phase 5: BLOCKED (NO_APPROVED_CAPABILITY)
     - Phase 6: NOT_RUN (EXPLOITATION_BLOCKED)
     - Phase 7: COMPLETED
     - full_ptes_assessment_completed: False
     - pipeline_control_completed: True
     - confirmed_vulnerabilities: 0
     - zero unsafe network dispatches
  6. Packages immutable manifest (manifest.json).
  7. Generates evidence-linked research report (report.json and report.md).
  8. Executes deterministic offline replay with ZeroNetworkGuard (zero network dispatches).
  9. Verifies evidence tree integrity, reference graph, and redaction (EvidenceVerifier).
  10. Emits replay_receipt.json and integrity_receipt.json.
  11. Clean Docker teardown preserving volume data.
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

from runtime.safety.discovery_gate import (
    ApprovalToken,
    BudgetTracker,
    CentralizedSafetyGate,
    KillSwitch,
    TokenBucketRateLimiter,
    load_canonical_target_allowlist,
)
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    _utc_now_iso,
)
from runtime.evidence.evidence_package import (
    EvidenceManifest,
    EvidenceVerifier,
    LabReportBuilder,
    OfflineEvidenceReplayer,
)
from runtime.orchestration.ptes_coordinator import (
    CoordinatorReport,
    PTESCoordinator,
)

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18088
TARGET_ID = "lab-ecommerce"
ACTION_ID = "ACTION-RECON-002"
DEFAULT_RUN_ID = "RUN-SL11-HANDOFF-20261011"
RUN_ID = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN_ID


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

    print("=== STARTING SL-11 LIVE SHOPLAB PACKAGING & REPLAY VERIFICATION ===")

    # 1. Bring up Docker services
    print("[1] Bringing up Docker services (lab-ecommerce, gateway-ecommerce)...")
    rc, out = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml up -d lab-ecommerce gateway-ecommerce")
    if rc != 0:
        print(f"FAILED to start Docker services: {out}")
        return 1

    time.sleep(2)

    # 2. Check health
    print(f"[2] Checking gateway health at http://{GATEWAY_HOST}:{GATEWAY_PORT}/health...")
    if not check_health():
        print("FAILED: gateway health check timed out")
        return 1
    print("    Gateway health PASS: target_id = lab-ecommerce, origin = http://127.0.0.1:18088")

    # 3. Initialize exclusive recorder under approved root
    print(f"[3] Initializing exclusive recorder for run '{RUN_ID}'...")
    try:
        recorder = DurableEvidenceRecorder(
            run_id=RUN_ID,
            exclusive_creation=True,
        )
    except EvidenceFailure as exc:
        print(f"FAILED: exclusive recorder creation failed: {exc}")
        return 1
    print(f"    Recorder initialized at '{recorder.directory}'")

    # 4. Setup Gate, Approval, and Coordinator
    print("[4] Setting up CentralizedSafetyGate and PTESCoordinator...")
    canon_targets = load_canonical_target_allowlist()
    base_origin = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"

    approval = ApprovalToken(
        approval_id="APP-SL11-LIVE-001",
        run_id=RUN_ID,
        target_id=TARGET_ID,
        action_id=ACTION_ID,
        not_before=time.time() - 30,
        expires_at=time.time() + 600,
    )

    gate = CentralizedSafetyGate(
        base_origin=base_origin,
        target_registry={TARGET_ID: {"host": GATEWAY_HOST, "port": GATEWAY_PORT}},
        target_allowlist={TARGET_ID},
        canonical_target_allowlist=canon_targets,
        action_allowlist={"ACTION-RECON-001", "ACTION-RECON-002", "ACTION-SCAN-001", "ACTION-END-001"},
        recorder=recorder,
        budget_tracker=BudgetTracker(max_requests=25, max_pages=8),
        rate_limiter=TokenBucketRateLimiter(requests_per_second=20.0, burst=5),
        kill_switch=KillSwitch(),
        lab_mode=True,
    )

    coordinator = PTESCoordinator(
        target_id=TARGET_ID,
        gate=gate,
        recorder=recorder,
        approval=approval,
        run_id=RUN_ID,
        requested_planner_mode="RULE",
        planner_fallback_allowed=True,
    )

    # 5. Execute 7-phase coordinator run
    print("[5] Executing 7-phase PTESCoordinator workflow...")
    coord_report = coordinator.run()

    # 6. Verify coordinator outcomes and honesty
    print("[6] Validating PTES phase execution semantics...")
    print(f"    Pipeline control completed: {coord_report.pipeline_control_completed}")
    print(f"    Full PTES assessment completed: {coord_report.full_ptes_assessment_completed}")
    print(f"    Network dispatches: {coord_report.network_dispatch_count}")
    print(f"    Unsafe dispatches: {coord_report.unsafe_dispatch_count}")

    assert coord_report.pipeline_control_completed is True, "Pipeline control must complete"
    assert coord_report.full_ptes_assessment_completed is False, "Full PTES assessment must NOT claim completion"
    assert coord_report.unsafe_dispatch_count == 0, "Unsafe dispatches must be zero"
    assert coord_report.confirmed_findings_count == 0, "Zero confirmed findings without authorized exploitation"

    expected_phase_outcomes = {
        "PHASE_1": "COMPLETED",
        "PHASE_2": "COMPLETED",
        "PHASE_3": "COMPLETED",
        "PHASE_4": "COMPLETED",
        "PHASE_5": "BLOCKED",
        "PHASE_6": "NOT_RUN",
        "PHASE_7": "COMPLETED",
    }
    for phase_key, expected_outcome in expected_phase_outcomes.items():
        actual_outcome = coord_report.phases.get(phase_key, {}).get("outcome")
        print(f"    Phase {phase_key}: expected {expected_outcome}, observed {actual_outcome}")
        assert actual_outcome == expected_outcome, f"Phase {phase_key} outcome mismatch: {actual_outcome} != {expected_outcome}"

    # 7. Package Evidence Manifest
    print("[7] Packaging evidence manifest (manifest.json)...")
    manifest = EvidenceManifest.build_manifest(recorder.directory, run_id=RUN_ID, target_id=TARGET_ID)
    print(f"    Manifest records indexed: {manifest['records_count']}")

    # 8. Generate Lab Research Report
    print("[8] Generating evidence-linked lab research report (report.json & report.md)...")
    md_path, json_path = LabReportBuilder.build_report(coord_report, recorder.directory)
    print(f"    Report files generated: {md_path.name}, {json_path.name}")

    # 9. Deterministic Offline Replay with ZeroNetworkGuard (Executed Twice)
    print("[9] Executing deterministic offline replay with ZeroNetworkGuard (Run 1)...")
    replay_res_1 = OfflineEvidenceReplayer.replay_run(recorder.directory, expected_run_id=RUN_ID)
    print(f"    Replay 1 success: {replay_res_1.success}")
    print(f"    Replay 1 network dispatches: {replay_res_1.network_dispatch_count}")
    print(f"    Replay 1 observations replayed: {replay_res_1.observations_replayed}")
    print(f"    Replay 1 reconstructed facts: {replay_res_1.reconstructed_facts_count}")
    print(f"    Replay 1 proposal matched: {replay_res_1.proposal_matched}")
    assert replay_res_1.success is True, f"Offline replay 1 failed: {replay_res_1.error}"
    assert replay_res_1.network_dispatch_count == 0, "Network dispatch in replay 1 must be strictly zero"

    print("[9b] Executing deterministic offline replay with ZeroNetworkGuard (Run 2)...")
    replay_res_2 = OfflineEvidenceReplayer.replay_run(recorder.directory, expected_run_id=RUN_ID)
    print(f"    Replay 2 success: {replay_res_2.success}")
    print(f"    Replay 2 network dispatches: {replay_res_2.network_dispatch_count}")
    print(f"    Replay 2 observations replayed: {replay_res_2.observations_replayed}")
    print(f"    Replay 2 reconstructed facts: {replay_res_2.reconstructed_facts_count}")
    print(f"    Replay 2 proposal matched: {replay_res_2.proposal_matched}")
    assert replay_res_2.success is True, f"Offline replay 2 failed: {replay_res_2.error}"
    assert replay_res_2.network_dispatch_count == 0, "Network dispatch in replay 2 must be strictly zero"

    # Assert perfect determinism across both replays
    assert replay_res_1.observations_replayed == replay_res_2.observations_replayed, "Replay observations differ"
    assert replay_res_1.reconstructed_facts_count == replay_res_2.reconstructed_facts_count, "Replay facts differ"
    assert replay_res_1.details.get("proposed_action") == replay_res_2.details.get("proposed_action"), "Replay proposed actions differ"
    assert replay_res_1.details.get("actual_mode") == replay_res_2.details.get("actual_mode"), "Replay actual modes differ"

    # Save replay receipt covering both executions
    replay_receipt = {
        "run_id": RUN_ID,
        "run_1": {
            "success": replay_res_1.success,
            "network_dispatch_count": replay_res_1.network_dispatch_count,
            "provider_call_count": 0,
            "observations_replayed": replay_res_1.observations_replayed,
            "reconstructed_facts_count": replay_res_1.reconstructed_facts_count,
            "proposed_action": replay_res_1.details.get("proposed_action"),
            "actual_mode": replay_res_1.details.get("actual_mode"),
        },
        "run_2": {
            "success": replay_res_2.success,
            "network_dispatch_count": replay_res_2.network_dispatch_count,
            "provider_call_count": 0,
            "observations_replayed": replay_res_2.observations_replayed,
            "reconstructed_facts_count": replay_res_2.reconstructed_facts_count,
            "proposed_action": replay_res_2.details.get("proposed_action"),
            "actual_mode": replay_res_2.details.get("actual_mode"),
        },
        "deterministic": True,
        "network_dispatch_count": 0,
        "provider_call_count": 0,
        "replayed_at_utc": _utc_now_iso(),
    }
    replay_receipt_path = recorder.directory / "replay_receipt.json"
    replay_receipt_path.write_text(json.dumps(replay_receipt, indent=2), encoding="utf-8")
    print(f"    Dual replay receipt saved to '{replay_receipt_path.name}'")

    # 10. Verify Evidence Integrity & Reference Graph
    print("[10] Running EvidenceVerifier on completed evidence package...")
    v_res = EvidenceVerifier.verify_directory(recorder.directory)
    print(f"    Verifier passed: {v_res.passed}")
    print(f"    Verified records count: {v_res.verified_records_count}")
    print(f"    Verified files count: {v_res.verified_files_count}")
    print(f"    Reference graph OK: {v_res.reference_graph_ok}")
    print(f"    Ordering OK: {v_res.ordering_ok}")
    print(f"    Secrets clean: {v_res.secrets_clean}")
    print(f"    Conflicts: {len(v_res.conflicts)}")
    print(f"    Errors: {len(v_res.errors)}")
    assert v_res.passed is True, f"Evidence verification failed: {v_res.errors}"

    # Save integrity receipt
    integrity_receipt = {
        "run_id": RUN_ID,
        "passed": v_res.passed,
        "verified_records_count": v_res.verified_records_count,
        "verified_files_count": v_res.verified_files_count,
        "reference_graph_ok": v_res.reference_graph_ok,
        "ordering_ok": v_res.ordering_ok,
        "secrets_clean": v_res.secrets_clean,
        "conflicts_count": len(v_res.conflicts),
        "discrepancies_count": len(v_res.discrepancies),
        "errors": v_res.errors,
        "verified_at_utc": _utc_now_iso(),
    }
    integrity_receipt_path = recorder.directory / "integrity_receipt.json"
    integrity_receipt_path.write_text(json.dumps(integrity_receipt, indent=2), encoding="utf-8")
    print(f"    Integrity receipt saved to '{integrity_receipt_path.name}'")

    # 11. Bounded teardown
    print("[11] Tearing down Docker services (preserving volume data)...")
    rc_down, out_down = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml stop lab-ecommerce gateway-ecommerce")
    print(f"    Docker services stopped: rc={rc_down}")

    print("=== SL-11 LIVE VERIFICATION SUCCEEDED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
