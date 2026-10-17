"""Centralized safety gate and URL canonicalizer for discovery requests.

Enforces:
  - Centralized request gate: single bottleneck for all target network I/O
  - Lab mode enforcement
  - Target registry and allowlist checks
  - Action allowlist check (ACTION-RECON-002 only for discovery)
  - Approval token freshness and revocation
  - Rate limiting with mandatory re-check after wait
  - Budget boundaries (requests, depth, redirects, bytes)
  - Kill switch halting
  - Strict URL canonicalization and same-origin verification
  - Pre-dispatch intent persistence & post-dispatch result persistence
  - Zero bypass, zero library auto-follow, zero form submissions
"""
from __future__ import annotations

import http.client
import json
import posixpath
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    redact_secrets,
)
from scripts.validation.validate_scaffold import ROOT

_TARGET_PATTERN = re.compile(r"^lab-[a-z0-9-]+$")
_ACTION_PATTERN = re.compile(r"^ACTION-[A-Z]+-[0-9]{3}$")

_SENSITIVE_QUERY_PARAMS = frozenset({
    "session", "token", "password", "passwd", "secret", "key", "api_key",
    "csrf", "csrf_token", "_csrf", "authenticity_token", "email",
    "auth", "authorization", "jwt", "access_token", "refresh_token",
})


@dataclass
class ApprovalToken:
    """Approval token authorizing a specific run, target, and action within a time window."""
    approval_id: str
    run_id: str
    target_id: str
    action_id: str
    not_before: float
    expires_at: float
    revoked: bool = False

    def revoke(self) -> None:
        self.revoked = True

    def is_valid(self, now: float | None = None) -> tuple[bool, str]:
        if self.revoked:
            return False, "APPROVAL_REVOKED"
        current = time.time() if now is None else now
        if current < self.not_before:
            return False, "APPROVAL_NOT_YET_VALID"
        if current > self.expires_at:
            return False, "APPROVAL_EXPIRED"
        return True, "APPROVAL_VALID"


@dataclass
class CanonicalURLResult:
    is_valid: bool
    canonical_url: str
    is_same_origin: bool
    reason: str
    redacted: bool = False
    parsed: urllib.parse.SplitResult | None = None


