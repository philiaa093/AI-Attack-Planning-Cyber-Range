"""Comprehensive Action-Space Normalization & De-duplication Tests (RT-05A1).

Verifies invariants:
- Test A: Legacy vs generic equivalent actions map to same semantic family / canonical ID.
- Test B: Planner candidate set contains no duplicate semantic actions.
- Test C: Rule planner baseline uses only canonical generic candidate set.
- Test D: Candidate generation remains strictly deterministic.
- Test E: Candidate generation remains visible-target-only.
- Test F: Hidden targets cannot appear through legacy aliases.
- Test G: Gym action mask has no alias duplication and does not leak hidden nodes.
- Test H: Scenario execution supports canonical generic benchmark actions.
- Test I: Legacy compatibility still passes existing transitions.
- Test J: Rule S1–S4 baseline remains qualitatively correct across all scenarios.
"""
from __future__ import annotations

import copy
from pathlib import Path
import pytest
import numpy as np

from actions.catalog.action_registry import (
    CANONICAL_BENCHMARK_ACTION_IDS,
    ACTION_FAMILY_MAP,
    CANONICAL_ACTION_MAP,
    LEGACY_EXECUTION_MAP,
    are_actions_equivalent,
    get_action_family,
    get_canonical_action_id,
    get_legacy_action_id,
    get_action_registry,
)
from agent.memory.state.belief_state import BeliefState
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.planner_context import PlannerDecisionContext
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.gym_adapter import SimulationGymEnv
from runtime.simulation.models.step_result import TerminationReason
from scripts.validation.validate_scaffold import ROOT

SCENARIOS_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"


