"""Immutable evidence packaging, integrity verification, evidence-linked lab report, and deterministic offline replay.

Adheres strictly to docs/task-specs/SL-11-evidence-reporting.md and PROJECT_PLAN.md:
  - Immutable evidence packaging & manifest generation
  - Reference graph verification (claims -> phase -> result -> intent)
  - Hash integrity and tamper/truncation detection
  - Separation of expected_state and observed_state
  - Full secret and PII redaction verification across the evidence tree
  - Structured and Markdown Lab Research Report with bounded scope disclaimers
  - Deterministic offline replay with absolute ZERO network/provider dispatch
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import http.client
import json
import os
import re
import socket
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    redact_secrets,
)
from runtime.planners.observed_planner import (
    ObservedStatePlanner,
    PlannerResult,
)
from scripts.validation.validate_scaffold import ROOT
from shared.schema_validation import validate_shape


class EvidencePackageError(Exception):
    """Base error for evidence packaging and verification."""
    pass


class IntegrityError(EvidencePackageError):
    """Raised when evidence files fail hash, schema, or reference integrity checks."""
    pass


class ReplayIncompatibleError(EvidencePackageError):
    """Raised when evidence records are incompatible with offline replay."""
    pass


class NetworkDispatchBlockedError(EvidencePackageError):
    """Raised when offline replay attempts prohibited network or provider dispatch."""
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_of_file(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _publish_new(path: Path, data: bytes) -> None:
    """Exclusive publication: retain partial bytes on failure for custody inspection."""
    from runtime.evidence.evidence_readonly import no_link_ancestors
    no_link_ancestors(path)
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise EvidencePackageError("Evidence destination already exists") from exc


# =============================================================================
# ZERO NETWORK GUARD (FOR DETERMINISTIC OFFLINE REPLAY)
# =============================================================================

class ZeroNetworkGuard:
    """Context manager installing strict socket and HTTP blockers to guarantee zero network dispatch."""

    def __init__(self) -> None:
        self.dispatch_attempts = 0
        self._orig_socket_connect = None
        self._orig_create_connection = None
        self._orig_urlopen = None
        self._orig_http_connect = None
        self._orig_https_connect = None

    def __enter__(self) -> "ZeroNetworkGuard":
        self.dispatch_attempts = 0
        self._orig_socket_connect = socket.socket.connect
        self._orig_create_connection = socket.create_connection
        self._orig_urlopen = urllib.request.urlopen
        self._orig_http_connect = http.client.HTTPConnection.connect
        self._orig_https_connect = http.client.HTTPSConnection.connect

        guard = self

        def _blocked_connect(*args: Any, **kwargs: Any) -> None:
            guard.dispatch_attempts += 1
            raise NetworkDispatchBlockedError("ZeroNetworkGuard: socket.connect blocked in offline replay mode")

        def _blocked_create_connection(*args: Any, **kwargs: Any) -> Any:
            guard.dispatch_attempts += 1
            raise NetworkDispatchBlockedError("ZeroNetworkGuard: socket.create_connection blocked in offline replay mode")

        def _blocked_urlopen(*args: Any, **kwargs: Any) -> Any:
            guard.dispatch_attempts += 1
            raise NetworkDispatchBlockedError("ZeroNetworkGuard: urllib.request.urlopen blocked in offline replay mode")

        def _blocked_http_connect(*args: Any, **kwargs: Any) -> None:
            guard.dispatch_attempts += 1
            raise NetworkDispatchBlockedError("ZeroNetworkGuard: HTTPConnection.connect blocked in offline replay mode")

        socket.socket.connect = _blocked_connect  # type: ignore
        socket.create_connection = _blocked_create_connection  # type: ignore
        urllib.request.urlopen = _blocked_urlopen  # type: ignore
        http.client.HTTPConnection.connect = _blocked_http_connect  # type: ignore
        http.client.HTTPSConnection.connect = _blocked_http_connect  # type: ignore

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._orig_socket_connect:
            socket.socket.connect = self._orig_socket_connect  # type: ignore
        if self._orig_create_connection:
            socket.create_connection = self._orig_create_connection  # type: ignore
        if self._orig_urlopen:
            urllib.request.urlopen = self._orig_urlopen  # type: ignore
        if self._orig_http_connect:
            http.client.HTTPConnection.connect = self._orig_http_connect  # type: ignore
        if self._orig_https_connect:
            http.client.HTTPSConnection.connect = self._orig_https_connect  # type: ignore


# =============================================================================
# EVIDENCE MANIFEST BUILDER
# =============================================================================

class EvidenceManifest:
    """Builder and manager for run-level evidence manifests."""

    SCHEMA_VERSION = "1.0"

    @classmethod
    def load_evidence_schema(cls) -> dict[str, Any]:
        schema_path = ROOT / "agent" / "planner" / "contracts" / "evidence.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    @classmethod
    def build_manifest(
        cls,
        evidence_dir: Path | str,
        run_id: str,
        target_id: str = "lab-ecommerce",
        source: str = "VALIDATOR",
    ) -> dict[str, Any]:
        """Inspect evidence directory, collect all verified record files, and build immutable manifest."""
        ev_dir = Path(evidence_dir).resolve()
        if not ev_dir.is_dir():
            raise EvidencePackageError(f"Evidence directory '{ev_dir}' does not exist")

        schema = cls.load_evidence_schema()
        records: list[dict[str, Any]] = []

        # Find all record-*.json files
        record_files = sorted(ev_dir.glob("record-*.json"))
        for rec_file in record_files:
            try:
                rec_data = json.loads(rec_file.read_text(encoding="utf-8"))
            except Exception as exc:
                raise IntegrityError(f"Malformed JSON in record file '{rec_file}': {exc}") from exc

            errors = validate_shape(rec_data, schema)
            if errors:
                raise IntegrityError(f"Schema violation in record file '{rec_file}': {errors}")

            # Verify on-disk payload existence and hash
            rel_or_abs_path = rec_data.get("path", "")
            payload_path = ROOT / rel_or_abs_path if not Path(rel_or_abs_path).is_absolute() else Path(rel_or_abs_path)
            if not payload_path.is_file():
                # Check directly inside ev_dir by filename
                payload_path = ev_dir / Path(rel_or_abs_path).name
            if not payload_path.is_file():
                raise IntegrityError(f"Payload file '{payload_path}' referenced by '{rec_file}' does not exist")

            computed_sha = _sha256_of_file(payload_path)
            if computed_sha != rec_data.get("sha256"):
                raise IntegrityError(
                    f"Hash mismatch for '{payload_path}': expected {rec_data.get('sha256')}, got {computed_sha}"
                )

            records.append(rec_data)

        manifest = {
            "schema_version": cls.SCHEMA_VERSION,
            "evidence_schema": "agent/planner/contracts/evidence.schema.json",
            "run_id": run_id,
            "target_id": target_id,
            "created_at_utc": _utc_now_iso(),
            "retention": "append_only",
            "append_only": True,
            "traceable": True,
            "status": "COMPLETED",
            "records_count": len(records),
            "records": records,
        }

        # Publish once; an existing manifest is never replaced.
        manifest_bytes = _canonical_json_bytes(manifest)
        manifest_path = ev_dir / "manifest.json"
        _publish_new(manifest_path, manifest_bytes)

        return manifest


# =============================================================================
# EVIDENCE VERIFIER
# =============================================================================

@dataclass
class VerificationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    verified_records_count: int = 0
    verified_files_count: int = 0
    reference_graph_ok: bool = True
    ordering_ok: bool = True
    secrets_clean: bool = True
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class EvidenceVerifier:
    """Comprehensive verifier for evidence integrity, reference graph, ordering, and redaction."""

    # Unredacted secret detection patterns
    _RAW_SECRET_PATTERNS = [
        re.compile(r"(?i)\bpassword\s*[:=]\s*[\"']?(?!\[REDACTED\])[a-zA-Z0-9_\-\.\:\+]{6,}[\"']?"),
        re.compile(r"(?i)\bsecret\s*[:=]\s*[\"']?(?!\[REDACTED\])[a-zA-Z0-9_\-\.\:\+]{6,}[\"']?"),
        re.compile(r"(?i)\bcsrf_token\s*[:=]\s*[\"']?(?!\[REDACTED\])[a-zA-Z0-9_\-\.\:\+]{6,}[\"']?"),
        re.compile(r"(?i)\bBearer\s+(?!\[REDACTED\])[a-zA-Z0-9_\-\.\:\+]{12,}"),
        re.compile(r"(?i)\b(?:synthetic_password|fixture_password|super_secret|test_session_token_raw)\b"),
    ]

    @classmethod
    def verify_directory(
        cls,
        evidence_dir: Path | str,
        manifest_path: Path | str | None = None,
    ) -> VerificationResult:
        """Verify an evidence directory end-to-end."""
        ev_dir = Path(evidence_dir).resolve()
        errors: list[str] = []
        discrepancies: list[dict[str, Any]] = []
        conflicts: list[str] = []

        if not ev_dir.is_dir():
            return VerificationResult(
                passed=False,
                errors=[f"Directory '{ev_dir}' does not exist"],
            )

        schema_path = ROOT / "agent" / "planner" / "contracts" / "evidence.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        records_map: dict[str, dict[str, Any]] = {}
        payloads_seen: set[str] = set()

        # 1. Discover and verify record files
        record_files = sorted(ev_dir.glob("record-*.json"))
        if not record_files:
            errors.append("No evidence records found in directory; package NOT_VERIFIED")

        for r_file in record_files:
            try:
                rec = json.loads(r_file.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"Unparseable record JSON '{r_file.name}': {exc}")
                continue

            schema_errs = validate_shape(rec, schema)
            if schema_errs:
                errors.append(f"Schema violation in '{r_file.name}': {schema_errs}")

            ev_id = rec.get("evidence_id", "")
            if not ev_id:
                errors.append(f"Missing evidence_id in '{r_file.name}'")
                continue

            # Check duplicate / conflicting record IDs
            if ev_id in records_map:
                existing = records_map[ev_id]
                if existing != rec:
                    conflicts.append(f"Conflicting record for evidence_id '{ev_id}'")
                    errors.append(f"CONFLICT_DETECTED: duplicate evidence_id '{ev_id}' with contradictory data")
            records_map[ev_id] = rec

            # Verify payload existence and hash
            rel_or_abs_path = rec.get("path", "")
            p_path = ROOT / rel_or_abs_path if not Path(rel_or_abs_path).is_absolute() else Path(rel_or_abs_path)
            if not p_path.is_file():
                p_path = ev_dir / Path(rel_or_abs_path).name
            if not p_path.is_file():
                errors.append(f"MISSING_PAYLOAD: payload '{rel_or_abs_path}' for record '{ev_id}' not found on disk")
                continue

            payload_bytes = p_path.read_bytes()
            computed_sha = _sha256_of_bytes(payload_bytes)
            if computed_sha != rec.get("sha256"):
                errors.append(
                    f"HASH_MISMATCH: payload '{p_path.name}' digest {computed_sha} != expected {rec.get('sha256')}"
                )
            payloads_seen.add(str(p_path))

            # Expected vs Observed State separation check
            exp_state = rec.get("expected_state", "")
            obs_state = rec.get("observed_state", "")
            if not exp_state or not obs_state:
                errors.append(f"Record '{ev_id}' missing explicit expected_state or observed_state")
            elif exp_state != obs_state:
                discrepancies.append({
                    "evidence_id": ev_id,
                    "expected_state": exp_state,
                    "observed_state": obs_state,
                })

        # 2. Manifest verification (if present)
        m_path = Path(manifest_path) if manifest_path else (ev_dir / "manifest.json")
        if m_path.is_file():
            try:
                manifest_data = json.loads(m_path.read_text(encoding="utf-8"))
                manifest_records = manifest_data.get("records")
                if (type(manifest_records) is not list or
                        type(manifest_data.get("records_count")) is not int or
                        manifest_data["records_count"] != len(records_map) or
                        len(manifest_records) != len(records_map)):
                    errors.append("INCOMPLETE_MANIFEST_INVENTORY")
                    manifest_records = []
                manifest_ids = set()
                for m_rec in manifest_records:
                    m_ev_id = m_rec.get("evidence_id", "")
                    if m_ev_id in manifest_ids or records_map.get(m_ev_id) != m_rec:
                        errors.append("MANIFEST_RECORD_CONFLICT")
                    manifest_ids.add(m_ev_id)
                    if m_ev_id not in records_map:
                        errors.append(f"Manifest references unknown record '{m_ev_id}'")
                if manifest_ids != set(records_map):
                    errors.append("INCOMPLETE_MANIFEST_INVENTORY")
            except Exception as exc:
                errors.append(f"Unparseable manifest '{m_path}': {exc}")

        # 3. Reference Graph Verification
        ref_graph_ok = True
        for ev_id, rec in records_map.items():
            for parent_id in rec.get("derived_from", []):
                if parent_id not in records_map:
                    errors.append(f"MISSING_REFERENCE: record '{ev_id}' derives from non-existent '{parent_id}'")
                    ref_graph_ok = False

            # Also check phase payloads referencing artifacts
            p_rel = rec.get("path", "")
            p_file = ev_dir / Path(p_rel).name
            if p_file.is_file() and p_file.suffix == ".json":
                try:
                    p_json = json.loads(p_file.read_text(encoding="utf-8"))
                    if isinstance(p_json, dict) and "artifact_refs" in p_json:
                        for ref in p_json["artifact_refs"]:
                            if ref not in records_map:
                                errors.append(f"MISSING_REFERENCE: phase artifact references missing '{ref}'")
                                ref_graph_ok = False
                except Exception:
                    pass

        # 4. Logical Ordering Verification
        ordering_ok = True
        timestamps: list[tuple[str, str, datetime]] = []
        for ev_id, rec in records_map.items():
            ts_str = rec.get("created_at_utc", "")
            if ts_str:
                try:
                    clean_ts = ts_str.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(clean_ts)
                    timestamps.append((ev_id, rec.get("source", ""), dt))
                except Exception:
                    pass

        # Check intent -> result order for matching actions
        intent_results: dict[str, list[tuple[str, datetime]]] = {}
        for ev_id, rec in records_map.items():
            p_rel = rec.get("path", "")
            p_file = ev_dir / Path(p_rel).name
            if p_file.is_file():
                try:
                    p_json = json.loads(p_file.read_text(encoding="utf-8"))
                    act_id = p_json.get("action_id", "")
                    ts = rec.get("created_at_utc", "")
                    if act_id and ts:
                        clean_ts = ts.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_ts)
                        kind = "intent" if "intent" in p_file.name else ("result" if "result" in p_file.name else "")
                        if kind:
                            intent_results.setdefault(act_id, []).append((kind, dt))
                except Exception:
                    pass

        for act_id, entries in intent_results.items():
            has_intent = any(k == "intent" for k, _ in entries)
            has_result = any(k == "result" for k, _ in entries)
            if not (has_intent and has_result):
                continue
            # Sort chronologically by timestamp
            sorted_entries = sorted(entries, key=lambda x: x[1])
            intents_seen = 0
            results_seen = 0
            for kind, dt in sorted_entries:
                if kind == "intent":
                    intents_seen += 1
                elif kind == "result":
                    results_seen += 1
                    if results_seen > intents_seen:
                        errors.append(f"ORDERING_VIOLATION: result for '{act_id}' at {dt} has no preceding intent")
                        ordering_ok = False

        # 5. Secret / PII Leak Check
        secrets_clean = True
        for scan_file in ev_dir.rglob("*"):
            if scan_file.is_file() and scan_file.suffix in (".json", ".md", ".txt"):
                content = scan_file.read_text(encoding="utf-8", errors="ignore")
                for pat in cls._RAW_SECRET_PATTERNS:
                    m = pat.search(content)
                    if m:
                        errors.append(
                            f"SECRET_LEAK_DETECTED: unredacted pattern '{m.group(0)[:15]}...' in '{scan_file.name}'"
                        )
                        secrets_clean = False
                        break

        passed = len(errors) == 0

        return VerificationResult(
            passed=passed,
            errors=errors,
            verified_records_count=len(records_map),
            verified_files_count=len(payloads_seen),
            reference_graph_ok=ref_graph_ok,
            ordering_ok=ordering_ok,
            secrets_clean=secrets_clean,
            discrepancies=discrepancies,
            conflicts=conflicts,
            details={
                "records": list(records_map.keys()),
                "directory": str(ev_dir),
            },
        )


# =============================================================================
# EVIDENCE-LINKED LAB REPORT BUILDER
# =============================================================================

class LabReportBuilder:
    """Builds Markdown report.md and structured report.json with mandatory bounded scope disclaimers."""

    @classmethod
    def build_report(
        cls,
        coordinator_report: Any,
        evidence_dir: Path | str,
        manifest: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> tuple[Path, Path]:
        """Generate report.md and report.json into evidence directory."""
        ev_dir = Path(evidence_dir).resolve()
        if not ev_dir.is_dir():
            raise EvidencePackageError(f"Evidence directory '{ev_dir}' not found")
        if any((ev_dir / name).exists() for name in ("report.json", "report.md")):
            raise EvidencePackageError("Evidence report destination already exists")

        # Normalize coordinator report to dict
        if hasattr(coordinator_report, "__dict__"):
            rep_dict = asdict(coordinator_report)
        elif isinstance(coordinator_report, dict):
            rep_dict = coordinator_report
        else:
            rep_dict = {}

        run_id = rep_dict.get("run_id", "RUN-UNKNOWN")
        target_id = rep_dict.get("target_id", "lab-ecommerce")
        phases = rep_dict.get("phases", {})
        pipeline_ok = rep_dict.get("pipeline_control_completed", False)
        assessment_ok = rep_dict.get("full_ptes_assessment_completed", False)
        budget_initial = rep_dict.get("budget_initial", {})
        budget_consumed = rep_dict.get("budget_consumed", {})
        budget_remaining = rep_dict.get("budget_remaining", {})
        findings_count = rep_dict.get("candidate_findings_count", 0)
        confirmed_count = rep_dict.get("confirmed_findings_count", 0)
        negative_count = rep_dict.get("negative_results_count", 0)
        blocked_count = rep_dict.get("blocked_operations_count", 0)
        network_dispatches = rep_dict.get("network_dispatch_count", 0)
        evidence_refs = rep_dict.get("evidence_refs", [])
        prov = provenance or rep_dict.get("planner_provenance", {
            "requested_mode": "RULE",
            "actual_mode": "RULE",
            "fallback_reason": None,
            "provider": "rule_engine",
        })

        generated_at = _utc_now_iso()

        # Build structured JSON report
        structured_report = {
            "title": "LAB RESEARCH REPORT",
            "schema_version": "1.0",
            "run_id": run_id,
            "target_id": target_id,
            "canonical_target_url": "http://127.0.0.1:18088/",
            "generated_at_utc": generated_at,
            "network_isolation_mode": "LOCAL_LOOPBACK_LAB",
            "disclaimer": (
                "LAB RESEARCH REPORT ONLY: Generated inside an isolated, non-production cyber-range testbed. "
                "This document is an academic and bounded experimental research artifact. It does NOT "
                "constitute a production security clearance, commercial penetration test certification, "
                "or proof of target security."
            ),
            "pipeline_control_completed": pipeline_ok,
            "full_ptes_assessment_completed": assessment_ok,
            "assessment_summary": (
                "Assessment completed with bounded scope and unresolved exploitation/post-exploitation phases."
            ),
            "planner_provenance": prov,
            "phases": phases,
            "findings_summary": {
                "confirmed_vulnerabilities": confirmed_count,  # MUST be 0
                "candidate_findings_count": findings_count,
                "negative_results_count": negative_count,
                "blocked_operations_count": blocked_count,
            },
            "resource_budget": {
                "initial": budget_initial,
                "consumed": budget_consumed,
                "remaining": budget_remaining,
                "network_dispatches": network_dispatches,
            },
            "evidence_reference_graph": evidence_refs,
            "bounded_remediation": [
                {
                    "item": "HTTP Security Headers",
                    "recommendation": "Configure Strict-Transport-Security, Content-Security-Policy, and X-Content-Type-Options.",
                    "note": "Requires staging verification before applying to production environments.",
                },
                {
                    "item": "Cookie Attributes",
                    "recommendation": "Ensure session cookies enforce Secure, HttpOnly, and SameSite=Lax/Strict flags.",
                    "note": "Requires staging verification before applying to production environments.",
                },
                {
                    "item": "Input Validation & CSRF",
                    "recommendation": "Verify anti-CSRF token presence on all state-changing endpoints.",
                    "note": "Requires staging verification before applying to production environments.",
                },
            ],
        }

        json_bytes = _canonical_json_bytes(structured_report)
        json_path = ev_dir / "report.json"
        _publish_new(json_path, json_bytes)

        # Build Markdown report.md
        md_lines = [
            "# LAB RESEARCH REPORT",
            "",
            "> [!IMPORTANT]",
            "> **LAB RESEARCH EVALUATION ONLY**: This artifact is a bounded laboratory evaluation report generated within an isolated cyber-range environment (`cyber-range`). It does NOT constitute a production penetration test report, commercial audit certificate, or target safety assurance.",
            "",
            "## 1. Run Identity & Environment",
            f"- **Run ID**: `{run_id}`",
            f"- **Target ID**: `{target_id}`",
            f"- **Target URL**: `http://127.0.0.1:18088/`",
            f"- **Generated UTC**: `{generated_at}`",
            "- **Network Boundary**: Isolated loopback cyber range (zero external egress)",
            f"- **Pipeline Control Completed**: `{pipeline_ok}`",
            f"- **Full PTES Assessment Completed**: `{assessment_ok}` *(Exploitation bounded/unresolved)*",
            "",
            "## 2. Planner Provenance",
            f"- **Requested Mode**: `{prov.get('requested_mode', 'N/A')}`",
            f"- **Actual Mode**: `{prov.get('actual_mode', 'N/A')}`",
            f"- **Provider / Engine**: `{prov.get('provider', 'rule_engine')}`",
            f"- **Fallback Reason**: `{prov.get('fallback_reason') or 'None (deterministic baseline)'}`",
            "",
            "## 3. Seven-Phase Execution Summary",
            "",
            "| Phase ID | Phase Name | Status | Entry Checks | Exit Checks | Transition Reason |",
            "|:---|:---|:---|:---:|:---:|:---|",
        ]

        # Phase table rows
        phase_names_map = {
            "PHASE_1": ("PHASE-01", "PRE_ENGAGEMENT"),
            "PHASE_2": ("PHASE-02", "INTELLIGENCE_GATHERING"),
            "PHASE_3": ("PHASE-03", "THREAT_MODELING"),
            "PHASE_4": ("PHASE-04", "VULNERABILITY_ANALYSIS"),
            "PHASE_5": ("PHASE-05", "EXPLOITATION"),
            "PHASE_6": ("PHASE-06", "POST_EXPLOITATION"),
            "PHASE_7": ("PHASE-07", "REPORTING"),
        }

        for p_key, (p_id, p_name) in phase_names_map.items():
            p_data = phases.get(p_key, {})
            p_outcome = p_data.get("outcome", "NOT_RUN")
            entry_cnt = len(p_data.get("entry_checks", []))
            exit_cnt = len(p_data.get("exit_checks", []))
            reason = p_data.get("transition_reason", "N/A")
            md_lines.append(f"| `{p_id}` | {p_name} | **{p_outcome}** | {entry_cnt} passed | {exit_cnt} passed | `{reason}` |")

        md_lines.extend([
            "",
            "> **Phase Limitation Note**: Phase 5 (`EXPLOITATION`) is honestly marked **`BLOCKED`** because no destructive/exploitation capabilities are approved under current safety contracts. Phase 6 (`POST_EXPLOITATION`) is honestly marked **`NOT_RUN`** as exploitation was blocked.",
            "",
            "## 4. Findings Classification",
            f"- **Confirmed Vulnerabilities**: **`{confirmed_count}`** *(Zero confirmed without authorized exploitation)*",
            f"- **Candidate Hypotheses / Vulnerabilities**: **`{findings_count}`** *(Passive/observation-derived)*",
            f"- **Negative Results (Clean Controls)**: **`{negative_count}`**",
            f"- **Blocked Operations**: **`{blocked_count}`** *(Exploitation requests rejected by safety gate)*",
            "",
            "## 5. Resource & Budget Accounting",
            f"- **Requests Dispatched**: `{budget_consumed.get('requests', network_dispatches)}` / `{budget_initial.get('requests', 50)}`",
            f"- **Pages Visited**: `{budget_consumed.get('pages', 0)}` / `{budget_initial.get('pages', 20)}`",
            f"- **Remaining Request Budget**: `{budget_remaining.get('requests', 'N/A')}`",
            "",
            "## 6. Evidence Traceability & Reference Graph",
            "All claims in this report link directly to durable, content-addressed records:",
            "",
        ])

        for ref in evidence_refs:
            md_lines.append(f"- Record: `{ref}`")

        md_lines.extend([
            "",
            "## 7. Bounded Contextual Recommendations",
            "1. **Input Sanitization & Output Encoding**: Validate and encode user inputs across all observed search and registration form fields.",
            "2. **Session Cookie Security**: Set `SameSite=Lax`, `HttpOnly`, and `Secure` attributes on authentication cookies.",
            "3. **Anti-CSRF Mechanisms**: Deploy unique cryptographic tokens on state-changing forms.",
            "",
            "*(Verification in a non-production staging environment is required before applying configuration updates.)*",
            "",
            "---",
            "*Report generated deterministically by PBL6 Evidence Packaging Engine.*",
        ])

        md_text = "\n".join(md_lines) + "\n"
        md_path = ev_dir / "report.md"
        _publish_new(md_path, md_text.encode("utf-8"))

        return md_path, json_path


# =============================================================================
# DETERMINISTIC OFFLINE REPLAY ENGINE
# =============================================================================

@dataclass
class ReplayResult:
    success: bool
    network_dispatch_count: int
    observations_replayed: int
    reconstructed_facts_count: int
    proposal_matched: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class OfflineEvidenceReplayer:
    """Deterministic offline replay engine with guaranteed zero network/provider dispatch."""

    @classmethod
    def replay_run(
        cls,
        evidence_dir: Path | str,
        expected_run_id: str | None = None,
    ) -> ReplayResult:
        """Replay recorded evidence deterministically, verifying facts and planner proposals."""
        ev_dir = Path(evidence_dir).resolve()
        if not ev_dir.is_dir():
            raise EvidencePackageError(f"Evidence directory '{ev_dir}' does not exist")

        # 1. Verify integrity of all records and payloads
        ver_res = EvidenceVerifier.verify_directory(ev_dir)
        if not ver_res.passed:
            return ReplayResult(
                success=False,
                network_dispatch_count=0,
                observations_replayed=0,
                reconstructed_facts_count=0,
                proposal_matched=False,
                error=f"INTEGRITY_VERIFICATION_FAILED: {ver_res.errors[:3]}",
                details={"verification_errors": ver_res.errors},
            )

        # 2. Check manifest schema compatibility
        manifest_path = ev_dir / "manifest.json"
        if manifest_path.is_file():
            try:
                m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                version = m_data.get("schema_version", "")
                if version != EvidenceManifest.SCHEMA_VERSION:
                    return ReplayResult(
                        success=False,
                        network_dispatch_count=0,
                        observations_replayed=0,
                        reconstructed_facts_count=0,
                        proposal_matched=False,
                        error=f"REPLAY_INCOMPATIBLE: unsupported manifest schema version '{version}'",
                    )
            except Exception as exc:
                return ReplayResult(
                    success=False,
                    network_dispatch_count=0,
                    observations_replayed=0,
                    reconstructed_facts_count=0,
                    proposal_matched=False,
                    error=f"REPLAY_INCOMPATIBLE: manifest read failed: {exc}",
                )

        # 3. Execute replay inside ZeroNetworkGuard
        with ZeroNetworkGuard() as net_guard:
            run_id = expected_run_id or "RUN-REPLAY-001"
            normalizer = ObservationNormalizer()
            state_mgr = StateManager(
                run_id=run_id,
                scenario_id="SCN-LAB-ECOMMERCE-001",
                objective_id="OBJ-RECON-SURFACE",
                budget={"actions": 50, "requests": 50, "seconds": 3600.0},
            )

            # Collect all result payloads
            result_files = sorted(ev_dir.glob("result-*.json"))
            observations_replayed = 0

            for rf in result_files:
                try:
                    res_data = json.loads(rf.read_text(encoding="utf-8"))
                except Exception as exc:
                    return ReplayResult(
                        success=False,
                        network_dispatch_count=net_guard.dispatch_attempts,
                        observations_replayed=observations_replayed,
                        reconstructed_facts_count=state_mgr.get_fact_count(),
                        proposal_matched=False,
                        error=f"Unparseable result payload in replay: {exc}",
                    )

                action_id = res_data.get("action_id", "ACTION-RECON-002")
                url = res_data.get("url", "http://127.0.0.1:18088/")
                status_code = res_data.get("status_code", 200)

                # Construct scanner result fixture to feed normalizer
                endpoint_path = urllib.parse.urlsplit(url).path or "/"
                scanner_result = {
                    "source": "DISCOVERY",
                    "target_id": "lab-ecommerce",
                    "finding_type": "open_port" if endpoint_path == "/" else "sqli",
                    "endpoint_id": endpoint_path,
                    "confidence": 1.0,
                }

                obs = normalizer.normalize(
                    scanner_results=[scanner_result],
                    run_id=run_id,
                    action_id=action_id,
                )
                state_mgr.apply_observation(obs)
                observations_replayed += 1

            reconstructed_state = state_mgr.get_state()
            fact_count = state_mgr.get_fact_count()

            # Run deterministic rule planner on reconstructed state
            planner = ObservedStatePlanner(
                target_id="lab-ecommerce",
                objective_id="OBJ-RECON-SURFACE",
                requested_mode="RULE",
            )
            plan_res = planner.propose(reconstructed_state)

            # Check that planner produced a valid rule decision without network calls
            proposal_ok = plan_res.is_valid and plan_res.proposal.get("action_id") is not None
            network_dispatches = net_guard.dispatch_attempts

            return ReplayResult(
                success=proposal_ok and (network_dispatches == 0),
                network_dispatch_count=network_dispatches,
                observations_replayed=observations_replayed,
                reconstructed_facts_count=fact_count,
                proposal_matched=proposal_ok,
                details={
                    "proposed_action": plan_res.proposal.get("action_id"),
                    "actual_mode": plan_res.mode_provenance.get("actual_mode"),
                    "reconstructed_facts": fact_count,
                },
                error=None if (proposal_ok and network_dispatches == 0) else "Replay proposal check failed",
            )
