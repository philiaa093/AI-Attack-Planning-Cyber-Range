"""Nhập báo cáo discovery ngoại tuyến; observations tùy chọn chỉ mô tả khai báo chưa xác minh."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

from runtime.safety.discovery_gate import (
    ApprovalToken, KillSwitch, URLCanonicalizer,
    load_canonical_action_allowlist, load_canonical_target_allowlist,
    load_canonical_target_registry,
)
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder, redact_secrets
from scripts.validation.validate_scaffold import ROOT, validate_shape

MAX_BYTES = 1048576
MAX_RECORDS = 256
MAX_DEPTH = 16
MAX_URL_CHARS = 2048
MAX_TECHNOLOGIES = 32
MAX_TECH_CHARS = 128
MAX_ITEMS = 1024
POLICY_ACTION = "ACTION-RECON-002"
OBSERVATION_ACTION = "ACTION-PLAN-003"
FORMATS = {"httpx-jsonl": "httpx", "whatweb-json": "WhatWeb"}
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+:/()\-]{0,127}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_PSEUDO_PLUGINS = {
    "ip", "country", "cookies", "title", "redirectlocation", "httpserver",
    "x-powered-by", "x-frame-options", "x-xss-protection", "httpheaders",
    "passwordfield", "email", "html5", "meta-author", "script",
}


def _reject(reason):
    # Không đưa dữ liệu đầu vào hoặc đường dẫn host vào thông báo lỗi.
    raise ValueError(reason)


def _plain_path(path):
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _reject("INPUT_LINK_OR_REPARSE_POINT")


def _identity(info):
    # Windows stat/fstat có semantics ctime khác nhau; inode, size và mtime vẫn được so khớp.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _read_report(report_path, approved_input_root, max_bytes=MAX_BYTES):
    try:
        root = Path(os.path.abspath(approved_input_root))
        path = Path(os.path.abspath(report_path))
        _plain_path(root)
        _plain_path(path)
        root = root.resolve(strict=True)
        path = path.resolve(strict=True)
        if not root.is_dir() or path == root or not path.is_relative_to(root):
            _reject("INPUT_OUTSIDE_APPROVED_ROOT")
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            _reject("INPUT_NOT_REGULAR_OR_TOO_LARGE")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
                _reject("INPUT_CHANGED")
            raw = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
        _plain_path(path)
        if len(raw) > max_bytes or _identity(before) != _identity(after) or _identity(after) != _identity(path.stat()):
            _reject("INPUT_CHANGED_OR_TOO_LARGE")
        # ponytail: root do operator kiểm soát; stat checks không chống mọi race đổi ancestor trên Windows.
        # Khi cần filesystem đối kháng đồng thời, dùng handle-relative no-follow theo OS trước khi mở scope.
        return raw
    except (OSError, TypeError, RuntimeError):
        _reject("INPUT_UNREADABLE")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _constant(_value):
    _reject("NONFINITE_JSON_NUMBER")


def _parse(text):
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                _reject("JSON_DEPTH_EXCEEDED")
        elif char in "]}":
            depth -= 1
    try:
        result = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (json.JSONDecodeError, RecursionError):
        _reject("MALFORMED_JSON")
    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, float) and not math.isfinite(value):
            _reject("NONFINITE_JSON_NUMBER")
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return result


def _records(raw, report_format):
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        _reject("INVALID_UTF8")
    if report_format == "httpx-jsonl":
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) > MAX_RECORDS:
            _reject("RECORD_LIMIT_EXCEEDED")
        records = [_parse(line) for line in lines]
    else:
        records = _parse(text)
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        _reject("INVALID_REPORT_SHAPE_OR_RECORD_LIMIT")
    if any(not isinstance(record, dict) for record in records):
        _reject("INVALID_RECORD_SHAPE")
    return records


def _endpoint(url, canonicalizer):
    if not isinstance(url, str) or not url or len(url) > MAX_URL_CHARS or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        _reject("INVALID_URL")
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "http" or not parsed.netloc:
            _reject("ABSOLUTE_HTTP_URL_REQUIRED")
        canonical = canonicalizer.canonicalize(url)
        if not canonical.is_valid or not canonical.is_same_origin:
            _reject("URL_NOT_APPROVED")
        path = urllib.parse.urlsplit(canonical.canonical_url).path
        if re.search(r"%(?![0-9A-Fa-f]{2})", path):
            _reject("INVALID_PERCENT_ENCODING")
        decoded = urllib.parse.unquote(path, errors="strict")
        if redact_secrets(decoded) != decoded or re.search(
            r"(?:^|[/;])(?:password|passwd|token|secret|session|csrf|api[_-]?key)(?:[/;=]|$)", decoded, re.I
        ) or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
            _reject("SENSITIVE_OR_INVALID_PATH")
        return urllib.parse.urlunsplit((parsed.scheme, urllib.parse.urlsplit(canonical.canonical_url).netloc, path, "", ""))
    except (ValueError, UnicodeError):
        _reject("URL_NOT_APPROVED")


def _technologies(record, report_format):
    if report_format == "httpx-jsonl":
        names = record.get("tech", [])
        if not isinstance(names, list):
            _reject("INVALID_TECHNOLOGY_LIST")
    else:
        plugins = record.get("plugins", {})
        if not isinstance(plugins, dict):
            _reject("INVALID_PLUGIN_MAP")
        names = [name for name in plugins if name.lower() not in _PSEUDO_PLUGINS]
    if len(names) > MAX_TECHNOLOGIES:
        _reject("TECHNOLOGY_LIMIT_EXCEEDED")
    for name in names:
        if not isinstance(name, str) or len(name) > MAX_TECH_CHARS or not _LABEL.fullmatch(name) or redact_secrets(name) != name:
            _reject("INVALID_TECHNOLOGY_LABEL")
    return sorted(set(names))


def import_discovery_report(
    report_path, *, report_format, approved_input_root, run_id, target_id,
    approval: ApprovalToken, run_approved_targets, run_approved_actions,
    recorder: DurableEvidenceRecorder, kill_switch: KillSwitch, lab_mode=False,
    observation_approval: ApprovalToken | None = None,
    simulation_fixture_path=None, simulation_max_steps=3,
):
    """Trả metadata chưa xác minh sau khi ghi bền vững; approval không cấp quyền chạy tool."""
    if not isinstance(report_format, str) or report_format not in FORMATS:
        _reject("UNSUPPORTED_REPORT_FORMAT")
    for allowed in (run_approved_targets, run_approved_actions):
        if not isinstance(allowed, (set, frozenset)) or any(not isinstance(item, str) for item in allowed):
            _reject("INVALID_RUN_ALLOWLIST")
    if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
        _reject("INVALID_RUN_ID")
    if not isinstance(target_id, str) or not re.fullmatch(r"lab-[a-z0-9-]+", target_id):
        _reject("INVALID_TARGET_ID")
    if not isinstance(recorder, DurableEvidenceRecorder) or recorder.run_id != run_id or recorder.source != "TOOL_ADAPTER":
        _reject("INVALID_RECORDER_IDENTITY")
    approved_evidence_root = recorder.approved_root
    evidence_directory = recorder.directory

    def check_evidence_destination():
        if recorder.run_id != run_id or recorder.source != "TOOL_ADAPTER":
            _reject("INVALID_RECORDER_IDENTITY")
        if recorder.approved_root != approved_evidence_root or recorder.directory != evidence_directory:
            _reject("EVIDENCE_DESTINATION_CHANGED")
        try:
            _plain_path(approved_evidence_root)
            _plain_path(evidence_directory)
            if not evidence_directory.resolve().is_relative_to(approved_evidence_root.resolve()):
                _reject("EVIDENCE_ROOT_ESCAPE")
        except OSError:
            _reject("EVIDENCE_DESTINATION_UNAVAILABLE")

    check_evidence_destination()

    def check_approval(token, action):
        if not isinstance(token, ApprovalToken) or (token.run_id, token.target_id, token.action_id) != (run_id, target_id, action):
            _reject("APPROVAL_IDENTITY_MISMATCH")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                   for value in (token.not_before, token.expires_at)) or not isinstance(token.approval_id, str) or not _ID.fullmatch(token.approval_id) or not token.is_valid()[0]:
            _reject("APPROVAL_INVALID")

    def check_policy():
        if lab_mode is not True or not isinstance(kill_switch, KillSwitch) or kill_switch.is_active():
            _reject("LAB_DISABLED_OR_KILL_SWITCH")
        registry = load_canonical_target_registry()
        if target_id not in load_canonical_target_allowlist() or target_id not in run_approved_targets or target_id not in registry:
            _reject("TARGET_NOT_APPROVED")
        actions = (POLICY_ACTION,) if observation_approval is None else (POLICY_ACTION, OBSERVATION_ACTION)
        canonical_actions = load_canonical_action_allowlist()
        if any(action not in canonical_actions or action not in run_approved_actions for action in actions):
            _reject("ACTION_NOT_APPROVED")
        check_approval(approval, POLICY_ACTION)
        if observation_approval is not None:
            check_approval(observation_approval, OBSERVATION_ACTION)
        port = registry[target_id].get("port")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            _reject("INVALID_TARGET_PORT")
        return f"http://127.0.0.1:{port}"

    origin = check_policy()
    fixture = None
    if simulation_fixture_path is not None:
        if observation_approval is None:
            _reject("SIMULATION_REQUIRES_REVIEW_APPROVAL")
        if type(simulation_max_steps) is not int or not 1 <= simulation_max_steps <= 3:
            _reject("INVALID_SIMULATION_BUDGET")
        fixture_raw = _read_report(simulation_fixture_path, approved_input_root, max_bytes=16384)
        try:
            fixture = _parse(fixture_raw.decode("utf-8", errors="strict"))
        except UnicodeError:
            _reject("INVALID_UTF8")
        if not isinstance(fixture, dict) or set(fixture) != {"rule", "audit", "control"}:
            _reject("INVALID_SIMULATION_FIXTURE")
        for item in fixture.values():
            if not isinstance(item, dict) or set(item) != {"expected", "observed"} or any(
                not isinstance(value, str) or value not in {"CLEAR", "BLOCKED", "MISSING"}
                for value in item.values()
            ):
                _reject("INVALID_SIMULATION_FIXTURE")
    raw = _read_report(report_path, approved_input_root)
    records = _records(raw, report_format)
    canonicalizer = URLCanonicalizer(origin)
    metadata = {}
    failed_records = 0
    for record in records:
        endpoint = _endpoint(record.get("url" if report_format == "httpx-jsonl" else "target"), canonicalizer)
        code = record.get("status_code" if report_format == "httpx-jsonl" else "http_status")
        if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 599 or 0 < code < 100:
            _reject("INVALID_HTTP_STATUS")
        failed = record.get("failed", False)
        if not isinstance(failed, bool):
            _reject("INVALID_FAILURE_FLAG")
        names = _technologies(record, report_format)
        if failed or code == 0 or code >= 400:
            failed_records += 1
            continue
        key = (endpoint, code)
        metadata.setdefault(key, set()).update(names)
        if len(metadata[key]) > MAX_TECHNOLOGIES or sum(1 + len(values) for values in metadata.values()) > MAX_ITEMS:
            _reject("METADATA_LIMIT_EXCEEDED")
    items = [{"endpoint": endpoint, "http_status": code, "declared_technologies": sorted(names),
              "verified": False} for (endpoint, code), names in sorted(metadata.items())]
    result = {
        "profile_id": f"discovery-import/{report_format}/v1",
        "run_id": run_id, "import_id": f"IMPORT-{uuid.uuid4().hex}", "target_id": target_id,
        "imported_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "declared_source": FORMATS[report_format], "source_sha256": hashlib.sha256(raw).hexdigest(),
        "provenance": "IMPORTED_OFFLINE", "external_execution": "UNRESOLVED",
        "action_executed": False, "network_dispatch_count": 0,
        "status": "IMPORTED" if items and not failed_records else "PARTIAL",
        "records_read": len(records), "failed_records": failed_records, "metadata": items,
        "limitations": ["Nguồn và phiên bản công cụ chưa được xác minh; không chứng minh tool đã chạy.",
                        "Metadata khai báo, không phải observations hoặc phát hiện lỗi đã xác nhận.",
                        "Không chuyển metadata tới state/planner; không chạy request hoặc follow redirect."],
    }
    observation = None
    if observation_approval is not None:
        facts = {}

        def add_fact(kind, subject, value, confidence):
            identity = json.dumps([target_id, kind, subject, value], ensure_ascii=True, separators=(",", ":"))
            fact_id = "FACT-IMPORT-" + hashlib.sha256(identity.encode()).hexdigest()
            facts[fact_id] = {"fact_id": fact_id, "fact_type": kind, "subject": subject,
                              "value": value, "confidence": confidence}

        for item in items:
            add_fact("ENDPOINT", target_id, item["endpoint"], 0)
            for name in item["declared_technologies"]:
                add_fact("SERVICE", item["endpoint"], name, 0)
        for marker in ("IMPORTED_OFFLINE", "EXTERNAL_EXECUTION_UNRESOLVED", "DECLARED_METADATA_UNVERIFIED"):
            add_fact("CONTROL", result["import_id"], marker, 1)
        observation = {"observation_id": "OBS-IMPORT-" + uuid.uuid4().hex, "run_id": run_id,
                       "action_id": OBSERVATION_ACTION, "timestamp_utc": result["imported_at_utc"],
                       "outcome": "PARTIAL", "new_facts": list(facts.values()), "evidence_refs": []}
        try:
            schema = json.loads((ROOT / "agent/planner/contracts/observation.schema.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _reject("OBSERVATION_SCHEMA_UNAVAILABLE")
        if validate_shape(observation, schema):
            _reject("INVALID_OBSERVATION")
        result["limitations"][1] = "Observations khai báo từ báo cáo ngoại tuyến; facts về target chưa xác minh."

    check_evidence_destination()
    if check_policy() != origin:
        _reject("POLICY_CHANGED")
    intent = recorder.persist_phase_artifact(
        "IMPORT_INTENT", {key: value for key, value in result.items() if key != "metadata"},
        expected_state="OFFLINE_IMPORT_REQUESTED", observed_state="OFFLINE_IMPORT_REQUESTED",
    )
    check_evidence_destination()
    if check_policy() != origin:
        _reject("POLICY_CHANGED")
    artifact = recorder.persist_phase_artifact(
        "IMPORT_RESULT", result, expected_state="OFFLINE_METADATA_RECORDED",
        observed_state="OFFLINE_METADATA_RECORDED", derived_from=[intent["evidence_id"]],
    )
    check_evidence_destination()
    if check_policy() != origin:
        _reject("POLICY_CHANGED")
    result["evidence_refs"] = [intent["evidence_id"], artifact["evidence_id"]]
    if observation is not None:
        observation["evidence_refs"] = list(result["evidence_refs"])
        if validate_shape(observation, schema):
            _reject("INVALID_OBSERVATION")
        observed = recorder.persist_phase_artifact(
            "IMPORT_OBSERVATION", observation, expected_state="OFFLINE_DECLARATIONS_RECORDED",
            observed_state="OFFLINE_DECLARATIONS_RECORDED", derived_from=[artifact["evidence_id"]],
        )
        check_evidence_destination()
        if check_policy() != origin:
            _reject("POLICY_CHANGED")
        result["observation"] = observation
        result["observation_evidence_ref"] = observed["evidence_id"]
    if fixture is not None:
        # ponytail: ba bước review fixture, không executor; mở rộng chỉ khi có scope offline riêng.
        simulation = {"simulation_id": "SIM-" + uuid.uuid4().hex, "provenance": "SIMULATED_FIXTURE",
                      "fixture_sha256": hashlib.sha256(fixture_raw).hexdigest(),
                      "transcript": [], "evidence_refs": [], "stop_reason": "BUDGET_EXHAUSTED"}
        deadline = time.monotonic() + 5
        step = "rule"
        parent = result["observation_evidence_ref"]

        def recheck():
            check_evidence_destination()
            if check_policy() != origin:
                _reject("POLICY_CHANGED")

        for _ in range(simulation_max_steps):
            recheck()
            if time.monotonic() >= deadline:
                simulation["stop_reason"] = "TIME_BUDGET_EXHAUSTED"
                break
            proposal = {"simulation_id": simulation["simulation_id"],
                        "provenance": simulation["provenance"], "fixture_sha256": simulation["fixture_sha256"],
                        "review_step": "REVIEW_" + step.upper(), "action_id": OBSERVATION_ACTION,
                        "source_observation_id": observation["observation_id"]}
            proposed = recorder.persist_phase_artifact(
                "SIMULATION_INTENT", proposal, expected_state="SIMULATED_REVIEW_REQUESTED",
                observed_state="SIMULATED_REVIEW_REQUESTED", derived_from=[parent],
            )
            simulation["evidence_refs"].append(proposed["evidence_id"])
            parent = proposed["evidence_id"]
            recheck()
            if time.monotonic() >= deadline:
                simulation["stop_reason"] = "TIME_BUDGET_EXHAUSTED"
                break
            item = fixture[step]
            entry = proposal | {"expected": item["expected"], "observed": item["observed"],
                                "mismatch": item["expected"] != item["observed"]}
            recorded = recorder.persist_phase_artifact(
                "SIMULATION_RESULT", entry, expected_state="SIMULATED_" + item["expected"],
                observed_state="SIMULATED_" + item["observed"], derived_from=[proposed["evidence_id"]],
            )
            simulation["transcript"].append(entry)
            simulation["evidence_refs"].append(recorded["evidence_id"])
            parent = recorded["evidence_id"]
            recheck()
            status = item["observed"]
            if status == "MISSING":
                simulation["stop_reason"] = "UNRESOLVED"
                break
            if step == "audit" and status == "BLOCKED":
                simulation["stop_reason"] = "NO_PROGRESS"
                break
            if step == "control":
                simulation["stop_reason"] = "COMPLETED_SIMULATION" if status == "CLEAR" else "CONTROL_BLOCKED"
                break
            step = "audit" if step == "rule" and status == "BLOCKED" else "control"
        recheck()
        if time.monotonic() >= deadline:
            simulation["stop_reason"] = "TIME_BUDGET_EXHAUSTED"
        summary = recorder.persist_phase_artifact(
            "SIMULATION_SUMMARY", simulation, expected_state="SIMULATED_REVIEW_RECORDED",
            observed_state="SIMULATED_REVIEW_RECORDED", derived_from=[parent],
        )
        recheck()
        # Ghi bền vững không thể bị ngắt giữa chừng; quá deadline sau summary thì không trả output.
        if simulation["stop_reason"] != "TIME_BUDGET_EXHAUSTED" and time.monotonic() >= deadline:
            _reject("SIMULATION_TIME_BUDGET_EXHAUSTED")
        simulation["evidence_refs"].append(summary["evidence_id"])
        result["simulation"] = simulation
    return result