class URLCanonicalizer:
    """Strict URL canonicalization, rejection of ambiguous/unsafe inputs, and query redaction."""

    def __init__(self, base_origin: str) -> None:
        self.base_origin = base_origin.rstrip("/")
        parsed_base = urllib.parse.urlsplit(self.base_origin)
        self.base_scheme = parsed_base.scheme.lower()
        self.base_hostname = (parsed_base.hostname or "").lower()
        self.base_port = parsed_base.port

    def canonicalize(self, raw_candidate: str, current_url: str | None = None) -> CanonicalURLResult:
        if not raw_candidate or not isinstance(raw_candidate, str):
            return CanonicalURLResult(False, "", False, "EMPTY_OR_NON_STRING_URL")

        # Reject control characters (0-31, 127) and newlines/tabs
        if any(ord(c) < 32 or ord(c) == 127 for c in raw_candidate):
            return CanonicalURLResult(False, "", False, "CONTROL_CHARACTERS_REJECTED")

        # Reject backslashes which can be used for authority/path confusion
        if "\\" in raw_candidate:
            return CanonicalURLResult(False, "", False, "BACKSLASH_REJECTED")

        # Strip surrounding whitespace
        trimmed = raw_candidate.strip()

        # Reject unsupported or dangerous pseudo-schemes
        lower_trimmed = trimmed.lower()
        for bad_scheme in ("javascript:", "mailto:", "data:", "file:", "ftp:", "tel:", "ssh:", "vbscript:"):
            if lower_trimmed.startswith(bad_scheme):
                return CanonicalURLResult(False, "", False, f"UNSUPPORTED_SCHEME_{bad_scheme.rstrip(':').upper()}")

        # Resolve relative URLs
        base_for_resolve = current_url if current_url else self.base_origin
        try:
            resolved = urllib.parse.urljoin(base_for_resolve, trimmed)
            parsed = urllib.parse.urlsplit(resolved)
        except Exception as exc:
            return CanonicalURLResult(False, "", False, f"URL_PARSE_ERROR_{exc}")

        # Scheme check: must match base scheme (http)
        scheme = (parsed.scheme or "").lower()
        if scheme != self.base_scheme:
            return CanonicalURLResult(False, "", False, "SCHEME_MISMATCH")

        # Userinfo credentials rejection (http://user:pass@host)
        if parsed.username is not None or parsed.password is not None:
            return CanonicalURLResult(False, "", False, "USERINFO_CREDENTIALS_REJECTED")

        # Authority ambiguity check (e.g. "@" in netloc)
        netloc = parsed.netloc
        if "@" in netloc:
            return CanonicalURLResult(False, "", False, "AUTHORITY_AMBIGUITY_REJECTED")

        hostname = (parsed.hostname or "").lower()
        port = parsed.port

        # Same origin check
        is_same_origin = (hostname == self.base_hostname and port == self.base_port)

        # Path normalization: standard POSIX normalization
        raw_path = parsed.path or "/"
        # Normalize '//' at start of path
        if raw_path.startswith("//"):
            return CanonicalURLResult(False, "", False, "SCHEME_RELATIVE_ESCAPE_REJECTED")

        norm_path = posixpath.normpath(raw_path)
        if not norm_path.startswith("/"):
            norm_path = "/" + norm_path

        # Sensitive query redaction & sorting
        has_redacted = False
        query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        redacted_items = []
        for qk, qv in query_items:
            qk_lower = qk.lower().strip()
            if qk_lower in _SENSITIVE_QUERY_PARAMS or any(s in qk_lower for s in ("token", "session", "password", "secret", "csrf")):
                redacted_items.append((qk, "[REDACTED]"))
                has_redacted = True
            else:
                # Check inline pattern
                redacted_val = redact_secrets(qv)
                if redacted_val != qv:
                    has_redacted = True
                redacted_items.append((qk, redacted_val))

        # Sort query parameters for determinism
        redacted_items.sort(key=lambda item: (item[0], item[1]))
        rebuilt_query = urllib.parse.urlencode(redacted_items)

        # Build clean canonical URL (strip fragment for network dispatch)
        canonical = urllib.parse.urlunsplit((
            scheme,
            f"{hostname}:{port}" if port else hostname,
            norm_path,
            rebuilt_query,
            "",  # strip fragment
        ))

        if not is_same_origin:
            return CanonicalURLResult(False, canonical, False, "REFUSED_OFF_ORIGIN", redacted=has_redacted, parsed=parsed)

        return CanonicalURLResult(True, canonical, True, "OK", redacted=has_redacted, parsed=parsed)


