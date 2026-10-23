"""Canonical Live Episode Environment for Mini Enterprise Cyber Range (RT-06B).

Enforces:
  1. Identical Public Interface to EpisodeEnvironment:
     - reset() -> BeliefState
     - step(proposal) -> EpisodeStepResult
     - get_belief_state() -> BeliefState
     - is_objective_achieved() -> bool
     - terminated, truncated, step_count, max_steps, max_budget
  2. Fog-of-War / Partial Observability:
     - reset() exposes ONLY the perimeter entry target (lab-enterprise-dmz).
     - Internal and restricted targets are discovered dynamically through observed facts.
  3. Seamless Planner Integration:
     - Planners (RuleBasedPlanner, LLM, Hybrid) interact with LiveEpisodeEnvironment
       using the identical PlannerDecisionContext loop with zero code changes.
"""
from __future__ import annotations

import copy
import logging
import uuid
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from runtime.lab.enterprise_range.harness import EnterpriseLiveRangeHarness
from runtime.lab.enterprise_range.topology import get_target_allowlist
from runtime.lab.live_executor_adapter import LiveExecutionResult, LiveExecutorAdapter
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch
from runtime.simulation.models.step_result import EpisodeStepResult, TerminationReason

logger = logging.getLogger(__name__)


def create_live_safety_gate(
    target_allowlist: frozenset[str] | None = None,
    action_allowlist: frozenset[str] | None = None,
    kill_switch: KillSwitch | None = None,
) -> CentralizedSafetyGate:
    """Create a CentralizedSafetyGate configured for the Enterprise Live Range."""
    targets = target_allowlist or get_target_allowlist()
    actions = action_allowlist or frozenset({
        "ACTION-RECON-001",
        "ACTION-SCAN-001",
        "ACTION-WEB-001",
        "ACTION-AUTH-001",
        "ACTION-FLOW-001",
        "ACTION-FLOW-002",
        "ACTION-STOP-001",
        "ACTION-END-001",
        "ACTION-DISCOVERY-001",
        "ACTION-FOOTHOLD-001",
        "ACTION-HOSTRECON-001",
        "ACTION-CREDS-001",
        "ACTION-PIVOT-001",
        "ACTION-PRIVESC-001",
        "ACTION-OBJECTIVE-001",
        "ACTION-PLAN-001",
    })

    return CentralizedSafetyGate(
        base_origin="http://127.0.0.1:18091",
        canonical_target_allowlist=targets,
        canonical_action_allowlist=actions,
        target_allowlist=targets,
        action_allowlist=actions,
        kill_switch=kill_switch or KillSwitch(),
        lab_mode=True,
    )


