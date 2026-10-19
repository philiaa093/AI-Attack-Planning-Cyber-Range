"""Shared bounded lab lifecycle, policy setup and evidence checks for local controls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from runtime.safety.discovery_gate import (
    BudgetTracker, CentralizedSafetyGate, DiscoveryRequest,
    TokenBucketRateLimiter, load_canonical_target_registry,
)
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder
from runtime.evidence.evidence_package import EvidenceVerifier
from runtime.planners.observed_planner import ObservedStatePlanner

ROOT = Path(__file__).resolve().parents[2]
TARGET = "lab-ecommerce"
ORIGIN = "http://127.0.0.1:18088"
ACTION = "ACTION-RECON-002"
SERVICES = (TARGET, "gateway-ecommerce")
COMPOSE = ROOT / "cyber-range/compose.yaml"
OUTPUT = ROOT / "scripts/demo/demo-output"


class DemoBlocked(RuntimeError):
    pass


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


def docker(*args):
    _ensure_docker_on_path()
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
    return result
