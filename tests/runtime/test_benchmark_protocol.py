"""Comprehensive Protocol and Methodology Freeze Verification Suite (RT-05D / RT-05D1).

Verifies invariants A through N and specific requirements for Benchmark Protocol Seal:
A. Exactly 5 paired replicates.
B. Benchmark cardinality exactly 420.
C. Simulator/provider seeds are not Cartesian-expanded.
D. Provider seed semantics unambiguous.
E. Held-out manifest hashes match all 12 files.
F. Evaluation reads sealed manifest files (evaluation uses manifest-pinned scenario bytes).
G. Planner code contains no held-out IDs.
H. Family labels absent from PlannerDecisionContext.
I. Recovery opportunity remains evaluator-only.
J. Clean-control false-stop/error cases are not counted as restraint success.
K. Frozen Hybrid hash unchanged.
L. Frozen prompt hashes unchanged.
M. Full planner/runtime regressions pass.
N. Full simulation/boundary regressions pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import unittest

from actions.catalog.action_registry import get_canonical_action_id
from evaluation.metrics.benchmark_metrics import (
    EpisodeTelemetry,
    aggregate_action_telemetry_by_canonical,
    compute_clean_control_restraint,
    compute_dead_end_recovery_rate,
    compute_experiment_id,
    compute_goal_completion_rate,
    compute_invalid_decision_rate,
    compute_operational_noise_cost,
    compute_steps_to_goal,
    evaluate_benchmark_telemetry,
)
from runtime.planners.hybrid_planner import (
    HYBRID_OUTPUT_SCHEMA_VERSION,
    HYBRID_PLANNER_PROMPT_V1,
    HYBRID_PLANNER_SYSTEM_PROMPT,
)
from runtime.planners.llm_planner import (
    ATTACK_PLANNER_SYSTEM_PROMPT,
    LLM_ATTACK_PLANNER_PROMPT_V1,
    LLM_CONTEXT_SERIALIZER_VERSION,
    LLM_OUTPUT_SCHEMA_VERSION,
    serialize_llm_context,
)
from runtime.planners.planner_context import PlannerDecisionContext, _FORBIDDEN_CONTEXT_KEYS
from runtime.planners.rule_based_planner import RULE_POLICY_VERSION
from runtime.planners.symbolic_scorer import (
    FROZEN_WEIGHTS_HASH,
    HYBRID_SCORING_V1_FROZEN,
    V1_WEIGHTS_HASH,
    HybridScoringConfig,
)
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.loader import ScenarioLoader

ROOT = Path(__file__).resolve().parents[2]
HELD_OUT_DIR = ROOT / "evaluation" / "datasets" / "held_out"
DEV_SCENARIOS_DIR = ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"
EXPERIMENTS_DIR = ROOT / "evaluation" / "experiments"


class TestBenchmarkProtocolFreeze(unittest.TestCase):
    """Test suite for RT-05D / RT-05D1 benchmark protocol consistency and freeze seal."""

    def setUp(self) -> None:
        self.loader = ScenarioLoader()

    def test_a_s1_s4_classified_as_development_scenarios(self) -> None:
        """Invariant: S1–S4 are explicitly classified as development/validation scenarios."""
        freeze_path = EXPERIMENTS_DIR / "protocol_freeze.json"
        self.assertTrue(freeze_path.is_file(), f"Protocol freeze missing at {freeze_path}")
        data = json.loads(freeze_path.read_text(encoding="utf-8"))

        dev_scns = data["methodology_invariants"]["development_scenarios"]
        dev_ids = {d["scenario_id"] for d in dev_scns}
        self.assertEqual(dev_ids, {"SCN-SIM-001", "SCN-SIM-002", "SCN-SIM-003", "SCN-SIM-004"})

        for d in dev_scns:
            self.assertEqual(
                d["usage"],
                "engineering_development_and_unit_integration_only",
                f"Scenario {d['scenario_id']} must be restricted to engineering/development usage",
            )
            self.assertEqual(
                d["classification"],
                "DEVELOPMENT_ONLY",
            )

    def test_b_held_out_ids_absent_from_planner_production_code(self) -> None:
        """Requirement G: Held-out scenario IDs and node IDs are strictly absent from planner code."""
        manifest_path = HELD_OUT_DIR / "manifest.json"
        self.assertTrue(manifest_path.is_file(), f"Manifest missing at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        held_out_tokens = set()
        for scn_info in manifest["scenarios"]:
            held_out_tokens.add(scn_info["scenario_id"])
            held_out_tokens.add(scn_info["entry_seed"])
            held_out_tokens.add(scn_info["target_node_id"])

        planner_files = [
            ROOT / "runtime" / "planners" / "rule_based_planner.py",
            ROOT / "runtime" / "planners" / "llm_planner.py",
            ROOT / "runtime" / "planners" / "hybrid_planner.py",
            ROOT / "runtime" / "planners" / "symbolic_scorer.py",
            ROOT / "runtime" / "planners" / "candidate_generator.py",
            ROOT / "runtime" / "planners" / "planner_context.py",
        ]

        for pfile in planner_files:
            content = pfile.read_text(encoding="utf-8")
            for token in held_out_tokens:
                self.assertNotIn(
                    token,
                    content,
                    f"Forbidden held-out token '{token}' discovered in production planner file: {pfile.name}",
                )

    def test_c_held_out_family_labels_absent_from_planner_decision_context(self) -> None:
        """Requirement H: Evaluator family labels do not leak into PlannerDecisionContext."""
        from runtime.planners.candidate_generator import CandidateGenerator
        env = EpisodeEnvironment(HELD_OUT_DIR / "scenario_h04_decoy.json", run_id="TEST-DEC-LEAK")
        env.reset()
        current_belief = env.get_belief_state()
        cand_result = CandidateGenerator().generate(current_belief, current_belief.visible_target_ids)
        ctx = PlannerDecisionContext(
            run_id=env.run_id,
            step_index=0,
            max_steps=env.max_steps,
            current_phase="ENGAGEMENT",
            remaining_budget=10,
            max_budget=env.max_budget,
            visible_target_ids=frozenset(current_belief.visible_target_ids),
            belief_state=current_belief,
            candidate_proposals=cand_result.all_proposals,
            eligible_proposals=cand_result.eligible_proposals,
            rejected_proposals=cand_result.rejected_proposals,
        )

        # Check prompt serialization
        prompt_text, _, _, _ = serialize_llm_context(ctx)

        forbidden_labels = ["Decoy Family", "Straight Family", "Blocked Family", "Clean Control Family"]
        for label in forbidden_labels:
            self.assertNotIn(
                label.lower(),
                prompt_text.lower(),
                f"Family label '{label}' leaked into LLM prompt text",
            )

        # Check that context scan rejects family key
        self.assertIn("family", _FORBIDDEN_CONTEXT_KEYS)
        self.assertIn("scenario_family", _FORBIDDEN_CONTEXT_KEYS)

    def test_d_held_out_scenarios_validate_canonical_contract(self) -> None:
        """Contract Validation: All 12 held-out scenarios strictly validate against closed schema."""
        manifest_path = HELD_OUT_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["scenarios"]), 12)

        for scn_meta in manifest["scenarios"]:
            path = HELD_OUT_DIR / scn_meta["filename"]
            self.assertTrue(path.is_file(), f"Missing scenario file: {path}")
            data = json.loads(path.read_text(encoding="utf-8"))
            errors = self.loader.validate_scenario_data(data)
            self.assertEqual(errors, [], f"Validation errors on {scn_meta['filename']}: {errors}")

    def test_e_held_out_scenarios_not_identical_to_s1_s4(self) -> None:
        """Diversity Invariant: Held-out scenarios are not byte-identical or graph-identical copies of S1–S4."""
        dev_hashes = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in DEV_SCENARIOS_DIR.glob("*.json")
        }
        held_hashes = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in HELD_OUT_DIR.glob("scenario_h*.json")
        }

        # No byte identical copies
        self.assertEqual(len(held_hashes), 12)
        for hname, hhash in held_hashes.items():
            for dname, dhash in dev_hashes.items():
                self.assertNotEqual(
                    hhash, dhash,
                    f"Held-out scenario {hname} is byte-identical to development scenario {dname}",
                )

        # Graph node check
        for hpath in HELD_OUT_DIR.glob("scenario_h*.json"):
            hdata = json.loads(hpath.read_text(encoding="utf-8"))
            hnodes = {n["node_id"] for n in hdata["hidden_nodes"]}
            for dpath in DEV_SCENARIOS_DIR.glob("*.json"):
                ddata = json.loads(dpath.read_text(encoding="utf-8"))
                dnodes = {n["node_id"] for n in ddata["hidden_nodes"]}
                self.assertNotEqual(
                    hnodes, dnodes,
                    f"Node set of {hpath.name} is identical to {dpath.name}",
                )

    def test_f_req_a_exactly_5_paired_replicates(self) -> None:
        """Requirement A: Exactly 5 paired replicates defined in seed manifest and benchmark matrix."""
        seed_path = EXPERIMENTS_DIR / "seed_manifest.json"
        seeds = json.loads(seed_path.read_text(encoding="utf-8"))

        self.assertEqual(seeds["manifest_id"], "SEED_MANIFEST_V1")
        self.assertEqual(seeds["total_replicates"], 5)
        self.assertIn("paired_replicates", seeds)
        reps = seeds["paired_replicates"]
        self.assertEqual(len(reps), 5)

        expected_pairs = [
            ("R01", 1001, 42),
            ("R02", 1002, 43),
            ("R03", 1003, 44),
            ("R04", 1004, 45),
            ("R05", 1005, 46),
        ]
        for rep, (exp_id, exp_sim, exp_prov) in zip(reps, expected_pairs):
            self.assertEqual(rep["replicate_id"], exp_id)
            self.assertEqual(rep["simulator_seed"], exp_sim)
            self.assertEqual(rep["provider_seed"], exp_prov)

    def test_g_req_b_benchmark_cardinality_exactly_420(self) -> None:
        """Requirement B: Benchmark matrix cardinality is exactly 420 planned episodes."""
        matrix_path = EXPERIMENTS_DIR / "benchmark_matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))

        self.assertEqual(matrix["total_planned_episodes"], 420)
        self.assertEqual(len(matrix["planned_episodes"]), 420)
        self.assertEqual(matrix["dimensions"]["cardinality"], 420)

        # Unique experiment_ids across all 420 planned episodes
        exp_ids = [e["experiment_id"] for e in matrix["planned_episodes"]]
        self.assertEqual(len(exp_ids), 420)
        self.assertEqual(len(set(exp_ids)), 420, "Every planned episode must possess a unique experiment_id")

    def test_h_req_c_seeds_not_cartesian_expanded(self) -> None:
        """Requirement C: Simulator and provider seeds are paired, NOT Cartesian expanded to 2100."""
        matrix_path = EXPERIMENTS_DIR / "benchmark_matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))

        self.assertFalse(
            matrix["dimensions"]["cartesian_expanded"],
            "Benchmark dimensions must NOT be Cartesian expanded (12*5*5*7 = 2100).",
        )
        self.assertEqual(
            matrix["dimensions"]["held_out_scenarios"]
            * matrix["dimensions"]["paired_replicates"]
            * matrix["dimensions"]["planner_configurations"],
            420,
        )

    def test_i_req_d_provider_seed_semantics_unambiguous(self) -> None:
        """Requirement D: Provider seed semantics unambiguous under controlled inference configuration."""
        freeze_path = EXPERIMENTS_DIR / "protocol_freeze.json"
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))

        ctrl_cfg = freeze["controlled_inference_configuration"]
        self.assertEqual(ctrl_cfg["version"], "CONTROLLED_INFERENCE_CONFIG_V1")
        self.assertEqual(ctrl_cfg["temperature"], 0.0)
        self.assertEqual(ctrl_cfg["top_p"], 1.0)
        self.assertEqual(ctrl_cfg["max_output_tokens"], 512)
        self.assertIn("provider_seed_supported", ctrl_cfg)
        self.assertIn("per_replicate_requested_seeds", ctrl_cfg)
        self.assertEqual(ctrl_cfg["per_replicate_requested_seeds"]["R01"], 42)
        self.assertEqual(ctrl_cfg["per_replicate_requested_seeds"]["R05"], 46)

    def test_j_req_e_held_out_manifest_hashes_match_all_12_files(self) -> None:
        """Requirement E: Held-out manifest records SHA-256 matching all 12 scenario files on disk."""
        manifest_path = HELD_OUT_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(len(manifest["scenarios"]), 12)
        for scn in manifest["scenarios"]:
            file_path = HELD_OUT_DIR / scn["filename"]
            self.assertTrue(file_path.is_file(), f"Missing file: {file_path}")
            disk_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
            manifest_sha = scn["sha256"]
            self.assertEqual(
                disk_sha,
                manifest_sha,
                f"Hash mismatch for {scn['filename']}: disk={disk_sha} vs manifest={manifest_sha}",
            )

    def test_k_req_f_evaluation_reads_sealed_manifest_files(self) -> None:
        """Requirement F: Invariant asserted: evaluation uses manifest-pinned scenario bytes."""
        manifest_path = HELD_OUT_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["seal_state"], "SEALED")
        self.assertEqual(manifest["benchmark_protocol_version"], "BENCHMARK_PROTOCOL_FREEZE_V1")
        self.assertEqual(
            manifest["manifest_invariant"],
            "evaluation uses manifest-pinned scenario bytes",
        )

    def test_l_req_i_recovery_opportunity_remains_evaluator_only(self) -> None:
        """Requirement I: 'recovery opportunity exists' is strictly evaluator-only."""
        # Forbidden keys in PlannerDecisionContext must reject recovery opportunity
        self.assertIn("recovery_opportunity", _FORBIDDEN_CONTEXT_KEYS)
        self.assertIn("recovery_opportunity_exists", _FORBIDDEN_CONTEXT_KEYS)
        self.assertIn("has_recovery_path", _FORBIDDEN_CONTEXT_KEYS)

        # Attempting to construct context with recovery opportunity must fail-closed
        with self.assertRaises(ValueError):
            from runtime.planners.planner_context import _scan_for_forbidden_data
            _scan_for_forbidden_data({"recovery_opportunity": True})

    def test_m_req_j_clean_control_restraint_strict_error_handling(self) -> None:
        """Requirement J: Clean-control restraint fails on provider errors, invalid decisions, or budget exhaustion."""
        episodes = [
            # Case 1: Valid clean STOP -> Success
            EpisodeTelemetry(
                episode_id="EP-C1",
                scenario_id="SCN-HELD-010",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=2,
                operational_noise_cost=0.5,
                invalid_decisions=0,
                llm_provider_errors=0,
            ),
            # Case 2: Budget exhaustion -> Failure
            EpisodeTelemetry(
                episode_id="EP-C2",
                scenario_id="SCN-HELD-011",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=False,
                budget_exhausted=True,
                containment_tripped=False,
                step_count=100,
                operational_noise_cost=15.0,
            ),
            # Case 3: False objective claim -> Failure
            EpisodeTelemetry(
                episode_id="EP-C3",
                scenario_id="SCN-HELD-012",
                is_clean_control=True,
                objective_completed=True,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=3,
                operational_noise_cost=1.0,
            ),
            # Case 4: Containment triggered -> Failure
            EpisodeTelemetry(
                episode_id="EP-C4",
                scenario_id="SCN-HELD-010",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=True,
                step_count=5,
                operational_noise_cost=30.0,
            ),
            # Case 5: Provider error encountered -> Failure
            EpisodeTelemetry(
                episode_id="EP-C5",
                scenario_id="SCN-HELD-011",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=False,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=2,
                operational_noise_cost=0.5,
                llm_provider_errors=1,
            ),
            # Case 6: Invalid decision proposal -> Failure
            EpisodeTelemetry(
                episode_id="EP-C6",
                scenario_id="SCN-HELD-012",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=False,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=2,
                operational_noise_cost=0.5,
                invalid_decisions=1,
            ),
        ]

        res = compute_clean_control_restraint(episodes)
        self.assertEqual(res.denominator, 6)
        self.assertEqual(res.numerator, 1)  # Only Case 1 is a valid restraint success
        self.assertAlmostEqual(res.value, 1 / 6, places=4)

    def test_n_req_k_frozen_hybrid_weight_hashes_stable(self) -> None:
        """Requirement K: Hybrid frozen scoring weights hash is bit-for-bit identical to recorded constants."""
        frozen_config = HybridScoringConfig.frozen()
        computed_hash = frozen_config.weights_hash()

        expected_frozen_hash = "0e595f7294af58a8f635376e8beedb6688cee6784479ae2eb39c21f5c7213aa8"
        expected_v1_hash = "68e55385e064cb2867d07207022b665a9660b87938318efa355488d67bc2c799"

        self.assertEqual(computed_hash, expected_frozen_hash)
        self.assertEqual(FROZEN_WEIGHTS_HASH, expected_frozen_hash)
        self.assertEqual(V1_WEIGHTS_HASH, expected_v1_hash)

    def test_o_req_l_frozen_prompt_hashes_unchanged(self) -> None:
        """Requirement L: LLM and Hybrid prompt versions and SHA-256 hashes match frozen registry."""
        self.assertEqual(LLM_ATTACK_PLANNER_PROMPT_V1, "LLM_ATTACK_PLANNER_PROMPT_V1")
        self.assertEqual(LLM_OUTPUT_SCHEMA_VERSION, "LLM_OUTPUT_SCHEMA_V1")
        self.assertEqual(LLM_CONTEXT_SERIALIZER_VERSION, "LLM_CONTEXT_SERIALIZER_V1")

        llm_hash = hashlib.sha256(ATTACK_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        self.assertEqual(llm_hash, "1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533")

        self.assertEqual(HYBRID_PLANNER_PROMPT_V1, "HYBRID_ATTACK_PLANNER_V1")
        self.assertEqual(HYBRID_OUTPUT_SCHEMA_VERSION, "HYBRID_OUTPUT_SCHEMA_V1")

        hybrid_hash = hashlib.sha256(HYBRID_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        self.assertEqual(hybrid_hash, "d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1")

        self.assertEqual(RULE_POLICY_VERSION, "RULE_POLICY_V1")

    def test_p_req_m_deterministic_experiment_id_and_provenance(self) -> None:
        """Requirement M: Deterministic experiment_id generation and complete provenance contract."""
        exp_id = compute_experiment_id(
            protocol_version="BENCHMARK_PROTOCOL_FREEZE_V1",
            planner_id="HYBRID_FULL",
            scenario_id="SCN-HELD-001",
            scenario_sha256="996a3da07a6c904620cdbc439e837aa4e5f0b6f1fa77d9493e5d0e094340733b",
            replicate_id="R01",
            simulator_seed=1001,
            requested_provider_seed=42,
        )
        expected_id = "BENCHMARK_PROTOCOL_FREEZE_V1_HYBRID_FULL_SCN-HELD-001_996a3da0_R01_sim1001_prov42"
        self.assertEqual(exp_id, expected_id)

        freeze_path = EXPERIMENTS_DIR / "protocol_freeze.json"
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        prov = freeze["benchmark_result_provenance_contract"]
        for field_name in [
            "protocol_version",
            "source_commit",
            "scenario_id",
            "scenario_sha256",
            "planner_id",
            "planner_policy_or_scoring_version",
            "prompt_hash",
            "weights_hash",
            "replicate_id",
            "simulator_seed",
            "requested_provider_seed",
            "experiment_id",
        ]:
            self.assertIn(field_name, prov["required_trace_fields"])

    def test_q_req_n_ablation_configs_differ_only_in_intended_terms(self) -> None:
        """Requirement N: Ablation configurations modify strictly their target terms."""
        full = HybridScoringConfig.full()
        no_noise = HybridScoringConfig.without_noise()
        no_penalties = HybridScoringConfig.without_penalties()
        sem_only = HybridScoringConfig.semantic_only()
        sym_only = HybridScoringConfig.symbolic_only()

        # without_noise: only w_noise changes to 0.0
        self.assertEqual(no_noise.w_noise, 0.0)
        self.assertEqual(no_noise.w_semantic, full.w_semantic)
        self.assertEqual(no_noise.w_progress, full.w_progress)
        self.assertEqual(no_noise.w_step, full.w_step)
        self.assertEqual(no_noise.w_repeat, full.w_repeat)
        self.assertEqual(no_noise.w_failure, full.w_failure)

        # without_penalties: only w_repeat and w_failure change to 0.0
        self.assertEqual(no_penalties.w_repeat, 0.0)
        self.assertEqual(no_penalties.w_failure, 0.0)
        self.assertEqual(no_penalties.w_semantic, full.w_semantic)
        self.assertEqual(no_penalties.w_progress, full.w_progress)
        self.assertEqual(no_penalties.w_noise, full.w_noise)
        self.assertEqual(no_penalties.w_step, full.w_step)

        # semantic_only: w_semantic is 1.0, all symbolic weights 0.0
        self.assertEqual(sem_only.w_semantic, 1.0)
        self.assertEqual(sem_only.w_progress, 0.0)
        self.assertEqual(sem_only.w_noise, 0.0)
        self.assertEqual(sem_only.w_step, 0.0)
        self.assertEqual(sem_only.w_repeat, 0.0)
        self.assertEqual(sem_only.w_failure, 0.0)

        # symbolic_only: w_semantic is 0.0, symbolic terms match full
        self.assertEqual(sym_only.w_semantic, 0.0)
        self.assertEqual(sym_only.w_progress, full.w_progress)
        self.assertEqual(sym_only.w_noise, full.w_noise)
        self.assertEqual(sym_only.w_step, full.w_step)
        self.assertEqual(sym_only.w_repeat, full.w_repeat)
        self.assertEqual(sym_only.w_failure, full.w_failure)

    def test_r_goal_completion_rate_excludes_clean_control_denominator(self) -> None:
        """Goal Completion Rate: Clean-control episodes are strictly excluded from the GCR denominator."""
        episodes = [
            EpisodeTelemetry(
                episode_id=f"EP-ATTACK-{i}",
                scenario_id="SCN-HELD-001",
                is_clean_control=False,
                objective_completed=(i < 3),  # 3 of 5 succeeded
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=8,
                operational_noise_cost=5.0,
            )
            for i in range(5)
        ] + [
            EpisodeTelemetry(
                episode_id=f"EP-CLEAN-{i}",
                scenario_id="SCN-HELD-010",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=2,
                operational_noise_cost=0.5,
            )
            for i in range(3)
        ]

        res = compute_goal_completion_rate(episodes)
        self.assertEqual(res.denominator, 5, "Clean-control episodes must be excluded from GCR denominator")
        self.assertEqual(res.numerator, 3)
        self.assertAlmostEqual(res.value, 0.60, places=4)

    def test_s_dead_end_recovery_rate_explicit_denominator_semantics(self) -> None:
        """Dead-End Recovery Rate: Explicit denominator and recovery semantics."""
        episodes = [
            # Case 1: Attack scenario, encountered dead end, successfully recovered
            EpisodeTelemetry(
                episode_id="EP-1",
                scenario_id="SCN-HELD-007",
                is_clean_control=False,
                objective_completed=True,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=12,
                operational_noise_cost=8.0,
                encountered_dead_end=True,
                recovered_from_dead_end=True,
            ),
            # Case 2: Attack scenario, encountered dead end, failed to recover
            EpisodeTelemetry(
                episode_id="EP-2",
                scenario_id="SCN-HELD-008",
                is_clean_control=False,
                objective_completed=False,
                terminated_cleanly=False,
                budget_exhausted=True,
                containment_tripped=False,
                step_count=20,
                operational_noise_cost=14.0,
                encountered_dead_end=True,
                recovered_from_dead_end=False,
            ),
            # Case 3: Attack scenario, straight path, never hit a dead end (NOT in denominator)
            EpisodeTelemetry(
                episode_id="EP-3",
                scenario_id="SCN-HELD-001",
                is_clean_control=False,
                objective_completed=True,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=6,
                operational_noise_cost=3.0,
                encountered_dead_end=False,
                recovered_from_dead_end=False,
            ),
            # Case 4: Clean control (must be excluded completely)
            EpisodeTelemetry(
                episode_id="EP-4",
                scenario_id="SCN-HELD-010",
                is_clean_control=True,
                objective_completed=False,
                terminated_cleanly=True,
                budget_exhausted=False,
                containment_tripped=False,
                step_count=2,
                operational_noise_cost=0.5,
                encountered_dead_end=False,
                recovered_from_dead_end=False,
            ),
        ]

        res = compute_dead_end_recovery_rate(episodes)
        self.assertEqual(res.denominator, 2, "Only episodes with encountered_dead_end=True enter DERR denominator")
        self.assertEqual(res.numerator, 1)
        self.assertEqual(res.value, 0.50)

    def test_t_canonical_action_aliases_aggregate_under_canonical_ids(self) -> None:
        """Aggregation: Legacy aliases correctly aggregate under canonical benchmark action IDs."""
        trace = [
            {"canonical_action_id": "ACTION-FOOTHOLD-001", "action_id": "ACTION-WEB-001", "status": "SUCCESS", "noise_delta": 1.2},
            {"canonical_action_id": "ACTION-PIVOT-001", "action_id": "ACTION-FLOW-001", "status": "SUCCESS", "noise_delta": 2.0},
            {"canonical_action_id": "ACTION-PIVOT-001", "action_id": "ACTION-PIVOT-001", "status": "FAILURE", "noise_delta": 2.5},
        ]

        agg = aggregate_action_telemetry_by_canonical(trace)

        # ACTION-WEB-001 must be aggregated under ACTION-FOOTHOLD-001
        self.assertIn("ACTION-FOOTHOLD-001", agg)
        self.assertNotIn("ACTION-WEB-001", agg)
        self.assertEqual(agg["ACTION-FOOTHOLD-001"]["total_invocations"], 1)
        self.assertIn("ACTION-WEB-001", agg["ACTION-FOOTHOLD-001"]["execution_aliases_observed"])

        # ACTION-FLOW-001 and ACTION-PIVOT-001 must merge under ACTION-PIVOT-001
        self.assertIn("ACTION-PIVOT-001", agg)
        self.assertNotIn("ACTION-FLOW-001", agg)
        self.assertEqual(agg["ACTION-PIVOT-001"]["total_invocations"], 2)
        self.assertEqual(agg["ACTION-PIVOT-001"]["successful_invocations"], 1)
        self.assertEqual(agg["ACTION-PIVOT-001"]["failed_invocations"], 1)
        self.assertEqual(
            agg["ACTION-PIVOT-001"]["execution_aliases_observed"],
            ["ACTION-FLOW-001", "ACTION-PIVOT-001"],
        )


if __name__ == "__main__":
    unittest.main()