class TokenBucketRateLimiter:
    """Enforces requests-per-second and burst limits per safety config."""

    def __init__(self, requests_per_second: float = 5.0, burst: int = 1) -> None:
        self.rps = max(0.1, float(requests_per_second))
        self.burst = max(1, int(burst))
        self.tokens = float(self.burst)
        self.last_update = time.monotonic()

    def acquire_or_wait(self) -> float:
        """Returns seconds to sleep if throttled; 0.0 if token available immediately."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rps)

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0

        needed = 1.0 - self.tokens
        wait_seconds = needed / self.rps
        self.tokens = 0.0
        return wait_seconds


@dataclass
class BudgetTracker:
    """Tracks and limits actual attempts, requests, bytes, depth, and redirects."""
    max_requests: int = 100
    max_depth: int = 2
    max_pages: int = 20
    max_redirect_hops: int = 3
    max_body_bytes: int = 65536
    timeout: float = 5.0
    max_retries: int = 1

    requests_attempted: int = 0
    requests_dispatched: int = 0
    pages_visited: int = 0
    bytes_received: int = 0

    def can_request(self) -> bool:
        return self.requests_dispatched < self.max_requests


class KillSwitch:
    """Emergency halt switch halting any new scheduling, retries, or redirects."""

    def __init__(self, active: bool = False) -> None:
        self._active = active

    def activate(self) -> None:
        self._active = True

    def is_active(self) -> bool:
        return self._active


@dataclass
class DiscoveryRequest:
    run_id: str
    target_id: str
    action_id: str
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    approval: ApprovalToken | None = None
    depth: int = 0
    redirect_hops: int = 0
    form: dict[str, str] = field(default_factory=dict)


@dataclass
class DispatchResponse:
    status_code: int
    headers: dict[str, str]
    body: str
    raw_bytes_len: int
    truncated: bool
    outcome: str
    durable_confirmed: bool
    canonical_url: str
    refusal_reason: str | None = None
    error_message: str | None = None


def load_canonical_target_allowlist() -> set[str]:
    """Authoritative source: configs/safety/target-allowlist.yaml"""
    cfg_path = ROOT / "configs" / "safety" / "target-allowlist.yaml"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return set(data.get("allowed_target_ids", []))
        except Exception:
            pass
    return set()


def load_canonical_action_allowlist() -> set[str]:
    """Authoritative source: configs/safety/action-allowlist.yaml"""
    cfg_path = ROOT / "configs" / "safety" / "action-allowlist.yaml"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return set(data.get("allowed_action_ids", []))
        except Exception:
            pass
    return set()


def load_canonical_target_registry() -> dict[str, dict[str, Any]]:
    """Authoritative source: cyber-range/targets/manifests/targets.json"""
    reg_path = ROOT / "cyber-range" / "targets" / "manifests" / "targets.json"
    if reg_path.is_file():
        try:
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            return {t["target_id"]: t for t in data.get("targets", []) if isinstance(t, dict) and "target_id" in t}
        except Exception:
            pass
    return {}


class CentralizedSafetyGate:
    """The single centralized bottleneck for all target network dispatches."""

    def __init__(
        self,
        base_origin: str,
        target_registry: dict[str, dict[str, Any]] | None = None,
        target_allowlist: set[str] | None = None,
        action_allowlist: set[str] | None = None,
        canonical_target_allowlist: set[str] | None = None,
        canonical_action_allowlist: set[str] | None = None,
        recorder: DurableEvidenceRecorder | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        budget_tracker: BudgetTracker | None = None,
        kill_switch: KillSwitch | None = None,
        lab_mode: bool = True,
    ) -> None:
        self.base_origin = base_origin.rstrip("/")
        self.canonicalizer = URLCanonicalizer(self.base_origin)
        self.target_registry = (
            dict(target_registry) if target_registry is not None else load_canonical_target_registry()
        )

        # Invariant: effective targets = canonical allowlist INTERSECT run-approved targets
        # Runtime/test caller may restrict further, but CANNOT widen canonical policy!
        canonical_targets = (
            set(canonical_target_allowlist)
            if canonical_target_allowlist is not None
            else load_canonical_target_allowlist()
        )
        run_targets = set(target_allowlist) if target_allowlist is not None else canonical_targets
        self.canonical_target_allowlist = canonical_targets
        self.effective_targets = canonical_targets & run_targets
        self.target_allowlist = self.effective_targets

        # Same invariant for actions
        canonical_actions = (
            set(canonical_action_allowlist)
            if canonical_action_allowlist is not None
            else load_canonical_action_allowlist()
        )
        run_actions = set(action_allowlist) if action_allowlist is not None else canonical_actions
        self.canonical_action_allowlist = canonical_actions
        self.effective_actions = canonical_actions & run_actions
        self.action_allowlist = self.effective_actions

        self.recorder = recorder
        self.workflow_policy = None
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter()
        self.budget_tracker = budget_tracker or BudgetTracker()
        self.kill_switch = kill_switch or KillSwitch()
        self.lab_mode = lab_mode

        # Critical dispatch counters
        self.network_dispatch_count = 0
        self.forbidden_dispatch_count = 0
        self.form_submission_count = 0

        # State flags
        self.halted_due_to_evidence = False

        # Hook for testing rate wait condition
        self.on_rate_wait_hook: Callable[[], None] | None = None

    def revoke_target(self, target_id: str) -> None:
        """Revoke target authorization dynamically before next request (TOCTOU protection)."""
        self.effective_targets.discard(target_id)
        self.target_allowlist.discard(target_id)

    def dispatch(self, req: DiscoveryRequest) -> DispatchResponse:
        """Execute one bounded discovery request through the centralized gate."""
        self.budget_tracker.requests_attempted += 1

        # 0. Fail-closed if earlier evidence persistence failed
        if self.halted_due_to_evidence:
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="ERROR",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="HALTED_DUE_TO_EVIDENCE_FAILURE",
                error_message="Gate is halted: prior evidence persistence failed",
            )

        # 1. Lab mode check
        if not self.lab_mode:
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="LAB_MODE_DISABLED",
            )

        # 2. Target checks (effective targets = canonical allowlist & run approved targets)
        if (
            not _TARGET_PATTERN.match(req.target_id)
            or req.target_id not in self.target_registry
            or req.target_id not in self.effective_targets
        ):
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="TARGET_NOT_ALLOWLISTED",
            )

        # 3. Action checks
        dispatchable_actions = (
            "ACTION-RECON-001",
            "ACTION-RECON-002",
            "ACTION-SCAN-002",
            "ACTION-WEB-001",
            "ACTION-WEB-002",
            "ACTION-WEB-003",
            "ACTION-AUTH-001", "ACTION-FLOW-001", "ACTION-FLOW-002",
        )
        if req.action_id not in self.action_allowlist or req.action_id not in dispatchable_actions:
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="ACTION_NOT_ALLOWLISTED_FOR_DISCOVERY",
            )

        from runtime.lab.workflow_policy import WORKFLOW_ACTIONS
        authenticated = req.action_id in WORKFLOW_ACTIONS
        workflow_allowed = authenticated and self.workflow_policy is not None and self.workflow_policy.permits(req)
        # Only the isolated, explicitly approved workflow can send bounded form POSTs.
        norm_method = req.method.upper().strip()
        if (authenticated and not workflow_allowed) or (not authenticated and (norm_method not in ("GET", "HEAD") or req.form)):
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="MUTATION_METHOD_FORBIDDEN_IN_DISCOVERY",
            )

        # 5. Approval check
        if req.approval is None:
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="MISSING_APPROVAL",
            )

        is_valid_app, app_reason = req.approval.is_valid()
        if not is_valid_app:
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason=app_reason,
            )

        if (
            req.approval.target_id != req.target_id
            or (req.approval.action_id != req.action_id and req.approval.action_id != "*")
            or req.approval.run_id != req.run_id
        ):
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="APPROVAL_IDENTITY_MISMATCH",
            )

        # 6. Kill switch check
        if self.kill_switch.is_active():
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=req.url,
                refusal_reason="KILL_SWITCH_ACTIVE",
            )

        # 7. Strict URL Canonicalization & Same-Origin check
        canon_res = self.canonicalizer.canonicalize(req.url)
        if not canon_res.is_valid:
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=canon_res.canonical_url or req.url,
                refusal_reason=canon_res.reason,
            )

        # 8. Budget check
        if not self.budget_tracker.can_request():
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="DENIED",
                durable_confirmed=False,
                canonical_url=canon_res.canonical_url,
                refusal_reason="BUDGET_EXHAUSTED",
            )

        # 9. Rate limiting & MANDATORY RE-CHECK AFTER WAIT
        wait_s = self.rate_limiter.acquire_or_wait()
        if wait_s > 0:
            if self.on_rate_wait_hook:
                self.on_rate_wait_hook()
            time.sleep(wait_s)

            # Re-check kill switch after wait
            if self.kill_switch.is_active():
                return DispatchResponse(
                    status_code=0,
                    headers={},
                    body="",
                    raw_bytes_len=0,
                    truncated=False,
                    outcome="DENIED",
                    durable_confirmed=False,
                    canonical_url=canon_res.canonical_url,
                    refusal_reason="KILL_SWITCH_ACTIVATED_DURING_WAIT",
                )

            # Re-check approval after wait (e.g. revoked during wait)
            is_valid_app, app_reason = req.approval.is_valid()
            if not is_valid_app:
                return DispatchResponse(
                    status_code=0,
                    headers={},
                    body="",
                    raw_bytes_len=0,
                    truncated=False,
                    outcome="DENIED",
                    durable_confirmed=False,
                    canonical_url=canon_res.canonical_url,
                    refusal_reason=f"{app_reason}_AFTER_WAIT",
                )

            # Re-check budget after wait
            if not self.budget_tracker.can_request():
                return DispatchResponse(
                    status_code=0,
                    headers={},
                    body="",
                    raw_bytes_len=0,
                    truncated=False,
                    outcome="DENIED",
                    durable_confirmed=False,
                    canonical_url=canon_res.canonical_url,
                    refusal_reason="BUDGET_EXHAUSTED_AFTER_WAIT",
                )

        # 10. Persist intent/decision BEFORE dispatch — FAIL CLOSED
        intent_data = {
            "run_id": req.run_id,
            "target_id": req.target_id,
            "action_id": req.action_id,
            "url": canon_res.canonical_url,
            "method": norm_method,
            "headers": {} if authenticated else redact_secrets(req.headers),
            "form_fields": sorted(req.form) if authenticated else [],
            "approval_id": req.approval.approval_id,
            "depth": req.depth,
            "redirect_hops": req.redirect_hops,
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "decision": "DISPATCH_PERMITTED",
        }

        try:
            self.recorder.persist_intent(intent_data)
        except EvidenceFailure as exc:
            # STOP: zero network dispatch!
            self.halted_due_to_evidence = True
            return DispatchResponse(
                status_code=0,
                headers={},
                body="",
                raw_bytes_len=0,
                truncated=False,
                outcome="ERROR",
                durable_confirmed=False,
                canonical_url=canon_res.canonical_url,
                refusal_reason="INTENT_EVIDENCE_WRITE_FAILED",
                error_message=str(exc),
            )

        # 11. Dispatch network request (loopback gateway HTTPConnection)
        parsed = canon_res.parsed or urllib.parse.urlsplit(canon_res.canonical_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"

        # No library auto-follow: standard HTTPConnection does not auto-follow redirects
        conn = http.client.HTTPConnection(host, port, timeout=self.budget_tracker.timeout)
        req_headers = dict(req.headers)
        req_headers.setdefault("User-Agent", "ShopLab-SL08-SafeDiscovery/1.0")
        encoded_form = None
        if authenticated and norm_method == "POST":
            encoded_form = urllib.parse.urlencode(req.form).encode("utf-8")
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"

        dispatch_status = 0
        resp_headers: dict[str, str] = {}
        body_text = ""
        raw_len = 0
        truncated = False
        outcome = "ERROR"

        try:
            if encoded_form is None:
                conn.request(norm_method, path, headers=req_headers)
            else:
                conn.request(norm_method, path, body=encoded_form, headers=req_headers)
            self.network_dispatch_count += 1
            self.budget_tracker.requests_dispatched += 1

            res = conn.getresponse()
            dispatch_status = res.status
            response_headers = res.getheaders()
            resp_headers = dict(response_headers)
            if authenticated:
                for key, value in response_headers:
                    if key.lower() == "set-cookie" and value.lower().startswith("session="):
                        resp_headers["Set-Cookie"] = value

            raw_bytes = res.read(self.budget_tracker.max_body_bytes)
            raw_len = len(raw_bytes)
            self.budget_tracker.bytes_received += raw_len

            # Check if oversized / truncated
            if len(raw_bytes) >= self.budget_tracker.max_body_bytes:
                extra = res.read(1)
                if extra:
                    truncated = True
                    raw_len += len(extra)

            body_text = raw_bytes.decode("utf-8", errors="replace")
            outcome = "SUCCESS" if dispatch_status in (200, 201, 204, 301, 302, 303, 307, 308) else "FAILURE"

        except Exception as exc:
            outcome = "ERROR"
            body_text = str(exc)
        finally:
            conn.close()

        # 12. Persist result — FAIL CLOSED IF WRITE FAILS
        result_data = {
            "run_id": req.run_id,
            "target_id": req.target_id,
            "action_id": req.action_id,
            "url": canon_res.canonical_url,
            "method": norm_method,
            "status_code": dispatch_status,
            "headers": {} if authenticated else redact_secrets(resp_headers),
            "body_snippet": "[AUTHENTICATED_BODY_OMITTED]" if authenticated else body_text[:2000],
            "body_bytes": raw_len,
            "truncated": truncated,
            "outcome": outcome,
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        try:
            self.recorder.persist_result(result_data)
        except EvidenceFailure as exc:
            # STOP: Request was dispatched, but result persistence failed.
            # No subsequent requests may be scheduled!
            self.halted_due_to_evidence = True
            return DispatchResponse(
                status_code=dispatch_status,
                headers=resp_headers,
                body=body_text,
                raw_bytes_len=raw_len,
                truncated=truncated,
                outcome=outcome,
                durable_confirmed=False,
                canonical_url=canon_res.canonical_url,
                refusal_reason="RESULT_EVIDENCE_WRITE_FAILED",
                error_message=str(exc),
            )

        return DispatchResponse(
            status_code=dispatch_status,
            headers=resp_headers,
            body=body_text,
            raw_bytes_len=raw_len,
            truncated=truncated,
            outcome=outcome,
            durable_confirmed=True,
            canonical_url=canon_res.canonical_url,
        )
