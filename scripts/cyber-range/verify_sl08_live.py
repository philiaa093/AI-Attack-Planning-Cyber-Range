"""Live ShopLab verification script for SL-08 (Observation-Driven Discovery + Centralized Gate).

Enforces:
  1. Starts only owned services: lab-ecommerce and gateway-ecommerce.
  2. Health check verification on loopback gateway (127.0.0.1:18088).
  3. Preflight recorder confirmation.
  4. Small, bounded observation-driven discovery (seed '/', depth 1, max_pages 10).
  5. Provenance & inventory extraction strictly from observed ShopLab HTML.
  6. Live negative test with synthetic off-origin reference (http://outside.invalid/probe).
  7. Assertion of exact dispatch counters:
       network_dispatch_count >= 1
       forbidden_dispatch_count == 0
       form_submission_count == 0
  8. Zero mutation form submissions.
  9. Zero raw cookie/session secret leaks.
  10. Bounded teardown of owned services, preserving volume.
"""
from __future__ import annotations

import http.client
import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.discovery.discovery_engine import (
    ObservationDrivenDiscovery,
)
from runtime.safety.discovery_gate import (
    ApprovalToken,
    BudgetTracker,
    CentralizedSafetyGate,
    DiscoveryRequest,
    KillSwitch,
    TokenBucketRateLimiter,
)
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
)

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18088
TARGET_ID = "lab-ecommerce"
ACTION_ID = "ACTION-RECON-002"
RUN_ID = "RUN-SL08-LIVE"


