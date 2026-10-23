"""Structured result and termination reasons for simulation episodes."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.memory.state.belief_state import BeliefState
from runtime.evaluators.action_evaluator import EvaluationResult


class TerminationReason(str, Enum):
    """Canonical bounded termination reasons for simulation episodes."""

    OBJECTIVE_ACHIEVED = "OBJECTIVE_ACHIEVED"
    PLANNER_STOP = "PLANNER_STOP"
    CONTAINED = "CONTAINED"
    NO_ELIGIBLE_ACTIONS = "NO_ELIGIBLE_ACTIONS"
    SAFETY_KILL_SWITCH = "SAFETY_KILL_SWITCH"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    MAX_STEPS = "MAX_STEPS"
    ERROR = "ERROR"

    @property
    def is_natural_termination(self) -> bool:
        """True if natural goal/task terminal state (terminated=True)."""
        return self in (
            TerminationReason.OBJECTIVE_ACHIEVED,
            TerminationReason.PLANNER_STOP,
            TerminationReason.CONTAINED,
            TerminationReason.NO_ELIGIBLE_ACTIONS,
            TerminationReason.SAFETY_KILL_SWITCH,
            TerminationReason.ERROR,
        )

    @property
    def is_truncation(self) -> bool:
        """True if external boundary limit exceeded (truncated=True)."""
        return self in (
            TerminationReason.BUDGET_EXHAUSTED,
            TerminationReason.MAX_STEPS,
        )


@dataclass(frozen=True)
class EpisodeStepResult:
    """Planner-safe step result returned from an EpisodeEnvironment step."""

    step_index: int
    action_id: str
    target_id: str | None
    success: bool
    terminated: bool
    truncated: bool
    termination_reason: TerminationReason | None
    step_cost: int
    noise_estimate: float
    belief_state: BeliefState
    observations: list[dict[str, Any]] = field(default_factory=list)
    eligibility: EvaluationResult | None = None
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize step result for logging/reporting without leaking ground truth."""
        return {
            "step_index": self.step_index,
            "action_id": self.action_id,
            "target_id": self.target_id,
            "success": self.success,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "termination_reason": (
                self.termination_reason.value if self.termination_reason else None
            ),
            "step_cost": self.step_cost,
            "noise_estimate": self.noise_estimate,
            "reasons": list(self.reasons),
            "observations_count": len(self.observations),
            "eligible": self.eligibility.eligible if self.eligibility else None,
        }
