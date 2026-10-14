"""Demo đọc-only ShopLab: chỉ điều phối API hiện có, không thực thi proposal."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

def _ensure_docker_on_path() -> None:
    if shutil.which("docker"):
        return
    candidates = [
        r"C:\Program Files\Docker\Docker\resources\bin",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin"),
        os.path.expanduser(r"~\AppData\Local\Programs\DockerDesktop\resources\bin"),
    ]
    for cand in candidates:
        if os.path.isdir(cand) and (os.path.isfile(os.path.join(cand, "docker.exe")) or os.path.isfile(os.path.join(cand, "docker"))):
            os.environ["PATH"] = cand + os.pathsep + os.environ.get("PATH", "")
            break

_ensure_docker_on_path()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.memory.state.state_manager import StateManager
from runtime.discovery.discovery_engine import ObservationDrivenDiscovery
from runtime.safety.discovery_gate import (
    ApprovalToken, BudgetTracker, CentralizedSafetyGate, DiscoveryRequest,
    TokenBucketRateLimiter, load_canonical_target_registry,
)
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder, EvidenceFailure, redact_secrets
from runtime.evidence.evidence_package import EvidenceVerifier
from runtime.planners.observed_planner import ObservedStatePlanner
from runtime.planners.planner_adapter import PlannerStateAdapter

TARGET = "lab-ecommerce"
ORIGIN = "http://127.0.0.1:18088"
ACTION = "ACTION-RECON-002"
SERVICES = (TARGET, "gateway-ecommerce")
COMPOSE = ROOT / "cyber-range/compose.yaml"
OUTPUT = Path(__file__).resolve().parent / "demo-output"
PHASES = ("PRE_ENGAGEMENT", "INTELLIGENCE_GATHERING", "THREAT_MODELING",
          "VULNERABILITY_ANALYSIS", "EXPLOITATION", "POST_EXPLOITATION", "REPORTING")


class DemoBlocked(RuntimeError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def section(title):
    print("\n" + "=" * 48 + "\n" + title + "\n" + "=" * 48)


def show(label, value):
    # Dữ liệu target chỉ được trình bày một dòng, không control sequence.
    text = str(redact_secrets(value))
    text = "".join(c if c.isprintable() else " " for c in text)
    print(f"{label}: {text[:450]}")


def docker(*args):
    try:
        result = subprocess.run(["docker", *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DemoBlocked("DOCKER_UNAVAILABLE") from exc
    if result.returncode:
        # Không dump stderr: Docker có thể in configuration chứa thông tin nhạy cảm.
        raise DemoBlocked("DOCKER_COMMAND_FAILED")
    return result.stdout


def compose(*args):
    return docker("compose", "-f", str(COMPOSE), *args)


def service_snapshot():
    rows = []
    for service in SERVICES:
        ids = compose("ps", "--all", "--quiet", service).split()
        if len(ids) > 1:
            raise DemoBlocked("AMBIGUOUS_SERVICE_OWNERSHIP")
        if ids:
            rows.extend(json.loads(docker("inspect", ids[0])))
    return {row["Config"]["Labels"]["com.docker.compose.service"]: row for row in rows}


def inspect_runtime(rows):
    for service in SERVICES:
        row = rows.get(service)
        if not row or not row["State"]["Running"]:
            raise DemoBlocked("RUNTIME_UNAVAILABLE")
        if row["Config"]["Labels"].get("com.docker.compose.project") != "cyber-range":
            raise DemoBlocked("UNEXPECTED_COMPOSE_PROJECT")
        networks = row["NetworkSettings"]["Networks"]
        if "cyber-range_lab" not in networks:
            raise DemoBlocked("LAB_NETWORK_MISSING")
        if service == TARGET:
            if set(networks) != {"cyber-range_lab"} or row["HostConfig"].get("PortBindings"):
                raise DemoBlocked("TARGET_ISOLATION_INVALID")
            if not any(m.get("Type") == "volume" and m.get("Destination") == "/app/data"
                       and m.get("Name") == "cyber-range_ecommerce-data" for m in row["Mounts"]):
                raise DemoBlocked("PERSISTENT_VOLUME_MISSING")
        else:
            bindings = row["HostConfig"].get("PortBindings") or {}
            if bindings != {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18088"}]}:
                raise DemoBlocked("GATEWAY_BINDING_INVALID")
    network = json.loads(docker("network", "inspect", "cyber-range_lab"))[0]
    if network.get("Internal") is not True:
        raise DemoBlocked("LAB_NETWORK_NOT_INTERNAL")


def start_services(owned):
    config = json.loads(COMPOSE.read_text(encoding="utf-8"))
    target = config["services"][TARGET]
    gateway = config["services"]["gateway-ecommerce"]
    if (config["networks"]["lab"].get("internal") is not True
            or target.get("networks") != ["lab"] or target.get("ports")
            or target.get("volumes") != ["ecommerce-data:/app/data"]
            or gateway.get("ports") != ["127.0.0.1:18088:8080"]
            or gateway.get("environment", {}).get("TARGET_HOST") != TARGET):
        raise DemoBlocked("COMPOSE_SCOPE_INVALID")
    before = service_snapshot()
    # ponytail: chỉ hai service cố định; không quản lý toàn bộ Docker project.
    for service in SERVICES:
        prior = before.get(service)
        if prior and prior["State"]["Running"]:
            continue
        if prior:
            compose("start", service)
        else:
            image = "cyber-range-lab-ecommerce:latest" if service == TARGET else "cyber-range-gateway:latest"
            docker("image", "inspect", image)
            compose("up", "-d", "--no-build", "--pull", "never", "--no-deps", "--no-recreate", service)
        after = service_snapshot().get(service)
        if not after or (prior and after["Id"] != prior["Id"]):
            raise DemoBlocked("SERVICE_IDENTITY_CHANGED")
        owned[service] = after["Id"]


def stop_owned(owned):
    if not owned:
        return "NOT_RUN_NO_OWNED_SERVICES"
    rows = service_snapshot()
    for service in reversed(SERVICES):
        if service not in owned:
            continue
        row = rows.get(service)
        if not row or row["Id"] != owned[service]:
            raise DemoBlocked("CLEANUP_OWNERSHIP_UNRESOLVED")
        # Stop theo container ID đã xác minh, không down/rm/prune hoặc xóa volume.
        docker("stop", "--time", "10", owned[service])
        current = json.loads(docker("inspect", owned[service]))[0]
        if current["State"]["Running"]:
            raise DemoBlocked("SERVICE_STOP_UNVERIFIED")
    docker("volume", "inspect", "cyber-range_ecommerce-data")
    return "OWNED_SERVICES_STOPPED_VOLUME_PRESERVED"


def new_recorder(directory, run_id):
    return DurableEvidenceRecorder(run_id, base_dir=directory, source="OPERATOR",
                                   exclusive_creation=True, approved_root=OUTPUT)


def make_gate(recorder, origin=ORIGIN, pages=8):
    registry = load_canonical_target_registry()
    gate = CentralizedSafetyGate(
        base_origin=origin, target_registry=registry, target_allowlist={TARGET},
        action_allowlist={ACTION, "ACTION-RECON-001", "ACTION-SCAN-001", "ACTION-END-001",
                          "ACTION-END-002", "ACTION-END-003"},
        recorder=recorder, budget_tracker=BudgetTracker(max_requests=pages, max_pages=pages,
            max_depth=2, max_retries=0, timeout=3),
        rate_limiter=TokenBucketRateLimiter(requests_per_second=2.0, burst=1), lab_mode=True,
    )
    if TARGET not in gate.effective_targets or ACTION not in gate.effective_actions:
        raise DemoBlocked("CANONICAL_POLICY_NOT_READY")
    if TARGET not in registry or registry[TARGET].get("port") != 18088:
        raise DemoBlocked("TARGET_MANIFEST_MISMATCH")
    return gate


def approval_for(run_id):
    now = time.time()
    return ApprovalToken("APP-DEMO-" + uuid.uuid4().hex, run_id, TARGET, ACTION, now, now + 180)


def verify(recorder):
    result = EvidenceVerifier.verify_directory(recorder.directory)
    if not result.passed:
        reason = "CORE_EVIDENCE_VERIFIER_ORDERING" if not result.ordering_ok else "EVIDENCE_VERIFICATION_FAILED"
        raise DemoBlocked(reason)
    return {"passed": result.passed, "records": result.verified_records_count,
            "verified_files": result.verified_files_count, "hashes": "VERIFIED",
            "redaction_check_passed": result.secrets_clean, "ordering": result.ordering_ok}


def deny_case(gate, recorder):
    planner = ObservedStatePlanner(TARGET, effective_targets=gate.effective_targets)
    permitted_example = {"target_id": TARGET, "action_id": ACTION}
    permitted = planner.evaluate_proposal_against_gate(permitted_example, gate)
    recorder.persist_phase_artifact("demo_permitted_proposal_example", {"synthetic": True, "proposal": permitted_example, "evaluation": permitted})
    section("SAFETY APPROVE — PROPOSAL SYNTHETIC ĐỌC-ONLY")
    show("Decision", permitted["decision"])
    show("Network dispatch", 0)
    show("Phạm vi kiểm tra", "target/action/kill/budget; approval/origin/rate NOT_EVALUATED")
    synthetic = {"target_id": "lab-not-approved", "action_id": ACTION}
    recorder.persist_phase_artifact("demo_deny_intent", {"synthetic": True, "proposal": synthetic})
    before = gate.network_dispatch_count
    response = gate.dispatch(DiscoveryRequest(recorder.run_id, synthetic["target_id"], ACTION,
                                             gate.base_origin + "/", approval=None))
    result = {"synthetic": True, "target": synthetic["target_id"], "decision": response.outcome,
              "reason": response.refusal_reason, "network_dispatch_delta": gate.network_dispatch_count - before,
              "proposal_evaluation": planner.evaluate_proposal_against_gate(synthetic, gate)}
    recorder.persist_phase_artifact("demo_deny_decision", result)
    if result["decision"] != "DENIED" or result["network_dispatch_delta"] != 0:
        raise DemoBlocked("DENY_INVARIANT_FAILED")
    recorder.persist_phase_artifact("demo_deny_result", result)
    section("SAFETY DENY — CA SYNTHETIC, KHÔNG GỬI NGOÀI LAB")
    for key in ("target", "decision", "reason", "network_dispatch_delta"):
        show(key, result[key])
    return result


def assess(gate, recorder, approval, planner_mode="rule", fallback=False, preview=False, summary=None):
    if approval is None or not approval.is_valid()[0]:
        raise DemoBlocked("MISSING_OR_INVALID_RUN_APPROVAL")
    section("DISCOVERY TỪ HTML THỰC TẾ")
    show("Seed", "/")
    show("Approval", "VALID" if approval and approval.is_valid()[0] else "MISSING")
    show("Giới hạn requests/pages", gate.budget_tracker.max_requests)
    started = time.monotonic()
    state = StateManager(recorder.run_id, "SCN-001", "OBJ-DEMO-001",
                         {"actions": 16, "requests": gate.budget_tracker.max_requests, "seconds": 180})
    dispatch = gate.dispatch

    def checked_dispatch(request):
        response = dispatch(request)
        if not response.durable_confirmed and response.outcome != "DENIED":
            raise DemoBlocked("EVIDENCE_NOT_DURABLE")
        if response.outcome in ("ERROR", "FAILURE"):
            raise DemoBlocked("DISCOVERY_RESPONSE_ERROR")
        return response

    # Chỉ propagate lỗi lifecycle; transport và mọi policy check vẫn thuộc core gate.
    gate.dispatch = checked_dispatch
    try:
        result = ObservationDrivenDiscovery(gate, recorder.run_id, TARGET, approval,
                                            state_manager=state).run("/")
    finally:
        gate.dispatch = dispatch
        state.decrement_requests(gate.network_dispatch_count)
        state.decrement_seconds(time.monotonic() - started)
    items = list(result.inventory.items.values())
    details = {"resources": len(items), "requests": result.network_dispatch_count,
               "forms_observed": sum(len(item.forms) for item in items),
               "forms_submitted": result.form_submission_count,
               "forbidden_dispatch_counter": result.forbidden_dispatch_count,
               "discovery_outcome": result.status, "stop_reason": result.stop_reason,
               "coverage": "ONE_PAGE_PREVIEW" if preview else "BOUNDED"}
    for index, item in enumerate(items[:4], 1):
        show(f"Resource {index}", f"{item.path} | status={item.status_code} | links={len(item.links_found)} | forms={len(item.forms)}")
    for key, value in details.items():
        show(key, value)
    minimized = PlannerStateAdapter(state).get_minimized_planner_state()
    section("NORMALIZATION → STATE")
    for fact in minimized["observed_facts"][:4]:
        show("Fact", {k: fact.get(k) for k in ("fact_type", "value", "source_observation_id", "confidence")})
    show("Observed facts", minimized["fact_count"])
    show("Endpoints", len(minimized["discovered_endpoints"]))
    show("Services", len(minimized["discovered_services"]))
    show("Previous safe actions", minimized.get("previous_actions", []))
    show("Remaining budget", minimized["remaining_budget"])
    recorder.persist_phase_artifact("demo_discovery_state", {"discovery": details, "state": minimized})
    if summary is not None:
        summary["discovery"] = details
        summary["state_summary"] = {"facts": minimized["fact_count"], "endpoints": len(minimized["discovered_endpoints"]),
                                    "remaining_budget": minimized["remaining_budget"]}
    if result.status not in ("COMPLETED", "COMPLETED_BOUNDED") or not result.durable_confirmed:
        raise DemoBlocked("DISCOVERY_STOPPED")
    evidence = verify(recorder)  # Không cho planner tiếp tục khi evidence chưa hợp lệ.
    planner = ObservedStatePlanner(TARGET, requested_mode="RULE" if planner_mode == "rule" else "LLM",
        fallback_allowed=fallback, effective_targets=gate.effective_targets,
        provider_callable=(lambda _system, _user: None) if planner_mode != "rule" else None)
    proposal = planner.propose(minimized)
    recorder.persist_phase_artifact("demo_planner", asdict(proposal))
    if summary is not None:
        summary["planner_provenance"] = proposal.mode_provenance
        summary["actual_planner_mode"] = proposal.mode_provenance.get("actual_mode")
    section("PLANNER — PROPOSAL, KHÔNG EXECUTE")
    for key, value in proposal.proposal.items():
        show(key, value)
    for key in ("requested_mode", "actual_mode", "fallback_reason", "decision_origin"):
        show(key, proposal.mode_provenance.get(key))
    if planner_mode != "rule":
        show("Requested mode", "LLM")
        show("Actual mode", proposal.mode_provenance.get("actual_mode"))
        show("Fallback", "PROVIDER_UNAVAILABLE — injected, không gọi LLM")
        show("Provider", "PROVIDER_NOT_CALLED_OFFLINE_DEMO")
    if not proposal.is_valid or proposal.mode_provenance.get("actual_mode") == "NONE":
        raise DemoBlocked("PLANNER_HALTED")
    decision = planner.evaluate_proposal_against_gate(proposal.proposal, gate)
    recorder.persist_phase_artifact("demo_proposal_decision", decision)
    show("Safety proposal evaluation", decision["decision"])
    show("Approval/origin/rate trong proposal evaluator", "NOT_EVALUATED — full checks thuộc dispatch gate")
    show("PLANNER TARGET DISPATCH COUNT", 0)
    return {"discovery": details, "state_summary": {"facts": minimized["fact_count"],
            "endpoints": len(minimized["discovered_endpoints"]), "remaining_budget": minimized["remaining_budget"]},
            "planner_provenance": proposal.mode_provenance, "proposal": proposal.proposal,
            "proposal_decision": decision, "evidence_verification": evidence}


def write_receipt(directory, summary):
    raw = json.dumps(redact_secrets(summary), ensure_ascii=False, indent=2).encode("utf-8")
    for name, data in (("summary.json", raw), ("summary.sha256", hashlib.sha256(raw).hexdigest().encode("ascii"))):
        with (directory / name).open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())


def file_hashes(directory):
    """Chụp bytes của run hiện tại; không tìm hoặc tái dùng run cũ."""
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise DemoBlocked("RECEIPT_PATH_ESCAPE")
        if path.is_file():
            result[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check_files(directory, expected):
    for name, digest in expected.items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
            raise DemoBlocked("RECEIPT_PATH_ESCAPE")
        raw = path.read_bytes()  # Thiếu file phải dừng; không lấy receipt cũ thay thế.
        if hashlib.sha256(raw).hexdigest() != digest:
            raise DemoBlocked("RECEIPT_HASH_CHANGED")
        if path.suffix == ".json":
            json.loads(raw)


def check_receipt(directory, run_id):
    raw = (directory / "summary.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (directory / "summary.sha256").read_text(encoding="ascii"):
        raise DemoBlocked("SUMMARY_HASH_MISMATCH")
    summary = json.loads(raw)
    if summary["run_id"] != run_id or directory.name != run_id:
        raise DemoBlocked("STALE_RECEIPT_REJECTED")
    groups = [(summary.get("evidence_refs", []), run_id)]
    groups.append((summary.get("health", {}).get("evidence_refs", []), run_id + "-HEALTH"))
    for refs, expected_id in groups:
        for ref in refs:
            path = Path(ref["record_path"])
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise DemoBlocked("EVIDENCE_REFERENCE_ESCAPE")
            record = json.loads(path.read_bytes())
            if record["run_id"] != expected_id or record["evidence_id"] != ref["evidence_id"]:
                raise DemoBlocked("STALE_EVIDENCE_REJECTED")
            artifact = Path(record["path"])
            if not artifact.is_absolute():
                artifact = ROOT / artifact
            if artifact.is_symlink() or not artifact.resolve().is_relative_to(directory.resolve()):
                raise DemoBlocked("EVIDENCE_REFERENCE_ESCAPE")
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != ref["sha256"] or record["sha256"] != ref["sha256"]:
                raise DemoBlocked("EVIDENCE_HASH_MISMATCH")
            json.loads(artifact.read_bytes())
    return summary


def write_json_exclusive(path, data):
    with path.open("xb") as handle:
        handle.write(json.dumps(redact_secrets(data), ensure_ascii=False, indent=2).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def parser():
    cli = argparse.ArgumentParser(description="Demo ShopLab đọc-only, không exploitation hoặc provider Internet.")
    cli.add_argument("--mode", choices=("presentation", "safe", "deny-demo"), default="presentation")
    cli.add_argument("--planner", choices=("rule", "llm-unavailable"), default="rule")
    cli.add_argument("--allow-rule-fallback", action="store_true")
    cli.add_argument("--approve-read-only", action="store_true", help="Phê duyệt GET lab cho invocation này, tối đa 180 giây.")
    cli.add_argument("--dry-run", action="store_true", help="Preflight; chỉ health GET nếu có approval, không assessment.")
    cli.add_argument("--start", action="store_true", help="Start hai service cố định; không build/pull/recreate.")
    cli.add_argument("--stop-owned", action="store_true", help="Stop dịch vụ invocation này đã start; giữ volume.")
    cli.add_argument("--preview-one-page", action="store_true", help="Preview một trang, KHÔNG nghiệm thu demo đa trang.")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    if args.dry_run and args.start:
        parser().error("--dry-run không được start service")
    run_id = "RUN-DEMO-" + uuid.uuid4().hex
    directory = OUTPUT / run_id
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError:
        show("Demo", "BLOCKED — RUN_DIRECTORY_COLLISION_OR_UNWRITABLE")
        return 2
    started = time.monotonic()
    # Sentinel mới chỉ đo ranh giới bảo toàn receipts, không tuyên bố DB đã reset.
    sentinel = directory / "boundary.txt"
    try:
        with sentinel.open("xb") as handle:
            handle.write((run_id + "\nDEMO_RECEIPT_BOUNDARY\n").encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        show("Demo", "BLOCKED — SENTINEL_WRITE_FAILED, thư mục incomplete được giữ lại")
        return 2
    summary = {"run_id": run_id, "target": TARGET, "origin": ORIGIN, "seed": "/", "source": "OPERATOR",
               "started_at_utc": utc(), "expected_state": "BOUNDED_DEMO_WITH_LIMITATIONS",
               "observed_state": "NOT_RUN", "demo_outcome": "BLOCKED", "approval": "NOT_GRANTED",
               "coordinator_execution": "NOT_RUN", "ptes_phases": {p: "NOT_RUN" for p in PHASES},
               "full_ptes_assessment_completed": False, "exploitation_policy": "NOT_AUTHORIZED",
               "requested_planner_mode": "RULE" if args.planner == "rule" else "LLM",
               "actual_planner_mode": "NOT_RUN", "restore_evidence": "NOT_RUN",
               "restore": "NOT_RUN", "confirmed_findings": 0, "candidate_findings": "NOT_ASSESSED",
               "limitations": ["Không đánh giá vulnerability hay full PTES.",
                   "Coordinator chưa chạy: blocker double-apply observations.",
                   "Verifier failure bất kỳ dừng demo trước proposal; không bypass.",
                   "Proposal evaluator không phải full dispatch authorization.",
                   "Không gọi LLM thật hoặc restore; hashes không phải WORM storage."], "blockers": []}
    summary["receipt_role"] = "PRESENTATION_SUMMARY_NOT_AUTHORITATIVE_EVIDENCE"
    summary["sentinel_hash_before"] = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    owned, recorder, gate, health_rec = {}, None, None, None
    exit_code = 2
    try:
        recorder = new_recorder(directory / "assessment", run_id)
        gate = make_gate(recorder, pages=1 if args.preview_one_page else 8)
        recorder.persist_phase_artifact("demo_scope", {"scope": summary, "approval_requested": args.approve_read_only})
        if args.mode == "deny-demo":
            summary["safety_deny"] = deny_case(gate, recorder)
            summary["evidence_verification"] = verify(recorder)
            summary.update(demo_outcome="DENY_DEMO_COMPLETED", observed_state="DENIED_ZERO_DISPATCH")
            exit_code = 0
        else:
            section("SHOPLAB / DEMO PREFLIGHT")
            docker("version", "--format", "{{.Server.Version}}")
            docker("image", "inspect", "cyber-range-lab-ecommerce:latest", "cyber-range-gateway:latest")
            show("Docker và images local", "PASS")
            show("Target/action canonical allowlist", "PASS")
            show("Evidence writable", "PASS — ghi durable scope thành công")
            show("Gateway", ORIGIN)
            show("Safety", "LAB ONLY")
            if args.start:
                start_services(owned)
            inspect_runtime(service_snapshot())
            show("Runtime configuration", "PASS — không chứng minh toàn bộ egress isolation")
            if not args.approve_read_only:
                show("Health", "NOT_CHECKED — thiếu per-run approval")
                raise DemoBlocked("MISSING_RUN_APPROVAL")
            health_id = run_id + "-HEALTH"
            health_rec = new_recorder(directory / "health", health_id)
            health_gate = make_gate(health_rec, pages=1)
            health_approval = approval_for(health_id)
            health = health_gate.dispatch(DiscoveryRequest(health_id, TARGET, ACTION, ORIGIN + "/health", approval=health_approval))
            summary["health"] = {"status_code": health.status_code, "dispatch_count": health_gate.network_dispatch_count,
                                 "durable_confirmed": health.durable_confirmed}
            if not health.durable_confirmed:
                raise DemoBlocked("HEALTH_EVIDENCE_FAILURE")
            if health.status_code != 200 or health.outcome != "SUCCESS":
                raise DemoBlocked("RUNTIME_HEALTH_FAILED")
            summary["health"]["verification"] = verify(health_rec)
            summary["health"]["evidence_refs"] = [{"evidence_id": a["evidence_id"], "sha256": a["sha256"],
                                                      "record_path": a["record_path"]} for a in health_rec.artifacts]
            show("Health", "PASS — GET qua gate và recorder riêng")
            if args.dry_run:
                summary.update(demo_outcome="PREFLIGHT_READY", observed_state="HEALTH_VERIFIED_NO_ASSESSMENT")
                show("Preflight", "PIPELINE_AVAILABLE — READY chỉ sau kiểm tra receipts cuối run")
            else:
                approval = approval_for(run_id)
                summary["approval"] = {"approval_id": approval.approval_id, "timestamp_utc": utc(),
                                       "target": TARGET, "action": ACTION, "expires_at": approval.expires_at}
                recorder.persist_phase_artifact("demo_authorization", summary["approval"])
                summary.update(assess(gate, recorder, approval, args.planner, args.allow_rule_fallback, args.preview_one_page, summary))
                # Gate riêng cho ca synthetic: budget assessment hết không làm sai ví dụ approve.
                summary["safety_deny"] = deny_case(make_gate(recorder), recorder)
                summary.update(demo_outcome="PREVIEW_COMPLETED_WITH_LIMITATIONS" if args.preview_one_page else "DEMO_COMPLETED_WITH_LIMITATIONS",
                               observed_state="BOUNDED_DISCOVERY_PROPOSAL_ONLY")
            summary["evidence_verification"] = verify(recorder)
            exit_code = 0
    except (DemoBlocked, EvidenceFailure, OSError, ValueError, KeyError, AttributeError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, DemoBlocked) else type(exc).__name__
        summary["blockers"].append(reason)
        section("DEMO BLOCKED — DỪNG, KHÔNG GIẢ PASS")
        show("Reason", reason)
    finally:
        summary["owned_services"] = owned
        summary["network_dispatch_count"] = gate.network_dispatch_count if gate else 0
        if recorder:
            summary["evidence_refs"] = [{"evidence_id": a["evidence_id"], "sha256": a["sha256"],
                                        "record_path": a["record_path"], "artifact_path": a["payload_path"]}
                                        for a in recorder.artifacts]
        expected = None
        try:
            # Summary trước stop là snapshot trình bày, không authoritative evidence/completion.
            write_json_exclusive(directory / "pipeline-summary.json", {
                "run_id": run_id, "completion_state": "PENDING_POST_RUN_CHECK" if exit_code == 0 else "INCOMPLETE",
                "pipeline_outcome": summary["demo_outcome"], "blockers": summary["blockers"],
                "receipt_role": summary["receipt_role"]})
            expected = file_hashes(directory)
            write_json_exclusive(directory / "preservation-before.json", {"run_id": run_id, "file_hashes": expected})
        except (OSError, ValueError, DemoBlocked) as exc:
            summary["blockers"].append("PRE_STOP_SNAPSHOT_FAILED:" + type(exc).__name__)
            exit_code = 2
        if args.stop_owned:
            try:
                summary["cleanup"] = stop_owned(owned)
            except (DemoBlocked, OSError, ValueError, KeyError) as exc:
                summary["blockers"].append(str(exc) if isinstance(exc, DemoBlocked) else type(exc).__name__)
                summary["cleanup"] = "UNRESOLVED"
                exit_code = 2
        else:
            summary["cleanup"] = "NOT_REQUESTED"
        summary["receipts_preserved"] = "NO"
        try:
            if expected is None or not expected:
                raise DemoBlocked("NO_PRESERVATION_BASELINE")
            check_files(directory, expected)
            baseline = json.loads((directory / "preservation-before.json").read_bytes())
            if baseline["run_id"] != run_id or baseline["file_hashes"] != expected:
                raise DemoBlocked("PRESERVATION_BASELINE_CHANGED")
            summary["sentinel_hash_after"] = hashlib.sha256(sentinel.read_bytes()).hexdigest()
            if summary["sentinel_hash_after"] != summary["sentinel_hash_before"]:
                raise DemoBlocked("SENTINEL_CHANGED")
            # Thực sự re-open/verify canonical evidence sau stop, không tin flags trước đó.
            if exit_code == 0:
                summary["evidence_verification"] = verify(recorder)
                if health_rec:
                    summary["health"]["verification"] = verify(health_rec)
            summary["receipts_preserved"] = "YES"
        except (DemoBlocked, EvidenceFailure, OSError, ValueError, KeyError) as exc:
            summary["blockers"].append("POST_RUN_PRESERVATION_FAILED:" + type(exc).__name__)
            exit_code = 2
        if exit_code != 0:
            summary["demo_outcome"] = "BLOCKED"
        summary["completion_state"] = "COMPLETE_WITH_LIMITATIONS" if exit_code == 0 else "INCOMPLETE"
        summary["ended_at_utc"] = utc()
        summary["duration_seconds"] = round(time.monotonic() - started, 3)
        summary["exit_code"] = exit_code
        receipt_verified = False
        try:
            write_receipt(directory, summary)
            check_receipt(directory, run_id)
            final_hashes = file_hashes(directory)
            write_json_exclusive(directory / "post-run-verification.json", {
                "run_id": run_id, "exit_code": exit_code, "demo_outcome": summary["demo_outcome"],
                "completion_state": summary["completion_state"], "checked_at_utc": utc(),
                "receipts_preserved": summary["receipts_preserved"], "file_hashes": final_hashes,
                "cleanup": summary["cleanup"], "sentinel_hash_after": summary.get("sentinel_hash_after")})
            check_files(directory, final_hashes)
            post = json.loads((directory / "post-run-verification.json").read_bytes())
            if post["run_id"] != run_id or post["file_hashes"] != final_hashes:
                raise DemoBlocked("POST_RUN_RECEIPT_CHANGED")
            receipt_verified = True
            show("Receipt directory", directory)
        except (OSError, ValueError, KeyError, DemoBlocked) as exc:
            show("Receipt", "WRITE_FAILED_OR_VERIFICATION_FAILED — BLOCKED: " + type(exc).__name__)
            exit_code = 2
            # Append lỗi, không sửa receipt đã publish hoặc xóa diagnostics.
            try:
                write_json_exclusive(directory / "blocked.json", {
                    "run_id": run_id, "demo_outcome": "BLOCKED", "completion_state": "INCOMPLETE",
                    "exit_code": 2, "reason": type(exc).__name__, "recorded_at_utc": utc()})
            except OSError:
                pass
        section("EVIDENCE / ASSESSMENT SUMMARY")
        show("Requests assessment", summary["network_dispatch_count"])
        show("Resources observed", summary.get("discovery", {}).get("resources", "NOT_RUN"))
        show("Confirmed findings", "0 — không có confirmation, không kết luận target an toàn")
        show("Planner mode", summary["actual_planner_mode"])
        verified = receipt_verified and exit_code == 0
        show("Intent / Decision / Result", "PRESENT — canonical refs verified" if verified and not args.dry_run else "XEM SCOPE / REFS; không giả assessment")
        show("Redacted / Hash verified", "VERIFIED" if verified else "NOT_VERIFIED")
        show("receipts_preserved", "YES" if receipt_verified and summary["receipts_preserved"] == "YES" else "NO")
        section("LIFECYCLE / PTES VÀ GIỚI HẠN")
        show("Assessment", summary["demo_outcome"] if exit_code == 0 else "BLOCKED / INCOMPLETE")
        show("PTES COORDINATOR", "NOT USED IN THIS REHEARSAL")
        show("Exploitation", "NOT_AUTHORIZED")
        show("Post-exploitation / Restore", "NOT_RUN / NOT_RUN")
        show("Cleanup", summary["cleanup"])
        live_ready = verified and args.mode != "deny-demo"
        show("READY_FOR_DEMO", "YES — bounded pipeline, không phải full PTES" if live_ready else "NO — deny-only hoặc invocation bị blocked")
    return exit_code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
