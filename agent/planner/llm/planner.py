"""
LLM Planner — adaptive pentest planning via LLM.
Maps PTES phase + observed facts → next action from action catalog.

Design:
- Takes state dict (from StateManager.get_state())
- Builds a structured prompt with current knowledge
- Calls LLM (via openai-compatible API or fallback stub)
- Returns plan dict conforming to plan.schema.json
- Falls back to rule-based decisions if LLM unavailable

Safety: output is a PROPOSAL — Safety gate must approve before execution.
Status: IMPLEMENTED (not VALIDATED without evidence)
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from agent.planner.action_catalog import ACTION_CATALOG

# PTES phase → allowed action classes
PTES_PHASE_ACTIONS: dict[str, list[str]] = {
    "pre_engagement":        ["RECON"],
    "intelligence_gathering": ["RECON", "SCAN"],
    "threat_modeling":       ["SCAN", "PLAN"],
    "vulnerability_research": ["SCAN", "WEB_TEST"],
    "exploitation":          ["WEB_TEST"],
    "post_exploitation":     ["WEB_TEST", "PLAN"],
    "reporting":             ["PLAN", "STOP"],
}

# Internal state machine phase → action class filter
INTERNAL_PHASE_MAP = {
    "RECON":     ["RECON"],
    "DISCOVERY": ["RECON", "SCAN"],
    "ANALYSIS":  ["SCAN", "PLAN"],
    "TESTING":   ["WEB_TEST"],
    "REPLAN":    ["PLAN"],
    "TERMINAL":  ["STOP"],
}

SYSTEM_PROMPT = """You are a security planning agent operating inside an isolated lab cyber range.
Your role: given the current pentest state (observed facts, phase, budget, previous actions),
select the SINGLE best next action from the allowed catalog.

Rules:
1. Output ONLY valid JSON matching the plan schema — no explanation, no markdown fences.
2. action_id MUST be from the allowed catalog list provided.
3. reason_code MUST be a short snake_case label (e.g. "initial_recon", "xss_candidate_found").
4. confidence is 0.0–1.0 based on how certain you are this action is useful.
5. Never propose STOP unless all testable classes have been attempted or budget is exhausted.
6. Do not repeat an action already in previous_actions unless evidence requires it.
7. Prioritize: if RECON not done → RECON; if surface unknown → SCAN; if candidate found → WEB_TEST.

Plan schema:
{
  "schema_version": "1.0",
  "plan_id": "<uuid>",
  "objective_id": "<from state>",
  "action_id": "<ACTION-CLASS-NNN>",
  "target_id": "<lab-target-id>",
  "reason_code": "<snake_case_label>",
  "confidence": 0.0
}"""

USER_PROMPT_TEMPLATE = """Current state:
- Target: {target_id}
- PTES Phase: {ptes_phase}
- Internal Phase: {internal_phase}
- Run ID: {run_id}
- Budget remaining: {budget}
- Previous actions: {previous_actions}

Observed facts ({fact_count} total):
{facts_summary}

Allowed actions for this phase:
{allowed_actions}

