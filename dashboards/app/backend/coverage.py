"""Read-only coverage projection from run-local, verified evidence records."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
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
ZAP_RULE_ID = re.compile(r"[1-9][0-9]{0,5}(?:-(?:0|[1-9][0-9]{0,5}))?")
NUCLEI_RULE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
SCANNER_SEVERITIES = ("informational", "low", "medium", "high", "critical")
REVIEW_ARTIFACTS = {"zap-passive": "zap_review", "zap-active": "zap_review", "nuclei": "nuclei_review"}
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


def verified_payload(record: dict, directory: Path) -> dict:
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


def scanner_batch_stop_reason(selected, completed: list[dict]) -> str | None:
    """Reason recorded at the end of an interrupted, ordered scanner batch."""
    if not completed or len(completed) >= len(selected):
        return None
    if [row.get("tool") for row in completed] != list(selected[:len(completed)]):
        return None
    last = completed[-1]
    reason = _safe_reason(last.get("reason"))
    if last.get("status") != "ERROR" or reason in (
        "SCANNER_REFUSAL_LIMIT", "SCANNER_TIMEOUT", "SCANNER_PROCESS_FAILED",
    ):
        return None
    return reason


def _skipped_scanner_reasons(selected, batches, scanners, timestamps) -> dict[str, str]:
    if not selected or len(batches) != 1:
        return {}
    batch_time, batch, parents = batches[0]
    rows = batch.get("results")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return {}
    reason = scanner_batch_stop_reason(selected, rows)
    refs = [row.get("evidence_id") for row in rows]
    if not reason or refs != parents or refs != batch.get("result_evidence_refs"):
        return {}
    for row in rows:
        observed = scanners.get(row["tool"])
        if observed is None:
            return {}
        payload, ref = observed
        if row != {**payload, "evidence_id": ref} or timestamps[ref] > batch_time:
            return {}
    skipped = {}
    for tool in selected[len(rows):]:
        if tool in scanners:
            payload, ref = scanners[tool]
            if payload.get("status") == "NOT_RUN" and timestamps[ref] >= batch_time:
                skipped[tool] = reason
    return skipped


def _scanner_review(tool: str, payload: dict, record: dict, scanner: dict) -> dict:
    """Project scanner metadata for dashboard review without exposing request aliases."""
    source = {"artifact": REVIEW_ARTIFACTS[tool], "evidence_id": record["evidence_id"]}
    unavailable = {"tool": tool, "status": "UNAVAILABLE", "alerts": [], "source": source}
    is_zap = tool != "nuclei"
    digest = payload.get("report_sha256")
    version = payload.get("format_version")
    rows = payload.get("alerts")
    if (record.get("source") != "TOOL_ADAPTER" or payload.get("tool") != tool
            or record.get("observed_state") not in ("AVAILABLE", "PARTIAL")
            or payload.get("report_state") != "AVAILABLE"
            or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or scanner.get("report_sha256") != digest
            or type(version) is not int or version not in ((1, 2) if is_zap else (1,))
            or type(rows) is not list or len(rows) > 1000):
        return unavailable
    alerts = []
    instance_count = 0
    for index, alert in enumerate(rows):
        if type(alert) is not dict or type(alert.get("alert_index")) is not int or alert["alert_index"] != index:
            return unavailable
        has_metadata = not is_zap or version == 2
        rule = alert.get("rule_id") if has_metadata else None
        severity = alert.get("severity") if has_metadata else None
        if has_metadata and ("rule_id" not in alert or "severity" not in alert):
            return unavailable
        rule_id_pattern = ZAP_RULE_ID if is_zap else NUCLEI_RULE_ID
        if ((rule is not None and (type(rule) is not str or not rule_id_pattern.fullmatch(rule)))
                or (severity is not None and severity not in SCANNER_SEVERITIES)):
            return unavailable
        if is_zap:
            urls = alert.get("urls")
            if type(urls) is not list or len(urls) > 2000 or any(
                    type(url) is not list or len(url) != 2 or type(url[0]) is not int
                    or url[0] <= 0 or type(url[1]) is not list for url in urls):
                return unavailable
            instances = len(urls)
        else:
            instances = alert.get("instances")
            if rule is None or type(instances) is not int or not 1 <= instances <= 1000:
                return unavailable
        instance_count += instances
        if instance_count > (2000 if is_zap else 1000):
            return unavailable
        alerts.append({"alert_index": index, "rule_id": rule, "severity": severity, "instances": instances})
    return {"tool": tool, "status": record["observed_state"], "alerts": alerts, "source": source}


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
        "scanner_reviews": [],
        "verifications": [],
        "matrix": [],
        "legacy_workflow_checks": [],
    }
    if integrity.state != "VERIFIED":
        return result

    scope: dict | None = None
    scanners: dict[str, tuple[dict, str]] = {}
    batches = []
    scanner_times = {}
    advisory_records = {}
    scanner_review_refs: dict[str, list[str]] = {}
    reviews: dict[str, tuple[dict, dict]] = {}
    checks: dict[str, tuple[dict, str]] = {}
    verifications: dict[tuple[str, str, str], dict] = {}
    restored = False
    try:
        records = []
        for path in directory.glob("record-*.json"):
            record = read_object(path, directory)
            evidence_id = record["evidence_id"]
            if evidence_id.startswith(("EV-DASHBOARD_RUN_SCOPE-", "EV-WORKFLOW_CHECK-",
                                       "EV-WORKFLOW_RESTORED-", "EV-SCAN_LAB_RESTORED-", "EV-SCANNER_RESULT-", "EV-SCANNER_BATCH-",
                                       "EV-ZAP_REVIEW-", "EV-NUCLEI_REVIEW-", "EV-SCANNER_ANALYSIS-",
                                       "EV-ACTION_WEB_001_VERIFICATION-", "EV-ACTION_WEB_002_VERIFICATION-",
                                       "EV-ACTION_WEB_003_VERIFICATION-")):
                records.append((datetime.fromisoformat(record["created_at_utc"].replace("Z", "+00:00")), evidence_id, record))
        for timestamp, evidence_id, record in sorted(records, key=lambda item: (item[0], item[1])):
            value = verified_payload(record, directory)
            if evidence_id.startswith("EV-DASHBOARD_RUN_SCOPE-"):
                if scope is not None and scope != value:
                    raise ValueError("conflicting scope records")
                scope = value
            elif evidence_id.startswith(("EV-WORKFLOW_RESTORED-", "EV-SCAN_LAB_RESTORED-")):
                restored = True
            elif evidence_id.startswith("EV-WORKFLOW_CHECK-"):
                name = _text(value.get("check"), 80)
                if name:
                    checks[name] = (value, evidence_id)
            elif evidence_id.startswith("EV-SCANNER_BATCH-"):
                batches.append((timestamp, value, record.get("derived_from", [])))
            elif evidence_id.startswith("EV-SCANNER_RESULT-"):
                tool = value.get("tool")
                if tool in SCANNERS:
                    scanners[tool] = (value, evidence_id)
                    scanner_times[evidence_id] = timestamp
                    prefix = f"EV-{REVIEW_ARTIFACTS[tool].upper()}-"
                    scanner_review_refs[tool] = [ref for ref in record.get("derived_from", []) if ref.startswith(prefix)]
            elif evidence_id.startswith("EV-SCANNER_ANALYSIS-"):
                from dashboards.app.backend.scanner_analysis import Interpretation
                parents = record.get("derived_from", [])
                advice = value.get("analysis")
                idx = value.get("alert_index")
                if (record.get("source") != "PLANNER" or len(parents) != 1 or value.get("format_version") != 1
                        or type(idx) is not int or idx < 0 or not isinstance(advice, dict)
                        or advice.get("status") != record["observed_state"]):
                    continue
                state = advice.get("status")
                if state == "AVAILABLE":
                    try:
                        fields = Interpretation.model_validate({k: v for k, v in advice.items()
                                                               if k not in ("status", "model")})
                    except ValueError:
                        continue
                    if not isinstance(advice.get("model"), str) or not 1 <= len(advice["model"]) <= 160:
                        continue
                    advice = {"status": state, "model": advice["model"], **fields.model_dump()}
                elif state in ("INVALID_RESPONSE", "PROVIDER_UNAVAILABLE"):
                    advice = {"status": state}
                else:
                    continue
                advisory_records[(parents[0], value["tool"], idx, value["rule_id"])] = {
                    **advice, "analysis_evidence_id": evidence_id}
            elif evidence_id.startswith(("EV-ZAP_REVIEW-", "EV-NUCLEI_REVIEW-")):
                reviews[evidence_id] = (value, record)
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
    skipped_reasons = _skipped_scanner_reasons(selected, batches, scanners, scanner_times)
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
            refs = scanner_review_refs[tool]
            if len(refs) == 1 and refs[0] in reviews:
                review, review_record = reviews[refs[0]]
                projection = _scanner_review(tool, review, review_record, payload)
                for alert in projection["alerts"]:
                    advice = advisory_records.get((refs[0], tool, alert["alert_index"], alert["rule_id"]))
                    if advice:
                        alert["analysis"] = advice
                result["scanner_reviews"].append(projection)
            elif refs or payload.get("status") == "COMPLETED":
                result["scanner_reviews"].append({
                    "tool": tool, "status": "UNAVAILABLE" if refs else "NOT_RECORDED", "alerts": [], "source": None,
                })
            seed = payload.get("seed_coverage")
            seed = seed if type(seed) is dict else {}
            seed_data = {key: seed[key] for key in SEED_FIELDS if type(seed.get(key)) is int and seed[key] >= 0}
            if type(seed.get("options_truncated")) is bool:
                seed_data["options_truncated"] = seed["options_truncated"]
            result["scanners"].append({
                "tool": tool, "status": _text(payload.get("status"), 40) or "UNKNOWN",
                "coverage": _text(payload.get("coverage"), 40) or "UNKNOWN",
                "reason": skipped_reasons.get(tool) or _safe_reason(payload.get("reason")), "seed_coverage": seed_data,
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
