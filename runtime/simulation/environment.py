"""Canonical Episode Environment for Enterprise Attack Planning (RT-04C).

Provides a single authoritative episode lifecycle loop coordinating:
1. Scenario loading & TrueState initialization
2. Local RNG seeding
3. Bootstrap observation emission (entry seed only)
4. Step loop: Proposal -> ActionConstraintEvaluator -> CentralizedSafetyGate ->
             SimulationExecutor -> TransitionEngine -> ObservationGenerator ->
             StateManager ingestion -> Belief projection
5. Termination & Truncation tracking
6. Separate read-only evaluator scoring view
7. Bit-for-bit deterministic replay
"""
from __future__ import annotations

import copy
import logging
import random
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch
from runtime.simulation.bootstrap import BootstrapObservationGenerator
from runtime.simulation.engine.simulation_executor import (
    SimulationExecutionResult,
    SimulationExecutor,
)
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.evaluator_view import ScenarioEvaluationView
from runtime.simulation.models.scenario import HiddenScenario
from runtime.simulation.models.step_result import EpisodeStepResult, TerminationReason
from runtime.simulation.models.true_state import TrueState

logger = logging.getLogger(__name__)


def create_default_safety_gate(
    scenario: HiddenScenario,
    actions: Sequence[str] | None = None,
    kill_switch: KillSwitch | None = None,
) -> CentralizedSafetyGate:
    """Create a default CentralizedSafetyGate for the evaluation/simulation environment.

    In accordance with RT-01: Safety Scope != Planner-Visible Scope.
    The Safety Gate maintains the authorized lab target envelope,
    while the Planner operates strictly under partial observability.
    """
    targets = frozenset(n.node_id for n in scenario.hidden_nodes)
    if actions is None:
        action_allowlist = frozenset(
            {
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
            }
        )
    else:
        action_allowlist = frozenset(actions)

    return CentralizedSafetyGate(
        base_origin="http://127.0.0.1:18088",
        canonical_target_allowlist=targets,
        canonical_action_allowlist=action_allowlist,
        target_allowlist=targets,
        action_allowlist=action_allowlist,
        kill_switch=kill_switch or KillSwitch(),
        lab_mode=True,
    )