Select the single best next action and return JSON only."""


def _facts_summary(facts: list[dict]) -> str:
    """Summarize facts for LLM prompt (bounded length)."""
    lines = []
    for f in facts[:30]:  # limit tokens
        lines.append(
            f"  [{f.get('fact_type','?')}] {f.get('subject','?')} → "
            f"{f.get('value','?')} (conf={f.get('confidence', 0):.2f})"
        )
    if len(facts) > 30:
        lines.append(f"  ... and {len(facts) - 30} more facts")
    return "\n".join(lines) if lines else "  (none)"


def _allowed_actions_for_phase(internal_phase: str) -> list[str]:
    """Return action IDs allowed for given internal phase."""
    allowed_classes = INTERNAL_PHASE_MAP.get(internal_phase, list(ACTION_CATALOG.keys()))
    return [
        f"{aid} ({meta['name']})"
        for aid, meta in ACTION_CATALOG.items()
        if meta["class"] in allowed_classes
    ]


def _ptes_phase_label(internal_phase: str, previous_actions: list[str]) -> str:
    """Map internal phase to PTES stage label."""
    if not previous_actions:
        return "pre_engagement"
    action_classes = {
        ACTION_CATALOG.get(a, {}).get("class", "") for a in previous_actions
    }
    if "WEB_TEST" in action_classes:
        return "exploitation"
    if "SCAN" in action_classes:
        return "vulnerability_research"
    if "RECON" in action_classes:
        return "intelligence_gathering"
    return "threat_modeling"


def _rule_fallback(state: dict, target_id: str) -> dict:
    """Deterministic rule-based fallback when LLM is unavailable."""
    phase = state.get("phase", "RECON")
    previous = state.get("previous_actions", [])
    facts = state.get("observed_facts", [])
    budget = state.get("remaining_budget", {})

    if budget.get("actions", 1) <= 0:
        action_id = "ACTION-END-002"
        reason = "budget_exhausted"
        confidence = 1.0
    elif "ACTION-RECON-001" not in previous:
        action_id = "ACTION-RECON-001"
        reason = "initial_recon_required"
        confidence = 0.95
    elif "ACTION-RECON-002" not in previous:
        action_id = "ACTION-RECON-002"
        reason = "surface_discovery_required"
        confidence = 0.90
    elif "ACTION-SCAN-001" not in previous:
        action_id = "ACTION-SCAN-001"
        reason = "passive_scan_required"
        confidence = 0.85
    else:
        # Check facts for candidates
        candidate_types = {
            f["value"] for f in facts
            if f.get("fact_type") == "CANDIDATE_FINDING"
        }
        confirmed_types = {
            f["value"] for f in facts
            if f.get("fact_type") == "CONFIRMED_FINDING"
        }
        tested = set()
        if "ACTION-WEB-001" in previous:
            tested.add("sqli")
        if "ACTION-WEB-002" in previous:
            tested.add("xss")
        if "ACTION-WEB-003" in previous:
            tested.add("path-traversal")

        if "sqli_signal" in candidate_types and "sqli" not in tested:
            action_id = "ACTION-WEB-001"
            reason = "sqli_candidate_found"
            confidence = 0.80
        elif "xss_signal" in candidate_types and "xss" not in tested:
            action_id = "ACTION-WEB-002"
            reason = "xss_candidate_found"
            confidence = 0.80
        elif "path_traversal_signal" in candidate_types and "path-traversal" not in tested:
            action_id = "ACTION-WEB-003"
            reason = "path_traversal_candidate_found"
            confidence = 0.80
        elif not candidate_types and "ACTION-SCAN-002" not in previous:
            action_id = "ACTION-SCAN-002"
            reason = "active_scan_no_candidates"
            confidence = 0.65
        elif len(confirmed_types) >= len(candidate_types) and confirmed_types:
            action_id = "ACTION-END-001"
            reason = "all_candidates_confirmed"
            confidence = 0.90
        else:
            action_id = "ACTION-END-003"
            reason = "no_further_progress"
            confidence = 0.70

    return {
        "schema_version": "1.0",
        "plan_id": str(uuid.uuid4()),
        "objective_id": state.get("objective_id", "OBJ-001"),
        "action_id": action_id,
        "target_id": target_id,
        "reason_code": reason,
        "confidence": confidence,
        "planner_mode": "RULE_FALLBACK",
    }


def _call_llm(prompt_system: str, prompt_user: str) -> str | None:
    """Call LLM API. Returns raw text response or None on failure."""
    # Try OpenAI-compatible API
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        return None

    try:
        import urllib.request
        api_base = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user},
            ],
            "max_tokens": 256,
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        # LLM call failed — fall back to rules
        return None


def _parse_plan_json(text: str, state: dict, target_id: str) -> dict | None:
    """Extract and validate plan JSON from LLM response."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return None
        try:
            plan = json.loads(match.group())
        except Exception:
            return None

    # Validate required fields
    required = ("objective_id", "action_id", "target_id", "reason_code", "confidence")
    if not all(k in plan for k in required):
        return None

    # Validate action_id is in catalog
    if plan.get("action_id") not in ACTION_CATALOG:
        return None

    # Validate target_id matches allowlist
    if not re.match(r'^lab-[a-z0-9-]+$', plan.get("target_id", "")):
        return None

    # Ensure plan_id exists
    if "plan_id" not in plan:
        plan["plan_id"] = str(uuid.uuid4())
    plan["schema_version"] = "1.0"
    plan["planner_mode"] = "LLM"
    return plan


