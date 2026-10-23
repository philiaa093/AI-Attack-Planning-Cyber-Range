"""Tests for Hybrid Belief-State Planner Baseline (RT-05C).

Verifies invariants A through Y:
  Test A: Hybrid receives same candidate set as Rule/LLM.
  Test B: Hybrid context contains no hidden data.
  Test C: Valid semantic ranking parsed correctly.
  Test D: Unknown semantic candidate fails semantic component validation.
  Test E: Duplicate ranking keys rejected.
  Test F: Candidate signature stable across ordinal candidate-key changes.
  Test G: Symbolic scores deterministic.
  Test H: Noise penalty works from public noise_cost only.
  Test I: Step cost penalty works.
  Test J: Repeat penalty works.
  Test K: Observable failure penalty works.
  Test L: Hidden failure cause does not influence score.
  Test M: Fusion formula exactly matches documented calculation.
  Test N: Fixed tie-break deterministic.
  Test O: Hybrid can select candidate different from LLM top-1 due to symbolic costs.
  Test P: Invalid LLM component uses explicit SYMBOLIC_ONLY fallback.
  Test Q: Fallback never calls RuleBasedPlanner.
  Test R: STOP can win when no meaningful progress remains.
  Test S: Same PlannerEpisodeRunner supports Hybrid.
  Test T: S1 scripted Hybrid reaches objective.
  Test U: S2 prompt contains no decoy oracle.
  Test V: S3 failure changes only observable-history-derived score.
  Test W: S4 clean terminates cleanly without false objective.
  Test X: Metrics and invalid ranking counters tracked accurately.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from actions.catalog.action_registry import get_canonical_action_id
from agent.memory.state.belief_state import BeliefState
from runtime.evaluation.usage_costs import TokenUsage
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.planners.candidate_generator import (
    CandidateGenerator,
    compute_candidate_key,
    compute_candidate_signature,
)
from runtime.planners.hybrid_planner import (
    FakeHybridRankingProvider,
    HYBRID_PLANNER_PROMPT_V1,
    HYBRID_PLANNER_SYSTEM_PROMPT,
    HybridPlanner,
    parse_hybrid_ranking_json,
)
from runtime.planners.llm_planner import LLMPlanner, serialize_llm_context
from runtime.planners.planner_context import PlannerDecisionContext
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.planners.symbolic_scorer import (
    CandidateScoreBreakdown,
    HybridScoringConfig,
    SymbolicScorer,
)
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.models.step_result import TerminationReason
from scripts.validation.validate_scaffold import ROOT

SCENARIOS_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"


@pytest.fixture
def sample_belief() -> BeliefState:
    facts = [
        {
            "fact_id": "FACT-TGT-001",
            "fact_type": "TARGET",
            "subject": "lab-dmz-entry",
            "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
            "confidence": 1.0,
        },
        {
            "fact_id": "FACT-SVC-001",
            "fact_type": "SERVICE",
            "subject": "lab-dmz-entry:80",
            "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP", "target_id": "lab-dmz-entry"},
            "confidence": 0.95,
        },
        {
            "fact_id": "FACT-FIND-001",
            "fact_type": "FINDING",
            "subject": "lab-dmz-entry",
            "value": {"finding_id": "VULN-SQLI-001", "severity": "HIGH", "target_id": "lab-dmz-entry"},
            "confidence": 0.90,
        },
    ]
    return BeliefState.from_facts(facts)


@pytest.fixture
def sample_context(sample_belief: BeliefState) -> PlannerDecisionContext:
    gen = CandidateGenerator()
    cands = gen.generate(
        belief_state=sample_belief,
        visible_target_ids=frozenset({"lab-dmz-entry"}),
        current_phase="INITIAL_ACCESS",
    )
    return PlannerDecisionContext(
        run_id="RUN-HYBRID-TEST-001",
        step_index=2,
        max_steps=50,
        current_phase="INITIAL_ACCESS",
        remaining_budget=18,
        max_budget=20,
        visible_target_ids=frozenset({"lab-dmz-entry"}),
        belief_state=sample_belief,
        candidate_proposals=cands.all_proposals,
        eligible_proposals=cands.eligible_proposals,
        rejected_proposals=cands.rejected_proposals,
        previous_outcome={
            "step": 1,
            "action_id": "ACTION-SCAN-001",
            "target_id": "lab-dmz-entry",
            "success": True,
            "step_cost": 1,
            "reasons": ["SERVICE_DISCOVERED"],
        },
        objective_statement="Attain mission objectives on target network.",
    )


class TestHybridPlannerBaseline:
    """Comprehensive test suite for Hybrid Belief-State Planner Baseline."""

    def test_a_hybrid_receives_same_candidate_set_as_rule_and_llm(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test A: Given identical PlannerDecisionContext, Rule, LLM, and Hybrid receive identical candidates."""
        rule = RuleBasedPlanner()
        llm = LLMPlanner(provider=FakeHybridRankingProvider())
        hybrid = HybridPlanner(provider=FakeHybridRankingProvider())

        # All planners consume the identical context.eligible_proposals
        rule_cands = [p.get("action_id") for p in sample_context.eligible_proposals]
        _, _, _, llm_map = serialize_llm_context(sample_context)
        llm_cands = [p.get("action_id") for p in llm_map.values()]

        # Hybrid scores over context.eligible_proposals
        scorer = SymbolicScorer()
        hybrid_breakdowns = scorer.score_all(sample_context.eligible_proposals, {}, sample_context)
        hybrid_cands = [b.action_id for b in hybrid_breakdowns]

        assert sorted(rule_cands) == sorted(llm_cands) == sorted(hybrid_cands)

    def test_b_hybrid_context_contains_no_hidden_data(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test B: Hybrid prompt and context contains zero Ground Truth, TrueState, or hidden simulation data."""
        prompt, p_hash, c_hash, cand_map = serialize_llm_context(
            sample_context, system_prompt=HYBRID_PLANNER_SYSTEM_PROMPT
        )

        forbidden_patterns = [
            "true_state", "hidden_scenario", "evaluator_view", "scenario_evaluation_view",
            "detection_model", "noise_threshold", "containment_threshold",
            "alert_threshold", "initial_detection_state", "success_probability",
            "gym_reward", "reward", "scenario_s1", "scenario_s2", "scenario_s3",
            "scenario_s4", "is_decoy", "honeypot", "treasury_dump",
        ]
        for pat in forbidden_patterns:
            assert pat not in prompt.lower(), f"Forbidden pattern {pat!r} found in Hybrid prompt"

    def test_c_valid_semantic_ranking_parsed_correctly(self) -> None:
        """Test C: parse_hybrid_ranking_json correctly parses JSON object and fences."""
        raw_json = json.dumps({
            "ranked_candidate_keys": ["CAND-001", "CAND-002"],
            "reason_code": "STRATEGIC_PRIORITY",
            "brief_justification": "Foothold prioritized",
        })
        parsed = parse_hybrid_ranking_json(raw_json)
        assert parsed is not None
        assert parsed["ranked_candidate_keys"] == ["CAND-001", "CAND-002"]

        # Fenced markdown JSON
        fenced = f"```json\n{raw_json}\n```"
        parsed_fenced = parse_hybrid_ranking_json(fenced)
        assert parsed_fenced is not None
        assert parsed_fenced["ranked_candidate_keys"] == ["CAND-001", "CAND-002"]

    def test_d_unknown_semantic_candidate_fails_semantic_component_validation(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test D: Model returning unknown candidate key fails semantic validation and degrades to SYMBOLIC_ONLY."""
        provider = FakeHybridRankingProvider(script=[
            {"ranked_candidate_keys": ["CAND-999"], "reason_code": "HALLUCINATED"}
        ])
        planner = HybridPlanner(provider=provider)
        dec = planner.plan(sample_context)

        assert dec.metadata["semantic_component_valid"] is False
        assert dec.metadata["semantic_fallback_mode"] == "SYMBOLIC_ONLY"
        assert dec.metadata["fallback_used"] is True
        assert planner.metrics["unknown_candidate_keys"] == 1

    def test_e_duplicate_ranking_keys_rejected(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test E: Model returning duplicate candidate keys fails validation and degrades to SYMBOLIC_ONLY."""
        first_key = sample_context.eligible_proposals[0]["candidate_key"]
        provider = FakeHybridRankingProvider(script=[
            {"ranked_candidate_keys": [first_key, first_key], "reason_code": "DUPLICATES"}
        ])
        planner = HybridPlanner(provider=provider)
        dec = planner.plan(sample_context)

        assert dec.metadata["semantic_component_valid"] is False
        assert dec.metadata["semantic_fallback_mode"] == "SYMBOLIC_ONLY"
        assert planner.metrics["duplicate_candidate_keys"] == 1

    def test_f_candidate_signature_stable_across_ordinal_candidate_key_changes(self) -> None:
        """Test F: candidate_signature derives strictly from action parameters and remains stable."""
        prop_a = {
            "action_id": "ACTION-FOOTHOLD-001",
            "target_id": "lab-dmz-entry",
            "from_node_id": None,
            "credential_id": None,
            "candidate_key": "CAND-001",
        }
        prop_b = {
            "action_id": "ACTION-FOOTHOLD-001",
            "target_id": "lab-dmz-entry",
            "from_node_id": None,
            "credential_id": None,
            "candidate_key": "CAND-008",  # Different ordinal position
        }

        sig_a = compute_candidate_signature(prop_a)
        sig_b = compute_candidate_signature(prop_b)
        assert sig_a == sig_b
        assert len(sig_a) == 64

    def test_g_symbolic_scores_deterministic(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test G: Given identical context and ranking map, SymbolicScorer produces bit-for-bit identical scores."""
        scorer = SymbolicScorer()
        ranking_map = {"CAND-001": (0, 1.0), "CAND-002": (1, 0.5)}

        run1 = scorer.score_all(sample_context.eligible_proposals, ranking_map, sample_context)
        run2 = scorer.score_all(sample_context.eligible_proposals, ranking_map, sample_context)

        for b1, b2 in zip(run1, run2):
            assert b1.candidate_signature == b2.candidate_signature
            assert b1.fused_score == b2.fused_score
            assert b1.progress_score == b2.progress_score
            assert b1.noise_cost_norm == b2.noise_cost_norm
            assert b1.step_cost_norm == b2.step_cost_norm

    def test_h_noise_penalty_works_from_public_noise_cost_only(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test H: Noise cost penalty derives strictly from public proposal noise_cost."""
        prop_quiet = {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "noise_cost": 0.5, "step_cost": 1}
        prop_noisy = {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "noise_cost": 5.0, "step_cost": 1}

        scorer = SymbolicScorer()
        b_quiet = scorer.score_candidate(prop_quiet, 0, 1.0, sample_context)
        b_noisy = scorer.score_candidate(prop_noisy, 0, 1.0, sample_context)

        assert b_noisy.noise_cost_norm > b_quiet.noise_cost_norm
        assert b_noisy.fused_score < b_quiet.fused_score

    def test_i_step_cost_penalty_works(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test I: Step cost penalty reflects public step_cost."""
        prop_cheap = {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "noise_cost": 1.0, "step_cost": 1}
        prop_costly = {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "noise_cost": 1.0, "step_cost": 4}

        scorer = SymbolicScorer()
        b_cheap = scorer.score_candidate(prop_cheap, 0, 1.0, sample_context)
        b_costly = scorer.score_candidate(prop_costly, 0, 1.0, sample_context)

        assert b_costly.step_cost_norm > b_cheap.step_cost_norm
        assert b_costly.fused_score < b_cheap.fused_score

    def test_j_repeat_penalty_works(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test J: Action history repetition increases repeat_penalty and decreases fused score."""
        ctx_with_history = PlannerDecisionContext(
            run_id=sample_context.run_id,
            step_index=3,
            max_steps=sample_context.max_steps,
            current_phase=sample_context.current_phase,
            remaining_budget=sample_context.remaining_budget,
            max_budget=sample_context.max_budget,
            visible_target_ids=sample_context.visible_target_ids,
            belief_state=sample_context.belief_state,
            candidate_proposals=sample_context.candidate_proposals,
            eligible_proposals=sample_context.eligible_proposals,
            rejected_proposals=sample_context.rejected_proposals,
            action_history=(
                {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False},
                {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False},
            ),
        )

        prop = {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "step_cost": 1, "noise_cost": 1}
        scorer = SymbolicScorer()
        b_clean = scorer.score_candidate(prop, 0, 1.0, sample_context)
        b_repeated = scorer.score_candidate(prop, 0, 1.0, ctx_with_history)

        assert b_repeated.repeat_count == 2
        assert b_repeated.repeat_penalty > b_clean.repeat_penalty
        assert b_repeated.fused_score < b_clean.fused_score

    def test_k_observable_failure_penalty_works(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test K: Prior step observable failure penalizes candidate."""
        ctx_with_failure = PlannerDecisionContext(
            run_id=sample_context.run_id,
            step_index=3,
            max_steps=sample_context.max_steps,
            current_phase=sample_context.current_phase,
            remaining_budget=sample_context.remaining_budget,
            max_budget=sample_context.max_budget,
            visible_target_ids=sample_context.visible_target_ids,
            belief_state=sample_context.belief_state,
            candidate_proposals=sample_context.candidate_proposals,
            eligible_proposals=sample_context.eligible_proposals,
            rejected_proposals=sample_context.rejected_proposals,
            previous_outcome={
                "step": 2,
                "action_id": "ACTION-FOOTHOLD-001",
                "target_id": "lab-dmz-entry",
                "success": False,
                "reasons": ["EXPLOIT_FAILED"],
            },
        )

        prop = {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "step_cost": 1, "noise_cost": 1}
        scorer = SymbolicScorer()
        b_clean = scorer.score_candidate(prop, 0, 1.0, sample_context)
        b_failed = scorer.score_candidate(prop, 0, 1.0, ctx_with_failure)

        assert b_failed.failure_count == 1
        assert b_failed.failure_penalty > 0.0
        assert b_failed.fused_score < b_clean.fused_score

    def test_l_hidden_failure_cause_does_not_influence_score(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test L: Scorer ignores hidden simulator reasons, using only observed success=False flag."""
        ctx_a = PlannerDecisionContext(
            run_id="RUN-A",
            step_index=1,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=sample_context.visible_target_ids,
            belief_state=sample_context.belief_state,
            candidate_proposals=sample_context.candidate_proposals,
            eligible_proposals=sample_context.eligible_proposals,
            rejected_proposals=sample_context.rejected_proposals,
            previous_outcome={"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False, "reasons": ["FIREWALL_FILTERED"]},
        )
        ctx_b = PlannerDecisionContext(
            run_id="RUN-B",
            step_index=1,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=sample_context.visible_target_ids,
            belief_state=sample_context.belief_state,
            candidate_proposals=sample_context.candidate_proposals,
            eligible_proposals=sample_context.eligible_proposals,
            rejected_proposals=sample_context.rejected_proposals,
            previous_outcome={"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False, "reasons": ["AUTH_REJECTED"]},
        )

        prop = {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "step_cost": 1, "noise_cost": 1}
        scorer = SymbolicScorer()
        b_a = scorer.score_candidate(prop, 0, 1.0, ctx_a)
        b_b = scorer.score_candidate(prop, 0, 1.0, ctx_b)

        assert b_a.failure_penalty == b_b.failure_penalty
        assert b_a.fused_score == b_b.fused_score

    def test_m_fusion_formula_exactly_matches_documented_calculation(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test M: Fused score precisely equals w_sem*S_sem + w_prog*S_prog - w_noise*C_noise - w_step*C_step - w_rep*P_rep - w_fail*P_fail."""
        cfg = HybridScoringConfig(
            w_semantic=0.40,
            w_progress=0.30,
            w_noise=0.10,
            w_step=0.05,
            w_repeat=0.15,
            w_failure=0.20,
        )
        scorer = SymbolicScorer(cfg)
        prop = {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "step_cost": 2.0, "noise_cost": 3.0}
        b = scorer.score_candidate(prop, 0, 1.0, sample_context)

        expected_fused = (
            cfg.w_semantic * b.semantic_score
            + cfg.w_progress * b.progress_score
            - cfg.w_noise * b.noise_cost_norm
            - cfg.w_step * b.step_cost_norm
            - cfg.w_repeat * b.repeat_penalty
            - cfg.w_failure * b.failure_penalty
        )
        assert abs(b.fused_score - expected_fused) < 1e-6

    def test_n_fixed_tie_break_deterministic(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test N: Equal fused scores resolve deterministically by documented tie-breaking keys."""
        prop_a = {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "step_cost": 1, "noise_cost": 1}
        prop_b = {"action_id": "ACTION-DISCOVERY-001", "target_id": "lab-dmz-entry", "step_cost": 1, "noise_cost": 1}

        # Semantic-only with equal 0.0 scores
        cfg = HybridScoringConfig.semantic_only()
        scorer = SymbolicScorer(cfg)
        results = scorer.score_all([prop_a, prop_b], {}, sample_context)

        # In tie-break: ACTION-DISCOVERY-001 comes before ACTION-SCAN-001 alphabetically
        assert results[0].canonical_action_id == "ACTION-DISCOVERY-001"
        assert results[1].canonical_action_id == "ACTION-SCAN-001"

    def test_o_hybrid_can_select_candidate_different_from_llm_top1_due_to_symbolic_costs(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test O: Symbolic costs (high noise + prior failure) cause Hybrid to overturn LLM top choice."""
        # Candidate 1: Foothold (noisy, repeatedly failed)
        # Candidate 2: Discovery on new target (quiet, unfailed, high progress)
        proposals = [
            {"candidate_key": "CAND-001", "action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "noise_cost": 9.0, "step_cost": 2.0},
            {"candidate_key": "CAND-002", "action_id": "ACTION-DISCOVERY-001", "target_id": "lab-internal-app", "noise_cost": 0.5, "step_cost": 1.0},
        ]
        history = [
            {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False},
            {"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False},
        ]

        ctx = PlannerDecisionContext(
            run_id="RUN-O",
            step_index=3,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry", "lab-internal-app"}),
            belief_state=sample_context.belief_state,
            candidate_proposals=tuple(proposals),
            eligible_proposals=tuple(proposals),
            rejected_proposals=(),
            previous_outcome={"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry", "success": False},
            action_history=tuple(history),
        )

        # Provider ranks CAND-001 at top #1, CAND-002 at #2
        provider = FakeHybridRankingProvider(script=[
            {"ranked_candidate_keys": ["CAND-001", "CAND-002"], "reason_code": "LLM_FAVORS_FOOTHOLD"}
        ])
        planner = HybridPlanner(provider=provider)
        dec = planner.plan(ctx)

        # Assert: Even though LLM ranked CAND-001 #1, CAND-002 won due to high noise and failure penalties
        assert dec.metadata["candidate_key"] == "CAND-002"
        assert dec.metadata["semantic_rank"] == 1  # 2nd choice of LLM
        assert dec.proposal["action_id"] == "ACTION-DISCOVERY-001"

    def test_p_invalid_llm_component_uses_explicit_symbolic_only_fallback(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test P: Malformed LLM output explicitly activates SYMBOLIC_ONLY fallback."""
        provider = FakeHybridRankingProvider(script=["NOT_JSON_AT_ALL"])
        planner = HybridPlanner(provider=provider)
        dec = planner.plan(sample_context)

        assert dec.metadata["valid"] is True
        assert dec.metadata["semantic_component_valid"] is False
        assert dec.metadata["semantic_fallback_mode"] == "SYMBOLIC_ONLY"
        assert dec.metadata["fallback_used"] is True
        assert dec.proposal is not None
        assert planner.metrics["symbolic_fallback_count"] == 1

    def test_q_fallback_never_calls_rule_based_planner(
        self, sample_context: PlannerDecisionContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test Q: Hybrid fallback uses internal symbolic scoring and NEVER instantiates or calls RuleBasedPlanner."""
        def forbidden_rule_init(*args, **kwargs):
            raise AssertionError("RuleBasedPlanner must NEVER be called by HybridPlanner!")

        monkeypatch.setattr(RuleBasedPlanner, "__init__", forbidden_rule_init)

        provider = FakeHybridRankingProvider(script=["MALFORMED"])
        planner = HybridPlanner(provider=provider)
        dec = planner.plan(sample_context)

        assert dec.metadata["valid"] is True
        assert dec.metadata["semantic_fallback_mode"] == "SYMBOLIC_ONLY"

    def test_r_stop_can_win_when_no_meaningful_progress_remains(self) -> None:
        """Test R: Heavily penalized repetitive progress actions drop below STOP action score."""
        proposals = [
            {"candidate_key": "CAND-001", "action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "noise_cost": 2.0, "step_cost": 1.0},
            {"candidate_key": "CAND-002", "action_id": "ACTION-STOP-001", "target_id": None, "noise_cost": 0.0, "step_cost": 0.0},
        ]
        history = [
            {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "success": False},
            {"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "success": False},
        ]
        ctx = PlannerDecisionContext(
            run_id="RUN-R",
            step_index=5,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=10,
            max_budget=20,
            visible_target_ids=frozenset({"lab-dmz-entry"}),
            belief_state=BeliefState.from_facts([]),
            candidate_proposals=tuple(proposals),
            eligible_proposals=tuple(proposals),
            rejected_proposals=(),
            previous_outcome={"action_id": "ACTION-SCAN-001", "target_id": "lab-dmz-entry", "success": False},
            action_history=tuple(history),
        )

        scorer = SymbolicScorer()
        results = scorer.score_all(proposals, {}, ctx)
        winner = results[0]

        assert winner.canonical_action_id == "ACTION-STOP-001"
        assert winner.candidate_key == "CAND-002"

    def test_s_same_planner_episode_runner_supports_hybrid(self) -> None:
        """Test S: PlannerEpisodeRunner seamlessly executes HybridPlanner over EpisodeEnvironment."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s4_clean.json", run_id="RUN-S4-HYBRID")
        planner = HybridPlanner(provider=FakeHybridRankingProvider())
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run(max_steps=5)
        assert result.total_steps > 0
        assert len(result.traces) > 0

    def test_t_s1_straight_scripted_hybrid_completes_objective(self) -> None:
        """Test T: S1 straight path completes objective with scripted Hybrid semantic rankings."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s1_straight.json", run_id="RUN-S1-HYBRID")

        script = [
            ["ACTION-DISCOVERY-001"],
            ["ACTION-SCAN-001"],
            ["ACTION-FOOTHOLD-001"],
            ["ACTION-HOSTRECON-001"],
            ["ACTION-CREDS-001"],
            [("ACTION-PIVOT-001", "lab-internal-app")],
            ["ACTION-HOSTRECON-001"],
            ["ACTION-CREDS-001"],
            [("ACTION-PIVOT-001", "lab-db-crown")],
            ["ACTION-OBJECTIVE-001"],
            ["ACTION-STOP-001"],
        ]
        provider = FakeHybridRankingProvider(script=script)
        planner = HybridPlanner(provider=provider)
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        assert result.terminated is True
        assert result.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED
        assert result.final_belief_state.is_objective_achieved() is True

    def test_u_s2_prompt_contains_no_decoy_oracle_and_trips_containment(self) -> None:
        """Test U: S2 decoy contains no honeypot oracle; Hybrid enters decoy based on observed services and trips containment."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s2_decoy.json", run_id="RUN-S2-HYBRID")

        script = [
            ["ACTION-DISCOVERY-001"],
            ["ACTION-SCAN-001"],
            ["ACTION-FOOTHOLD-001"],
            ["ACTION-HOSTRECON-001"],
            ["ACTION-CREDS-001"],
            [("ACTION-PIVOT-001", "lab-internal-app")],
            ["ACTION-HOSTRECON-001"],
            ["ACTION-CREDS-001"],
            [("ACTION-PIVOT-001", "lab-decoy-honeypot")],
            ["ACTION-STOP-001"],
        ]
        provider = FakeHybridRankingProvider(script=script)
        planner = HybridPlanner(provider=provider)
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        # Invariant U: Prompt contained no decoy oracle labels
        for prompt in provider.call_history:
            assert "is_decoy" not in prompt.lower()
            assert "decoy_label" not in prompt.lower()
            assert "honeypot_type" not in prompt.lower()

        assert result.terminated is True
        assert result.termination_reason == TerminationReason.CONTAINED

    def test_v_s3_replan_context_uses_only_observable_failure(self) -> None:
        """Test V: S3 direct pivot failure increases failure penalty, causing Hybrid to pivot to jump-box."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s3_blocked.json", run_id="RUN-S3-HYBRID")

        script = [
            ("ACTION-DISCOVERY-001", "lab-dmz-entry"),
            ("ACTION-SCAN-001", "lab-dmz-entry"),
            ("ACTION-FOOTHOLD-001", "lab-dmz-entry"),
            ("ACTION-DISCOVERY-001", "lab-internal-app"),
            ("ACTION-CREDS-001", "lab-dmz-entry"),
            ("ACTION-PIVOT-001", "lab-internal-app"),
            ("ACTION-DISCOVERY-001", "lab-db-crown"),
            ("ACTION-DISCOVERY-001", "lab-jump-box"),
            ("ACTION-HOSTRECON-001", "lab-internal-app"),
            ("ACTION-CREDS-001", "lab-internal-app"),
            ("ACTION-PIVOT-001", "lab-db-crown", "lab-internal-app"),  # Direct pivot fails
            ("ACTION-PIVOT-001", "lab-jump-box", "lab-internal-app"),  # Replan to jump box
            ("ACTION-HOSTRECON-001", "lab-jump-box"),
            ("ACTION-CREDS-001", "lab-jump-box"),
            ("ACTION-PRIVESC-001", "lab-jump-box"),
            ("ACTION-OBJECTIVE-001", "lab-db-crown", "lab-jump-box"),
        ]
        provider = FakeHybridRankingProvider(script=script)
        planner = HybridPlanner(provider=provider)
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        failed_pivot_seen = False
        jump_box_chosen = False

        for t in result.traces:
            p = t.chosen_proposal or {}
            if p.get("action_id") in ("ACTION-PIVOT-001", "ACTION-FLOW-001") and p.get("target_id") == "lab-db-crown" and not jump_box_chosen:
                failed_pivot_seen = True
            if failed_pivot_seen and p.get("target_id") == "lab-jump-box":
                jump_box_chosen = True

        assert failed_pivot_seen is True
        assert jump_box_chosen is True
        assert result.terminated is True
        assert result.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED

    def test_w_s4_clean_terminates_cleanly_without_false_objective(self) -> None:
        """Test W: S4 clean scenario terminates cleanly on STOP without fabricated objective success."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s4_clean.json", run_id="RUN-S4-HYBRID")

        script = [
            ["ACTION-DISCOVERY-001"],
            ["ACTION-SCAN-001"],
            ["ACTION-STOP-001"],
        ]
        provider = FakeHybridRankingProvider(script=script)
        planner = HybridPlanner(provider=provider)
        runner = PlannerEpisodeRunner(env, planner)

        result = runner.run()

        assert result.terminated is True
        assert result.termination_reason == TerminationReason.PLANNER_STOP
        assert result.final_belief_state.is_objective_achieved() is False
        assert result.total_steps <= 5

    def test_x_metrics_and_invalid_ranking_counters(
        self, sample_context: PlannerDecisionContext
    ) -> None:
        """Test X: Metrics tracking invalid rankings and fallback counts."""
        k1 = sample_context.eligible_proposals[0]["candidate_key"]
        provider = FakeHybridRankingProvider(script=[
            {"ranked_candidate_keys": [k1], "reason_code": "VALID"},
            "NOT_JSON",
            {"ranked_candidate_keys": ["CAND-999"]},
            {"ranked_candidate_keys": [k1, k1]},
        ])
        planner = HybridPlanner(provider=provider)

        d1 = planner.plan(sample_context)
        d2 = planner.plan(sample_context)
        d3 = planner.plan(sample_context)
        d4 = planner.plan(sample_context)

        m = planner.metrics
        assert m["total_decisions"] == 4
        assert m["valid_semantic_rankings"] == 1
        assert m["invalid_semantic_rankings"] == 3
        assert m["malformed_semantic_responses"] == 1
        assert m["unknown_candidate_keys"] == 1
        assert m["duplicate_candidate_keys"] == 1
        assert m["symbolic_fallback_count"] == 3
