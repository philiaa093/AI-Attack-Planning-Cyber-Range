"""Durable, fail-closed evidence recorder for observation-driven discovery.

Adheres strictly to evidence.schema.json.
Enforces the mandatory prerequisite ordering:
  validate request
  -> policy decision
  -> persist intent/decision
  -> confirm persistence
  -> dispatch network request
  -> receive result
  -> persist result
  -> confirm persistence
  -> allow scheduling next request
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.validation.validate_scaffold import ROOT
from shared.schema_validation import validate_shape

_SENSITIVE_PARAM_NAMES = frozenset({
    "session", "token", "password", "passwd", "secret", "key", "api_key",
    "csrf", "csrf_token", "_csrf", "authenticity_token", "email",
    "auth", "authorization", "cookie", "set-cookie", "jwt",
    "access_token", "refresh_token", "credential", "credentials",
})

_SENSITIVE_HEADER_NAMES = frozenset({
    "cookie", "set-cookie", "authorization", "x-csrf-token", "x-api-key",
})

_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(session|token|csrf_token|_csrf|password|passwd|secret|key|api_key|auth|credential|credentials)=([a-zA-Z0-9_\-\.\:\+]{6,})"
)
_BEARER_PATTERN = re.compile(
    r"(?i)\bBearer\s+([a-zA-Z0-9_\-\.\:\+]{6,})"
)
_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([\?&](?:session|token|csrf_token|_csrf|password|passwd|secret|key|api_key|auth|credentials?)=)([^&]+)"
)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
)


class EvidenceFailure(RuntimeError):
    """Raised when evidence recording fails or cannot be confirmed durable."""
    pass


def _utc_now_iso() -> str:
    """Return ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(data: Any) -> bytes:
    """Deterministic, sorted, whitespace-minimized UTF-8 JSON bytes."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def redact_secrets(obj: Any) -> Any:
    """Recursively redact cookies, session tokens, passwords, CSRF tokens, credentials, and PII."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            k_lower = str(k).lower().strip()
            if k_lower in _SENSITIVE_PARAM_NAMES or k_lower in _SENSITIVE_HEADER_NAMES:
                redacted[k] = "[REDACTED]"
            elif any(s in k_lower for s in ("password", "secret", "token", "session", "csrf", "credential", "passwd")):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_secrets(v)
        return redacted
    if isinstance(obj, list):
        return [redact_secrets(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_secrets(item) for item in obj)
    if isinstance(obj, set):
        return {redact_secrets(item) for item in obj}
    if isinstance(obj, str):
        # Redact Bearer tokens, query param secrets, inline key=val secrets, and emails
        s = _BEARER_PATTERN.sub("Bearer [REDACTED]", obj)
        s = _QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", s)
        s = _INLINE_SECRET_PATTERN.sub(r"\1=[REDACTED]", s)
        s = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", s)
        return s
    return obj


CANONICAL_EVIDENCE_ROOT: Path = (ROOT / "evidence").resolve()

_CONFIGURED_APPROVED_ROOT: Path | None = None


def get_approved_evidence_root(target: Path | None = None) -> Path:
    """Return the authoritative approved evidence root."""
    if _CONFIGURED_APPROVED_ROOT is not None:
        return _CONFIGURED_APPROVED_ROOT
    env_root = os.environ.get("APPROVED_EVIDENCE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    canonical = CANONICAL_EVIDENCE_ROOT
    if target is not None:
        target_resolved = target.resolve()
        try:
            target_resolved.relative_to(canonical)
            return canonical
        except ValueError:
            pass
        # Support unit test isolation in temp directory with an 'evidence' root
        temp_dir = Path(tempfile.gettempdir()).resolve()
        try:
            target_resolved.relative_to(temp_dir)
            curr = target_resolved
            while curr != temp_dir and curr != curr.parent:
                if curr.name == "evidence":
                    return curr
                curr = curr.parent
            # Fall back to top-level folder under temp_dir
            curr = target_resolved
            while curr.parent != temp_dir and curr != curr.parent:
                curr = curr.parent
            return curr
        except ValueError:
            pass
    return canonical


def set_approved_evidence_root(path: Path | str | None) -> None:
    """Set the authoritative approved evidence root for tests/runtime."""
    global _CONFIGURED_APPROVED_ROOT
    _CONFIGURED_APPROVED_ROOT = Path(path).resolve() if path is not None else None


class DurableEvidenceRecorder:
    """Durable, fail-closed evidence recorder implementing pre-dispatch and post-dispatch persistence."""

    def __init__(
        self,
        run_id: str,
        base_dir: Path | str | None = None,
        source: str = "EXECUTOR",
        exclusive_creation: bool = False,
        approved_root: Path | str | None = None,
    ) -> None:
        if not run_id or not isinstance(run_id, str):
            raise EvidenceFailure("run_id must be a non-empty string")
        if any(c in run_id for c in ("..", "/", "\\", "\0")):
            raise EvidenceFailure(f"path traversal or invalid characters in run_id '{run_id}'")
        if source not in ("VALIDATOR", "UNIT_TEST", "COMPILE_CHECK", "PLANNER", "EXECUTOR", "TOOL_ADAPTER", "OPERATOR"):
            raise EvidenceFailure(f"invalid evidence source '{source}' per evidence.schema.json")

        self.run_id = run_id
        self.source = source
        self.exclusive_creation = exclusive_creation
        self.artifacts: list[dict[str, Any]] = []

        # Failure injection flags for preflight and edge testing
        self._inject_intent_failure = False
        self._inject_decision_failure = False
        self._inject_result_failure = False
        self._inject_partial_write = False
        self._inject_dir_error = False
        self._inject_flush_failure = False
        self._inject_fsync_failure = False

        # 1. Determine authoritative approved root
        if approved_root is not None:
            self.approved_root = Path(approved_root).resolve()
        else:
            raw_target = Path(base_dir) if base_dir is not None else None
            self.approved_root = get_approved_evidence_root(raw_target)

        # 2. Determine destination
        if base_dir is None:
            target_path = (self.approved_root / "runtime" / run_id).resolve()
        else:
            target_path = Path(base_dir).resolve()

        # 3. Invariant: resolved destination MUST be contained inside approved_root
        try:
            target_path.relative_to(self.approved_root)
        except ValueError:
            raise EvidenceFailure(
                f"evidence root escape rejected: destination '{target_path}' is outside approved root '{self.approved_root}'"
            )

        # 4. Check for symlink escape in path components leading to destination
        raw_path = Path(base_dir) if base_dir is not None else (self.approved_root / "runtime" / run_id)
        curr = raw_path
        while curr != self.approved_root and curr != curr.parent:
            if curr.is_symlink():
                resolved_link = curr.resolve()
                try:
                    resolved_link.relative_to(self.approved_root)
                except ValueError:
                    raise EvidenceFailure(
                        f"symlink escape rejected: symlink '{curr}' resolves to '{resolved_link}' outside approved root '{self.approved_root}'"
                    )
            curr = curr.parent

        self.directory = target_path
        self._init_directory()

    def _init_directory(self) -> None:
        try:
            if self.exclusive_creation:
                if self.directory.exists():
                    raise EvidenceFailure(
                        f"run directory '{self.directory}' already exists; collision rejected under exclusive creation"
                    )
                self.directory.mkdir(parents=True, exist_ok=False)
            else:
                self.directory.mkdir(parents=True, exist_ok=True)
            if not self.directory.is_dir():
                raise EvidenceFailure(f"evidence directory '{self.directory}' is not a directory")
        except EvidenceFailure:
            raise
        except Exception as exc:
            raise EvidenceFailure(f"evidence directory initialization failed: {exc}") from exc

    def inject_intent_failure(self, flag: bool = True) -> None:
        self._inject_intent_failure = flag

    def inject_decision_failure(self, flag: bool = True) -> None:
        self._inject_decision_failure = flag

    def inject_result_failure(self, flag: bool = True) -> None:
        self._inject_result_failure = flag

    def inject_partial_write(self, flag: bool = True) -> None:
        self._inject_partial_write = flag

    def inject_dir_error(self, flag: bool = True) -> None:
        self._inject_dir_error = flag

    def inject_flush_failure(self, flag: bool = True) -> None:
        self._inject_flush_failure = flag

    def inject_fsync_failure(self, flag: bool = True) -> None:
        self._inject_fsync_failure = flag

    def _load_evidence_schema(self) -> dict[str, Any]:
        schema_path = ROOT / "agent" / "planner" / "contracts" / "evidence.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def _persist_file(
        self,
        prefix: str,
        payload_data: dict[str, Any],
        expected_state: str,
        observed_state: str,
        derived_from: list[str] | None = None,
    ) -> dict[str, Any]:
        """Atomically persist payload and evidence record with temp -> fsync -> atomic publish pattern."""
        if self._inject_dir_error:
            raise EvidenceFailure("simulated evidence directory error")

        redacted_payload = redact_secrets(payload_data)
        encoded_payload = _canonical_json_bytes(redacted_payload)
        token = uuid.uuid4().hex
        payload_path = self.directory / f"{prefix}-{token}.json"
        tmp_payload_path = self.directory / f"{prefix}-{token}.tmp"

        try:
            with tmp_payload_path.open("xb") as handle:
                if self._inject_partial_write:
                    # Write truncated bytes then fail
                    handle.write(encoded_payload[:max(1, len(encoded_payload) // 2)])
                    handle.flush()
                    raise EvidenceFailure("simulated short/partial payload write")
                written = handle.write(encoded_payload)
                if written != len(encoded_payload):
                    raise EvidenceFailure("incomplete evidence payload write")
                if self._inject_flush_failure:
                    raise EvidenceFailure("simulated flush failure")
                handle.flush()
                if self._inject_fsync_failure:
                    raise EvidenceFailure("simulated fsync failure")
                os.fsync(handle.fileno())
            # Atomic publish to final filename
            os.replace(tmp_payload_path, payload_path)
        except EvidenceFailure:
            raise
        except Exception as exc:
            raise EvidenceFailure(f"failed to write evidence payload: {exc}") from exc
        finally:
            if tmp_payload_path.exists():
                tmp_payload_path.unlink(missing_ok=True)

        # Confirm payload persistence and SHA-256
        if not payload_path.is_file() or payload_path.stat().st_size != len(encoded_payload):
            raise EvidenceFailure("durable persistence confirmation failed for payload file")

        payload_digest = hashlib.sha256(encoded_payload).hexdigest()

        # Build evidence record
        record_token = uuid.uuid4().hex
        record_path = self.directory / f"record-{prefix}-{record_token}.json"
        tmp_record_path = self.directory / f"record-{prefix}-{record_token}.tmp"
        evidence_id = f"EV-{prefix.upper()}-{record_token[:12]}"
        created_utc = _utc_now_iso()

        record = {
            "evidence_id": evidence_id,
            "run_id": self.run_id,
            "path": str(payload_path.relative_to(ROOT)) if payload_path.is_relative_to(ROOT) else str(payload_path),
            "sha256": payload_digest,
            "created_at_utc": created_utc,
            "source": self.source,
            "redacted": True,
            "expected_state": expected_state,
            "observed_state": observed_state,
            "derived_from": list(derived_from or []),
        }

        # Validate schema conformance
        schema = self._load_evidence_schema()
        errors = validate_shape(record, schema)
        if errors:
            raise EvidenceFailure(f"evidence record schema violation: {errors}")

        encoded_record = _canonical_json_bytes(record)
        try:
            with tmp_record_path.open("xb") as handle:
                written = handle.write(encoded_record)
                if written != len(encoded_record):
                    raise EvidenceFailure("incomplete evidence record write")
                if self._inject_flush_failure:
                    raise EvidenceFailure("simulated flush failure")
                handle.flush()
                if self._inject_fsync_failure:
                    raise EvidenceFailure("simulated fsync failure")
                os.fsync(handle.fileno())
            # Atomic publish to final filename
            os.replace(tmp_record_path, record_path)
        except EvidenceFailure:
            raise
        except Exception as exc:
            raise EvidenceFailure(f"failed to write evidence record: {exc}") from exc
        finally:
            if tmp_record_path.exists():
                tmp_record_path.unlink(missing_ok=True)

        # Confirm record persistence
        if not record_path.is_file() or record_path.stat().st_size != len(encoded_record):
            raise EvidenceFailure("durable persistence confirmation failed for record file")

        artifact = {
            "evidence_id": evidence_id,
            "payload_path": str(payload_path),
            "record_path": str(record_path),
            "sha256": payload_digest,
            "created_at_utc": created_utc,
            "derived_from": list(derived_from or []),
        }
        self.artifacts.append(artifact)
        return artifact

    def persist_intent(
        self, intent_data: dict[str, Any], derived_from: list[str] | None = None
    ) -> dict[str, Any]:
        """Persist dispatch intent and policy decision before any network transmission."""
        if self._inject_intent_failure:
            raise EvidenceFailure("simulated intent persistence failure")
        if self._inject_decision_failure:
            raise EvidenceFailure("simulated policy decision persistence failure")

        return self._persist_file(
            prefix="intent",
            payload_data=intent_data,
            expected_state="INTENT_RECORDED",
            observed_state="INTENT_RECORDED",
            derived_from=derived_from,
        )

    def persist_result(
        self, result_data: dict[str, Any], derived_from: list[str] | None = None
    ) -> dict[str, Any]:
        """Persist dispatch result before scheduling any subsequent request."""
        if self._inject_result_failure:
            raise EvidenceFailure("simulated result persistence failure")

        return self._persist_file(
            prefix="result",
            payload_data=result_data,
            expected_state="DISPATCH_CONFIRMED",
            observed_state="DISPATCH_CONFIRMED",
            derived_from=derived_from,
        )

    def persist_phase_artifact(
        self,
        phase_name: str,
        payload_data: dict[str, Any],
        expected_state: str = "PHASE_RECORDED",
        observed_state: str = "PHASE_RECORDED",
        derived_from: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist phase artifact and confirm durability."""
        clean_prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", phase_name.lower())
        return self._persist_file(
            prefix=clean_prefix,
            payload_data=payload_data,
            expected_state=expected_state,
            observed_state=observed_state,
            derived_from=derived_from,
        )
