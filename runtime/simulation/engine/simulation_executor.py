"""Canonical Simulation Executor (RT-04B).

Coordinates the end-to-end execution pipeline for Red Team simulation actions
following the strict architectural invariant:

  Planner Proposal
  → ActionConstraintEvaluator (preconditions against Belief State)
  → CentralizedSafetyGate (target/action allowlist, budget, approval)
  → Simulation Executor / Transition Engine (ground truth mutation)
  → Observation Generator (canonical schema observation)
  → State/Knowledge ingestion (StateManager / KnowledgeStateStore)
  → Belief Projection (BeliefState)

HARD INVARIANTS:
1. Zero Bypass:
   No action can reach the TransitionEngine without passing ActionConstraintEvaluator
   and CentralizedSafetyGate checks.
2. Eligible != Successful:
   An action deemed eligible under current Belief State can still fail in ground truth
   due to partial observability (Fog-of-War).
3. Ground Truth Isolation:
   TrueState remains internal to the simulation/evaluation environment and is NEVER
   exposed to the Planner or returned in public planner decision contexts.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
from typing import Any, Mapping, Sequence
import uuid

from actions.catalog.action_registry import get_action_registry, get_legacy_action_id
from agent.memory.state.belief_state import BeliefState
from agent.memory.state.state_manager import StateManager
from runtime.evaluators.action_evaluator import ActionConstraintEvaluator, EvaluationResult
from runtime.safety.discovery_gate import ApprovalToken, CentralizedSafetyGate
from runtime.simulation.engine.observation_generator import ObservationGenerator
from runtime.simulation.engine.transition_engine import TransitionEngine, TransitionResult
from runtime.simulation.models.scenario import HiddenScenario
from runtime.simulation.models.true_state import TrueState



def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SimulationExecutionResult:
    """End-to-end execution result following canonical pipeline ordering."""

    success: bool
    status: str  # "EXECUTED", "REJECTED_BY_CONSTRAINTS", "REJECTED_BY_SAFETY_GATE", "UNAUTHORIZED"
    transition_result: TransitionResult | None = None
    canonical_observation: dict[str, Any] | None = None
    constraint_evaluation: EvaluationResult | None = None
    updated_belief_state: BeliefState | None = None
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.success

    def to_dict(self) -> dict[str, Any]:
        """Serialize result for evaluation and reporting without leaking ground truth TrueState."""
        res: dict[str, Any] = {
            "success": self.success,
            "status": self.status,
            "reasons": list(self.reasons),
        }
        if self.transition_result is not None:
            res["transition"] = self.transition_result.to_dict()
        if self.canonical_observation is not None:
            res["observation"] = copy.deepcopy(self.canonical_observation)
        if self.constraint_evaluation is not None:
            res["constraint_evaluation"] = self.constraint_evaluation.to_dict()
        return res


class SimulationExecutor:
    """Executes Red Team actions against the Enterprise Simulator adhering to canonical safety and policy ordering."""

    def __init__(
        self,
        scenario: HiddenScenario,
        initial_true_state: TrueState | None = None,
        run_id: str | None = None,
        safety_gate: CentralizedSafetyGate | None = None,
        state_manager: StateManager | None = None,
        random_seed: int | None = None,
    ) -> None:
        self.scenario = scenario
        self.run_id = run_id or f"RUN-SIM-{uuid.uuid4().hex[:8]}"
        effective_seed = (
            random_seed
            if random_seed is not None
            else (scenario.random_seed or 42)
        )
        self.true_state = initial_true_state or scenario.create_initial_true_state(
            run_id=self.run_id, seed=effective_seed
        )
        self.safety_gate = safety_gate
        self.state_manager = state_manager
        self.evaluator = ActionConstraintEvaluator()
        self.action_registry = get_action_registry()
        self.transition_engine = TransitionEngine()
        self.observation_generator = ObservationGenerator()
        self.rng = random.Random(effective_seed)
        self.step_count = 0


    def get_true_state(self) -> TrueState:
        """Access current ground-truth state (for Evaluation/Simulator environment only)."""
        return self.true_state

    def get_belief_state(self) -> BeliefState | None:
        """Access current planner-visible belief state (if StateManager configured)."""
        if self.state_manager is not None:
            return self.state_manager.get_belief_state()
        return None

    def is_objective_achieved(self) -> bool:
        """Check if scenario objective is achieved in ground truth."""
        return self.true_state.is_objective_achieved()

    def execute_proposal(
        self,
        proposal: Mapping[str, Any],
        belief_state: BeliefState | None = None,
        approval_token: ApprovalToken | None = None,
        from_node_id: str | None = None,
        credential_id: str | None = None,
        timestamp_utc: str | None = None,
    ) -> SimulationExecutionResult:
        """Execute a proposal through the mandatory canonical pipeline.

        Ordering:
          1. ActionConstraintEvaluator check (Planner-visible BeliefState)
          2. CentralizedSafetyGate check (Policy, Allowlist, Approval)
          3. TransitionEngine execution (Hidden Scenario + TrueState)
          4. ObservationGenerator (Canonical Observation)
          5. StateManager / BeliefState ingestion & projection
        """
        action_id = str(proposal.get("action_id", ""))
        target_id = proposal.get("target_id")
        if target_id is not None:
            target_id = str(target_id)

        eff_from = from_node_id or proposal.get("from_node_id")
        eff_cred = credential_id or proposal.get("credential_id")

        # -------------------------------------------------------------
        # STEP 1: ActionConstraintEvaluator (Belief State Preconditions)
        # -------------------------------------------------------------
        current_belief = belief_state
        if current_belief is None and self.state_manager is not None:
            current_belief = self.state_manager.get_belief_state()

        constraint_eval: EvaluationResult | None = None
        if current_belief is not None:
            action_def = self.action_registry.get_action(action_id) or action_id
            vis_targets = (
                set(current_belief.visible_target_ids)
                if hasattr(current_belief, "visible_target_ids")
                else None
            )
            constraint_eval = self.evaluator.evaluate(
                action=action_def,
                target_id=target_id,
                belief_state=current_belief,
                visible_target_ids=vis_targets,
                proposal_parameters=dict(proposal),
            )

            if not constraint_eval.eligible:
                return SimulationExecutionResult(
                    success=False,
                    status="REJECTED_BY_CONSTRAINTS",
                    constraint_evaluation=constraint_eval,
                    reasons=constraint_eval.reasons or tuple(constraint_eval.reason_codes),
                )


        # -------------------------------------------------------------
        # STEP 2: CentralizedSafetyGate (Safety & Authorization Checks)
        # -------------------------------------------------------------
        if self.safety_gate is not None:
            # Lab mode enforcement
            if not self.safety_gate.lab_mode:
                return SimulationExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=("LAB_MODE_MANDATORY",),
                )

            # Kill switch check
            if self.safety_gate.kill_switch.is_active():
                return SimulationExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=("KILL_SWITCH_ACTIVE",),
                )

            # Target allowlist check (if target specified)
            if target_id is not None and target_id not in self.safety_gate.target_allowlist:
                return SimulationExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=(f"TARGET_NOT_IN_ALLOWLIST: '{target_id}'",),
                )

            # Action allowlist check
            legacy_alias = get_legacy_action_id(action_id)
            if action_id not in self.safety_gate.action_allowlist and (
                not legacy_alias or legacy_alias not in self.safety_gate.action_allowlist
            ):
                return SimulationExecutionResult(
                    success=False,
                    status="REJECTED_BY_SAFETY_GATE",
                    constraint_evaluation=constraint_eval,
                    reasons=(f"ACTION_NOT_IN_ALLOWLIST: '{action_id}'",),
                )

            # Approval token freshness check (if token provided)
            if approval_token is not None:
                valid, reason = approval_token.is_valid()
                if not valid:
                    return SimulationExecutionResult(
                        success=False,
                        status="REJECTED_BY_SAFETY_GATE",
                        constraint_evaluation=constraint_eval,
                        reasons=(f"APPROVAL_TOKEN_INVALID: {reason}",),
                    )

        # -------------------------------------------------------------
        # STEP 3: TransitionEngine (Hidden True-State Mutation)
        # -------------------------------------------------------------
        self.step_count += 1
        now_ts = timestamp_utc or _now_utc()
        transition_result = self.transition_engine.transition(
            true_state=self.true_state,
            scenario=self.scenario,
            action=action_id,
            target=target_id,
            rng=self.rng,
            from_node_id=eff_from,
            credential_id=eff_cred,
            authorized=True,
            step=self.step_count,
            timestamp_utc=now_ts,
        )

        # Update environment TrueState
        self.true_state = transition_result.new_true_state

        # -------------------------------------------------------------
        # STEP 4: ObservationGenerator (Canonical Observation Envelope)
        # -------------------------------------------------------------
        canonical_obs = self.observation_generator.generate_observation(
            transition_result=transition_result,
            run_id=self.run_id,
            action_id=action_id,
            target_id=target_id,
            step=self.step_count,
            timestamp_utc=now_ts,
        )

        # -------------------------------------------------------------
        # STEP 5: State Ingestion & Belief State Projection
        # -------------------------------------------------------------
        updated_belief: BeliefState | None = None
        if self.state_manager is not None:
            self.state_manager.apply_observation(canonical_obs)
            updated_belief = self.state_manager.get_belief_state()
        elif current_belief is not None:
            # Deterministic projection from existing facts + new facts
            existing_facts = list(current_belief.to_dict().get("observed_facts", []))
            all_facts = existing_facts + canonical_obs.get("new_facts", [])
            updated_belief = BeliefState.from_facts(all_facts, observations=[canonical_obs])

        return SimulationExecutionResult(
            success=transition_result.success,
            status="EXECUTED",
            transition_result=transition_result,
            canonical_observation=canonical_obs,
            constraint_evaluation=constraint_eval,
            updated_belief_state=updated_belief,
            reasons=(transition_result.reason,),
        )