class EpisodeEnvironment:
    """Authoritative episode simulation environment for Red Team AI Planning."""

    def __init__(
        self,
        scenario: HiddenScenario | Path | str,
        run_id: str | None = None,
        random_seed: int = 42,
        max_steps: int = 50,
        max_budget: int = 20,
        safety_gate: CentralizedSafetyGate | None = None,
    ) -> None:
        if isinstance(scenario, (str, Path)):
            self.scenario = ScenarioLoader().load_from_file(scenario)
        else:
            self.scenario = scenario

        self.random_seed = int(random_seed)
        self.max_steps = int(max_steps)
        self.max_budget = int(max_budget)
        self.base_run_id = run_id
        self._user_safety_gate = safety_gate

        self.run_id: str = ""
        self.step_count: int = 0
        self._terminated: bool = False
        self._truncated: bool = False
        self._termination_reason: TerminationReason | None = None
        self._action_history: list[dict[str, Any]] = []

        self.bootstrap_generator = BootstrapObservationGenerator()
        self.loader = ScenarioLoader()

        # Initialize episode state
        self.reset(seed=self.random_seed)

    @property
    def terminated(self) -> bool:
        """True if episode reached a natural or policy terminal state."""
        return self._terminated

    @property
    def truncated(self) -> bool:
        """True if episode reached an external bound (max steps or budget exhaustion)."""
        return self._truncated

    @property
    def termination_reason(self) -> TerminationReason | None:
        """Active termination reason if terminated or truncated."""
        return self._termination_reason

    def reset(
        self,
        seed: int | None = None,
        scenario: HiddenScenario | Path | str | None = None,
        run_id: str | None = None,
        timestamp_utc: str | None = None,
    ) -> tuple[dict[str, Any], BeliefState]:
        """Reset simulation episode to initial state conforming to Fog-of-War.

        Returns:
            Tuple of (bootstrap_observation_envelope, initial_belief_state).
        """
        if seed is not None:
            self.random_seed = int(seed)

        if scenario is not None:
            if isinstance(scenario, (str, Path)):
                self.scenario = self.loader.load_from_file(scenario)
            else:
                self.scenario = scenario

        self.run_id = run_id or self.base_run_id or f"RUN-EP-{self.scenario.scenario_id}-{self.random_seed}"
        self.step_count = 0
        self._terminated = False
        self._truncated = False
        self._termination_reason = None
        self._action_history = []

        # 1. Initialize TrueState with deterministic seed
        initial_true_state = self.scenario.create_initial_true_state(
            run_id=self.run_id,
            seed=self.random_seed,
        )

        # 2. Initialize Planner-safe StateManager with budget (+1 to account for bootstrap)
        self.state_manager = StateManager(
            run_id=self.run_id,
            scenario_id=self.scenario.scenario_id,
            objective_id=self.scenario.objective.objective_id,
            budget={"actions": self.max_budget + 1, "requests": 500, "seconds": 3600.0},
        )

        # 3. Setup Safety Gate
        if self._user_safety_gate is not None:
            self.safety_gate = self._user_safety_gate
        else:
            self.safety_gate = create_default_safety_gate(self.scenario)

        # 4. Setup SimulationExecutor
        self.executor = SimulationExecutor(
            scenario=self.scenario,
            initial_true_state=initial_true_state,
            run_id=self.run_id,
            safety_gate=self.safety_gate,
            state_manager=self.state_manager,
            random_seed=self.random_seed,
        )

        # 5. Emit bootstrap observation exposing entry seed only
        bootstrap_obs = self.bootstrap_generator.generate_bootstrap_observation(
            scenario=self.scenario,
            run_id=self.run_id,
            timestamp_utc=timestamp_utc,
        )

        # Ingest bootstrap observation to populate t=0 initial belief
        self.state_manager.apply_observation(bootstrap_obs)

        initial_belief = self.state_manager.get_belief_state()
        return bootstrap_obs, initial_belief

    def step(
        self,
        proposal: Mapping[str, Any] | str,
        target_id: str | None = None,
        **kwargs: Any,
    ) -> EpisodeStepResult:
        """Execute one simulation step following the mandatory pipeline order.

        Args:
            proposal: Either a dict containing 'action_id' and 'target_id', or action_id str.
            target_id: Target node ID if proposal is passed as string action_id.
            **kwargs: Additional proposal parameters (e.g. from_node_id, credential_id).
        """
        # Normalize proposal mapping
        if isinstance(proposal, str):
            prop_dict: dict[str, Any] = {"action_id": proposal}
            if target_id is not None:
                prop_dict["target_id"] = target_id
            prop_dict.update(kwargs)
        else:
            prop_dict = dict(proposal)
            if target_id is not None and "target_id" not in prop_dict:
                prop_dict["target_id"] = target_id
            prop_dict.update(kwargs)

        action_id = str(prop_dict.get("action_id", ""))
        eff_target_id = prop_dict.get("target_id")
        if eff_target_id is not None:
            eff_target_id = str(eff_target_id)

        current_belief = self.get_belief_state()

        # If already terminal, return no-op result
        if self._terminated or self._truncated:
            return EpisodeStepResult(
                step_index=self.step_count,
                action_id=action_id,
                target_id=eff_target_id,
                success=False,
                terminated=self._terminated,
                truncated=self._truncated,
                termination_reason=self._termination_reason,
                step_cost=0,
                noise_estimate=0.0,
                belief_state=current_belief,
                reasons=("EPISODE_ALREADY_FINISHED",),
            )

        # Check external step limit
        if self.step_count >= self.max_steps:
            self._truncated = True
            self._termination_reason = TerminationReason.MAX_STEPS
            return EpisodeStepResult(
                step_index=self.step_count,
                action_id=action_id,
                target_id=eff_target_id,
                success=False,
                terminated=False,
                truncated=True,
                termination_reason=TerminationReason.MAX_STEPS,
                step_cost=0,
                noise_estimate=0.0,
                belief_state=current_belief,
                reasons=("MAX_STEPS_REACHED",),
            )

        # Check budget availability in StateManager
        remaining_budget = self.state_manager._budget.get("actions", 0)
        if remaining_budget <= 0:
            self._truncated = True
            self._termination_reason = TerminationReason.BUDGET_EXHAUSTED
            return EpisodeStepResult(
                step_index=self.step_count,
                action_id=action_id,
                target_id=eff_target_id,
                success=False,
                terminated=False,
                truncated=True,
                termination_reason=TerminationReason.BUDGET_EXHAUSTED,
                step_cost=0,
                noise_estimate=0.0,
                belief_state=current_belief,
                reasons=("BUDGET_EXHAUSTED",),
            )

        # Check Kill Switch before execution
        if self.safety_gate is not None and self.safety_gate.kill_switch.is_active():
            self._terminated = True
            self._termination_reason = TerminationReason.SAFETY_KILL_SWITCH
            return EpisodeStepResult(
                step_index=self.step_count,
                action_id=action_id,
                target_id=eff_target_id,
                success=False,
                terminated=True,
                truncated=False,
                termination_reason=TerminationReason.SAFETY_KILL_SWITCH,
                step_cost=0,
                noise_estimate=0.0,
                belief_state=current_belief,
                reasons=("KILL_SWITCH_ACTIVE",),
            )

        # -----------------------------------------------------------------
        # Execute action proposal through canonical SimulationExecutor
        # (ConstraintEvaluator -> SafetyGate -> TransitionEngine -> Generator -> Ingestion)
        # -----------------------------------------------------------------
        self.step_count += 1

        exec_res: SimulationExecutionResult = self.executor.execute_proposal(
            proposal=prop_dict,
            belief_state=current_belief,
            timestamp_utc=prop_dict.get("timestamp_utc"),
        )

        updated_belief = self.get_belief_state()
        step_cost = 1
        noise_estimate = 0.0
        if exec_res.transition_result is not None:
            noise_estimate = exec_res.transition_result.noise_delta

        # Record action in history
        self._action_history.append(
            {
                "step": self.step_count,
                "proposal": copy.deepcopy(prop_dict),
                "success": exec_res.success,
                "status": exec_res.status,
            }
        )

        obs_list = [exec_res.canonical_observation] if exec_res.canonical_observation else []

        # -----------------------------------------------------------------
        # Evaluate Episode Termination Conditions
        # -----------------------------------------------------------------
        # 1. Kill Switch triggered during execution
        if self.safety_gate is not None and self.safety_gate.kill_switch.is_active():
            self._terminated = True
            self._termination_reason = TerminationReason.SAFETY_KILL_SWITCH

        # 2. Action STOP (clean exit)
        elif action_id in ("ACTION-STOP-001", "ACTION-END-001"):
            self._terminated = True
            self._termination_reason = TerminationReason.PLANNER_STOP

        # 3. Ground truth objective achieved
        elif self.executor.is_objective_achieved():
            self._terminated = True
            self._termination_reason = TerminationReason.OBJECTIVE_ACHIEVED

        # 4. Defender containment
        elif (
            self.executor.get_true_state().defender_state.detection_state
            == "CONTAINED"
        ):
            self._terminated = True
            self._termination_reason = TerminationReason.CONTAINED

        # 5. External budget exhausted
        elif self.state_manager._budget.get("actions", 0) <= 0:
            self._truncated = True
            self._termination_reason = TerminationReason.BUDGET_EXHAUSTED

        # 6. Max steps reached
        elif self.step_count >= self.max_steps:
            self._truncated = True
            self._termination_reason = TerminationReason.MAX_STEPS

        return EpisodeStepResult(
            step_index=self.step_count,
            action_id=action_id,
            target_id=eff_target_id,
            success=exec_res.success,
            terminated=self._terminated,
            truncated=self._truncated,
            termination_reason=self._termination_reason,
            step_cost=step_cost,
            noise_estimate=noise_estimate,
            belief_state=updated_belief,
            observations=obs_list,
            eligibility=exec_res.constraint_evaluation,
            reasons=exec_res.reasons,
        )

    def get_belief_state(self) -> BeliefState:
        """Return the current Planner-safe BeliefState."""
        return self.state_manager.get_belief_state()

    def get_evaluator_view(self) -> ScenarioEvaluationView:
        """Return read-only scoring view combining TrueState, BeliefState, and History.

        HARD BOUNDARY: Intended exclusively for Evaluation and Benchmark tools.
        """
        belief_dict = self.get_belief_state().to_dict()
        true_st = self.executor.get_true_state()
        return ScenarioEvaluationView(
            true_state=true_st,
            belief_state=belief_dict,
            action_history=tuple(true_st.action_history),
        )
