"""Planner-neutral Decision Context and Trace Contracts (RT-05A).

Defines the typed immutable context surface shared across all planner types
(Rule-Based baseline, LLM planner, Hybrid router) without separate integration paths.

HARD INVARIANTS:
1. Ground Truth Isolation: Context contains ZERO ground truth models
   (No TrueState, No HiddenScenario, No ScenarioEvaluationView, No defender state).
2. Partial Observability: Derived strictly from BeliefState and visible_target_ids.
3. Reward Boundary: Numeric Gym reward is NEVER passed into the Planner Decision Context.
4. Proposal Scope: Only logically eligible proposals and structured rejection reasons.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from agent.memory.state.belief_state import BeliefState

_TARGET_PATTERN = re.compile(r"^lab-[a-z0-9-]+$")
_FORBIDDEN_CONTEXT_KEYS = frozenset({
    "true_state",
    "hidden_scenario",
    "hidden_nodes",
    "hidden_topology",
    "hidden_credentials",
    "detection_model",
    "defender_state",
    "evaluator_view",
    "scenario_evaluation_view",
    "reward",
    "gym_reward",
    "true_cost",
    "accumulated_noise",
    "is_decoy",
    "is_blocked",
    "recovery_opportunity",
    "recovery_opportunity_exists",
    "has_recovery_path",
    "scenario_family",
    "family",
})


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scan_for_forbidden_data(value: Any, path: str = "$") -> None:
    """Recursively scan dict or object to prevent ground truth or reward leakage into context."""
    if isinstance(value, Mapping):
        for k, v in value.items():
            k_lower = str(k).lower()
            if k_lower in _FORBIDDEN_CONTEXT_KEYS:
                raise ValueError(
                    f"Forbidden ground truth or reward key '{k}' found at {path}.{k} in PlannerDecisionContext"
                )
            _scan_for_forbidden_data(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for idx, item in enumerate(value):
            _scan_for_forbidden_data(item, f"{path}[{idx}]")
    elif hasattr(value, "__dict__") and not isinstance(value, BeliefState):
        for k, v in vars(value).items():
            k_lower = str(k).lower()
            if k_lower in _FORBIDDEN_CONTEXT_KEYS:
                raise ValueError(
                    f"Forbidden ground truth attribute '{k}' found in object at {path}.{k}"
                )
            _scan_for_forbidden_data(v, f"{path}.{k}")


@dataclass(frozen=True)
class PlannerDecisionContext:
    """Typed immutable context containing exclusively planner-safe information."""

    run_id: str
    step_index: int
    max_steps: int
    current_phase: str
    remaining_budget: int
    max_budget: int
    visible_target_ids: frozenset[str]
    belief_state: BeliefState
    candidate_proposals: tuple[dict[str, Any], ...]
    eligible_proposals: tuple[dict[str, Any], ...]
    rejected_proposals: tuple[dict[str, Any], ...]
    previous_outcome: dict[str, Any] | None = None
    objective_statement: str | None = None
    action_history: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id or not isinstance(self.run_id, str):
            raise ValueError("PlannerDecisionContext requires a non-empty run_id string")
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        if type(self.max_steps) is not int or self.max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        if type(self.remaining_budget) is not int or self.remaining_budget < 0:
            raise ValueError("remaining_budget must be a non-negative integer")
        if type(self.max_budget) is not int or self.max_budget <= 0:
            raise ValueError("max_budget must be a positive integer")
        if not isinstance(self.visible_target_ids, (set, frozenset)):
            raise ValueError("visible_target_ids must be a frozenset")
        if not isinstance(self.belief_state, BeliefState):
            raise ValueError("belief_state must be a valid BeliefState instance")
        if not isinstance(self.candidate_proposals, tuple):
            object.__setattr__(self, "candidate_proposals", tuple(self.candidate_proposals))
        if not isinstance(self.eligible_proposals, tuple):
            object.__setattr__(self, "eligible_proposals", tuple(self.eligible_proposals))
        if not isinstance(self.rejected_proposals, tuple):
            object.__setattr__(self, "rejected_proposals", tuple(self.rejected_proposals))
        if not isinstance(self.action_history, tuple):
            object.__setattr__(self, "action_history", tuple(self.action_history))

        # Deep scan to enforce Ground Truth and Reward isolation
        if self.previous_outcome is not None:
            _scan_for_forbidden_data(self.previous_outcome, "previous_outcome")
        for idx, p in enumerate(self.eligible_proposals):
            _scan_for_forbidden_data(p, f"eligible_proposals[{idx}]")
        for idx, p in enumerate(self.rejected_proposals):
            _scan_for_forbidden_data(p, f"rejected_proposals[{idx}]")
        for idx, h in enumerate(self.action_history):
            _scan_for_forbidden_data(h, f"action_history[{idx}]")

    def to_dict(self) -> dict[str, Any]:
        """Convert context to detached dictionary representation."""
        return {
            "run_id": self.run_id,
            "step_index": self.step_index,
            "max_steps": self.max_steps,
            "current_phase": self.current_phase,
            "remaining_budget": self.remaining_budget,
            "max_budget": self.max_budget,
            "visible_target_ids": sorted(self.visible_target_ids),
            "belief_state": self.belief_state.to_dict(),
            "eligible_proposals": [copy.deepcopy(p) for p in self.eligible_proposals],
            "rejected_proposals": [copy.deepcopy(p) for p in self.rejected_proposals],
            "previous_outcome": copy.deepcopy(self.previous_outcome) if self.previous_outcome else None,
            "objective_statement": self.objective_statement,
            "action_history": [copy.deepcopy(h) for h in self.action_history],
        }

    def summary(self) -> dict[str, Any]:
        """Compact summary of planner context without deep fact serialization."""
        return {
            "run_id": self.run_id,
            "step": self.step_index,
            "remaining_budget": self.remaining_budget,
            "visible_targets_count": len(self.visible_target_ids),
            "eligible_count": len(self.eligible_proposals),
            "rejected_count": len(self.rejected_proposals),
            "known_hosts_count": len(self.belief_state.known_hosts),
            "active_sessions_count": len(self.belief_state.active_sessions),
        }


@dataclass(frozen=True)
class PlannerDecision:
    """Decision output generated by any planner (Rule, LLM, or Hybrid)."""

    proposal: dict[str, Any] | None
    rationale: str
    reason_code: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rationale:
            raise ValueError("PlannerDecision requires a non-empty rationale")
        if not self.reason_code:
            raise ValueError("PlannerDecision requires a non-empty reason_code")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.proposal is not None and not isinstance(self.proposal, Mapping):
            raise ValueError("proposal must be a dictionary or None")
        if self.proposal is not None and "action_id" not in self.proposal:
            raise ValueError("proposal dictionary must contain 'action_id'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": copy.deepcopy(self.proposal) if self.proposal else None,
            "rationale": self.rationale,
            "reason_code": self.reason_code,
            "confidence": self.confidence,
            "metadata": copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True)
class PlannerDecisionTrace:
    """Planner-safe decision trace record for post-run evaluation and RT-07 metrics."""

    step_index: int
    visible_targets: tuple[str, ...]
    candidate_action_ids: tuple[str, ...]
    eligible_candidates: tuple[dict[str, Any], ...]
    chosen_proposal: dict[str, Any] | None
    decision_rationale: str
    reason_code: str
    observable_prior_outcome: dict[str, Any] | None = None
    planning_latency_ms: float | None = None
    timestamp_utc: str = field(default_factory=_now_utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "visible_targets": list(self.visible_targets),
            "candidate_action_ids": list(self.candidate_action_ids),
            "eligible_candidates": [copy.deepcopy(p) for p in self.eligible_candidates],
            "chosen_proposal": copy.deepcopy(self.chosen_proposal) if self.chosen_proposal else None,
            "decision_rationale": self.decision_rationale,
            "reason_code": self.reason_code,
            "observable_prior_outcome": copy.deepcopy(self.observable_prior_outcome) if self.observable_prior_outcome else None,
            "planning_latency_ms": self.planning_latency_ms,
            "timestamp_utc": self.timestamp_utc,
        }
