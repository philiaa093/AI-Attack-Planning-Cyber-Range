from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_ACTIONS = (
    "ACTION-RECON-001",
    "ACTION-RECON-002",
    "ACTION-SCAN-001",
    "ACTION-SCAN-002",
    "ACTION-WEB-001",
    "ACTION-WEB-002",
    "ACTION-WEB-003",
    "ACTION-PLAN-001",
    "ACTION-PLAN-002",
    "ACTION-PLAN-003",
    "ACTION-END-001",
    "ACTION-END-002",
    "ACTION-END-003",
)


@dataclass
class RLState:
    scenario_id: str = "SCN-001"
    objective_id: str = "OBJ-001"
    phase: str = "DISCOVERY"
    remaining_actions: int = 10
    remaining_requests: int = 20
    remaining_seconds: float = 60.0
    observed_facts: list[dict[str, Any]] = field(default_factory=list)
    previous_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": "RUN-001",
            "scenario_id": self.scenario_id,
            "objective_id": self.objective_id,
            "phase": self.phase,
            "remaining_budget": {
                "actions": self.remaining_actions,
                "requests": self.remaining_requests,
                "seconds": self.remaining_seconds,
            },
            "observed_facts": list(self.observed_facts),
            "previous_actions": list(self.previous_actions),
        }


class BoundedRLEnvironment:
    """Deterministic, local-only RL environment for the project baseline."""

    def __init__(self) -> None:
        self.state = RLState()

    def reset(self) -> dict[str, Any]:
        self.state = RLState()
        return self.state.to_dict()

    def step(self, action_id: str) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        if action_id not in ALLOWED_ACTIONS:
            raise ValueError(f"Action is not allowlisted: {action_id}")

        if self.state.remaining_actions <= 0:
            return (
                self.state.to_dict(),
                0.0,
                True,
                {"outcome": "DENIED", "reason": "ACTION_BUDGET_EXHAUSTED"},
            )

        self.state.remaining_actions -= 1
        self.state.previous_actions.append(action_id)

        terminated = action_id.startswith("ACTION-END-")

        return (
            self.state.to_dict(),
            0.0,
            terminated,
            {"outcome": "SUCCESS"},
        )
