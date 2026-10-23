from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RewardCoefficients:
    """Reward coefficients.

    Values remain unresolved until an approved project configuration
    defines them.
    """

    safe_completion: float | None = None
    budget_compliance: float | None = None
    evidence_quality: float | None = None


class RewardModel:
    """Bounded reward model specification for the local RL environment."""

    def __init__(self, coefficients: RewardCoefficients) -> None:
        self.coefficients = coefficients

    def calculate(
        self,
        state: dict[str, Any],
        action: str,
        next_state: dict[str, Any],
        info: dict[str, Any],
    ) -> float:
        """Calculate reward when all required coefficients are resolved."""

        if not isinstance(state, dict):
            raise TypeError("state must be a dictionary")

        if not isinstance(next_state, dict):
            raise TypeError("next_state must be a dictionary")

        if not isinstance(info, dict):
            raise TypeError("info must be a dictionary")

        if not action:
            raise ValueError("action must not be empty")

        coefficients = (
            self.coefficients.safe_completion,
            self.coefficients.budget_compliance,
            self.coefficients.evidence_quality,
        )

        if any(value is None for value in coefficients):
            raise ValueError(
                "Reward coefficients are unresolved (TBD)"
            )

        return 0.0
