"""Observed-state planner with strict schema validation, provenance tracking, and explicit fallback policy.

Enforces:
  - Planner input is strictly observed state from StateManager (no preset routes, no ground truth answer key)
  - Output conforms strictly to plan.schema.json with additionalProperties: false
  - Mode provenance distinguishes requested_mode from actual_mode and records fallback_reason
  - Fallback to rule baseline only when explicitly authorized (fallback_allowed=True); otherwise halts
  - Provider failure is strictly distinguished from target failure and rule decision
  - Zero target network dispatch from planner decisions
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from runtime.discovery_gate import (
    CentralizedSafetyGate,
    load_canonical_action_allowlist,
    load_canonical_target_allowlist,
)
from runtime.discovery_recorder import redact_secrets
from scripts.validation.validate_scaffold import ROOT, validate_shape

ACTION_CATALOG = {
    "ACTION-RECON-001": {"name": "DISCOVER_TARGET",      "class": "RECON"},
    "ACTION-RECON-002": {"name": "DISCOVER_WEB_SURFACE", "class": "RECON"},
    "ACTION-SCAN-001":  {"name": "PASSIVE_WEB_SCAN",     "class": "SCAN"},
    "ACTION-SCAN-002":  {"name": "ACTIVE_WEB_SCAN",      "class": "SCAN"},
    "ACTION-WEB-001":   {"name": "TEST_SQLI_CLASS",      "class": "WEB_TEST"},
    "ACTION-WEB-002":   {"name": "TEST_XSS_CLASS",       "class": "WEB_TEST"},
    "ACTION-WEB-003":   {"name": "TEST_PATH_TRAVERSAL",  "class": "WEB_TEST"},
    "ACTION-PLAN-001":  {"name": "CHANGE_TARGET",        "class": "PLAN"},
    "ACTION-PLAN-002":  {"name": "CHANGE_HYPOTHESIS",    "class": "PLAN"},
    "ACTION-PLAN-003":  {"name": "REVISIT_EVIDENCE",     "class": "PLAN"},
    "ACTION-END-001":   {"name": "STOP_SUCCESS",         "class": "STOP"},
    "ACTION-END-002":   {"name": "STOP_BUDGET",          "class": "STOP"},
    "ACTION-END-003":   {"name": "STOP_NO_PROGRESS",     "class": "STOP"},
}

SYSTEM_PROMPT = """You are a security planning agent operating inside an isolated lab cyber range.
Given the observed pentest state, select the single best next action from the allowed catalog.
Output ONLY a JSON object matching this schema:
{
  "schema_version": "1.0",
  "plan_id": "<uuid>",
  "objective_id": "<string>",
  "action_id": "<ACTION-CLASS-NNN>",
  "target_id": "<lab-target-id>",
  "reason_code": "<snake_case_label>",
  "confidence": 1.0
}
No extra text, no markdown fences."""


@dataclass
class PlannerResult:
    proposal: dict[str, Any]
    mode_provenance: dict[str, Any]
    validation_errors: list[str] = field(default_factory=list)
    is_valid: bool = True


def _call_real_provider(
    system_prompt: str,
    user_prompt: str,
    timeout: float = 10.0,
    max_response_bytes: int = 8192,
) -> tuple[str | None, str | None, dict[str, Any]]:
    """Invoke real provider if API key and configuration exist in environment."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        return None, "MISSING_API_KEY", {}

    api_base = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    parsed = urllib.parse.urlsplit(api_base)
    host = parsed.hostname or "api.openai.com"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path.rstrip("/") + "/chat/completions"

    payload_data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 256,
        "temperature": 0.1,
    }
    encoded = json.dumps(payload_data).encode("utf-8")

    t0 = time.monotonic()
    try:
        conn = http.client.HTTPSConnection(host, port, timeout=timeout) if parsed.scheme == "https" else http.client.HTTPConnection(host, port, timeout=timeout)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Length": str(len(encoded)),
        }
        conn.request("POST", path, body=encoded, headers=headers)
        res = conn.getresponse()
        elapsed_ms = (time.monotonic() - t0) * 1000

        raw = res.read(max_response_bytes)
        conn.close()

        if res.status != 200:
            return None, f"HTTP_{res.status}", {"status": res.status, "latency_ms": elapsed_ms}

        data = json.loads(raw.decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        metadata = {
            "model_returned": data.get("model", model),
            "usage": data.get("usage", {}),
            "latency_ms": round(elapsed_ms, 1),
        }
        return content, None, metadata
    except Exception as exc:
        return None, f"PROVIDER_ERROR_{type(exc).__name__}", {}


class ObservedStatePlanner:
    """Planner proposing actions from observed StateManager state with strict provenance and validation."""

    def __init__(
        self,
        target_id: str,
        objective_id: str = "OBJ-001",
        requested_mode: str = "RULE",
        fallback_allowed: bool = True,
        effective_targets: set[str] | None = None,
        provider_callable: Callable[[str, str], str | None] | None = None,
        configured_provider: str = "openai-compatible",
        configured_model: str = "gpt-4o-mini",
    ) -> None:
        self.target_id = target_id
        self.objective_id = objective_id
        self.requested_mode = requested_mode.upper().strip()
        self.fallback_allowed = fallback_allowed
        self.effective_targets = (
            set(effective_targets)
            if effective_targets is not None
            else load_canonical_target_allowlist()
        )
        self.provider_callable = provider_callable
        self.configured_provider = configured_provider
        self.configured_model = configured_model

        # Load plan schema
        plan_schema_path = ROOT / "agent" / "planner" / "contracts" / "plan.schema.json"
        self._plan_schema = json.loads(plan_schema_path.read_text(encoding="utf-8"))

    def propose(self, state: dict[str, Any]) -> PlannerResult:
        """Evaluate state and return a validated proposal with complete mode provenance."""
        remaining_budget = state.get("remaining_budget", {})
        actions_budget = remaining_budget.get("actions", 1)
        phase = state.get("phase", "RECON")
        previous = list(state.get("previous_actions", []))
        facts = list(state.get("observed_facts", []))
        endpoints = list(state.get("discovered_endpoints", []))

        # Stop condition 1: Budget exhausted
        if actions_budget <= 0:
            proposal = {
                "schema_version": "1.0",
                "plan_id": str(uuid.uuid4()),
                "objective_id": state.get("objective_id", self.objective_id),
                "action_id": "ACTION-END-002",
                "target_id": self.target_id,
                "reason_code": "budget_exhausted",
                "confidence": 1.0,
            }
            return self._build_result(
                proposal=proposal,
                actual_mode="RULE",
                fallback_reason=None,
                origin="budget_stop",
            )

        # Stop condition 2: Terminal phase
        if phase == "TERMINAL":
            proposal = {
                "schema_version": "1.0",
                "plan_id": str(uuid.uuid4()),
                "objective_id": state.get("objective_id", self.objective_id),
                "action_id": "ACTION-END-001",
                "target_id": self.target_id,
                "reason_code": "terminal_phase_stop",
                "confidence": 1.0,
            }
            return self._build_result(
                proposal=proposal,
                actual_mode="RULE",
                fallback_reason=None,
                origin="terminal_stop",
            )

        # Mode execution: RULE mode
        if self.requested_mode == "RULE":
            proposal = self._derive_rule_proposal(state, previous, facts, endpoints)
            return self._build_result(
                proposal=proposal,
                actual_mode="RULE",
                fallback_reason=None,
                origin="rule_engine",
            )

        # Mode execution: LLM / LLM_MOCK mode
        provider_text: str | None = None
        provider_err: str | None = None
        provider_meta: dict[str, Any] = {}

        user_prompt = self._build_minimized_prompt(state, endpoints, facts, previous)

        if self.provider_callable is not None:
            # Test or mock provider callable
            try:
                provider_text = self.provider_callable(SYSTEM_PROMPT, user_prompt)
                if not provider_text:
                    provider_err = "MOCK_PROVIDER_RETURNED_EMPTY"
            except Exception as exc:
                provider_err = f"MOCK_PROVIDER_ERROR_{type(exc).__name__}"
        else:
            # Real provider if credentials present
            provider_text, provider_err, provider_meta = _call_real_provider(
                SYSTEM_PROMPT, user_prompt
            )

        # Attempt to parse and validate provider output
        parsed_plan: dict[str, Any] | None = None
        if provider_text:
            parsed_plan, parse_err = self._parse_provider_json(provider_text)
            if not parsed_plan:
                provider_err = parse_err or "MALFORMED_PROVIDER_OUTPUT"

        if parsed_plan:
            # Successful LLM decision
            return self._build_result(
                proposal=parsed_plan,
                actual_mode="LLM",
                fallback_reason=None,
                origin="llm_provider",
                extra_meta=provider_meta,
            )

        # Provider failed: evaluate fallback policy
        if self.fallback_allowed:
            fallback_proposal = self._derive_rule_proposal(state, previous, facts, endpoints)
            return self._build_result(
                proposal=fallback_proposal,
                actual_mode="RULE",
                fallback_reason=provider_err or "PROVIDER_UNAVAILABLE",
                origin="rule_fallback",
                extra_meta=provider_meta,
            )
        else:
            # Fallback explicitly forbidden -> STOP
            halt_proposal = {
                "schema_version": "1.0",
                "plan_id": str(uuid.uuid4()),
                "objective_id": state.get("objective_id", self.objective_id),
                "action_id": "ACTION-END-003",
                "target_id": self.target_id,
                "reason_code": "provider_unavailable_halt",
                "confidence": 1.0,
            }
            return self._build_result(
                proposal=halt_proposal,
                actual_mode="NONE",
                fallback_reason=f"FALLBACK_NOT_ALLOWED:{provider_err}",
                origin="provider_halt_stop",
                extra_meta=provider_meta,
            )

    def _derive_rule_proposal(
        self,
        state: dict[str, Any],
        previous: list[str],
        facts: list[dict[str, Any]],
        endpoints: list[str],
    ) -> dict[str, Any]:
        """Observation-driven rule baseline with zero route name assumptions."""
        obj_id = state.get("objective_id", self.objective_id)

        # Extract semantic sets independent of observation ordering
        observed_endpoints = set(endpoints)
        observed_services = set(state.get("discovered_services", []))
        refused_actions = set(state.get("refused_actions", []))
        target_facts = set()

        for f in facts:
            ft = f.get("fact_type", "")
            val = f.get("value")
            if ft in ("TARGET", "TARGET_DISCOVERED", "HOST") and val:
                target_facts.add(val)
            elif ft == "SERVICE" and val:
                observed_services.add(val)
            elif ft == "ENDPOINT" and val:
                observed_endpoints.add(val)
            elif ft in ("REFUSAL", "DENIAL", "ACTION_REFUSED") or (ft == "ACTION_OUTCOME" and val in ("REFUSED", "DENIED")):
                action_ref = f.get("subject") if (ft == "ACTION_OUTCOME") else (val or f.get("action_id"))
                if not action_ref and val and str(val).startswith("ACTION-"):
                    action_ref = val
                if action_ref:
                    refused_actions.add(action_ref)

        has_target_info = bool(target_facts) or ("ACTION-RECON-001" in previous)

        if not has_target_info and "ACTION-RECON-001" not in refused_actions:
            action_id = "ACTION-RECON-001"
            reason = "initial_target_discovery"
            confidence = 0.95
        elif "ACTION-RECON-002" not in previous and "ACTION-RECON-002" not in refused_actions:
            action_id = "ACTION-RECON-002"
            reason = "surface_discovery_required"
            confidence = 0.90
        elif observed_endpoints and "ACTION-SCAN-001" not in previous and "ACTION-SCAN-001" not in refused_actions:
            action_id = "ACTION-SCAN-001"
            reason = "passive_scan_discovered_surface"
            confidence = 0.85
        else:
            action_id = "ACTION-END-001"
            reason = "discovery_surface_complete"
            confidence = 1.0

        return {
            "schema_version": "1.0",
            "plan_id": str(uuid.uuid4()),
            "objective_id": obj_id,
            "action_id": action_id,
            "target_id": self.target_id,
            "reason_code": reason,
            "confidence": confidence,
        }

    def _parse_provider_json(self, raw_text: str) -> tuple[dict[str, Any] | None, str | None]:
        """Strictly parse and validate provider JSON matching plan.schema.json."""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            # Try to extract substring
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None, "NO_JSON_OBJECT_FOUND"
            try:
                data = json.loads(match.group())
            except Exception as exc:
                return None, f"JSON_DECODE_ERROR_{type(exc).__name__}"

        if not isinstance(data, dict):
            return None, "ROOT_NOT_OBJECT"

        # Validate schema shape (additionalProperties: false)
        errors = validate_shape(data, self._plan_schema)
        if errors:
            return None, f"SCHEMA_VALIDATION_ERROR_{errors[0]}"

        # Action catalog check
        if data.get("action_id") not in ACTION_CATALOG:
            return None, f"UNKNOWN_ACTION_ID_{data.get('action_id')}"

        # Target allowlist check
        target = data.get("target_id")
        if target != self.target_id or target not in self.effective_targets:
            return None, f"UNAUTHORIZED_TARGET_{target}"

        return data, None

    def _build_minimized_prompt(
        self,
        state: dict[str, Any],
        endpoints: list[str],
        facts: list[dict[str, Any]],
        previous: list[str],
    ) -> str:
        """Build minimized prompt containing no secrets, raw cookies, or full HTML bodies."""
        return (
            f"Target: {self.target_id}\n"
            f"Objective: {state.get('objective_id', self.objective_id)}\n"
            f"Phase: {state.get('phase', 'RECON')}\n"
            f"Remaining actions: {state.get('remaining_budget', {}).get('actions', 0)}\n"
            f"Previous actions: {previous}\n"
            f"Discovered endpoints count: {len(endpoints)}\n"
            f"Observed facts count: {len(facts)}\n"
            f"Choose next action from catalog: ACTION-RECON-001, ACTION-RECON-002, ACTION-SCAN-001, ACTION-END-001, ACTION-END-002, ACTION-END-003."
        )

    def _build_result(
        self,
        proposal: dict[str, Any],
        actual_mode: str,
        fallback_reason: str | None,
        origin: str,
        extra_meta: dict[str, Any] | None = None,
    ) -> PlannerResult:
        errors = validate_shape(proposal, self._plan_schema)
        is_valid = len(errors) == 0

        mode_provenance = {
            "requested_mode": self.requested_mode,
            "actual_mode": actual_mode,
            "fallback_reason": fallback_reason,
            "provider": self.configured_provider if actual_mode == "LLM" else "rule_engine",
            "model": self.configured_model if actual_mode == "LLM" else "none",
            "decision_origin": origin,
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if extra_meta:
            mode_provenance.update(extra_meta)

        return PlannerResult(
            proposal=proposal,
            mode_provenance=mode_provenance,
            validation_errors=errors,
            is_valid=is_valid,
        )

    def evaluate_proposal_against_gate(
        self,
        proposal: dict[str, Any],
        gate: CentralizedSafetyGate,
    ) -> dict[str, Any]:
        """Safety evaluation only — strictly ZERO target network dispatch."""
        target = proposal.get("target_id")
        action = proposal.get("action_id")

        if not target or target not in gate.effective_targets:
            return {"decision": "DENIED", "reason": "TARGET_NOT_ALLOWLISTED", "target_dispatches": 0}

        if not action or action not in gate.action_allowlist:
            return {"decision": "DENIED", "reason": "ACTION_NOT_ALLOWLISTED", "target_dispatches": 0}

        if gate.kill_switch.is_active():
            return {"decision": "DENIED", "reason": "KILL_SWITCH_ACTIVE", "target_dispatches": 0}

        if not gate.budget_tracker.can_request():
            return {"decision": "DENIED", "reason": "BUDGET_EXHAUSTED", "target_dispatches": 0}

        return {"decision": "PERMITTED_PROPOSAL_ONLY", "reason": "VALID_PROPOSAL", "target_dispatches": 0}
