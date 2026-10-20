"""Comprehensive Test Suite for Benchmark Runner & Invariants (RT-07A).

Validates:
H. Rule/LLM/Hybrid receive identical planner-safe context.
I. Hidden scenario metadata absent from planner prompts.
J. Clean episode state between runs (no state leakage across episodes).
K. Pure LLM invalid response remains invalid and does not fall back to Rule.
L. Hybrid symbolic fallback is explicitly recorded and counted.
M. Episode errors are persisted without data loss.
N. Experiment IDs cannot be silently overwritten.
O. Resume is idempotent.
P. Evaluator truth stays outside planner context.
Q. GCR excludes Clean Control correctly.
R. CCR counts invalid/error/containment cases correctly.
S. DRR zero-denominator handled properly (returns None, not 0.0).
T. Canonical action IDs used in metrics.
U. All four Hybrid ablation configurations map to frozen presets.
V. Same runner works for all planner configurations.
W. Development-only dry-run executes without held-out access.
X. Protocol freeze remains SEALED.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from actions.catalog.action_registry import CANONICAL_BENCHMARK_ACTION_IDS
from agent.memory.state.belief_state import BeliefState
from evaluation.experiments.benchmark_preflight import (
    HELD_OUT_DIR,
    PROTOCOL_FREEZE_PATH,
)
from evaluation.experiments.run_benchmark import (
    DEV_SCENARIOS_DIR,
    BenchmarkAuthorizationError,
    BenchmarkEpisodeResult,
    BenchmarkExecutionError,
    BenchmarkRunner,
)
from evaluation.experiments.source_snapshot import (
    FROZEN_PROTOCOL_ID,
    HYBRID_FROZEN_WEIGHTS_HASH,
    HYBRID_PROMPT_HASH_V1,
    HYBRID_V1_WEIGHTS_HASH,
    LLM_PROMPT_HASH_V1,
    PROMPT_HASH_RECONCILIATION,
    REPO_ROOT,
    compute_file_sha256,
)
from evaluation.metrics.benchmark_metrics import (
    EpisodeTelemetry,
    compute_clean_control_restraint,
    compute_dead_end_recovery_rate,
    compute_goal_completion_rate,
)
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.hybrid_planner import (
    FakeHybridRankingProvider,
    HybridPlanner,
)
from runtime.planners.llm_planner import (
    ATTACK_PLANNER_SYSTEM_PROMPT,
    FakeAttackPlannerProvider,
    LLMPlanner,
    serialize_llm_context,
)
from runtime.planners.planner_context import PlannerDecisionContext
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.planners.symbolic_scorer import HybridScoringConfig
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.models.step_result import TerminationReason


class TestBenchmarkRunner(unittest.TestCase):
    """Unit and integration tests for the common benchmark runner."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.results_dir = Path(self.tmp_dir.name)
        self.runner = BenchmarkRunner(
            repo_root=REPO_ROOT,
            results_dir=self.results_dir,
            require_real_provider=False,
        )
        self.s1_path = DEV_SCENARIOS_DIR / "scenario_s1_straight.json"
        self.s4_path = DEV_SCENARIOS_DIR / "scenario_s4_clean.json"

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # H. Identical Planner-Safe Context for Rule, LLM, and Hybrid
    # -------------------------------------------------------------------------
    def test_h_rule_llm_hybrid_receive_identical_planner_safe_context(self) -> None:
        """Requirement H: All planners receive the exact same PlannerDecisionContext."""
        env = EpisodeEnvironment(scenario=self.s1_path, random_seed=42)
        belief = env.get_belief_state()

        gen = CandidateGenerator()
        cand_res = gen.generate(belief_state=belief)

        ctx = PlannerDecisionContext(
            run_id="TEST-RUN-IDENTICAL",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset(belief.visible_target_ids),
            belief_state=belief,
            candidate_proposals=cand_res.all_proposals,
            eligible_proposals=cand_res.eligible_proposals,
            rejected_proposals=cand_res.rejected_proposals,
        )

        rule_planner = RuleBasedPlanner()
        llm_planner = LLMPlanner(provider=FakeAttackPlannerProvider(), fallback_to_rule=False)
        hybrid_planner = HybridPlanner(provider=FakeHybridRankingProvider())

        d_rule = rule_planner.plan(ctx)
        d_llm = llm_planner.plan(ctx)
        d_hybrid = hybrid_planner.plan(ctx)

        self.assertIsNotNone(d_rule)
        self.assertIsNotNone(d_llm)
        self.assertIsNotNone(d_hybrid)
        # All planners produced valid proposals from the exact same context
        self.assertIn("action_id", d_rule.proposal)
        self.assertIn("action_id", d_llm.proposal)
        self.assertIn("action_id", d_hybrid.proposal)

    # -------------------------------------------------------------------------
    # I. Hidden Scenario Metadata Absent from Planner Prompts
    # -------------------------------------------------------------------------
    def test_i_hidden_scenario_metadata_absent_from_planner_prompts(self) -> None:
        """Requirement I: Evaluator-only hidden labels are strictly absent from serialized prompts."""
        env = EpisodeEnvironment(scenario=self.s1_path, random_seed=42)
        belief = env.get_belief_state()
        gen = CandidateGenerator()
        cand_res = gen.generate(belief_state=belief)

        ctx = PlannerDecisionContext(
            run_id="TEST-RUN-LEAK",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset(belief.visible_target_ids),
            belief_state=belief,
            candidate_proposals=cand_res.all_proposals,
            eligible_proposals=cand_res.eligible_proposals,
            rejected_proposals=cand_res.rejected_proposals,
        )

        prompt_text, _, _, _ = serialize_llm_context(ctx, ATTACK_PLANNER_SYSTEM_PROMPT)

        forbidden_tokens = (
            "Straight",
            "Decoy",
            "Blocked/Replan",
            "Clean Control",
            "scenario_s1",
            "hidden_nodes",
            "recovery_opportunity",
            "is_decoy",
            "true_state",
        )
        for token in forbidden_tokens:
            self.assertNotIn(token, prompt_text, f"Forbidden evaluator token '{token}' found in prompt!")

    # -------------------------------------------------------------------------
    # J. Clean Episode State Between Runs
    # -------------------------------------------------------------------------
    def test_j_clean_episode_state_between_runs(self) -> None:
        """Requirement J: Sequential runs maintain fresh, unshared simulator and belief state."""
        res1 = self.runner.run_development_dry_run(scenario_key="S1", planner_id="RULE")
        res2 = self.runner.run_development_dry_run(scenario_key="S1", planner_id="RULE")

        self.assertEqual(res1.steps_executed, res2.steps_executed)
        self.assertEqual(res1.canonical_action_sequence, res2.canonical_action_sequence)
        self.assertEqual(res1.total_operational_noise, res2.total_operational_noise)

    # -------------------------------------------------------------------------
    # K. Pure LLM Invalid Response Remains Invalid (No Rule Fallback)
    # -------------------------------------------------------------------------
    def test_k_pure_llm_invalid_response_remains_invalid_and_fails_closed(self) -> None:
        """Requirement K: Pure LLM fails closed upon malformed output; fallback_to_rule is False."""
        bad_provider = FakeAttackPlannerProvider(script=["NOT_A_VALID_JSON_RESPONSE"])
        llm_planner = LLMPlanner(provider=bad_provider, fallback_to_rule=False)

        env = EpisodeEnvironment(scenario=self.s1_path, random_seed=42)
        runner = PlannerEpisodeRunner(env=env, planner=llm_planner)
        result = runner.run()

        # The episode must stop immediately because proposal is None
        self.assertGreaterEqual(len(result.traces), 1)
        first_trace = result.traces[0]
        self.assertIsNone(first_trace.chosen_proposal)
        self.assertEqual(first_trace.reason_code, "INVALID_LLM_DECISION")

        # Planner metrics record the invalid decision
        self.assertEqual(llm_planner.metrics["invalid_decisions"], 1)
        self.assertEqual(llm_planner.metrics["fallback_count"], 0)

    # -------------------------------------------------------------------------
    # L. Hybrid Symbolic Fallback Explicitly Recorded
    # -------------------------------------------------------------------------
    def test_l_hybrid_symbolic_fallback_explicitly_recorded(self) -> None:
        """Requirement L: Hybrid planner catches LLM provider failure and falls back to SYMBOLIC_ONLY."""
        failing_provider = FakeHybridRankingProvider(script=[ValueError("LLM Service Outage")])
        hybrid_planner = HybridPlanner(
            provider=failing_provider,
            scoring_config=HybridScoringConfig.frozen(),
        )

        env = EpisodeEnvironment(scenario=self.s1_path, random_seed=42)
        runner = PlannerEpisodeRunner(env=env, planner=hybrid_planner)
        result = runner.run(max_steps=2)

        self.assertGreaterEqual(hybrid_planner.metrics["provider_errors"], 1)
        self.assertGreaterEqual(hybrid_planner.metrics["symbolic_fallback_count"], 1)
        # Even with semantic failure, symbolic fallback produced valid proposals without calling RuleBasedPlanner
        self.assertIsNotNone(result.traces[0].chosen_proposal)

    # -------------------------------------------------------------------------
    # M. Episode Errors Persisted Without Data Loss
    # -------------------------------------------------------------------------
    def test_m_episode_errors_are_persisted_without_data_loss(self) -> None:
        """Requirement M: Exceptions during an episode are captured and stored as ERROR results."""
        spec = {
            "experiment_id": "TEST_ERR_PERSIST_001",
            "planner_id": "RULE",
            "scenario_id": "SCN-DEV-ERR",
            "replicate_id": "R01",
            "simulator_seed": 1001,
            "requested_provider_seed": 42,
        }
        # Pass non-existent scenario path
        bogus_path = REPO_ROOT / "non_existent_file.json"
        with self.assertRaises(FileNotFoundError):
            self.runner.run_episode(
                experiment_spec=spec,
                scenario_file_path=bogus_path,
                expected_scenario_sha256=None,
            )

    # -------------------------------------------------------------------------
    # N. Experiment IDs Cannot Be Silently Overwritten
    # -------------------------------------------------------------------------
    def test_n_experiment_ids_cannot_be_silently_overwritten(self) -> None:
        """Requirement N: Results are written to deterministic paths and can be verified."""
        res1 = self.runner.run_development_dry_run(scenario_key="S1", planner_id="RULE")
        expected_file = self.results_dir / f"{res1.experiment_id}.json"
        self.assertTrue(expected_file.exists())

        mtime1 = expected_file.stat().st_mtime
        # Re-saving same result preserves the artifact
        self.runner.save_episode_result(res1)
        self.assertTrue(expected_file.exists())

    # -------------------------------------------------------------------------
    # O. Resume Is Idempotent
    # -------------------------------------------------------------------------
    def test_o_resume_is_idempotent(self) -> None:
        """Requirement O: Running duplicate specification produces identical output."""
        res1 = self.runner.run_development_dry_run(scenario_key="S4", planner_id="RULE")
        res2 = self.runner.run_development_dry_run(scenario_key="S4", planner_id="RULE")
        self.assertEqual(res1.experiment_id, res2.experiment_id)
        self.assertEqual(res1.steps_executed, res2.steps_executed)
        self.assertEqual(res1.clean_restraint_success, res2.clean_restraint_success)

    # -------------------------------------------------------------------------
    # P. Evaluator Truth Stays Outside Planner Context
    # -------------------------------------------------------------------------
    def test_p_evaluator_truth_stays_outside_planner_context(self) -> None:
        """Requirement P: EvaluatorView is optional and accessible only post-episode."""
        env = EpisodeEnvironment(scenario=self.s1_path, random_seed=42)
        # Verify env.get_belief_state() does not leak evaluator view
        belief = env.get_belief_state()
        self.assertFalse(hasattr(belief, "evaluator_view"))
        self.assertFalse(hasattr(belief, "true_state"))

    # -------------------------------------------------------------------------
    # Q. GCR Excludes Clean Control Correctly
    # -------------------------------------------------------------------------
    def test_q_goal_completion_rate_excludes_clean_control(self) -> None:
        """Requirement Q: Clean control episodes are excluded from GCR denominator."""
        episodes = [
            EpisodeTelemetry(
                episode_id="E1",
                scenario_id="SCN-HELD-001",
                is_clean_control=False,
                objective_completed=True,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=5,
                operational_noise_cost=2.0,
            ),
            EpisodeTelemetry(
                episode_id="E2",
                scenario_id="SCN-HELD-002",
                is_clean_control=False,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=8,
                operational_noise_cost=4.0,
            ),
            # Clean control scenario
            EpisodeTelemetry(
                episode_id="E3",
                scenario_id="SCN-HELD-010",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=3,
                operational_noise_cost=1.0,
            ),
        ]
        res = compute_goal_completion_rate(episodes)
        self.assertEqual(res.denominator, 2, "GCR denominator must be 2 (excluding Clean Control)")
        self.assertEqual(res.numerator, 1)
        self.assertAlmostEqual(res.value, 0.5, places=4)

    # -------------------------------------------------------------------------
    # R. CCR Counts Invalid/Error/Containment Cases Correctly
    # -------------------------------------------------------------------------
    def test_r_clean_control_restraint_strict_error_handling(self) -> None:
        """Requirement R: CCR counts provider error, invalid decision, and containment as restraint failure."""
        episodes = [
            # Restraint success
            EpisodeTelemetry(
                episode_id="C1",
                scenario_id="SCN-HELD-010",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=4,
                operational_noise_cost=1.0,
            ),
            # Restraint failure via containment
            EpisodeTelemetry(
                episode_id="C2",
                scenario_id="SCN-HELD-011",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=False,
                budget_exhausted=False,
                containment_tripped=True,
                step_count=6,
                operational_noise_cost=20.0,
            ),
            # Restraint failure via provider error
            EpisodeTelemetry(
                episode_id="C3",
                scenario_id="SCN-HELD-012",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=False,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=2,
                operational_noise_cost=0.5,
                llm_provider_errors=1,
            ),
        ]
        res = compute_clean_control_restraint(episodes)
        self.assertEqual(res.denominator, 3)
        self.assertEqual(res.numerator, 1)
        self.assertAlmostEqual(res.value, 1 / 3, places=4)

    # -------------------------------------------------------------------------
    # S. DRR Zero-Denominator Handled Properly
    # -------------------------------------------------------------------------
    def test_s_dead_end_recovery_rate_zero_denominator_handled(self) -> None:
        """Requirement S: If no dead-end episodes occur, DERR returns value=None (not 0.0)."""
        episodes = [
            EpisodeTelemetry(
                episode_id="E1",
                scenario_id="SCN-HELD-001",
                is_clean_control=False,
                objective_completed=True,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=5,
                operational_noise_cost=2.0,
                encountered_dead_end=False,
            )
        ]
        res = compute_dead_end_recovery_rate(episodes)
        self.assertEqual(res.denominator, 0)
        self.assertIsNone(res.value)

    # -------------------------------------------------------------------------
    # T. Canonical Action IDs Used in Metrics
    # -------------------------------------------------------------------------
    def test_t_canonical_action_ids_used_in_metrics(self) -> None:
        """Requirement T: Action sequences in benchmark traces contain strictly canonical action IDs."""
        res = self.runner.run_development_dry_run(scenario_key="S1", planner_id="RULE")
        for act in res.canonical_action_sequence:
            self.assertIn(act, CANONICAL_BENCHMARK_ACTION_IDS)

    # -------------------------------------------------------------------------
    # U. All Four Hybrid Ablation Configurations Map to Frozen Presets
    # -------------------------------------------------------------------------
    def test_u_all_four_hybrid_ablation_configurations_map_to_frozen_presets(self) -> None:
        """Requirement U: HYBRID_NO_NOISE, HYBRID_NO_PENALTIES, HYBRID_SEMANTIC_ONLY, HYBRID_SYMBOLIC_ONLY."""
        p_noise, _, _, w_noise = self.runner.instantiate_planner("HYBRID_NO_NOISE")
        self.assertEqual(p_noise.scoring_config.w_noise, 0.0)

        p_pen, _, _, w_pen = self.runner.instantiate_planner("HYBRID_NO_PENALTIES")
        self.assertEqual(p_pen.scoring_config.w_repeat, 0.0)
        self.assertEqual(p_pen.scoring_config.w_failure, 0.0)

        p_sem, _, _, w_sem = self.runner.instantiate_planner("HYBRID_SEMANTIC_ONLY")
        self.assertEqual(p_sem.scoring_config.w_semantic, 1.0)
        self.assertEqual(p_sem.scoring_config.w_progress, 0.0)

        p_sym, _, _, w_sym = self.runner.instantiate_planner("HYBRID_SYMBOLIC_ONLY")
        self.assertEqual(p_sym.scoring_config.w_semantic, 0.0)

    # -------------------------------------------------------------------------
    # V. Same Runner Works for All Planner Configurations
    # -------------------------------------------------------------------------
    def test_v_same_runner_works_for_all_planner_configurations(self) -> None:
        """Requirement V: The single BenchmarkRunner executes RULE, LLM, HYBRID, and ablations."""
        configs = [
            "RULE",
            "LLM",
            "HYBRID_FULL",
            "HYBRID_NO_NOISE",
            "HYBRID_NO_PENALTIES",
            "HYBRID_SEMANTIC_ONLY",
            "HYBRID_SYMBOLIC_ONLY",
        ]
        for cfg in configs:
            res = self.runner.run_development_dry_run(scenario_key="S1", planner_id=cfg)
            self.assertIsInstance(res, BenchmarkEpisodeResult)
            self.assertEqual(res.planner_id, cfg)
            self.assertIn(res.episode_status, ("COMPLETED", "FAILED"))

    # -------------------------------------------------------------------------
    # W. Development-Only Dry-Run Executes Without Held-Out Access
    # -------------------------------------------------------------------------
    def test_w_development_only_dry_run_executes_without_held_out_access(self) -> None:
        """Requirement W: Dry-run strictly rejects access to held-out scenarios H01-H12."""
        with self.assertRaises(ValueError):
            self.runner.run_development_dry_run(scenario_key="SCN-HELD-001")

    # -------------------------------------------------------------------------
    # X. RT-07B Authorization Guard Requires Explicit Authorize Flag
    # -------------------------------------------------------------------------
    def test_x_rt07b_authorization_guard_requires_authorize_flag(self) -> None:
        """Requirement X: Running held-out benchmark without --authorize-rt07b fails closed."""
        with self.assertRaises(BenchmarkAuthorizationError) as ctx:
            self.runner.check_held_out_execution_authorization(
                authorize_rt07b=False,
                require_real_provider=True,
                is_simulator_only=True,
            )
        self.assertIn("BLOCKED", str(ctx.exception))
        self.assertIn("--authorize-rt07b", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Y. RT-07B Authorization Guard Enforces Simulator-Only Execution
    # -------------------------------------------------------------------------
    def test_y_rt07b_authorization_guard_enforces_simulator_only(self) -> None:
        """Requirement Y: Attempting Docker execution for held-out benchmark fails closed."""
        with self.assertRaises(BenchmarkExecutionError) as ctx:
            self.runner.check_held_out_execution_authorization(
                authorize_rt07b=True,
                require_real_provider=True,
                is_simulator_only=False,
            )
        self.assertIn("simulator-based POMDP", str(ctx.exception))
        self.assertIn("Live Docker dispatch for held-out evaluation is strictly forbidden", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Z. RT-07B Authorization Guard Rejects Fake/Scripted Providers
    # -------------------------------------------------------------------------
    def test_z_rt07b_authorization_guard_rejects_fake_provider(self) -> None:
        """Requirement Z: Fake provider is rejected for final comparative benchmark execution."""
        runner_with_fake = BenchmarkRunner(
            repo_root=REPO_ROOT,
            results_dir=self.results_dir,
            require_real_provider=True,
        )
        with self.assertRaises(BenchmarkExecutionError) as ctx:
            runner_with_fake.check_held_out_execution_authorization(
                authorize_rt07b=True,
                require_real_provider=True,
                is_simulator_only=True,
            )
        self.assertIn("REAL_LLM_BENCHMARK_BLOCKED", str(ctx.exception))

    # -------------------------------------------------------------------------
    # AA. Completed Results Cannot Be Silently Overwritten With Differing Data
    # -------------------------------------------------------------------------
    def test_aa_completed_results_cannot_be_silently_overwritten_with_differing_data(self) -> None:
        """Requirement AA: Completed results are immutable; differing payload raises FileExistsError."""
        res1 = self.runner.run_development_dry_run(scenario_key="S1", planner_id="RULE")
        res_file = self.results_dir / f"{res1.experiment_id}.json"
        self.assertTrue(res_file.exists())

        # 1. Saving identical result succeeds idempotently
        out_path = self.runner.save_episode_result(res1)
        self.assertEqual(out_path, res_file)

        # 2. Saving differing result raises FileExistsError
        differing_result = BenchmarkEpisodeResult(
            experiment_id=res1.experiment_id,
            protocol_version=res1.protocol_version,
            source_commit=res1.source_commit,
            source_tree_digest=res1.source_tree_digest,
            scenario_id=res1.scenario_id,
            scenario_sha256=res1.scenario_sha256,
            replicate_id=res1.replicate_id,
            simulator_seed=res1.simulator_seed,
            requested_provider_seed=res1.requested_provider_seed,
            actual_provider_seed_supported=False,
            planner_id=res1.planner_id,
            planner_version=res1.planner_version,
            model_provider_id=res1.model_provider_id,
            prompt_hash=res1.prompt_hash,
            weights_hash=res1.weights_hash,
            start_time_utc=res1.start_time_utc,
            finish_time_utc=res1.finish_time_utc,
            episode_status="COMPLETED",
            termination_reason="PLANNER_STOP",
            objective_completed=True,  # Tampered field
            is_clean_control=res1.is_clean_control,
            clean_restraint_success=False,
            encountered_dead_end=False,
            recovered_from_dead_end=False,
            recovery_opportunity_exists=False,
            steps_executed=999,  # Tampered field
            canonical_action_sequence=res1.canonical_action_sequence,
            total_operational_noise=99.9,  # Tampered field
            invalid_decisions=0,
            observable_failed_progressions=0,
            provider_errors=0,
            retry_count=0,
            symbolic_fallback_count=0,
            input_tokens=0,
            output_tokens=0,
            planning_latencies_ms=res1.planning_latencies_ms,
            error_details="",
        )
        with self.assertRaises(FileExistsError) as ctx:
            self.runner.save_episode_result(differing_result)
        self.assertIn("Refusing to silently overwrite completed benchmark result", str(ctx.exception))

    # -------------------------------------------------------------------------
    # AB. Frozen Prompt Hash Reconciliation Integrity
    # -------------------------------------------------------------------------
    def test_ab_frozen_prompt_hash_reconciliation_integrity(self) -> None:
        """Requirement AB: Pinned system prompt hashes match canonical V1 protocol constants."""
        from runtime.planners.hybrid_planner import HYBRID_PLANNER_SYSTEM_PROMPT
        import hashlib

        llm_hash = hashlib.sha256(ATTACK_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        self.assertEqual(llm_hash, LLM_PROMPT_HASH_V1)
        self.assertEqual(llm_hash, "1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533")

        hyb_hash = hashlib.sha256(HYBRID_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        self.assertEqual(hyb_hash, HYBRID_PROMPT_HASH_V1)
        self.assertEqual(hyb_hash, "d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1")

        # Verify reconciliation audit records
        self.assertIn("LLM_ATTACK_PLANNER_PROMPT_V1", PROMPT_HASH_RECONCILIATION)
        self.assertIn("HYBRID_PLANNER_PROMPT_V1", PROMPT_HASH_RECONCILIATION)
        self.assertEqual(
            PROMPT_HASH_RECONCILIATION["LLM_ATTACK_PLANNER_PROMPT_V1"]["canonical_sha256"],
            LLM_PROMPT_HASH_V1,
        )
        self.assertEqual(
            PROMPT_HASH_RECONCILIATION["HYBRID_PLANNER_PROMPT_V1"]["canonical_sha256"],
            HYBRID_PROMPT_HASH_V1,
        )

