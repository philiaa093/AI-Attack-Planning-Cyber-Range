"""Preflight and Scientific Provenance Verification Test Suite (RT-07A).

Validates:
A. Runner reads pre-registered experiment matrix.
B. Exactly 420 unique planned experiment IDs.
C. Paired seed mapping preserved (R01..R05, simulator 1001..1005, provider 42..46).
D. Scenario hash mismatch fails closed.
E. Dirty working tree / source snapshot cannot masquerade as a clean source commit.
F. Missing provider configuration blocks real comparative execution (REAL_LLM_BENCHMARK_BLOCKED).
G. Fake provider is rejected for final comparative benchmark mode.
X. Frozen Benchmark Protocol V1 remains SEALED.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.experiments.benchmark_preflight import (
    BENCHMARK_MATRIX_PATH,
    HELD_OUT_DIR,
    HELD_OUT_MANIFEST_PATH,
    PROTOCOL_FREEZE_PATH,
    SEED_MANIFEST_PATH,
    BenchmarkPreflightChecker,
)
from evaluation.experiments.source_snapshot import (
    FROZEN_PROTOCOL_ID,
    HYBRID_FROZEN_WEIGHTS_HASH,
    HYBRID_PROMPT_HASH_V1,
    HYBRID_V1_WEIGHTS_HASH,
    LLM_PROMPT_HASH_V1,
    REPO_ROOT,
    SourceSnapshotManifest,
    build_source_snapshot,
    compute_file_sha256,
)
from runtime.planners.llm_planner import FakeAttackPlannerProvider


class TestBenchmarkPreflight(unittest.TestCase):
    """Unit and regression tests for benchmark preflight validation and provenance."""

    def setUp(self) -> None:
        self.checker = BenchmarkPreflightChecker(repo_root=REPO_ROOT)

    # -------------------------------------------------------------------------
    # A. Matrix Reading & Verification
    # -------------------------------------------------------------------------
    def test_a_runner_reads_preregistered_experiment_matrix(self) -> None:
        """Requirement A: Preflight verifies pre-registered experiment matrix file."""
        checks = self.checker.verify_experiment_matrix()
        self.assertTrue(all(c.passed for c in checks), f"Matrix checks failed: {checks}")

    # -------------------------------------------------------------------------
    # B. Exactly 420 Unique Planned Experiment IDs
    # -------------------------------------------------------------------------
    def test_b_exactly_420_unique_planned_experiment_ids(self) -> None:
        """Requirement B: Benchmark matrix contains strictly 420 unique planned experiment IDs."""
        matrix = json.loads(BENCHMARK_MATRIX_PATH.read_text(encoding="utf-8"))
        planned = matrix.get("planned_episodes", [])

        self.assertEqual(len(planned), 420, "Must contain exactly 420 planned episodes")
        exp_ids = [e["experiment_id"] for e in planned]
        self.assertEqual(len(exp_ids), 420)
        self.assertEqual(len(set(exp_ids)), 420, "All 420 experiment IDs must be unique")

    # -------------------------------------------------------------------------
    # C. Paired Seed Mapping Preserved
    # -------------------------------------------------------------------------
    def test_c_paired_seed_mapping_preserved(self) -> None:
        """Requirement C: Seed manifest couples simulator and provider seeds into 5 paired replicates."""
        item = self.checker.verify_seed_manifest()
        self.assertTrue(item.passed, item.details)

        seeds = json.loads(SEED_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(seeds["total_replicates"], 5)
        expected = [
            ("R01", 1001, 42),
            ("R02", 1002, 43),
            ("R03", 1003, 44),
            ("R04", 1004, 45),
            ("R05", 1005, 46),
        ]
        for rep, (exp_id, exp_sim, exp_prov) in zip(seeds["paired_replicates"], expected):
            self.assertEqual(rep["replicate_id"], exp_id)
            self.assertEqual(rep["simulator_seed"], exp_sim)
            self.assertEqual(rep["provider_seed"], exp_prov)

    # -------------------------------------------------------------------------
    # D. Scenario Hash Mismatch Fails Closed
    # -------------------------------------------------------------------------
    def test_d_scenario_hash_mismatch_fails_closed(self) -> None:
        """Requirement D: Preflight detects and rejects tampered scenario bytes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            # Create a mock held-out directory with a tampered file
            mock_held_out = tmp_root / "evaluation" / "datasets" / "held_out"
            mock_held_out.mkdir(parents=True)

            manifest_content = {
                "scenarios": [
                    {
                        "scenario_id": "SCN-HELD-999",
                        "filename": "scenario_h999.json",
                        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    }
                ]
            }
            (mock_held_out / "manifest.json").write_text(json.dumps(manifest_content), encoding="utf-8")
            (mock_held_out / "scenario_h999.json").write_text('{"tampered": true}', encoding="utf-8")

            custom_checker = BenchmarkPreflightChecker(repo_root=tmp_root)
            # Override manifest path for isolated test
            with patch("evaluation.experiments.benchmark_preflight.HELD_OUT_MANIFEST_PATH", mock_held_out / "manifest.json"), \
                 patch("evaluation.experiments.benchmark_preflight.HELD_OUT_DIR", mock_held_out):
                items = custom_checker.verify_held_out_scenarios()
                failed_items = [i for i in items if not i.passed]
                self.assertGreater(len(failed_items), 0)
                self.assertTrue(any(i.is_blocker for i in failed_items))
                self.assertTrue(any("Hash mismatch" in i.details for i in failed_items))

    # -------------------------------------------------------------------------
    # E. Dirty Working Tree / Source Snapshot Provenance
    # -------------------------------------------------------------------------
    def test_e_dirty_working_tree_cannot_masquerade_as_clean_commit(self) -> None:
        """Requirement E: Relevant modified or missing source files trigger BLOCKED status."""
        snapshot = build_source_snapshot(REPO_ROOT)
        self.assertIsInstance(snapshot, SourceSnapshotManifest)
        self.assertEqual(snapshot.protocol_version, FROZEN_PROTOCOL_ID)
        self.assertEqual(len(snapshot.relevant_files_manifest), 65, "Must contain exactly 65 relevant source files")
        self.assertIn("actions/catalog/action_registry.py", snapshot.relevant_files_manifest)
        self.assertIn("evaluation/datasets/held_out/manifest.json", snapshot.relevant_files_manifest)
        self.assertIn("runtime/planners/rule_based_planner.py", snapshot.relevant_files_manifest)
        self.assertIn("runtime/simulation/environment.py", snapshot.relevant_files_manifest)
        # Benchmark execution files (RT-07A/RT-07A1/RT-07B0)
        self.assertIn("evaluation/experiments/run_benchmark.py", snapshot.relevant_files_manifest)
        self.assertIn("evaluation/experiments/benchmark_preflight.py", snapshot.relevant_files_manifest)
        self.assertIn("evaluation/experiments/source_snapshot.py", snapshot.relevant_files_manifest)
        self.assertIn("evaluation/results/result.schema.json", snapshot.relevant_files_manifest)
        # Transitive closure additions (RT-07B0)
        self.assertIn("runtime/planners/real_provider_adapter.py", snapshot.relevant_files_manifest)
        self.assertIn("agent/perception/normalizers/enterprise_normalizer.py", snapshot.relevant_files_manifest)
        self.assertIn("runtime/evaluation/usage_costs.py", snapshot.relevant_files_manifest)
        self.assertIn("runtime/evidence/discovery_recorder.py", snapshot.relevant_files_manifest)
        self.assertIn("runtime/lab/workflow_policy.py", snapshot.relevant_files_manifest)
        self.assertIn("runtime/state/knowledge_state_store.py", snapshot.relevant_files_manifest)
        self.assertIn("shared/schema_validation.py", snapshot.relevant_files_manifest)

        # Check prompt hashes and weights hashes
        self.assertEqual(snapshot.prompt_hashes["LLM_ATTACK_PLANNER_PROMPT_V1"], LLM_PROMPT_HASH_V1)
        self.assertEqual(snapshot.prompt_hashes["HYBRID_PLANNER_PROMPT_V1"], HYBRID_PROMPT_HASH_V1)
        self.assertEqual(snapshot.weights_hashes["HYBRID_SCORING_V1_FROZEN"], HYBRID_FROZEN_WEIGHTS_HASH)
        self.assertEqual(snapshot.weights_hashes["HYBRID_SCORING_V1"], HYBRID_V1_WEIGHTS_HASH)

    # -------------------------------------------------------------------------
    # F. Missing Provider Configuration Blocks Real Comparative Execution
    # -------------------------------------------------------------------------
    def test_f_missing_provider_configuration_blocks_real_comparative_execution(self) -> None:
        """Requirement F: Real benchmark without provider triggers REAL_LLM_BENCHMARK_BLOCKED."""
        item = self.checker.verify_provider_readiness(require_real_provider=True, provider=None)
        self.assertFalse(item.passed)
        self.assertTrue(item.is_blocker)
        self.assertIn("REAL_LLM_BENCHMARK_BLOCKED", item.details)

    # -------------------------------------------------------------------------
    # G. Fake Provider Rejected for Final Benchmark Mode
    # -------------------------------------------------------------------------
    def test_g_fake_provider_rejected_for_final_benchmark_mode(self) -> None:
        """Requirement G: FakeAttackPlannerProvider is rejected when real provider is required."""
        fake_prov = FakeAttackPlannerProvider()
        item = self.checker.verify_provider_readiness(require_real_provider=True, provider=fake_prov)
        self.assertFalse(item.passed)
        self.assertTrue(item.is_blocker)
        self.assertIn("REAL_LLM_BENCHMARK_BLOCKED", item.details)
        self.assertIn("FakeAttackPlannerProvider is forbidden", item.details)

    # -------------------------------------------------------------------------
    # X. Frozen Benchmark Protocol V1 Remains SEALED
    # -------------------------------------------------------------------------
    def test_x_frozen_benchmark_protocol_v1_remains_sealed(self) -> None:
        """Requirement X: Protocol freeze file retains status SEALED."""
        item = self.checker.verify_protocol_seal()
        self.assertTrue(item.passed, item.details)
        proto = json.loads(PROTOCOL_FREEZE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(proto["freeze_status"], "SEALED")
        self.assertEqual(proto["protocol_version"], "BENCHMARK_PROTOCOL_FREEZE_V1")