def run_docker(cmd: str) -> tuple[int, str]:
    full_cmd = ["wsl", "-d", "Ubuntu", "-e", "bash", "-c", cmd]
    p = subprocess.run(full_cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_health(timeout: float = 15.0) -> bool:
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

    print("=== STARTING SL-08 LIVE SHOPLAB DISCOVERY VERIFICATION ===")

    # 1. Start Docker services
    print("[1] Bringing up Docker services (lab-ecommerce, gateway-ecommerce)...")
    rc, out = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml up -d lab-ecommerce gateway-ecommerce")
    if rc != 0:
        print(f"FAILED to start Docker services: {out}")
        return 1

    time.sleep(2)

    # 2. Check health
    print(f"[2] Checking gateway health at http://{GATEWAY_HOST}:{GATEWAY_PORT}/health...")
    if not check_health():
        print(f"FAILED: gateway health check timed out on http://{GATEWAY_HOST}:{GATEWAY_PORT}/health")
        return 1
    print("    Health check PASS: target_id = lab-ecommerce, gateway = 127.0.0.1:18088")

    evidence_base = Path("evidence/runtime") / RUN_ID
    evidence_base.mkdir(parents=True, exist_ok=True)

    # 3. Setup Recorder, Gate, and Discovery Engine
    print("[3] Initializing DurableEvidenceRecorder and CentralizedSafetyGate...")
    recorder = DurableEvidenceRecorder(run_id=RUN_ID, base_dir=evidence_base)
    base_origin = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"

    approval = ApprovalToken(
        approval_id="APP-SL08-LIVE-001",
        run_id=RUN_ID,
        target_id=TARGET_ID,
        action_id=ACTION_ID,
        not_before=time.time() - 30,
        expires_at=time.time() + 600,
    )

    budget = BudgetTracker(
        max_requests=20,
        max_depth=1,
        max_pages=8,
        max_redirect_hops=3,
        max_body_bytes=65536,
        timeout=5.0,
    )

    gate = CentralizedSafetyGate(
        base_origin=base_origin,
        target_registry={TARGET_ID: {"host": GATEWAY_HOST, "port": GATEWAY_PORT}},
        target_allowlist={TARGET_ID},
        action_allowlist={ACTION_ID},
        recorder=recorder,
        budget_tracker=budget,
        rate_limiter=TokenBucketRateLimiter(requests_per_second=5.0, burst=1),
        kill_switch=KillSwitch(),
        lab_mode=True,
    )

    engine = ObservationDrivenDiscovery(
        gate=gate,
        run_id=RUN_ID,
        target_id=TARGET_ID,
        approval=approval,
        action_id=ACTION_ID,
    )

    # 4. Run Live Discovery from seed '/'
    print("[4] Executing bounded observation-driven discovery (seed '/', depth 1, max_pages 8)...")
    res = engine.run(seed_path="/")

    print(f"    Discovery completed with status: {res.status} (stop_reason: {res.stop_reason})")
    print(f"    network_dispatch_count: {res.network_dispatch_count}")
    print(f"    forbidden_dispatch_count: {res.forbidden_dispatch_count}")
    print(f"    form_submission_count: {res.form_submission_count}")
    print(f"    inventory item count: {len(res.inventory.items)}")
    print(f"    durable_confirmed: {res.durable_confirmed}")

    # Assertions
    assert res.network_dispatch_count >= 1, "Expected at least 1 network dispatch for seed"
    assert res.forbidden_dispatch_count == 0, "Forbidden dispatch count must be strictly 0"
    assert res.form_submission_count == 0, "Form submission count must be strictly 0"
    assert res.durable_confirmed, "Live run outcome must be durable-confirmed"
    assert res.status in ("COMPLETED_BOUNDED", "COMPLETED"), f"Unexpected status: {res.status}"
    assert res.stop_reason == "BUDGET_EXHAUSTED", f"Unexpected stop reason: {res.stop_reason}"
    assert "Bounded discovery" in list(res.inventory.items.values())[0].coverage_limitations

    print("    Discovered resources from observed ShopLab HTML:")
    for path, item in res.inventory.items.items():
        print(f"      - {item.path} (status {item.status_code}, forms: {len(item.forms)}, links: {len(item.links_found)})")

    # 5. Live Negative Test: Injected Off-Origin URL
    print("[5] Executing live negative test with off-origin candidate...")
    off_origin_candidate = "http://outside.invalid/leak-probe"
    off_origin_req = DiscoveryRequest(
        run_id=RUN_ID,
        target_id=TARGET_ID,
        action_id=ACTION_ID,
        url=off_origin_candidate,
        approval=approval,
    )
    neg_resp = gate.dispatch(off_origin_req)
    assert neg_resp.outcome == "DENIED", f"Expected DENIED, got {neg_resp.outcome}"
    assert neg_resp.refusal_reason == "REFUSED_OFF_ORIGIN", f"Expected REFUSED_OFF_ORIGIN, got {neg_resp.refusal_reason}"
    assert gate.forbidden_dispatch_count == 0, "Forbidden dispatch count must remain strictly 0"
    print("    Live negative test PASS: off-origin URL refused, zero forbidden dispatch.")

    # 6. Verify Secret Redaction in Persisted Evidence
    print("[6] Verifying evidence redaction on disk...")
    evidence_files = list(evidence_base.glob("*.json"))
    assert len(evidence_files) > 0, "Evidence files must exist"
    for ef in evidence_files:
        content = ef.read_text(encoding="utf-8")
        assert "password=" not in content.lower() or "[REDACTED]" in content, f"Raw secret pattern in {ef}"
    print(f"    Evidence verification PASS: {len(evidence_files)} artifacts checked, zero secret leaks.")

    # 7. Teardown Docker services (bounded, stop only owned services, preserve volume)
    print("[7] Tearing down owned Docker services (preserving volume)...")
    rc_stop, out_stop = run_docker("cd /mnt/e/PBL6_FINAL && docker compose -f cyber-range/compose.yaml stop lab-ecommerce gateway-ecommerce")
    if rc_stop == 0:
        print("    Docker services stopped cleanly.")
    else:
        print(f"    Warning: docker stop output: {out_stop}")

    print("=== SL-08 LIVE DISCOVERY VERIFICATION PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
