"""Live ShopLab PTES Coordinator Runner."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.discovery_gate import (
    ApprovalToken,
    BudgetTracker,
    CentralizedSafetyGate,
    KillSwitch,
    TokenBucketRateLimiter,
    load_canonical_target_allowlist,
)
from runtime.discovery_recorder import DurableEvidenceRecorder
from runtime.ptes_coordinator import PTESCoordinator


def main() -> None:
    evidence_dir = Path("reports/live_coordinator_evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"RUN-LIVE-SHOPLAB-{int(time.time())}"

    rec = DurableEvidenceRecorder(run_id=run_id, base_dir=evidence_dir)
    canon_targets = load_canonical_target_allowlist()

    app = ApprovalToken(
        approval_id="APP-LIVE-SL10",
        run_id=run_id,
        target_id="lab-ecommerce",
        action_id="ACTION-RECON-002",
        not_before=time.time() - 10,
        expires_at=time.time() + 600,
    )

    gate = CentralizedSafetyGate(
        base_origin="http://127.0.0.1:18088",
        target_registry={"lab-ecommerce": {"host": "127.0.0.1", "port": 18088}},
        target_allowlist={"lab-ecommerce"},
        canonical_target_allowlist=canon_targets,
        action_allowlist={"ACTION-RECON-001", "ACTION-RECON-002", "ACTION-SCAN-001", "ACTION-END-001"},
        recorder=rec,
        budget_tracker=BudgetTracker(max_requests=15, max_pages=5),
        rate_limiter=TokenBucketRateLimiter(requests_per_second=20.0, burst=5),
        kill_switch=KillSwitch(),
        lab_mode=True,
    )

    coord = PTESCoordinator(
        target_id="lab-ecommerce",
        gate=gate,
        recorder=rec,
        approval=app,
        run_id=run_id,
        requested_planner_mode="RULE",
        planner_fallback_allowed=True,
    )

    report = coord.run()

    print("=== LIVE COORDINATOR RUN COMPLETED ===")
    print(f"Run ID: {report.run_id}")
    print(f"Target ID: {report.target_id}")
    print(f"Pipeline Control Completed: {report.pipeline_control_completed}")
    print(f"Full PTES Assessment Completed: {report.full_ptes_assessment_completed}")
    print(f"Network Dispatches: {report.network_dispatch_count}")
    print(f"Unsafe Dispatches: {report.unsafe_dispatch_count}")
    print(f"Inventory Count: {report.observed_inventory_count}")
    print(f"Hypotheses Count: {report.hypotheses_count}")
    print(f"Candidate Findings: {report.candidate_findings_count}")
    print(f"Negative Results: {report.negative_results_count}")
    print(f"Confirmed Findings: {report.confirmed_findings_count}")
    print("Phase Statuses:")
    for p_name, p_data in report.phases.items():
        print(f"  {p_name} ({p_data['phase_id']}, {p_data['phase_name']}): {p_data['outcome']} | Reason: {p_data['transition_reason']}")
    print(f"Evidence Artifacts ({len(report.evidence_refs)}):")
    for ev in report.evidence_refs:
        print(f"  - {ev}")


if __name__ == "__main__":
    main()
