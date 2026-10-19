"""Simulator Observation Generator (RT-04B).

Transforms transition results and raw simulator observation templates into
canonical, schema-compliant observations conforming to observation.schema.json
and the RT-02 enterprise observation vocabulary.

HARD INVARIANTS:
1. Canonical Vocabulary:
   All emitted facts must strictly adhere to the 15-fact canonical vocabulary
   (TARGET, HOST, SERVICE, ENDPOINT, PARAMETER, CANDIDATE_FINDING, CONFIRMED_FINDING,
   ACCESS, CREDENTIAL, SESSION, REACHABILITY, ACTION_OUTCOME, DETECTION_SIGNAL,
   OBJECTIVE, CONTROL).
2. Secret Redaction & Sanitization:
   Plaintext secrets (password, cleartext, private_key) are never emitted to the Planner.
   Opaque handles and validity states are used instead.
3. Ground Truth Isolation:
   Forbidden ground truth keys (hidden_topology, ground_truth, detector_internal_state)
   are rejected and stripped fail-closed.
4. Schema Conformity:
   Every emitted observation envelope is validated against observation.schema.json
   and validate_canonical_observation before being returned.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from agent.perception.normalizers.enterprise_normalizer import (
    CANONICAL_FACT_TYPES,
    FORBIDDEN_GROUND_TRUTH_KEYS,
    SECRET_FIELD_NAMES,
    make_enterprise_fact_id,
    validate_canonical_observation,
)
from runtime.simulation.engine.transition_engine import TransitionResult


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_value(value: Any) -> Any:
    """Recursively strip forbidden secrets and ground truth keys from values."""
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            k_lower = str(k).lower()
            if k_lower in FORBIDDEN_GROUND_TRUTH_KEYS:
                continue
            if k_lower in SECRET_FIELD_NAMES:
                continue
            sanitized[k] = _sanitize_value(v)
        return sanitized
    elif isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _sanitize_failure_reason(reason: str | None) -> str:
    """Map internal transition failure reason to generic attacker-observable status without leakage.

    Guarantees no internal guard names, transition IDs, vulnerability IDs,
    credential secrets, decoy markers, or defender states leak to the attacker.
    """
    if not reason:
        return "ACTION_FAILED"
    r_lower = reason.lower()
    if "authorized" in r_lower or "safety gate" in r_lower:
        return "ACTION_NOT_AUTHORIZED"
    if "timeout" in r_lower or "connection" in r_lower or "blocked" in r_lower:
        return "CONNECTION_FAILED"
    if "session" in r_lower:
        return "SESSION_REQUIRED"
    if "credential" in r_lower:
        return "AUTHENTICATION_FAILED"
    return "ACTION_EXECUTION_FAILED"


class ObservationGenerator:
    """Generates canonical observation envelopes from simulator transition outcomes."""

    def __init__(self) -> None:
        pass

    def generate_observation(
        self,
        transition_result: TransitionResult,
        run_id: str,
        action_id: str | None = None,
        target_id: str | None = None,
        step: int | None = None,
        timestamp_utc: str | None = None,
    ) -> dict[str, Any]:
        """Convert a TransitionResult into a canonical observation envelope.

        Args:
            transition_result: The result produced by TransitionEngine.
            run_id: Execution run ID.
            action_id: Optional action_id override.
            target_id: Optional target_id override.
            step: Optional sequence step number override.
            timestamp_utc: Optional ISO 8601 UTC timestamp override.

        Returns:
            Dictionary strictly conforming to observation.schema.json.
        """
        eff_action_id = action_id or transition_result.action_id
        eff_target_id = target_id if target_id is not None else transition_result.target_id
        eff_step = step if step is not None else transition_result.new_true_state.current_step
        eff_ts = timestamp_utc or transition_result.timestamp_utc or _now_utc()

        facts: list[dict[str, Any]] = []
        has_outcome_fact = False

        for raw_fact in transition_result.raw_observations:
            fact_type = str(raw_fact.get("fact_type", "ACTION_OUTCOME"))
            if fact_type not in CANONICAL_FACT_TYPES:
                fact_type = "ACTION_OUTCOME"

            subject = str(raw_fact.get("subject", eff_target_id or "UNKNOWN"))
            raw_val = raw_fact.get("value")
            val = _sanitize_value(raw_val)

            conf = max(0.0, min(1.0, float(raw_fact.get("confidence", 1.0))))
            fact_id = make_enterprise_fact_id(fact_type, subject, val)

            facts.append(
                {
                    "fact_id": fact_id,
                    "fact_type": fact_type,
                    "subject": subject,
                    "value": val,
                    "confidence": conf,
                }
            )

            if fact_type == "ACTION_OUTCOME":
                has_outcome_fact = True

        # If transition failed and no ACTION_OUTCOME was explicitly provided in templates,
        # generate an authoritative ACTION_OUTCOME fact reflecting failure reason
        if not transition_result.success and not has_outcome_fact:
            subject = eff_target_id or "ENVIRONMENT"
            val = {"outcome": "FAILURE", "reason": _sanitize_failure_reason(transition_result.reason)}
            facts.append(
                {
                    "fact_id": make_enterprise_fact_id("ACTION_OUTCOME", subject, val),
                    "fact_type": "ACTION_OUTCOME",
                    "subject": subject,
                    "value": val,
                    "confidence": 1.0,
                }
            )

        # Deduplicate facts by (fact_type, subject, canonical_value)
        deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for f in facts:
            val_str = json.dumps(f["value"], sort_keys=True) if isinstance(f["value"], dict) else str(f["value"])
            k = (f["fact_type"], f["subject"], val_str)
            if k not in deduped or f["confidence"] > deduped[k]["confidence"]:
                deduped[k] = f
        final_facts = list(deduped.values())

        # Generate deterministic observation_id
        fact_hash = hashlib.sha256(
            json.dumps([f["fact_id"] for f in final_facts], sort_keys=True).encode("utf-8")
        ).hexdigest()[:10]
        obs_id = f"OBS-SIM-{eff_action_id}-{eff_step}-{fact_hash}"

        obs: dict[str, Any] = {
            "observation_id": obs_id,
            "run_id": run_id,
            "action_id": eff_action_id,
            "timestamp_utc": eff_ts,
            "outcome": "SUCCESS" if transition_result.success else "FAILURE",
            "new_facts": final_facts,
            "evidence_refs": [f"sim-trace://{run_id}/{eff_step}"],
            "source_kind": "SIMULATED",
            "confidence": 1.0,
            "sequence_num": eff_step,
        }

        if eff_target_id:
            obs["source_target"] = eff_target_id

        # Validate against canonical observation schema
        errors = validate_canonical_observation(obs)
        if errors:
            raise ValueError(f"ObservationGenerator produced invalid canonical observation: {errors}")

        return obs
