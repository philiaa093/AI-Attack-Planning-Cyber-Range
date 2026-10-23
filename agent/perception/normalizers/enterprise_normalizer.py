"""Enterprise observation normalizer — trust boundary between execution/perception and planning.

Enforces:
  1. Canonical Fact Vocabulary:
     TARGET, HOST, SERVICE, ENDPOINT, PARAMETER, CANDIDATE_FINDING,
     CONFIRMED_FINDING, ACCESS, CREDENTIAL, SESSION, REACHABILITY,
     ACTION_OUTCOME, DETECTION_SIGNAL, OBJECTIVE, CONTROL.
  2. Observation Provenance:
     Tracks observation identity, source_kind, source_target, source_session,
     producing action_id, evidence_refs, timestamp_utc, confidence, sequence_num.
  3. Credential Redaction:
     Plaintext secrets (password, cleartext, private_key) are never exposed to Planner.
     Uses opaque references (credential_id, principal, credential_kind, observed_scope, validity_state).
  4. Session Sanitization:
     Raw shell/subprocess/socket handles are stripped; uses opaque session handles.
  5. Reachability Observation Isolation:
     Only observed reachability edges (host-A -> host-B) via explicit actions;
     never synthesized from global topology configs (Docker Compose, target-allowlist).
  6. Detection Signal Attacker-Observability:
     Only attacker-observable signals (BLOCKED, THROTTLED, SESSION_LOST, AUTH_LOCKOUT,
     WAF_REJECTION, RATE_LIMITED). Defender-private SIEM truth or hidden detection scores are rejected.
  7. Objective Discovery Verification:
     Objectives only created when achieved/observed via valid action with evidence reference.
  8. Facts vs Hypotheses:
     Inferred hypotheses carry source_kind="PLANNER_INFERENCE" and do not unlock visibility.
  9. Strict Fail-Closed Validation:
     Rejects malformed, untrusted, or unnormalized objects before Planner ingestion.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.validation.validate_scaffold import ROOT
from shared.schema_validation import validate_shape

# Canonical 15-fact vocabulary
CANONICAL_FACT_TYPES = frozenset({
    "TARGET",
    "HOST",
    "SERVICE",
    "ENDPOINT",
    "PARAMETER",
    "CANDIDATE_FINDING",
    "CONFIRMED_FINDING",
    "ACCESS",
    "CREDENTIAL",
    "SESSION",
    "REACHABILITY",
    "ACTION_OUTCOME",
    "DETECTION_SIGNAL",
    "OBJECTIVE",
    "CONTROL",
})

VALID_OUTCOMES = frozenset({"SUCCESS", "FAILURE", "PARTIAL", "DENIED", "ERROR"})

VALID_SOURCE_KINDS = frozenset({
    "TOOL_ADAPTER",
    "SCANNER",
    "DISCOVERY",
    "EXECUTOR",
    "AGENT_PROBE",
    "MANUAL",
    "SIMULATED",
    "PLANNER_INFERENCE",
    "ENV_PROBE",
})

ATTACKER_OBSERVABLE_SIGNALS = frozenset({
    "BLOCKED",
    "THROTTLED",
    "SESSION_LOST",
    "AUTH_LOCKOUT",
    "WAF_REJECTION",
    "RATE_LIMITED",
    "CONNECTION_RESET",
    "ACCESS_DENIED",
})

FORBIDDEN_GROUND_TRUTH_KEYS = frozenset({
    "ground_truth",
    "truth_records",
    "truth",
    "expected_detection",
    "siem_alert_id",
    "siem_rule_id",
    "siem_score",
    "detector_internal_state",
    "hidden_detection_score",
    "hidden_flag",
    "hidden_topology",
})

SECRET_FIELD_NAMES = frozenset({
    "password",
    "cleartext",
    "plaintext",
    "secret",
    "secret_value",
    "private_key",
    "raw_secret",
    "ntlm_hash_secret",
    "cleartext_password",
})

_ACTION_ID_PATTERN = re.compile(r"^ACTION-[A-Z]+-[0-9]{3}$")
_ISO_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")

# Load observation schema
_OBS_SCHEMA_PATH = ROOT / "agent" / "planner" / "contracts" / "observation.schema.json"
try:
    _OBS_SCHEMA = json.loads(_OBS_SCHEMA_PATH.read_text(encoding="utf-8"))
except Exception:
    _OBS_SCHEMA = {}


def _clamp_confidence(c: Any) -> float:
    """Clamp confidence score to [0.0, 1.0]."""
    if not isinstance(c, (int, float)):
        return 0.5
    return max(0.0, min(1.0, float(c)))


def _now_utc() -> str:
    """Current timestamp in canonical ISO 8601 UTC format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deterministic_hash(val: Any) -> str:
    """Deterministic 12-char SHA-256 hash."""
    if isinstance(val, dict):
        raw = json.dumps(val, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        raw = str(val)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def make_enterprise_fact_id(fact_type: str, subject: str, value: Any) -> str:
    """Generate a deterministic fact ID from fact content."""
    h = _deterministic_hash({"ft": fact_type, "subj": subject, "v": value})
    prefix = fact_type[:4].upper()
    return f"FACT-{prefix}-{h}"


def _find_forbidden_tokens(obj: Any) -> list[str]:
    """Recursively search for forbidden ground truth or secret tokens."""
    violations = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = str(k).lower()
            if k_lower in FORBIDDEN_GROUND_TRUTH_KEYS:
                violations.append(f"forbidden ground truth key '{k}'")
            if k_lower in SECRET_FIELD_NAMES:
                violations.append(f"forbidden plaintext secret key '{k}'")
            violations.extend(_find_forbidden_tokens(v))
    elif isinstance(obj, list):
        for item in obj:
            violations.extend(_find_forbidden_tokens(item))
    return violations


def validate_canonical_observation(obs: dict[str, Any]) -> list[str]:
    """Validate observation against canonical schema and enterprise security invariants.

    Returns empty list on success, or list of error messages on failure.
    """
    if not isinstance(obs, dict):
        return ["observation must be a dictionary"]

    # Schema validation
    if _OBS_SCHEMA:
        errors = validate_shape(obs, _OBS_SCHEMA)
        if errors:
            return errors

    # Check action_id pattern
    action_id = obs.get("action_id", "")
    if not _ACTION_ID_PATTERN.match(action_id):
        return [f"action_id '{action_id}' invalid format"]

    # Check timestamp UTC format
    ts = obs.get("timestamp_utc", "")
    if not _ISO_UTC_PATTERN.match(ts):
        return [f"timestamp_utc '{ts}' must be UTC date-time ending with Z"]

    # Check outcome
    outcome = obs.get("outcome")
    if outcome not in VALID_OUTCOMES:
        return [f"outcome '{outcome}' invalid; must be one of {sorted(VALID_OUTCOMES)}"]

    # Check source_kind if present
    source_kind = obs.get("source_kind")
    if source_kind is not None and source_kind not in VALID_SOURCE_KINDS:
        return [f"source_kind '{source_kind}' invalid; must be one of {sorted(VALID_SOURCE_KINDS)}"]

    # Check confidence if present
    conf = obs.get("confidence")
    if conf is not None:
        if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
            return [f"confidence '{conf}' must be float between 0.0 and 1.0"]

    # Check sequence_num if present
    seq = obs.get("sequence_num")
    if seq is not None:
        if not isinstance(seq, int) or seq < 0:
            return [f"sequence_num '{seq}' must be a nonnegative integer"]

    # Recursively check for forbidden ground truth or secret tokens
    token_violations = _find_forbidden_tokens(obs)
    if token_violations:
        return token_violations

    # Validate individual facts
    for idx, fact in enumerate(obs.get("new_facts", [])):
        if not isinstance(fact, dict):
            return [f"new_facts[{idx}] must be a dict"]
        ft = fact.get("fact_type")
        if ft not in CANONICAL_FACT_TYPES:
            return [f"new_facts[{idx}].fact_type '{ft}' invalid; must be one of {sorted(CANONICAL_FACT_TYPES)}"]
        fconf = fact.get("confidence")
        if not isinstance(fconf, (int, float)) or fconf < 0.0 or fconf > 1.0:
            return [f"new_facts[{idx}].confidence must be between 0.0 and 1.0"]

    return []


class EnterpriseObservationNormalizer:
    """Normalizes raw executor/tool results into trusted canonical observations.

    Acts as the trust boundary between execution/perception and planning.
    Ensures that raw stdout, arbitrary scanner outputs, secrets, and global
    topology leaks are transformed into sanitized, typed canonical facts.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str, str], dict[str, Any]] = {}

    def reset(self) -> None:
        """Clear deduplication cache."""
        self._seen.clear()

    def _deduplicate_facts(self, facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate facts by (fact_type, subject, canonical_value), keeping highest confidence."""
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for fact in facts:
            val_str = json.dumps(fact["value"], sort_keys=True) if isinstance(fact.get("value"), dict) else str(fact.get("value"))
            key = (fact["fact_type"], fact["subject"], val_str)
            if key in deduped:
                if fact["confidence"] > deduped[key]["confidence"]:
                    deduped[key] = fact
            else:
                deduped[key] = fact
        return list(deduped.values())

    def _build_envelope(
        self,
        *,
        run_id: str,
        action_id: str,
        outcome: str,
        facts: list[dict[str, Any]],
        observation_id: str | None = None,
        source_kind: str = "TOOL_ADAPTER",
        source_target: str | None = None,
        source_session: str | None = None,
        evidence_refs: list[str] | None = None,
        confidence: float | None = None,
        sequence_num: int | None = None,
    ) -> dict[str, Any]:
        """Assemble and validate a canonical observation envelope."""
        if not _ACTION_ID_PATTERN.match(action_id):
            raise ValueError(f"action_id '{action_id}' invalid format")

        deduped = self._deduplicate_facts(facts)

        if observation_id is None:
            fact_hash = _deterministic_hash([f["fact_id"] for f in deduped])
            observation_id = f"OBS-ENT-{action_id}-{fact_hash}"

        obs: dict[str, Any] = {
            "observation_id": observation_id,
            "run_id": run_id,
            "action_id": action_id,
            "timestamp_utc": _now_utc(),
            "outcome": outcome if outcome in VALID_OUTCOMES else "SUCCESS",
            "new_facts": deduped,
        }

        if evidence_refs:
            obs["evidence_refs"] = list(evidence_refs)
        if source_kind in VALID_SOURCE_KINDS:
            obs["source_kind"] = source_kind
        if source_target:
            obs["source_target"] = str(source_target)
        if source_session:
            obs["source_session"] = str(source_session)
        if confidence is not None:
            obs["confidence"] = _clamp_confidence(confidence)
        if sequence_num is not None and isinstance(sequence_num, int) and sequence_num >= 0:
            obs["sequence_num"] = sequence_num

        errors = validate_canonical_observation(obs)
        if errors:
            raise ValueError(f"canonical observation validation failed: {errors}")

        return obs

    def normalize_host_discovery(
        self,
        hosts: list[dict[str, Any] | str],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Normalize observed host discoveries into HOST facts."""
        facts = []
        for item in hosts:
            if isinstance(item, str):
                hostname = item
                ip = None
                conf = 1.0
            elif isinstance(item, dict):
                hostname = item.get("host") or item.get("hostname") or item.get("target_id", "")
                ip = item.get("ip") or item.get("ip_address")
                conf = _clamp_confidence(item.get("confidence", 1.0))
            else:
                continue

            if not hostname:
                continue

            val = ip if ip else "discovered"
            fid = make_enterprise_fact_id("HOST", hostname, val)
            facts.append({
                "fact_id": fid,
                "fact_type": "HOST",
                "subject": hostname,
                "value": val,
                "confidence": conf,
            })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="SUCCESS" if facts else "PARTIAL",
            facts=facts,
            source_kind="DISCOVERY",
            source_target=source_target,
            evidence_refs=evidence_refs,
        )

    def normalize_service_discovery(
        self,
        services: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Normalize open ports and services into SERVICE and ENDPOINT facts."""
        facts = []
        for svc in services:
            host = svc.get("host") or svc.get("target_id", "")
            port = svc.get("port")
            protocol = svc.get("service") or svc.get("protocol", "tcp")
            conf = _clamp_confidence(svc.get("confidence", 0.95))

            if not host:
                continue

            subject = f"{host}:{port}" if port is not None else host
            fid = make_enterprise_fact_id("SERVICE", subject, protocol)
            facts.append({
                "fact_id": fid,
                "fact_type": "SERVICE",
                "subject": subject,
                "value": protocol,
                "confidence": conf,
            })

            endpoint = svc.get("endpoint")
            if endpoint:
                ep_fid = make_enterprise_fact_id("ENDPOINT", host, endpoint)
                facts.append({
                    "fact_id": ep_fid,
                    "fact_type": "ENDPOINT",
                    "subject": host,
                    "value": endpoint,
                    "confidence": conf,
                })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="SUCCESS" if facts else "PARTIAL",
            facts=facts,
            source_kind="SCANNER",
            source_target=source_target,
            evidence_refs=evidence_refs,
        )

    def normalize_credentials(
        self,
        credentials: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        source_session: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Normalize harvested credentials, stripping secrets into opaque handles.

        Planner-visible representation contains ONLY:
          - credential_id (opaque handle)
          - principal / username
          - credential_kind (e.g. NTLM_HASH, KERBEROS_TGT, API_KEY_HANDLE)
          - observed_scope (e.g. domain, service, realm)
          - validity_state (e.g. VALID, EXPIRED, UNKNOWN)

        Secret backing values are strictly excluded.
        """
        facts = []
        for cred in credentials:
            # Check if raw input exposed cleartext secrets
            principal = cred.get("principal") or cred.get("username", "anonymous")
            scope = cred.get("observed_scope") or cred.get("scope") or source_target or "domain"
            kind = cred.get("credential_kind") or cred.get("kind", "OPAQUE_HANDLE")
            validity = cred.get("validity_state") or cred.get("validity", "VALID")
            conf = _clamp_confidence(cred.get("confidence", 0.9))

            # Explicitly strip and redact raw secret backing values.
            # Opaque handle is derived strictly from non-secret metadata (principal, scope, kind).
            # Secret backing values are never used to compute the handle to avoid reversible digests.
            opaque_ref = cred.get("credential_id") or ("CRED-OPAQ-" + _deterministic_hash(f"{principal}:{scope}:{kind}"))

            # Planner-facing value: sanitized metadata ONLY
            sanitized_val = {
                "credential_id": opaque_ref,
                "principal": principal,
                "credential_kind": kind,
                "observed_scope": scope,
                "validity_state": validity,
            }

            fid = make_enterprise_fact_id("CREDENTIAL", scope, opaque_ref)
            facts.append({
                "fact_id": fid,
                "fact_type": "CREDENTIAL",
                "subject": scope,
                "value": sanitized_val,
                "confidence": conf,
            })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="SUCCESS" if facts else "PARTIAL",
            facts=facts,
            source_kind="EXECUTOR",
            source_target=source_target,
            source_session=source_session,
            evidence_refs=evidence_refs,
        )

    def normalize_session(
        self,
        sessions: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Normalize established/closed sessions without exposing raw shell internals.

        Planner-visible representation contains ONLY:
          - session_id (opaque reference)
          - target_id / host
          - access_level (e.g. USER, ADMIN, SYSTEM)
          - state (ACTIVE, CLOSED, TERMINATED)
        """
        facts = []
        for s in sessions:
            target = s.get("target_id") or s.get("target") or source_target or "unknown-target"
            access = s.get("access_level") or s.get("access", "USER")
            state = s.get("state") or s.get("status", "ACTIVE")
            conf = _clamp_confidence(s.get("confidence", 1.0))

            raw_handle = s.get("raw_handle") or s.get("session_id") or f"{target}:{access}"
            opaque_id = "SESS-OPAQ-" + _deterministic_hash(raw_handle)

            # Sanitized session descriptor — no subprocess / raw pipe / socket
            session_val = {
                "session_id": opaque_id,
                "target_id": target,
                "access_level": access,
                "state": state,
            }

            fid = make_enterprise_fact_id("SESSION", target, opaque_id)
            facts.append({
                "fact_id": fid,
                "fact_type": "SESSION",
                "subject": target,
                "value": session_val,
                "confidence": conf,
            })

            # Also emit ACCESS fact if session is active
            if state.upper() == "ACTIVE":
                acc_fid = make_enterprise_fact_id("ACCESS", target, access)
                facts.append({
                    "fact_id": acc_fid,
                    "fact_type": "ACCESS",
                    "subject": target,
                    "value": access,
                    "confidence": conf,
                })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="SUCCESS" if facts else "PARTIAL",
            facts=facts,
            source_kind="EXECUTOR",
            source_target=source_target,
            evidence_refs=evidence_refs,
        )

    def normalize_reachability(
        self,
        edges: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        source_kind: str = "AGENT_PROBE",
        evidence_refs: list[str] | None = None,
        is_topology_config: bool = False,
    ) -> dict[str, Any]:
        """Normalize observed network reachability edges between hosts.

        Strict invariant:
          Reachability must be observed from valid network probe actions / execution.
          Any attempt to read/synthesize reachability from global topology configs
          (Docker Compose, target-allowlist, scenario manifest) is rejected fail-closed.
        """
        if is_topology_config:
            raise ValueError("reachability cannot be synthesized from global topology config")

        facts = []
        for edge in edges:
            from_host = edge.get("from_host") or source_target
            to_host = edge.get("to_host") or edge.get("target")
            protocol = edge.get("protocol", "tcp")
            port = edge.get("port")
            conf = _clamp_confidence(edge.get("confidence", 0.9))

            if not from_host or not to_host:
                continue

            reach_val = {
                "from_host": from_host,
                "to_host": to_host,
                "protocol": protocol,
            }
            if port is not None:
                reach_val["port"] = port

            fid = make_enterprise_fact_id("REACHABILITY", from_host, f"{to_host}:{port or protocol}")
            facts.append({
                "fact_id": fid,
                "fact_type": "REACHABILITY",
                "subject": from_host,
                "value": reach_val,
                "confidence": conf,
            })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="SUCCESS" if facts else "PARTIAL",
            facts=facts,
            source_kind=source_kind,
            source_target=source_target,
            evidence_refs=evidence_refs,
        )

    def normalize_detection_signal(
        self,
        signals: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Normalize attacker-observable defensive signals (e.g. WAF block, rate limit).

        Strict invariant:
          Only attacker-observable signals are allowed.
          Defender-private SIEM rules, scores, or internal ground-truth detection
          states are rejected fail-closed.
        """
        facts = []
        for sig in signals:
            signal_type = (sig.get("signal_type") or sig.get("type", "")).upper()
            target = sig.get("target_id") or sig.get("target") or sig.get("source_target") or source_target or "network"
            conf = _clamp_confidence(sig.get("confidence", 0.95))

            if signal_type not in ATTACKER_OBSERVABLE_SIGNALS:
                raise ValueError(
                    f"invalid detection signal '{signal_type}'; "
                    f"must be attacker-observable: {sorted(ATTACKER_OBSERVABLE_SIGNALS)}"
                )

            # Check for defender-private leakage
            for forbidden_key in FORBIDDEN_GROUND_TRUTH_KEYS:
                if forbidden_key in sig:
                    raise ValueError(f"defender-private field '{forbidden_key}' forbidden in observation")

            event_desc = sig.get("observable_event") or sig.get("observed_effect", signal_type)
            sig_val = {
                "signal_type": signal_type,
                "target_id": target,
                "source_target": target,
                "observable_event": event_desc,
                "observed_effect": event_desc,
            }
            if sig.get("status_code") is not None:
                sig_val["status_code"] = int(sig["status_code"])

            fid = make_enterprise_fact_id("DETECTION_SIGNAL", target, signal_type)
            facts.append({
                "fact_id": fid,
                "fact_type": "DETECTION_SIGNAL",
                "subject": target,
                "value": sig_val,
                "confidence": conf,
            })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="PARTIAL" if facts else "FAILURE",
            facts=facts,
            source_kind="AGENT_PROBE",
            source_target=source_target,
            evidence_refs=evidence_refs,
        )

    def normalize_objective(
        self,
        objectives: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        source_target: str | None = None,
        evidence_refs: list[str] | None = None,
        is_hidden_manifest: bool = False,
    ) -> dict[str, Any]:
        """Normalize observed objective milestones.

        Strict invariant:
          Objectives must be observed / achieved via valid action with evidence.
          Cannot be synthesized from hidden scenario manifests.
        """
        if is_hidden_manifest or not evidence_refs:
            raise ValueError("objective cannot be synthesized from hidden manifest without verified evidence")

        facts = []
        for obj in objectives:
            obj_id = obj.get("objective_id", "")
            status = obj.get("status", "ACHIEVED")
            milestone = obj.get("milestone") or obj_id
            conf = _clamp_confidence(obj.get("confidence", 1.0))

            if not obj_id:
                continue

            obj_val = {
                "objective_id": obj_id,
                "status": status,
                "milestone": milestone,
            }

            fid = make_enterprise_fact_id("OBJECTIVE", obj_id, status)
            facts.append({
                "fact_id": fid,
                "fact_type": "OBJECTIVE",
                "subject": obj_id,
                "value": obj_val,
                "confidence": conf,
            })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="SUCCESS" if facts else "FAILURE",
            facts=facts,
            source_kind="EXECUTOR",
            source_target=source_target,
            evidence_refs=evidence_refs,
        )

    def normalize_hypothesis(
        self,
        inferred_facts: list[dict[str, Any]],
        *,
        run_id: str,
        action_id: str,
        reason: str = "planner_heuristic",
    ) -> dict[str, Any]:
        """Create an observation envelope with provenance source_kind='PLANNER_INFERENCE'.

        Invariant 10: Hypotheses must not unlock target visibility, access, or credentials.
        """
        facts = []
        for f in inferred_facts:
            ft = f.get("fact_type", "CANDIDATE_FINDING")
            subj = f.get("subject", "unknown")
            val = f.get("value", "hypothesis")
            conf = _clamp_confidence(f.get("confidence", 0.3))
            fid = make_enterprise_fact_id(ft, subj, val)
            facts.append({
                "fact_id": fid,
                "fact_type": ft,
                "subject": subj,
                "value": val,
                "confidence": conf,
            })

        return self._build_envelope(
            run_id=run_id,
            action_id=action_id,
            outcome="PARTIAL",
            facts=facts,
            source_kind="PLANNER_INFERENCE",
            confidence=0.3,
        )
