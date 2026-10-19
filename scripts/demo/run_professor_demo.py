"""Demo đọc-only ShopLab: chỉ điều phối API hiện có, không thực thi proposal."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.memory.state.state_manager import StateManager
from runtime.discovery.discovery_engine import ObservationDrivenDiscovery
from runtime.safety.discovery_gate import ApprovalToken, DiscoveryRequest
from runtime.evidence.discovery_recorder import EvidenceFailure, redact_secrets
from runtime.lab import control_support as lab
from runtime.planners.observed_planner import ObservedStatePlanner
from runtime.planners.planner_adapter import PlannerStateAdapter

PHASES = ("PRE_ENGAGEMENT", "INTELLIGENCE_GATHERING", "THREAT_MODELING",
          "VULNERABILITY_ANALYSIS", "EXPLOITATION", "POST_EXPLOITATION", "REPORTING")


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def section(title):
    print("\n" + "=" * 48 + "\n" + title + "\n" + "=" * 48)


def show(label, value):
    # Dữ liệu target chỉ được trình bày một dòng, không control sequence.
    text = str(redact_secrets(value))
    text = "".join(c if c.isprintable() else " " for c in text)
    print(f"{label}: {text[:450]}")


def approval_for(run_id):
    now = time.time()
    return ApprovalToken("APP-DEMO-" + uuid.uuid4().hex, run_id, lab.TARGET, lab.ACTION, now, now + 180)


def deny_case(gate, recorder):
    result = lab.deny_case(gate, recorder)
    section("KIỂM TRA ĐỀ XUẤT SYNTHETIC ĐỌC-ONLY")
    show("Network dispatch", 0)
    show("Phạm vi kiểm tra", "target/action/kill/budget; approval/origin/rate NOT_EVALUATED")
    section("SAFETY DENY — CA SYNTHETIC, KHÔNG GỬI NGOÀI LAB")
    for key in ("target", "decision", "reason", "network_dispatch_delta"):
        show(key, result[key])
    return result


def assess(gate, recorder, approval, planner_mode="rule", fallback=False, preview=False, summary=None):
    if approval is None or not approval.is_valid()[0]:
        raise lab.DemoBlocked("MISSING_OR_INVALID_RUN_APPROVAL")
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
            raise lab.DemoBlocked("EVIDENCE_NOT_DURABLE")
        if response.outcome in ("ERROR", "FAILURE"):
            raise lab.DemoBlocked("DISCOVERY_RESPONSE_ERROR")
        return response

    # Chỉ propagate lỗi lifecycle; transport và mọi policy check vẫn thuộc core gate.
    gate.dispatch = checked_dispatch
    try:
        result = ObservationDrivenDiscovery(gate, recorder.run_id, lab.TARGET, approval,
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
        raise lab.DemoBlocked("DISCOVERY_STOPPED")
    evidence = lab.verify(recorder)  # Không cho planner tiếp tục khi evidence chưa hợp lệ.
    planner = ObservedStatePlanner(lab.TARGET, requested_mode="RULE" if planner_mode == "rule" else "LLM",
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
        raise lab.DemoBlocked("PLANNER_HALTED")
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
            raise lab.DemoBlocked("RECEIPT_PATH_ESCAPE")
        if path.is_file():
            result[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check_files(directory, expected):
    for name, digest in expected.items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
            raise lab.DemoBlocked("RECEIPT_PATH_ESCAPE")
        raw = path.read_bytes()  # Thiếu file phải dừng; không lấy receipt cũ thay thế.
        if hashlib.sha256(raw).hexdigest() != digest:
            raise lab.DemoBlocked("RECEIPT_HASH_CHANGED")
        if path.suffix == ".json":
            json.loads(raw)


def check_receipt(directory, run_id):
    raw = (directory / "summary.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != (directory / "summary.sha256").read_text(encoding="ascii"):
        raise lab.DemoBlocked("SUMMARY_HASH_MISMATCH")
    summary = json.loads(raw)
    if summary["run_id"] != run_id or directory.name != run_id:
        raise lab.DemoBlocked("STALE_RECEIPT_REJECTED")
    groups = [(summary.get("evidence_refs", []), run_id)]
    groups.append((summary.get("health", {}).get("evidence_refs", []), run_id + "-HEALTH"))
    for refs, expected_id in groups:
        for ref in refs:
            path = Path(ref["record_path"])
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise lab.DemoBlocked("EVIDENCE_REFERENCE_ESCAPE")
            record = json.loads(path.read_bytes())
            if record["run_id"] != expected_id or record["evidence_id"] != ref["evidence_id"]:
                raise lab.DemoBlocked("STALE_EVIDENCE_REJECTED")
            artifact = Path(record["path"])
            if not artifact.is_absolute():
                artifact = lab.ROOT / artifact
            if artifact.is_symlink() or not artifact.resolve().is_relative_to(directory.resolve()):
                raise lab.DemoBlocked("EVIDENCE_REFERENCE_ESCAPE")
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != ref["sha256"] or record["sha256"] != ref["sha256"]:
                raise lab.DemoBlocked("EVIDENCE_HASH_MISMATCH")
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
    directory = lab.OUTPUT / run_id
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
    summary = {"run_id": run_id, "target": lab.TARGET, "origin": lab.ORIGIN, "seed": "/", "source": "OPERATOR",
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
        recorder = lab.new_recorder(directory / "assessment", run_id)
        gate = lab.make_gate(recorder, pages=1 if args.preview_one_page else 8)
        recorder.persist_phase_artifact("demo_scope", {"scope": summary, "approval_requested": args.approve_read_only})
        if args.mode == "deny-demo":
            summary["safety_deny"] = deny_case(gate, recorder)
            summary["evidence_verification"] = lab.verify(recorder)
            summary.update(demo_outcome="DENY_DEMO_COMPLETED", observed_state="DENIED_ZERO_DISPATCH")
            exit_code = 0
        else:
            section("SHOPLAB / DEMO PREFLIGHT")
            lab.docker("version", "--format", "{{.Server.Version}}")
            lab.docker("image", "inspect", "cyber-range-lab-ecommerce:latest", "cyber-range-gateway:latest")
            show("Docker và images local", "PASS")
            show("Target/action canonical allowlist", "PASS")
            show("Evidence writable", "PASS — ghi durable scope thành công")
            show("Gateway", lab.ORIGIN)
            show("Safety", "LAB ONLY")
            if args.start:
                lab.start_services(owned)
            lab.inspect_runtime(lab.service_snapshot())
            show("Runtime configuration", "PASS — không chứng minh toàn bộ egress isolation")
            if not args.approve_read_only:
                show("Health", "NOT_CHECKED — thiếu per-run approval")
                raise lab.DemoBlocked("MISSING_RUN_APPROVAL")
            health_id = run_id + "-HEALTH"
            health_rec = lab.new_recorder(directory / "health", health_id)
            health_gate = lab.make_gate(health_rec, pages=1)
            health_approval = approval_for(health_id)
            health = health_gate.dispatch(DiscoveryRequest(health_id, lab.TARGET, lab.ACTION, lab.ORIGIN + "/health", approval=health_approval))
            summary["health"] = {"status_code": health.status_code, "dispatch_count": health_gate.network_dispatch_count,
                                 "durable_confirmed": health.durable_confirmed}
            if not health.durable_confirmed:
                raise lab.DemoBlocked("HEALTH_EVIDENCE_FAILURE")
            if health.status_code != 200 or health.outcome != "SUCCESS":
                raise lab.DemoBlocked("RUNTIME_HEALTH_FAILED")
            summary["health"]["verification"] = lab.verify(health_rec)
            summary["health"]["evidence_refs"] = [{"evidence_id": a["evidence_id"], "sha256": a["sha256"],
                                                      "record_path": a["record_path"]} for a in health_rec.artifacts]
            show("Health", "PASS — GET qua gate và recorder riêng")
            if args.dry_run:
                summary.update(demo_outcome="PREFLIGHT_READY", observed_state="HEALTH_VERIFIED_NO_ASSESSMENT")
                show("Preflight", "PIPELINE_AVAILABLE — READY chỉ sau kiểm tra receipts cuối run")
            else:
                approval = approval_for(run_id)
                summary["approval"] = {"approval_id": approval.approval_id, "timestamp_utc": utc(),
                                       "target": lab.TARGET, "action": lab.ACTION, "expires_at": approval.expires_at}
                recorder.persist_phase_artifact("demo_authorization", summary["approval"])
                summary.update(assess(gate, recorder, approval, args.planner, args.allow_rule_fallback, args.preview_one_page, summary))
                # Gate riêng cho ca synthetic: budget assessment hết không làm sai ví dụ approve.
                summary["safety_deny"] = deny_case(lab.make_gate(recorder), recorder)
                summary.update(demo_outcome="PREVIEW_COMPLETED_WITH_LIMITATIONS" if args.preview_one_page else "DEMO_COMPLETED_WITH_LIMITATIONS",
                               observed_state="BOUNDED_DISCOVERY_PROPOSAL_ONLY")
            summary["evidence_verification"] = lab.verify(recorder)
            exit_code = 0
    except (lab.DemoBlocked, EvidenceFailure, OSError, ValueError, KeyError, AttributeError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, lab.DemoBlocked) else type(exc).__name__
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
        except (OSError, ValueError, lab.DemoBlocked) as exc:
            summary["blockers"].append("PRE_STOP_SNAPSHOT_FAILED:" + type(exc).__name__)
            exit_code = 2
        if args.stop_owned:
            try:
                summary["cleanup"] = lab.stop_owned(owned)
            except (lab.DemoBlocked, OSError, ValueError, KeyError) as exc:
                summary["blockers"].append(str(exc) if isinstance(exc, lab.DemoBlocked) else type(exc).__name__)
                summary["cleanup"] = "UNRESOLVED"
                exit_code = 2
        else:
            summary["cleanup"] = "NOT_REQUESTED"
        summary["receipts_preserved"] = "NO"
        try:
            if expected is None or not expected:
                raise lab.DemoBlocked("NO_PRESERVATION_BASELINE")
            check_files(directory, expected)
            baseline = json.loads((directory / "preservation-before.json").read_bytes())
            if baseline["run_id"] != run_id or baseline["file_hashes"] != expected:
                raise lab.DemoBlocked("PRESERVATION_BASELINE_CHANGED")
            summary["sentinel_hash_after"] = hashlib.sha256(sentinel.read_bytes()).hexdigest()
            if summary["sentinel_hash_after"] != summary["sentinel_hash_before"]:
                raise lab.DemoBlocked("SENTINEL_CHANGED")
            # Thực sự re-open/verify canonical evidence sau stop, không tin flags trước đó.
            if exit_code == 0:
                summary["evidence_verification"] = lab.verify(recorder)
                if health_rec:
                    summary["health"]["verification"] = lab.verify(health_rec)
            summary["receipts_preserved"] = "YES"
        except (lab.DemoBlocked, EvidenceFailure, OSError, ValueError, KeyError) as exc:
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
                raise lab.DemoBlocked("POST_RUN_RECEIPT_CHANGED")
            receipt_verified = True
            show("Receipt directory", directory)
        except (OSError, ValueError, KeyError, lab.DemoBlocked) as exc:
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