class LiveEpisodeEnvironment:
    """Authoritative Live Range Episode Environment for Red Team AI Planning Validation."""

    def __init__(
        self,
        harness: EnterpriseLiveRangeHarness,
        entry_target_id: str = "lab-enterprise-dmz",
        objective_id: str = "OBJ-ENTERPRISE-MISSION",
        run_id: str | None = None,
        max_steps: int = 30,
        max_budget: int = 20,
        safety_gate: CentralizedSafetyGate | None = None,
    ) -> None:
        self.harness = harness
        self.entry_target_id = entry_target_id
        self.objective_id = objective_id
        self.run_id = run_id or f"RUN-LIVE-EP-{uuid.uuid4().hex[:8]}"
        self.max_steps = max_steps
        self.max_budget = max_budget
        self.safety_gate = safety_gate or create_live_safety_gate()

        self.scenario = SimpleNamespace(scenario_id="LIVE-ENTERPRISE-RANGE-V1")

        self.state_manager = StateManager(
            run_id=self.run_id,
            scenario_id="LIVE-ENTERPRISE-VALIDATION",
            objective_id=self.objective_id,
            budget={"actions": self.max_budget, "requests": 500, "seconds": 3600.0},
        )

        self.executor = LiveExecutorAdapter(
            harness=self.harness,
            run_id=self.run_id,
            safety_gate=self.safety_gate,
            state_manager=self.state_manager,
        )

        self.step_count = 0
        self.terminated = False
        self.truncated = False
        self.termination_reason: TerminationReason | None = None
        self._initialized = False

        # Seed initial state and reset harness/StateManager
        self.reset()

    def reset(self) -> BeliefState:
        """Reset the live environment and emit initial entry seed observation."""
        self.step_count = 0
        self.terminated = False
        self.truncated = False
        self.termination_reason = None

        # Reset target states in live harness
        self.harness.reset_all()

        # Reset StateManager
        self.state_manager = StateManager(
            run_id=self.run_id,
            scenario_id="LIVE-ENTERPRISE-VALIDATION",
            objective_id=self.objective_id,
            budget={"actions": self.max_budget, "requests": 500, "seconds": 3600.0},
        )

        self.executor.state_manager = self.state_manager
        self.executor.step_count = 0
        self.executor.network_dispatch_count = 0

        # Seed initial partial observability: Only entry target is visible to Planner
        initial_obs = {
            "observation_id": f"OBS-LIVE-INIT-{uuid.uuid4().hex[:8]}",
            "run_id": self.run_id,
            "action_id": "BOOTSTRAP",
            "source_kind": "EXECUTOR",
            "source_target": self.entry_target_id,
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": f"FACT-TARGET-{self.entry_target_id}",
                    "fact_type": "TARGET",
                    "subject": self.entry_target_id,
                    "value": self.entry_target_id,
                    "confidence": 1.0,
                }
            ],
            "confidence": 1.0,
            "sequence_num": 0,
            "evidence_refs": [f"EVID-BOOTSTRAP-{self.run_id}"],
            "timestamp_utc": "2026-10-18T00:00:00Z",
        }
        self.state_manager.apply_observation(initial_obs)
        self._initialized = True
        return self.state_manager.get_belief_state()

    def get_belief_state(self) -> BeliefState:
        return self.state_manager.get_belief_state()

    def is_objective_achieved(self) -> bool:
        belief = self.state_manager.get_belief_state()
        return belief.is_objective_achieved()

    def step(self, proposal: Mapping[str, Any]) -> EpisodeStepResult:
        """Execute a proposal in the live range environment adhering to canonical loop."""
        if self.terminated or self.truncated:
            raise RuntimeError("Cannot step an already terminated episode")

        action_id = str(proposal.get("action_id", ""))
        target_id = proposal.get("target_id")
        self.step_count += 1

        exec_res: LiveExecutionResult = self.executor.execute_proposal(
            proposal=proposal,
            belief_state=self.state_manager.get_belief_state(),
        )

        step_cost = 1

        # Check termination conditions
        observations = [exec_res.canonical_observation] if exec_res.canonical_observation else []
        is_stop = action_id in ("ACTION-STOP-001", "ACTION-END-001")
        obj_achieved = self.is_objective_achieved()

        if is_stop:
            self.terminated = True
            self.termination_reason = (
                TerminationReason.OBJECTIVE_ACHIEVED if obj_achieved else TerminationReason.PLANNER_STOP
            )
        elif obj_achieved:
            self.terminated = True
            self.termination_reason = TerminationReason.OBJECTIVE_ACHIEVED
        elif self.state_manager._budget.get("actions", 0) <= 0:
            self.truncated = True
            self.termination_reason = TerminationReason.BUDGET_EXHAUSTED
        elif self.step_count >= self.max_steps:
            self.truncated = True
            self.termination_reason = TerminationReason.MAX_STEPS

        updated_belief = self.get_belief_state()

        return EpisodeStepResult(
            step_index=self.step_count,
            action_id=action_id,
            target_id=str(target_id) if target_id else "",
            success=exec_res.success,
            terminated=self.terminated,
            truncated=self.truncated,
            termination_reason=self.termination_reason,
            step_cost=step_cost,
            noise_estimate=0.0,
            belief_state=updated_belief,
            observations=observations,
            eligibility=exec_res.constraint_evaluation,
            reasons=exec_res.reasons,
        )

    def close(self) -> None:
        """Close environment resources."""
        pass
