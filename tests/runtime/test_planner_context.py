"""Tests for Planner-neutral Decision Context and Trace Contracts (RT-05A).

Verifies invariants:
- Test A: PlannerDecisionContext contains NO TrueState.
- Test B: PlannerDecisionContext contains NO HiddenScenario.
- Test C: PlannerDecisionContext contains NO ScenarioEvaluationView.
- Test K: PlannerDecisionContext contains NO reward / numeric gym reward.
- Immutability and serialization validation.
"""
from __future__ import annotations

import copy
import pytest
from dataclasses import FrozenInstanceError

from agent.memory.state.belief_state import BeliefState
from runtime.planners.planner_context import (
    PlannerDecision,
    PlannerDecisionContext,
    PlannerDecisionTrace,
)


def _make_dummy_belief() -> BeliefState:
    return BeliefState.from_facts([
        {
            "fact_id": "FACT-001",
            "fact_type": "SERVICE",
            "subject": "lab-dmz-entry:80",
            "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
            "confidence": 1.0,
        }
    ])


class TestPlannerDecisionContextInvariants:
    """Validate strict ground truth and reward isolation in PlannerDecisionContext."""

    def test_a_planner_decision_context_rejects_true_state(self) -> None:
        """Test A: Context scanning rejects any TrueState or true_state fields."""
        belief = _make_dummy_belief()
        # Direct forbidden key in eligible proposals
        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'true_state'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=0,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=20,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=({"action_id": "ACTION-RECON-001", "true_state": "LEAK"},),
                rejected_proposals=(),
            )

        # Forbidden key in previous_outcome
        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'defender_state'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=1,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=19,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=(),
                rejected_proposals=(),
                previous_outcome={"action_id": "ACTION-RECON-001", "defender_state": "ALERT"},
            )

    def test_b_planner_decision_context_rejects_hidden_scenario(self) -> None:
        """Test B: Context scanning rejects HiddenScenario or hidden_scenario fields."""
        belief = _make_dummy_belief()
        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'hidden_scenario'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=0,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=20,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=(),
                rejected_proposals=(),
                previous_outcome={"action_id": "ACTION-RECON-001", "hidden_scenario": {}},
            )

        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'hidden_nodes'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=0,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=20,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=({"action_id": "ACTION-RECON-001", "hidden_nodes": ["lab-db-crown"]},),
                rejected_proposals=(),
            )

    def test_c_planner_decision_context_rejects_evaluator_view(self) -> None:
        """Test C: Context scanning rejects evaluator views and scoring."""
        belief = _make_dummy_belief()
        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'evaluator_view'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=0,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=20,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=(),
                rejected_proposals=(),
                previous_outcome={"action_id": "ACTION-RECON-001", "evaluator_view": {"score": 100}},
            )

    def test_k_planner_decision_context_rejects_reward(self) -> None:
        """Test K: Context scanning rejects numeric reward or gym_reward."""
        belief = _make_dummy_belief()
        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'reward'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=0,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=20,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=(),
                rejected_proposals=(),
                previous_outcome={"action_id": "ACTION-RECON-001", "reward": 10.0},
            )

        with pytest.raises(ValueError, match="Forbidden ground truth or reward key 'gym_reward'"):
            PlannerDecisionContext(
                run_id="RUN-TEST-001",
                step_index=0,
                max_steps=50,
                current_phase="ENGAGEMENT",
                remaining_budget=20,
                max_budget=20,
                visible_target_ids=frozenset({"lab-dmz-entry"}),
                belief_state=belief,
                candidate_proposals=(),
                eligible_proposals=({"action_id": "ACTION-RECON-001", "gym_reward": 5.0},),
                rejected_proposals=(),
            )

    def test_context_immutability(self) -> None:
        """Context is frozen dataclass and cannot be mutated."""
        belief = _make_dummy_belief()
        ctx = PlannerDecisionContext(
            run_id="RUN-TEST-001",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry"}),
            belief_state=belief,
            candidate_proposals=(),
            eligible_proposals=({"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"},),
            rejected_proposals=(),
        )

        with pytest.raises(FrozenInstanceError):
            ctx.step_index = 1  # type: ignore

        with pytest.raises(FrozenInstanceError):
            ctx.remaining_budget = 19  # type: ignore

    def test_context_to_dict_and_summary(self) -> None:
        """to_dict and summary return clean detached structures."""
        belief = _make_dummy_belief()
        ctx = PlannerDecisionContext(
            run_id="RUN-TEST-001",
            step_index=2,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=18,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry"}),
            belief_state=belief,
            candidate_proposals=(),
            eligible_proposals=({"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"},),
            rejected_proposals=(),
            objective_statement="OBJ-TEST-001",
        )

        d = ctx.to_dict()
        assert d["run_id"] == "RUN-TEST-001"
        assert d["step_index"] == 2
        assert d["visible_target_ids"] == ["lab-dmz-entry"]
        assert d["objective_statement"] == "OBJ-TEST-001"

        s = ctx.summary()
        assert s["run_id"] == "RUN-TEST-001"
        assert s["step"] == 2
        assert s["eligible_count"] == 1
