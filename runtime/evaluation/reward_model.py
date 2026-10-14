"""TASK-024 design artifact: score trusted offline metadata-review outcomes.

This pure scorer does not authorize actions or replace TASK-023 rewards. Only the
simulator may supply outcomes; planner claims are not accepted as evidence.
Candidate presence, severity and exploitation are deliberately not scoring inputs.
"""
from dataclasses import dataclass
from types import MappingProxyType


# Each tuple is (progress, penalty, completion). Penalties are signed.
_TERMS = MappingProxyType({
    "INVENTORY_OBSERVED": (0.1, 0.0, 0.0),
    "REPORT_REVIEWED": (0.2, 0.0, 0.0),
    "REPORT_UNAVAILABLE": (0.2, 0.0, 0.0),
    "NO_PROGRESS": (0.0, -0.1, 0.0),
    "DENIED_RATE": (0.0, -0.5, 0.0),
    "DENIED_ORDER": (0.0, -0.5, 0.0),
    "DENIED_LAB_MODE": (0.0, -2.0, 0.0),
    "DENIED_TARGET": (0.0, -2.0, 0.0),
    "DENIED_APPROVAL": (0.0, -2.0, 0.0),
    "DENIED_MALFORMED": (0.0, -2.0, 0.0),
    "REVIEW_COMPLETE": (0.0, 0.0, 1.0),
    "STOPPED_EARLY": (0.0, -0.5, 0.0),
})


@dataclass(frozen=True)
class RewardBreakdown:
    """Reviewable mathematical terms, not an audit/evidence record."""

    outcome: str
    step_cost: float
    progress: float
    penalty: float
    completion: float

    @property
    def total(self) -> float:
        return self.step_cost + self.progress + self.penalty + self.completion


def score_replay_reward(outcome: str) -> RewardBreakdown:
    """Score one trusted, committed replay decision; reject unknown labels.

    TASK-023 emits first-review outcomes once per slot per episode, and
    NO_PROGRESS for repeated reads. Deduplication stays with that environment.
    Never expose this function to planner-authored event labels. Reusing the
    same outcome outside its original transition would double-count progress.

    DENIED_MALFORMED is for evaluator diagnostics only: TASK-023 raises and
    stops on malformed input; this scorer must not turn that exception into a
    successful step. RESET and restore events are not rewarded decisions.
    """
    if type(outcome) is not str or outcome not in _TERMS:
        raise ValueError("trusted closed replay outcome required")
    progress, penalty, completion = _TERMS[outcome]
    return RewardBreakdown(outcome, -0.01, progress, penalty, completion)