class LLMPlanner:
    """
    Adaptive LLM-based pentest planner.

    Usage:
        planner = LLMPlanner(target_id="lab-webapp-a")
        plan = planner.propose(state)  # state from StateManager.get_state()
        # plan is proposal only — requires safety gate approval
    """

    def __init__(self, target_id: str, objective_id: str = "OBJ-PTES-001") -> None:
        if not re.match(r'^lab-[a-z0-9-]+$', target_id):
            raise ValueError(f"invalid target_id '{target_id}'")
        self.target_id = target_id
        self.objective_id = objective_id
        self._llm_available: bool | None = None  # lazy detect

    def propose(self, state: dict) -> dict:
        """
        Given current state, propose the next action.

        Returns:
            plan dict conforming to plan.schema.json.
            This is a PROPOSAL — safety gate must approve before execution.
        """
        phase = state.get("phase", "RECON")
        previous = state.get("previous_actions", [])
        facts = state.get("observed_facts", [])
        budget = state.get("remaining_budget", {})

        # Hard-stop if budget exhausted
        if budget.get("actions", 1) <= 0:
            return {
                "schema_version": "1.0",
                "plan_id": str(uuid.uuid4()),
                "objective_id": state.get("objective_id", self.objective_id),
                "action_id": "ACTION-END-002",
                "target_id": self.target_id,
                "reason_code": "budget_exhausted",
                "confidence": 1.0,
                "planner_mode": "LLM",
            }

        # Build prompt
        ptes_phase = _ptes_phase_label(phase, previous)
        allowed = _allowed_actions_for_phase(phase)
        prompt_user = USER_PROMPT_TEMPLATE.format(
            target_id=self.target_id,
            ptes_phase=ptes_phase,
            internal_phase=phase,
            run_id=state.get("run_id", "RUN-???"),
            budget=json.dumps(budget),
            previous_actions=previous or "(none)",
            fact_count=len(facts),
            facts_summary=_facts_summary(facts),
            allowed_actions="\n".join(f"  - {a}" for a in allowed),
        )

        # Try LLM
        raw = _call_llm(SYSTEM_PROMPT, prompt_user)
        if raw:
            plan = _parse_plan_json(raw, state, self.target_id)
            if plan:
                # Override target to prevent injection
                plan["target_id"] = self.target_id
                plan["objective_id"] = state.get("objective_id", self.objective_id)
                return plan

        # Fall back to rule-based
        plan = _rule_fallback(state, self.target_id)
        return plan

    def propose_for_ptes_phase(self, state: dict, ptes_phase: str) -> dict:
        """
        Propose action explicitly for a PTES phase.
        Maps PTES phase to internal phase before calling propose().
        """
        phase_internal_map = {
            "pre_engagement":        "RECON",
            "intelligence_gathering": "DISCOVERY",
            "threat_modeling":       "ANALYSIS",
            "vulnerability_research": "ANALYSIS",
            "exploitation":          "TESTING",
            "post_exploitation":     "TESTING",
            "reporting":             "TERMINAL",
        }
        state = dict(state)
        state["phase"] = phase_internal_map.get(ptes_phase, state.get("phase", "RECON"))
        return self.propose(state)
