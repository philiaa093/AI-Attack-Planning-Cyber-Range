"""Common Planner Episode Integration Layer and Episode Runner (RT-05A).

Coordinates the canonical planner-environment execution loop:
  EpisodeEnvironment
  -> PlannerDecisionContext
  -> Candidate Generation
  -> Planner
  -> Proposal
  -> EpisodeEnvironment.step()

HARD INVARIANTS:
1. Neutral Information Surface: All planners receive the identical PlannerDecisionContext.
2. Separation of Concerns: Planner logic has zero knowledge of simulator internals.
   Runner interacts only through public EpisodeEnvironment methods.
3. Ground Truth Isolation: Evaluator-only view is optional and accessed strictly POST-episode.
4. Clean Termination: Episode halts cleanly upon objective achievement, stop action,
   budget exhaustion, defender containment, or step limit.
"""
from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.memory.state.belief_state import BeliefState
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.planner_context import (
    PlannerDecision,
    PlannerDecisionContext,
    PlannerDecisionTrace,
)
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.models.evaluator_view import ScenarioEvaluationView
from runtime.simulation.models.step_result import EpisodeStepResult, TerminationReason

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EpisodeRunResult:
    """Outcome of a complete planner episode run."""

    run_id: str
    scenario_id: str
    terminated: bool
    truncated: bool
    termination_reason: TerminationReason | None
    total_steps: int
    traces: tuple[PlannerDecisionTrace, ...]
    final_belief_state: BeliefState
    evaluator_view: ScenarioEvaluationView | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "termination_reason": self.termination_reason.value if self.termination_reason else None,
            "total_steps": self.total_steps,
            "traces_count": len(self.traces),
            "traces": [t.to_dict() for t in self.traces],
            "objective_achieved_in_belief": self.final_belief_state.is_objective_achieved(),
        }


class PlannerEpisodeRunner:
    """Executes an attack planning episode using a unified PlannerDecisionContext loop."""

    def __init__(
        self,
        env: EpisodeEnvironment,
        planner: Any,
        candidate_generator: CandidateGenerator | None = None,
    ) -> None:
        self.env = env
        self.planner = planner
        self.candidate_generator = candidate_generator or CandidateGenerator()

    def run(self, max_steps: int | None = None) -> EpisodeRunResult:
        """Run complete attack episode until termination or step exhaustion."""
        traces: list[PlannerDecisionTrace] = []
        action_history: list[dict[str, Any]] = []
        last_outcome: dict[str, Any] | None = None
        effective_max_steps = max_steps or self.env.max_steps

        # Episode execution loop
        while not self.env.terminated and not self.env.truncated and self.env.step_count < effective_max_steps:
            step_idx = self.env.step_count
            current_belief = self.env.get_belief_state()

            # 1. Candidate Generation from current belief
            cand_result = self.candidate_generator.generate(
                belief_state=current_belief,
                visible_target_ids=current_belief.visible_target_ids,
            )

            # 2. Build Planner-neutral Context
            remaining_budget = self.env.state_manager._budget.get("actions", 0)
            obj_statement = getattr(self.env.state_manager, "objective_id", None)

            context = PlannerDecisionContext(
                run_id=self.env.run_id,
                step_index=step_idx,
                max_steps=self.env.max_steps,
                current_phase="ENGAGEMENT",
                remaining_budget=remaining_budget,
                max_budget=self.env.max_budget,
                visible_target_ids=frozenset(current_belief.visible_target_ids),
                belief_state=current_belief,
                candidate_proposals=cand_result.all_proposals,
                eligible_proposals=cand_result.eligible_proposals,
                rejected_proposals=cand_result.rejected_proposals,
                previous_outcome=copy.deepcopy(last_outcome) if last_outcome else None,
                objective_statement=obj_statement,
                action_history=tuple(action_history),
            )

            # 3. Ask Planner for Decision
            t0 = time.perf_counter()
            decision: PlannerDecision = self.planner.plan(context)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            # 4. Record Decision Trace
            trace = PlannerDecisionTrace(
                step_index=step_idx,
                visible_targets=tuple(sorted(context.visible_target_ids)),
                candidate_action_ids=cand_result.candidate_action_ids,
                eligible_candidates=cand_result.eligible_proposals,
                chosen_proposal=copy.deepcopy(decision.proposal) if decision.proposal else None,
                decision_rationale=decision.rationale,
                reason_code=decision.reason_code,
                observable_prior_outcome=copy.deepcopy(last_outcome) if last_outcome else None,
                planning_latency_ms=latency_ms,
            )
            traces.append(trace)

            # 5. Handle Planner termination decision
            if decision.proposal is None:
                break

            act_id = decision.proposal.get("action_id", "")
            is_stop_action = act_id in ("ACTION-STOP-001", "ACTION-END-001")

            # 6. Execute proposal in EpisodeEnvironment
            step_result: EpisodeStepResult = self.env.step(decision.proposal)

            last_outcome = {
                "step": step_idx,
                "success": step_result.success,
                "action_id": step_result.action_id,
                "target_id": step_result.target_id,
                "from_node_id": decision.proposal.get("from_node_id"),
                "credential_id": decision.proposal.get("credential_id"),
                "step_cost": step_result.step_cost,
                "reasons": list(step_result.reasons),
                "observations_count": len(step_result.observations),
            }
            action_history.append(copy.deepcopy(last_outcome))

            if is_stop_action:
                break

        # Optional post-episode evaluation view for reporting
        eval_view: ScenarioEvaluationView | None = None
        try:
            eval_view = self.env.get_evaluator_view()
        except Exception:
            eval_view = None

        return EpisodeRunResult(
            run_id=self.env.run_id,
            scenario_id=self.env.scenario.scenario_id,
            terminated=self.env.terminated,
            truncated=self.env.truncated,
            termination_reason=self.env.termination_reason,
            total_steps=self.env.step_count,
            traces=tuple(traces),
            final_belief_state=self.env.get_belief_state(),
            evaluator_view=eval_view,
        )