class TestActionSpaceNormalization:
    """Validate RT-05A1 action space normalization and de-duplication invariants."""

    def test_a_legacy_and_generic_map_to_same_semantic_family_and_canonical_id(self) -> None:
        """Test A: Legacy actions and Generic Enterprise actions map to consistent canonical IDs."""
        pairs = [
            ("ACTION-RECON-001", "ACTION-DISCOVERY-001", "NETWORK_DISCOVERY", "ACTION-DISCOVERY-001"),
            ("ACTION-WEB-001", "ACTION-FOOTHOLD-001", "INITIAL_FOOTHOLD", "ACTION-FOOTHOLD-001"),
            ("ACTION-AUTH-001", "ACTION-CREDS-001", "CREDENTIAL_DISCOVERY", "ACTION-CREDS-001"),
            ("ACTION-FLOW-001", "ACTION-PIVOT-001", "LATERAL_PIVOT", "ACTION-PIVOT-001"),
            ("ACTION-FLOW-002", "ACTION-OBJECTIVE-001", "OBJECTIVE_ACCESS", "ACTION-OBJECTIVE-001"),
            ("ACTION-END-001", "ACTION-STOP-001", "STOP", "ACTION-STOP-001"),
        ]

        for legacy_id, generic_id, expected_family, expected_canonical in pairs:
            # Semantic family check
            assert get_action_family(legacy_id) == expected_family, f"{legacy_id} family mismatch"
            assert get_action_family(generic_id) == expected_family, f"{generic_id} family mismatch"

            # Canonical ID check
            assert get_canonical_action_id(legacy_id) == expected_canonical, f"{legacy_id} canonical mismatch"
            assert get_canonical_action_id(generic_id) == expected_canonical, f"{generic_id} canonical mismatch"

            # Equivalence check
            assert are_actions_equivalent(legacy_id, generic_id) is True, f"{legacy_id} vs {generic_id} not equivalent"
            assert are_actions_equivalent(generic_id, legacy_id) is True

            # Legacy execution lookup
            assert get_legacy_action_id(generic_id) == legacy_id

    def test_b_planner_candidate_set_contains_no_duplicate_semantic_actions(self) -> None:
        """Test B: CandidateGenerator never emits duplicate proposals for the same capability."""
        belief = BeliefState.from_facts([
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
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-TGT-002",
                "fact_type": "TARGET",
                "subject": "lab-internal-app",
                "value": {"target_id": "lab-internal-app", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SESS-001",
                "fact_type": "SESSION",
                "subject": "sess-dmz",
                "value": {"node_id": "lab-dmz-entry", "session_state": "ACTIVE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-ACC-001",
                "fact_type": "ACCESS",
                "subject": "lab-dmz-entry",
                "value": {"access_level": "FOOTHOLD"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-CRED-001",
                "fact_type": "CREDENTIAL",
                "subject": "cred-app-svc",
                "value": {
                    "credential_id": "cred-app-svc",
                    "observed_scope": "lab-internal-app",
                    "validity_state": "VALID",
                },
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-REACH-001",
                "fact_type": "REACHABILITY",
                "subject": "lab-dmz-entry->lab-internal-app",
                "value": {
                    "from_host": "lab-dmz-entry",
                    "to_host": "lab-internal-app",
                    "protocol": "TCP",
                },
                "confidence": 1.0,
            },
        ])

        cand_gen = CandidateGenerator()
        result = cand_gen.generate(belief_state=belief)

        # 1. Check all emitted action IDs are canonical benchmark actions
        for prop in result.all_proposals:
            assert prop["action_id"] in CANONICAL_BENCHMARK_ACTION_IDS, f"Non-canonical action {prop['action_id']} found"

        # 2. Check no duplicate proposals for (canonical_action_id, target_id, from_node_id, credential_id)
        seen_keys: set[tuple[str, str, str, str]] = set()
        for prop in result.all_proposals:
            key = (
                prop["action_id"],
                str(prop.get("target_id") or ""),
                str(prop.get("from_node_id") or prop.get("from_host") or ""),
                str(prop.get("credential_id") or ""),
            )
            assert key not in seen_keys, f"Duplicate proposal key {key} emitted by CandidateGenerator"
            seen_keys.add(key)

        # 3. Check legacy aliases never appear in proposals
        all_action_ids = {p["action_id"] for p in result.all_proposals}
        assert "ACTION-FLOW-001" not in all_action_ids
        assert "ACTION-FLOW-002" not in all_action_ids
        assert "ACTION-RECON-001" not in all_action_ids
        assert "ACTION-WEB-001" not in all_action_ids
        assert "ACTION-AUTH-001" not in all_action_ids
        assert "ACTION-END-001" not in all_action_ids

    def test_c_rule_planner_baseline_uses_canonical_generic_candidate_set(self) -> None:
        """Test C: Rule planner baseline decisions always select canonical generic proposals."""
        belief = BeliefState.from_facts([
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
                "value": {"port": 80, "protocol": "HTTP", "service_type": "HTTP"},
                "confidence": 1.0,
            },
        ])

        cand_gen = CandidateGenerator()
        cands = cand_gen.generate(belief_state=belief)

        ctx = PlannerDecisionContext(
            run_id="RUN-NORM-001",
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
        decision = planner.plan(ctx)

        assert decision.proposal is not None
        assert decision.proposal["action_id"] in CANONICAL_BENCHMARK_ACTION_IDS
        assert decision.proposal["action_id"] in ("ACTION-SCAN-001", "ACTION-FOOTHOLD-001", "ACTION-DISCOVERY-001")

    def test_d_candidate_generation_remains_strictly_deterministic(self) -> None:
        """Test D: CandidateGenerator produces bit-for-bit identical proposal lists."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-TGT-002",
                "fact_type": "TARGET",
                "subject": "lab-internal-app",
                "value": {"target_id": "lab-internal-app", "status": "REACHABLE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SESS-001",
                "fact_type": "SESSION",
                "subject": "sess-dmz",
                "value": {"node_id": "lab-dmz-entry", "session_state": "ACTIVE"},
                "confidence": 1.0,
            },
        ])

        cand_gen = CandidateGenerator()
        run1 = cand_gen.generate(belief_state=belief)
        run2 = cand_gen.generate(belief_state=belief)

        assert run1.all_proposals == run2.all_proposals
        assert run1.eligible_proposals == run2.eligible_proposals
        assert run1.rejected_proposals == run2.rejected_proposals
        assert run1.candidate_action_ids == run2.candidate_action_ids

    def test_e_candidate_generation_remains_visible_target_only(self) -> None:
        """Test E: Candidate generation only creates proposals for currently visible targets."""
        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-001",
                "fact_type": "TARGET",
                "subject": "lab-dmz-entry",
                "value": {"target_id": "lab-dmz-entry", "status": "REACHABLE"},
                "confidence": 1.0,
            }
        ])

        cand_gen = CandidateGenerator()
        result = cand_gen.generate(belief_state=belief)

        for prop in result.all_proposals:
            tgt = prop.get("target_id")
            if tgt is not None:
                assert tgt in belief.visible_target_ids or tgt.split(":")[0] in belief.visible_target_ids

    def test_f_hidden_targets_cannot_appear_through_legacy_aliases(self) -> None:
        """Test F: Hidden scenario targets (e.g., database, jump-box) cannot appear through legacy aliases."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s3_blocked.json", run_id="RUN-LEAK-TEST")
        bootstrap_obs, initial_belief = env.reset(seed=42)

        cand_gen = CandidateGenerator()
        result = cand_gen.generate(belief_state=initial_belief)

        hidden_nodes = {"lab-internal-app", "lab-jump-box", "lab-db-crown"}
        for prop in result.all_proposals:
            tgt = prop.get("target_id")
            if tgt:
                tgt_host = tgt.split(":")[0]
                assert tgt_host not in hidden_nodes, f"Hidden node {tgt_host} leaked into candidate proposals!"

    def test_g_gym_action_mask_has_no_alias_duplication_and_no_leakage(self) -> None:
        """Test G: Gymnasium action mask has no alias duplication and hidden node count cannot leak."""
        env_s1 = SimulationGymEnv(SCENARIOS_DIR / "scenario_s1_straight.json", max_actions=64)
        obs_s1, info_s1 = env_s1.reset(seed=42)

        # 1. Action mask equals number of admissible proposals
        mask_s1 = info_s1["action_mask"]
        admissible_s1 = env_s1._current_admissible_proposals
        assert int(np.sum(mask_s1)) == len(admissible_s1)

        # 2. Admissible proposals contain only canonical actions (no legacy duplicate aliases)
        for p in admissible_s1:
            assert p["action_id"] in CANONICAL_BENCHMARK_ACTION_IDS

        # 3. Hidden nodes invariant: S1 and S3 have same initial visible belief (only lab-dmz-entry)
        # Even though S3 has more hidden nodes (4 nodes vs 3 nodes), initial visible candidate count must be identical
        env_s3 = SimulationGymEnv(SCENARIOS_DIR / "scenario_s3_blocked.json", max_actions=64)
        obs_s3, info_s3 = env_s3.reset(seed=42)
        mask_s3 = info_s3["action_mask"]
        admissible_s3 = env_s3._current_admissible_proposals

        assert len(admissible_s1) == len(admissible_s3)
        assert np.array_equal(mask_s1, mask_s3)

    def test_h_scenario_execution_supports_canonical_generic_benchmark_actions(self) -> None:
        """Test H: SimulationExecutor executes canonical generic benchmark actions against legacy scenario definitions."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s1_straight.json", run_id="RUN-CANONICAL-TEST")
        env.reset(seed=42)

        # Direct execution of canonical generic action ACTION-DISCOVERY-001 (scenario defines ACTION-RECON-001)
        res1 = env.step({"action_id": "ACTION-DISCOVERY-001", "target_id": "lab-dmz-entry"})
        assert res1.success is True, f"Failed canonical discovery step: {res1.reasons}"

        # Direct execution of canonical generic action ACTION-FOOTHOLD-001 (scenario defines ACTION-WEB-001)
        res2 = env.step({"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-dmz-entry"})
        assert res2.success is True, f"Failed canonical foothold step: {res2.reasons}"
        assert env.get_belief_state().access_state.get("lab-dmz-entry") == "FOOTHOLD"

    def test_i_legacy_compatibility_still_passes(self) -> None:
        """Test I: Legacy action IDs (e.g. ACTION-RECON-001, ACTION-WEB-001) still succeed for backward compatibility."""
        env = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s1_straight.json", run_id="RUN-LEGACY-TEST")
        env.reset(seed=42)

        res1 = env.step({"action_id": "ACTION-RECON-001", "target_id": "lab-dmz-entry"})
        assert res1.success is True, f"Failed legacy recon step: {res1.reasons}"

        res2 = env.step({"action_id": "ACTION-WEB-001", "target_id": "lab-dmz-entry"})
        assert res2.success is True, f"Failed legacy web foothold step: {res2.reasons}"

    def test_j_rule_s1_s4_baseline_remains_qualitatively_correct(self) -> None:
        """Test J: Rule planner baseline produces correct qualitative behaviors across S1–S4."""
        # S1: Straight path succeeds
        env_s1 = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s1_straight.json", run_id="RUN-S1-CHECK")
        res_s1 = PlannerEpisodeRunner(env_s1, RuleBasedPlanner()).run()
        assert res_s1.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED

        # S2: Decoy honeypot trips containment
        env_s2 = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s2_decoy.json", run_id="RUN-S2-CHECK")
        res_s2 = PlannerEpisodeRunner(env_s2, RuleBasedPlanner()).run()
        assert res_s2.termination_reason == TerminationReason.CONTAINED

        # S3: Blocked path replans via jump box and achieves objective
        env_s3 = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s3_blocked.json", run_id="RUN-S3-CHECK")
        res_s3 = PlannerEpisodeRunner(env_s3, RuleBasedPlanner()).run()
        assert res_s3.termination_reason == TerminationReason.OBJECTIVE_ACHIEVED

        # S4: Clean baseline terminates with PLANNER_STOP
        env_s4 = EpisodeEnvironment(SCENARIOS_DIR / "scenario_s4_clean.json", run_id="RUN-S4-CHECK")
        res_s4 = PlannerEpisodeRunner(env_s4, RuleBasedPlanner()).run()
        assert res_s4.termination_reason == TerminationReason.PLANNER_STOP
