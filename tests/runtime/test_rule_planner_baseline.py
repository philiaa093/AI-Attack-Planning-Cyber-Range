"""Tests for Rule-Based Planner Baseline and Common Episode Runner (RT-05A).

Verifies invariants:
- Test H: Rule decision is bit-for-bit deterministic for identical context.
- Test I: Rule uses only eligible candidates.
- Test J: Rule cannot choose hidden target.
- Test L: S1 complete episode produces deterministic Rule trace.
- Test M: S2 decoy identity not known before observable evidence.
- Test N: S3 blocked path causes observable replanning rather than oracle alternate-path selection.
- Test O: S4 terminates cleanly without false objective achievement.
- Test P: Safety denial still prevents transition (Safety Gate is final authority).
"""
from __future__ import annotations

import copy
from pathlib import Path
import pytest

from agent.memory.state.belief_state import BeliefState
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.planner_context import PlannerDecisionContext
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.models.step_result import TerminationReason
from scripts.validation.validate_scaffold import ROOT

SCENARIOS_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"


class TestRulePlannerBaseline:
    """Validate Rule-based baseline execution and invariants."""

    def test_h_rule_decision_deterministic_for_identical_context(self) -> None:
        """Test H: Given identical PlannerDecisionContext, Rule planner returns identical decision."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-001",
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
        ])

        cand_gen = CandidateGenerator()
        cands = cand_gen.generate(belief_state=belief)

        ctx = PlannerDecisionContext(
            run_id="RUN-DET-001",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry"}),
            belief_state=belief,
            candidate_proposals=cands.all_proposals,
            eligible_proposals=cands.eligible_proposals,
            rejected_proposals=cands.rejected_proposals,
        )

        planner1 = RuleBasedPlanner()
        planner2 = RuleBasedPlanner()

        dec1 = planner1.plan(ctx)
        dec2 = planner1.plan(ctx)
        dec3 = planner2.plan(ctx)

        assert dec1.proposal == dec2.proposal == dec3.proposal
        assert dec1.reason_code == dec2.reason_code == dec3.reason_code
        assert dec1.confidence == dec2.confidence == dec3.confidence
        assert dec1.rationale == dec2.rationale == dec3.rationale

    def test_i_rule_uses_only_eligible_candidates(self) -> None:
        """Test I: Rule planner chooses only from eligible_proposals."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-001",
                "fact_type": "SERVICE",
                "subject": "lab-dmz-entry:80",
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
        ])

        cand_gen = CandidateGenerator()
        cands = cand_gen.generate(belief_state=belief)

        ctx = PlannerDecisionContext(
            run_id="RUN-ELIG-001",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry"}),
            belief_state=belief,
            candidate_proposals=cands.all_proposals,
            eligible_proposals=cands.eligible_proposals,
            rejected_proposals=cands.rejected_proposals,
        )

        planner = RuleBasedPlanner()
        dec = planner.plan(ctx)

        # Chosen proposal must be in eligible_proposals or be None
        assert dec.proposal is not None
        match_found = False
        for ep in ctx.eligible_proposals:
            if ep.get("action_id") == dec.proposal.get("action_id") and ep.get("target_id") == dec.proposal.get("target_id"):
                match_found = True
                break
        assert match_found, f"Chosen proposal {dec.proposal} not in eligible proposals: {ctx.eligible_proposals}"

    def test_j_rule_cannot_choose_hidden_target(self) -> None:
        """Test J: Rule planner validation prevents choosing unobserved or hidden targets."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            }
        ])

        ctx = PlannerDecisionContext(
            run_id="RUN-HIDDEN-001",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry"}),
            belief_state=belief,
            candidate_proposals=(),
            eligible_proposals=({"action_id": "ACTION-STOP-001"},),
            rejected_proposals=(),
        )

        planner = RuleBasedPlanner()
        dec = planner.plan(ctx)
        assert dec.proposal.get("target_id") is None or dec.proposal.get("target_id") in ctx.visible_target_ids

    def test_l_s1_straight_complete_episode_and_trace(self) -> None:
        """Test L: S1 complete episode produces deterministic Rule trace and achieves objective."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s1_straight.json", run_id="RUN-S1-TEST")
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        assert result.terminated is True
        assert result.truncated is False
        assert result.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED
        assert result.final_belief_state.is_objective_achieved() is True
        assert result.total_steps <= 15
        assert len(result.traces) == result.total_steps

        # Trace contains no hidden truth keys
        trace_dict = result.traces[0].to_dict()
        assert "true_state" not in trace_dict
        assert "hidden_scenario" not in trace_dict
        assert "reward" not in trace_dict

    def test_m_s2_decoy_not_known_beforehand_and_trips_containment(self) -> None:
        """Test M: S2 decoy identity is unknown to Rule planner; attacker enters decoy and trips containment."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s2_decoy.json", run_id="RUN-S2-TEST")
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        assert result.terminated is True
        assert result.termination_reason == TerminationReason.CONTAINED
        assert result.final_belief_state.is_objective_achieved() is False

        # Invariant M: Honeypot target was entered as a normal lateral pivot
        assert any(
            t.chosen_proposal.get("target_id") == "lab-decoy-honeypot" and t.reason_code == "LATERAL_PIVOT"
            for t in result.traces if t.chosen_proposal
        ), "Planner did not attempt lateral pivot to decoy honeypot"

    def test_n_s3_blocked_path_causes_replanning_to_jump_box(self) -> None:
        """Test N: S3 blocked direct pivot to DB causes replanning to jump box and achieves objective."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s3_blocked.json", run_id="RUN-S3-TEST")
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        assert result.terminated is True
        assert result.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED
        assert result.final_belief_state.is_objective_achieved() is True

        # Invariant N: Direct pivot to DB failed first, then jump box was chosen
        failed_pivot_seen = False
        jump_box_chosen = False
        for trace in result.traces:
            p = trace.chosen_proposal or {}
            if p.get("action_id") in ("ACTION-FLOW-001", "ACTION-PIVOT-001") and p.get("target_id") == "lab-db-crown" and p.get("from_node_id") == "lab-internal-app":
                failed_pivot_seen = True
            if failed_pivot_seen and p.get("target_id") == "lab-jump-box":
                jump_box_chosen = True
                break

        assert failed_pivot_seen, "Direct pivot to crown DB from internal app was not attempted"
        assert jump_box_chosen, "Planner did not replan to alternate jump box path after direct failure"

    def test_o_s4_clean_baseline_terminates_cleanly_without_false_objective(self) -> None:
        """Test O: S4 clean scenario terminates cleanly without fabricating objective success."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s4_clean.json", run_id="RUN-S4-TEST")
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        assert result.terminated is True
        assert result.termination_reason == TerminationReason.PLANNER_STOP
        assert result.final_belief_state.is_objective_achieved() is False
        assert result.total_steps <= 10

        # Last trace chose STOP due to NO_VALID_CANDIDATE
        last_trace = result.traces[-1]
        assert last_trace.reason_code == "NO_VALID_CANDIDATE"

    def test_p_safety_denial_prevents_transition(self) -> None:
        """Test P: CentralizedSafetyGate denial prevents transition even if candidate was eligible."""
        # Create a restricted safety gate that forbids ACTION-WEB-001
        gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            canonical_target_allowlist=frozenset({"lab-dmz-entry"}),
            canonical_action_allowlist=frozenset({"ACTION-RECON-001", "ACTION-SCAN-001", "ACTION-STOP-001"}),  # No WEB-001
            target_allowlist=frozenset({"lab-dmz-entry"}),
            action_allowlist=frozenset({"ACTION-RECON-001", "ACTION-SCAN-001", "ACTION-STOP-001"}),
            kill_switch=KillSwitch(),
            lab_mode=True,
        )

        env = EpisodeEnvironment(
            SCENARIOS_DIR / "scenario_s1_straight.json",
            run_id="RUN-SAFETY-TEST",
            safety_gate=gate,
        )
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        # Engagement could not gain initial foothold because safety gate denied ACTION-WEB-001
        assert result.final_belief_state.is_objective_achieved() is False
        # Verify safety denial reason in action history
        assert any("ACTION_NOT_IN_ALLOWLIST" in str(t.observable_prior_outcome) for t in result.traces)
