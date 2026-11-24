"""Read-only coverage projection from run-local, verified evidence records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from runtime.evidence.evidence_readonly import bounded_bytes, read_object, verify_records
from runtime.lab.authenticated_workflow import WORKFLOW_CHECK_CONTEXT
from scripts.validation.validate_scaffold import ROOT


SCANNERS = ("zap-passive", "zap-active", "nuclei")
SEED_FIELDS = ("observed_seed_count", "selected_seed_count", "requested_seed_count",
               "successful_seed_count", "not_requested_seed_count")
PLANNED_CASES = {
    "user_admin_mutation_denied": ("/admin/products/add", "POST", "USER", "AUTHENTICATED", "ADMIN_MUTATION", True, "Access denied without a write"),
    "expired_cart_session_denied": ("/cart/add", "POST", "USER", "EXPIRED", "EXPIRED_SESSION", True, "Access denied without a write"),
}


def _text(value: Any, limit: int = 256) -> str | None:
    return value[:limit] if type(value) is str else None


def _safe_reason(value: Any) -> str | None:
    text = _text(value, 256)
    return text if text and re.fullmatch(r"[A-Za-z0-9_ .:,;()/='-]+", text) else None


def _path(value: Any) -> str | None:
    text = _text(value, 2048)
    if not text:
        return None
    try:
        result = urlsplit(text).path
    except ValueError:
        return None
    return result[:512] if result.startswith("/") else None


def _payload(record: dict, directory: Path) -> dict:
    path = Path(record["path"])
    if not path.is_absolute():
        path = ROOT / path
    data = bounded_bytes(path, directory)
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("evidence changed while reading")
    def unique_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate payload field")
            result[key] = item
        return result
    value = json.loads(data, object_pairs_hook=unique_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite payload")))
    if type(value) is not dict or value.get("run_id") != record["run_id"]:
        raise ValueError("invalid coverage evidence")
    return value


def build_coverage(run_dir: Path, run_id: str) -> dict[str, Any]:
    directory = run_dir / "assessment" if (run_dir / "assessment").is_dir() else run_dir
    integrity = verify_records(directory, run_id)
    result: dict[str, Any] = {
        "run_id": run_id,
        "integrity": integrity.state,
        "record_count": integrity.record_count,
        "scope": None,
        "workflow": {"status": "UNKNOWN", "restore": "UNKNOWN", "recorded_checks": 0},
        "scan_isolation": {"restore": "UNKNOWN"},
        "scanners": [],
        "verifications": [],
        "matrix": [],
        "legacy_workflow_checks": [],
    }
    if integrity.state != "VERIFIED":
        return result

    scope: dict | None = None
    scanners: dict[str, tuple[dict, str]] = {}
    checks: dict[str, tuple[dict, str]] = {}
    verifications: dict[tuple[str, str, str], dict] = {}
    restored = False
    try:
        records = []
        for path in directory.glob("record-*.json"):
            record = read_object(path, directory)
            evidence_id = record["evidence_id"]
            if evidence_id.startswith(("EV-DASHBOARD_RUN_SCOPE-", "EV-WORKFLOW_CHECK-",
                                       "EV-WORKFLOW_RESTORED-", "EV-SCANNER_RESULT-",
                                       "EV-ACTION_WEB_001_VERIFICATION-", "EV-ACTION_WEB_002_VERIFICATION-",
                                       "EV-ACTION_WEB_003_VERIFICATION-")):
                records.append((record["created_at_utc"], evidence_id, record))
        for _, evidence_id, record in sorted(records, key=lambda item: (item[0], item[1])):
            value = _payload(record, directory)
            if evidence_id.startswith("EV-DASHBOARD_RUN_SCOPE-"):
                if scope is not None and scope != value:
                    raise ValueError("conflicting scope records")
                scope = value
            elif evidence_id.startswith("EV-WORKFLOW_RESTORED-"):
                restored = True
            elif evidence_id.startswith("EV-WORKFLOW_CHECK-"):
                name = _text(value.get("check"), 80)
                if name:
                    checks[name] = (value, evidence_id)
            elif evidence_id.startswith("EV-SCANNER_RESULT-"):
                tool = value.get("tool")
                if tool in SCANNERS:
                    scanners[tool] = (value, evidence_id)
            else:
                action = _text(value.get("action_id"), 64)
                expected_action = next((f"ACTION-WEB-{number}" for number in ("001", "002", "003")
                                        if evidence_id.startswith(f"EV-ACTION_WEB_{number}_VERIFICATION-")), None)
                if action != expected_action:
                    raise ValueError("verification action identity mismatch")
                resource = _path(value.get("resource"))
                parameter = _text(value.get("parameter"), 128)
                if not action or not resource or not parameter:
                    continue
                key = (action, resource, parameter)
                prior = verifications.get(key, {})
                classification = value.get("classification") if value.get("classification") in (
                    "NEGATIVE", "SIGNAL", "VERIFIED_IN_LAB", "INCONCLUSIVE", "REFUSED") else "UNKNOWN"
                reason = _safe_reason(value.get("reason"))
                if (action == "ACTION-WEB-003" and classification == "VERIFIED_IN_LAB"
                        and not any(part in parameter.lower() for part in
                                    ("file", "path", "template", "document", "download", "folder", "dir", "include"))):
                    classification, reason = "INCONCLUSIVE", "PATH_INPUT_NOT_OBSERVED"
                verifications[key] = {
                    "action": action, "resource": resource, "parameter": parameter,
                    "attempts": prior.get("attempts", 0) + 1,
                    "classification": classification, "reason": reason, "evidence_id": evidence_id,
                }
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        result["integrity"] = "FAILED"
        return result

    selected = scope.get("external_scanners") if scope else None
    if type(selected) is not list or any(tool not in SCANNERS for tool in selected):
        selected = None
    approved = scope.get("authenticated_workflow_approved") if scope else None
    approved = approved if type(approved) is bool else None
    if scope:
        scope_name = scope.get("execution_scope")
        if scope_name is None:
            scope_name = "LEGACY"
        elif scope_name not in ("scan", "workflow", "combined"):
            scope_name = "UNKNOWN"
        result["scope"] = {
            "execution_scope": scope_name,
            "workflow_approved": approved,
            "active_verification_approved": scope.get("active_verification_approved")
                if type(scope.get("active_verification_approved")) is bool else None,
            "selected_scanners": selected,
        }
    result["workflow"] = {
        "status": "CHECKS_RECORDED" if checks else "NOT_SELECTED" if approved is False else "UNKNOWN",
        "reason": "WORKFLOW_NOT_APPROVED" if approved is False else None,
        "restore": "RECORDED" if restored and approved is True else "UNKNOWN",
        "recorded_checks": len(checks),
    }
    if scope and scope.get("execution_scope") in ("scan", "combined") and approved is False:
        result["scan_isolation"] = {"restore": "RECORDED" if restored else "UNKNOWN"}
    for tool in SCANNERS:
        if tool in scanners:
            payload, evidence_id = scanners[tool]
            seed = payload.get("seed_coverage")
            seed = seed if type(seed) is dict else {}
            seed_data = {key: seed[key] for key in SEED_FIELDS if type(seed.get(key)) is int and seed[key] >= 0}
            if type(seed.get("options_truncated")) is bool:
                seed_data["options_truncated"] = seed["options_truncated"]
            result["scanners"].append({
                "tool": tool, "status": _text(payload.get("status"), 40) or "UNKNOWN",
                "coverage": _text(payload.get("coverage"), 40) or "UNKNOWN",
                "reason": _safe_reason(payload.get("reason")), "seed_coverage": seed_data,
                "refused_requests": payload.get("refused_requests") if type(payload.get("refused_requests")) is int and payload["refused_requests"] >= 0 else None,
                "candidate_count": payload.get("candidate_count") if type(payload.get("candidate_count")) is int and payload["candidate_count"] >= 0 else None,
                "evidence_id": evidence_id,
            })
        else:
            status = "NOT_SELECTED" if selected is not None and tool not in selected else "UNKNOWN"
            result["scanners"].append({"tool": tool, "status": status, "coverage": "NOT_RECORDED",
                                       "reason": "NOT_SELECTED" if status == "NOT_SELECTED" else "NO_SCANNER_RESULT_RECORDED",
                                       "seed_coverage": {}, "evidence_id": None})

    for name, context in {**WORKFLOW_CHECK_CONTEXT, **PLANNED_CASES}.items():
        route, method, role, auth_state, case, negative, expected = context
        row = {"check": name, "route": route, "method": method, "role": role,
               "auth_state": auth_state, "case": case, "negative": negative, "expected": expected,
               "status": "NOT_RUN" if approved is False else "NOT_RECORDED" if approved is True else "UNKNOWN",
               "reason": "WORKFLOW_NOT_APPROVED" if approved is False else "NO_CHECK_EVIDENCE",
               "evidence_id": None, "http_status": None}
        if name in checks:
            payload, evidence_id = checks[name]
            row["evidence_id"] = evidence_id
            expected_context = (route, method, role, auth_state, case, negative, expected)
            actual_context = tuple(payload.get(key) for key in
                                   ("route", "method", "role", "auth_state", "case", "negative", "expected"))
            if actual_context == expected_context and payload.get("status") in ("PASS", "FAIL"):
                row["status"] = payload["status"]
                row["reason"] = None
                if type(payload.get("http_status")) is int:
                    row["http_status"] = payload["http_status"]
            else:
                row["status"] = "UNKNOWN"
                row["reason"] = "CHECK_CONTEXT_NOT_RECORDED_OR_MISMATCHED"
                result["legacy_workflow_checks"].append({
                    "check": name, "status": _text(payload.get("status"), 20) or "UNKNOWN",
                    "evidence_id": evidence_id,
                })
        result["matrix"].append(row)
    result["verifications"] = list(verifications.values())
    return result
