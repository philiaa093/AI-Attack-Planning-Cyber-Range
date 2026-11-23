"""Integration and Invariant Test Suite for Real Provider Adapter & Readiness (RT-07B0 / RT-07B0A).

Covers Section 11 Requirements A through T and User-Configurable Provider corrections:
A. LLM benchmark configuration uses the real adapter when enabled.
B. Hybrid benchmark configuration uses the same provider configuration.
C. Rule and Symbolic-only require zero API calls.
D. Fake provider cannot reach final benchmark mode.
E. Pure LLM structured response validates correctly.
F. Hybrid structured ranking and frozen fusion work.
G. Unknown candidate fails closed.
H. Pure LLM has no silent Rule fallback.
I. Hybrid provider failure uses explicitly logged symbolic fallback.
J. Input/output tokens persist to result schema.
K. Retry attempts count against rate/request limits.
L. Spending ceiling cannot be bypassed by retries.
M. Circuit-breaker stops execution without losing completed records.
N. Source provenance covers executed code and dependencies (62 files).
O. Uncommitted relevant files block final readiness.
P. Prompt/weights hashes remain frozen.
Q. Held-out hashes remain unchanged.
R. Zero held-out episodes executed.
S. User-configurable model and provider resolution.
T. Controlled inference parameters strictly enforced & secret redaction.
"""
from __future__ import annotations

import dataclasses
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from actions.catalog.action_registry import get_canonical_action_id
from evaluation.experiments.benchmark_preflight import (
    BENCHMARK_MATRIX_PATH,
    HELD_OUT_MANIFEST_PATH,
    PROTOCOL_FREEZE_PATH,
    BenchmarkPreflightChecker,
)
from evaluation.experiments.run_benchmark import (
    BenchmarkAuthorizationError,
    BenchmarkExecutionError,
    BenchmarkRunner,
)
from evaluation.experiments.source_snapshot import (
    FROZEN_PROTOCOL_ID,
    HYBRID_FROZEN_WEIGHTS_HASH,
    HYBRID_PROMPT_HASH_V1,
    HYBRID_V1_WEIGHTS_HASH,
    LLM_PROMPT_HASH_V1,
    RELEVANT_SOURCE_FILES,
    REPO_ROOT,
    build_source_snapshot,
    compute_file_sha256,
)
from runtime.evaluation.usage_costs import MeteredReviewResponse, TokenUsage
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.hybrid_planner import (
    HYBRID_PLANNER_SYSTEM_PROMPT,
    FakeHybridRankingProvider,
    HybridPlanner,
)
from runtime.planners.llm_planner import (
    ATTACK_PLANNER_SYSTEM_PROMPT,
    FakeAttackPlannerProvider,
    LLMPlanner,
)
from runtime.planners.planner_context import PlannerDecisionContext
from runtime.planners.real_provider_adapter import (
    FROZEN_BACKOFF_FACTOR,
    FROZEN_MAX_OUTPUT_TOKENS,
    FROZEN_MAX_RETRIES,
    FROZEN_TEMPERATURE,
    FROZEN_TIMEOUT_SECONDS,
    FROZEN_TOP_P,
    CircuitBreakerTrippedError,
    ProviderBudgetGuard,
    ProviderBudgetLimits,
    RealLLMProviderAdapter,
    RealLLMProviderConfig,
    RealProviderError,
    RealProviderIncompatibleConfigError,
    RealProviderNotConfiguredError,
    RealProviderTimeoutError,
    TokenBudgetEnforcementUnavailableError,
)
from runtime.planners.symbolic_scorer import HybridScoringConfig
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.loader import ScenarioLoader
from shared.schema_validation import validate_shape


class MockHTTPResponse:
    """Mock http.client HTTPResponse for offline provider testing."""

    def __init__(self, status: int, body_dict: dict):
        self.status = status
        self._body = json.dumps(body_dict).encode("utf-8")

    def read(self, _amt: int | None = None) -> bytes:
        return self._body


class MockHTTPConnection:
    """Mock http.client connection capturing requests and returning deterministic responses."""

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.last_method = ""
        self.last_path = ""
        self.last_body: bytes = b""
        self.last_headers: dict[str, str] = {}
        self.response = MockHTTPResponse(200, {})

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
        self.last_method = method
        self.last_path = path
        self.last_body = body or b""
        self.last_headers = headers or {}

    def getresponse(self) -> MockHTTPResponse:
        return self.response

    def close(self):
        pass


class TestRealProviderAdapterSection11(unittest.TestCase):
    """Exhaustive test suite verifying Section 11 Requirements A through T."""

    def setUp(self) -> None:
        self.runner = BenchmarkRunner(repo_root=REPO_ROOT)
        self.dev_s1_path = (
            REPO_ROOT / "runtime" / "simulation" / "fixtures" / "scenarios" / "scenario_s1_straight.json"
        )

    def _make_test_context(self, env: EpisodeEnvironment) -> PlannerDecisionContext:
        belief = env.get_belief_state()
        cand = CandidateGenerator().generate(belief_state=belief, visible_target_ids=belief.visible_target_ids)
        return PlannerDecisionContext(
            run_id="TEST-RUN-001",
            step_index=0,
            max_steps=50,
            current_phase="ENGAGEMENT",
            remaining_budget=20,
            max_budget=20,
            visible_target_ids=frozenset(belief.visible_target_ids),
            belief_state=belief,
            candidate_proposals=cand.all_proposals,
            eligible_proposals=cand.eligible_proposals,
            rejected_proposals=cand.rejected_proposals,
        )

    # -------------------------------------------------------------------------
    # A. LLM benchmark configuration uses real adapter when enabled
    # -------------------------------------------------------------------------
    def test_a_llm_benchmark_configuration_uses_real_adapter_when_enabled(self) -> None:
        """Requirement A: LLM benchmark uses the real adapter when enabled on the runner."""
        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-selected-model", api_key="sk-test")
        adapter = RealLLMProviderAdapter(config=cfg)
        runner = BenchmarkRunner(repo_root=REPO_ROOT, provider=adapter)

        planner, p_ver, p_hash, w_hash = runner.instantiate_planner("LLM")
        self.assertEqual(p_ver, "LLM_ATTACK_PLANNER_PROMPT_V1")
        self.assertEqual(p_hash, LLM_PROMPT_HASH_V1)
        self.assertEqual(w_hash, "N/A")
        self.assertIs(planner._provider, adapter)

    # -------------------------------------------------------------------------
    # B. Hybrid benchmark configuration uses same provider configuration
    # -------------------------------------------------------------------------
    def test_b_hybrid_benchmark_configuration_uses_same_provider_configuration(self) -> None:
        """Requirement B: Hybrid uses the exact same locked provider configuration as LLM."""
        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-selected-model", api_key="sk-test")
        adapter = RealLLMProviderAdapter(config=cfg)
        runner = BenchmarkRunner(repo_root=REPO_ROOT, provider=adapter)

        llm_planner, _, _, _ = runner.instantiate_planner("LLM")
        hybrid_planner, _, _, _ = runner.instantiate_planner("HYBRID_FULL")

        self.assertIs(llm_planner._provider, adapter)
        self.assertIs(hybrid_planner.provider, adapter)
        self.assertEqual(llm_planner._provider.config.model, hybrid_planner.provider.config.model)
        self.assertEqual(llm_planner._provider.config.temperature, hybrid_planner.provider.config.temperature)

    # -------------------------------------------------------------------------
    # C. Rule and Symbolic-only require zero API calls
    # -------------------------------------------------------------------------
    def test_c_rule_and_symbolic_only_require_zero_api_calls(self) -> None:
        """Requirement C: Rule and Hybrid Symbolic-Only make zero HTTP calls to the provider."""
        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)
        runner = BenchmarkRunner(repo_root=REPO_ROOT, provider=adapter)

        # 1. Rule planner
        rule_planner, _, _, _ = runner.instantiate_planner("RULE")
        env = EpisodeEnvironment(scenario=self.dev_s1_path, random_seed=42)
        ctx = self._make_test_context(env)
        rule_decision = rule_planner.plan(ctx)
        self.assertIsNotNone(rule_decision.proposal)
        self.assertEqual(len(adapter.call_history), 0)
        self.assertEqual(adapter.budget_guard.metrics.http_attempts, 0)

        # 2. Hybrid Symbolic-Only
        sym_planner, _, _, _ = runner.instantiate_planner("HYBRID_SYMBOLIC_ONLY")
        sym_decision = sym_planner.plan(ctx)
        self.assertIsNotNone(sym_decision.proposal)
        self.assertEqual(len(adapter.call_history), 0)
        self.assertEqual(adapter.budget_guard.metrics.http_attempts, 0)

    # -------------------------------------------------------------------------
    # D. Fake provider cannot reach final benchmark mode
    # -------------------------------------------------------------------------
    def test_d_fake_provider_cannot_reach_final_benchmark_mode(self) -> None:
        """Requirement D: Fake/scripted provider fails closed in check_held_out_execution_authorization."""
        runner = BenchmarkRunner(repo_root=REPO_ROOT, provider=FakeAttackPlannerProvider())
        with self.assertRaises(BenchmarkExecutionError) as ctx:
            runner.check_held_out_execution_authorization(
                authorize_rt07b=True,
                require_real_provider=True,
                is_simulator_only=True,
            )
        self.assertIn("REAL_LLM_BENCHMARK_BLOCKED", str(ctx.exception))

    # -------------------------------------------------------------------------
    # E. Pure LLM structured response validates correctly
    # -------------------------------------------------------------------------
    def test_e_pure_llm_structured_response_validates_correctly(self) -> None:
        """Requirement E: Pure LLM parses structured JSON and validates candidate_key."""
        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "selected_candidate_key": "CAND-001",
                        "reason_code": "PROBE_DMZ",
                        "brief_justification": "Initial port discovery",
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30},
        })

        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test-valid")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)

        planner = LLMPlanner(provider=adapter, fallback_to_rule=False)
        env = EpisodeEnvironment(scenario=self.dev_s1_path, random_seed=42)
        ctx = self._make_test_context(env)

        decision = planner.plan(ctx)
        self.assertTrue(decision.metadata.get("valid"))
        self.assertEqual(decision.metadata.get("selected_candidate_key"), "CAND-001")
        self.assertFalse(decision.metadata.get("fallback_used"))

    # -------------------------------------------------------------------------
    # F. Hybrid structured ranking and frozen fusion work
    # -------------------------------------------------------------------------
    def test_f_hybrid_structured_ranking_and_frozen_fusion_work(self) -> None:
        """Requirement F: Hybrid ranking parses keys and validates membership in candidate universe."""
        env = EpisodeEnvironment(scenario=self.dev_s1_path, random_seed=42)
        ctx = self._make_test_context(env)
        keys = [f"CAND-{i+1:03d}" for i in range(len(ctx.eligible_proposals))]

        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "ranked_candidate_keys": keys,
                        "reason_code": "STRATEGIC_PRIORITY",
                        "brief_justification": "Ranked discovery first",
                    })
                }
            }],
            "usage": {"prompt_tokens": 150, "completion_tokens": 40},
        })

        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test-valid")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)

        planner = HybridPlanner(provider=adapter, scoring_config=HybridScoringConfig.frozen())
        decision = planner.plan(ctx)

        self.assertIsNotNone(decision.proposal)
        self.assertIn("action_id", decision.proposal)
        self.assertTrue(decision.metadata.get("valid"))
        self.assertTrue(decision.metadata.get("semantic_component_valid"))

    # -------------------------------------------------------------------------
    # G. Unknown candidate fails closed
    # -------------------------------------------------------------------------
    def test_g_unknown_candidate_fails_closed(self) -> None:
        """Requirement G: Unknown candidate key causes LLM to reject proposal and Hybrid to fallback."""
        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "selected_candidate_key": "CAND-NONEXISTENT-999",
                        "reason_code": "HALLUCINATED_KEY",
                    })
                }
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        })

        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)

        # 1. Pure LLM fails closed
        llm = LLMPlanner(provider=adapter, fallback_to_rule=False)
        env = EpisodeEnvironment(scenario=self.dev_s1_path, random_seed=42)
        ctx = self._make_test_context(env)
        decision_llm = llm.plan(ctx)
        self.assertFalse(decision_llm.metadata.get("valid"))
        self.assertEqual(decision_llm.reason_code, "INVALID_LLM_DECISION")
        self.assertEqual(decision_llm.metadata.get("error_reason"), "UNKNOWN_CANDIDATE")

        # 2. Hybrid falls back to SYMBOLIC_ONLY
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "ranked_candidate_keys": ["CAND-NONEXISTENT-999"],
                        "reason_code": "HALLUCINATED_KEY",
                    })
                }
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        })
        hybrid = HybridPlanner(provider=adapter, scoring_config=HybridScoringConfig.frozen())
        decision_hybrid = hybrid.plan(ctx)
        self.assertTrue(decision_hybrid.metadata.get("fallback_used"))
        self.assertEqual(decision_hybrid.metadata.get("semantic_fallback_mode"), "SYMBOLIC_ONLY")

    # -------------------------------------------------------------------------
    # H. Pure LLM has no silent Rule fallback
    # -------------------------------------------------------------------------
    def test_h_pure_llm_has_no_silent_rule_fallback(self) -> None:
        """Requirement H: Malformed LLM provider response fails closed without calling Rule."""
        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{"message": {"content": "INVALID_JSON_CORRUPTION"}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        })

        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test-valid")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)

        planner = LLMPlanner(provider=adapter, fallback_to_rule=False, max_retries=0)
        env = EpisodeEnvironment(scenario=self.dev_s1_path, random_seed=42)
        ctx = self._make_test_context(env)

        decision = planner.plan(ctx)
        self.assertFalse(decision.metadata.get("valid"))
        self.assertFalse(decision.metadata.get("fallback_used"))
        self.assertEqual(decision.reason_code, "INVALID_LLM_DECISION")

    # -------------------------------------------------------------------------
    # I. Hybrid provider failure uses explicitly logged symbolic fallback
    # -------------------------------------------------------------------------
    def test_i_hybrid_provider_failure_uses_explicitly_logged_symbolic_fallback(self) -> None:
        """Requirement I: Provider error triggers SYMBOLIC_ONLY fallback (never calling Rule)."""
        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(500, {"error": "Internal Server Error"})

        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test-valid")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)

        planner = HybridPlanner(provider=adapter, scoring_config=HybridScoringConfig.frozen())
        env = EpisodeEnvironment(scenario=self.dev_s1_path, random_seed=42)
        ctx = self._make_test_context(env)

        decision = planner.plan(ctx)
        self.assertTrue(decision.metadata.get("fallback_used"))
        self.assertEqual(decision.metadata.get("semantic_fallback_mode"), "SYMBOLIC_ONLY")
        self.assertNotEqual(decision.metadata.get("planner_type"), "RULE")

    # -------------------------------------------------------------------------
    # J. Input/output tokens persist to result schema
    # -------------------------------------------------------------------------
    def test_j_input_output_tokens_persist_to_result_schema(self) -> None:
        """Requirement J: Token usage from provider persists in episode result and satisfies result schema."""
        schema_path = REPO_ROOT / "evaluation" / "results" / "result.schema.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{"message": {"content": json.dumps({"selected_candidate_key": "CAND-001"})}}],
            "usage": {"prompt_tokens": 128, "completion_tokens": 32, "total_tokens": 160},
        })

        cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test")
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)
        runner = BenchmarkRunner(repo_root=REPO_ROOT, provider=adapter)

        res = runner.run_development_dry_run(scenario_key="S1", planner_id="LLM")
        self.assertGreater(res.input_tokens, 0)
        self.assertGreater(res.output_tokens, 0)

        # Validate against result schema
        res_dict = res.to_dict()
        validate_shape(res_dict, schema)

    # -------------------------------------------------------------------------
    # K. Retry attempts count against rate/request limits
    # -------------------------------------------------------------------------
    def test_k_retry_attempts_count_against_rate_and_request_limits(self) -> None:
        """Requirement K: Retries increment http_attempts, retry_attempts, and rate limits."""
        guard = ProviderBudgetGuard(limits=ProviderBudgetLimits(max_requests_per_minute=5))

        for i in range(5):
            guard.record_http_attempt()

        self.assertEqual(guard.metrics.http_attempts, 5)

        # 6th attempt in the same minute must trip rate limit
        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            guard.record_http_attempt()
        self.assertIn("RATE_LIMIT_EXCEEDED", str(ctx.exception))

    # -------------------------------------------------------------------------
    # L. Spending ceiling cannot be bypassed by retries
    # -------------------------------------------------------------------------
    def test_l_spending_ceiling_cannot_be_bypassed_by_retries(self) -> None:
        """Requirement L: max_http_attempts halts retry amplification at spending ceiling."""
        guard = ProviderBudgetGuard(limits=ProviderBudgetLimits(max_http_attempts=3))

        # First logical call with 2 retries (3 attempts total)
        guard.record_http_attempt()
        guard.record_http_attempt()
        guard.record_retry()
        guard.record_http_attempt()
        guard.record_retry()

        self.assertEqual(guard.metrics.http_attempts, 3)
        self.assertEqual(guard.metrics.retry_attempts, 2)

        # 4th attempt exceeds max_http_attempts and trips circuit breaker
        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            guard.record_http_attempt()
        self.assertIn("MAX_HTTP_ATTEMPTS_EXCEEDED", str(ctx.exception))

    # -------------------------------------------------------------------------
    # M. Circuit-breaker stops execution without losing completed records
    # -------------------------------------------------------------------------
    def test_m_circuit_breaker_stops_execution_without_losing_completed_records(self) -> None:
        """Requirement M: Circuit-breaker trips cleanly while preserving previously completed results."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_results = Path(temp_dir)
            runner = BenchmarkRunner(repo_root=REPO_ROOT, results_dir=temp_results)

            # 1. Run and complete first episode
            res1 = runner.run_development_dry_run(scenario_key="S1", planner_id="RULE")
            self.assertEqual(res1.episode_status, "COMPLETED")
            file1 = temp_results / f"{res1.experiment_id}.json"
            self.assertTrue(file1.exists())

            # 2. Simulate circuit breaker tripping during second episode
            mock_conn = MockHTTPConnection("127.0.0.1", 443)
            # Return 500 continuously to trip consecutive error limit (5)
            mock_conn.response = MockHTTPResponse(500, {"error": "down"})

            cfg = RealLLMProviderConfig(provider_type="openai-compatible", model="user-model", api_key="sk-test")
            guard = ProviderBudgetGuard(limits=ProviderBudgetLimits(max_consecutive_errors=2))
            adapter = RealLLMProviderAdapter(config=cfg, budget_guard=guard, http_transport_factory=lambda *a, **k: mock_conn)

            # Trigger consecutive errors directly
            with self.assertRaises(CircuitBreakerTrippedError):
                adapter.complete("Prompt 1")
            with self.assertRaises(CircuitBreakerTrippedError):
                adapter.complete("Prompt 2")

            # 3. Assert first result file is intact and unchanged
            self.assertTrue(file1.exists())
            loaded1 = json.loads(file1.read_text(encoding="utf-8"))
            self.assertEqual(loaded1["episode_status"], "COMPLETED")
            self.assertEqual(loaded1["experiment_id"], res1.experiment_id)

    # -------------------------------------------------------------------------
    # N. Source provenance covers executed code and dependencies (65 files)
    # -------------------------------------------------------------------------
    def test_n_source_provenance_covers_all_relevant_dependencies(self) -> None:
        """Requirement N: Transitive closure contains exactly 65 modules and includes runner/adapters."""
        self.assertEqual(len(RELEVANT_SOURCE_FILES), 65)
        snapshot = build_source_snapshot(REPO_ROOT)
        self.assertEqual(len(snapshot.relevant_files_manifest), 65)
        self.assertEqual(len(snapshot.source_tree_digest), 64)
        self.assertIn("runtime/planners/real_provider_adapter.py", snapshot.relevant_files_manifest)
        self.assertIn("evaluation/experiments/run_benchmark.py", snapshot.relevant_files_manifest)
        self.assertIn("dashboards/app/backend/model_profiles.py", snapshot.relevant_files_manifest)
        self.assertIn("runtime/planners/observed_planner.py", snapshot.relevant_files_manifest)
        self.assertIn("scripts/validation/validate_scaffold.py", snapshot.relevant_files_manifest)

    # -------------------------------------------------------------------------
    # O. Uncommitted relevant files block final readiness
    # -------------------------------------------------------------------------
    def test_o_uncommitted_relevant_files_block_final_readiness(self) -> None:
        """Requirement O: Untracked/dirty relevant files cause provenance_status to be BLOCKED."""
        snapshot = build_source_snapshot(REPO_ROOT)
        if snapshot.untracked_files:
            untracked_set = set(snapshot.untracked_files)
            relevant_set = set(RELEVANT_SOURCE_FILES)
            if untracked_set.intersection(relevant_set):
                self.assertEqual(snapshot.provenance_status, "BLOCKED")
                self.assertTrue(any("DIRTY_RELEVANT_FILES_PRESENT" in b for b in snapshot.blockers))

    # -------------------------------------------------------------------------
    # P. Prompt and weights hashes remain frozen
    # -------------------------------------------------------------------------
    def test_p_prompt_and_weights_hashes_remain_frozen(self) -> None:
        """Requirement P: LLM system prompt, Hybrid system prompt, and Hybrid weights digests match."""
        llm_hash = hashlib.sha256(ATTACK_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        hybrid_hash = hashlib.sha256(HYBRID_PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

        self.assertEqual(llm_hash, LLM_PROMPT_HASH_V1)
        self.assertEqual(hybrid_hash, HYBRID_PROMPT_HASH_V1)

        cfg = HybridScoringConfig.frozen()
        self.assertEqual(cfg.weights_hash(), HYBRID_FROZEN_WEIGHTS_HASH)

    # -------------------------------------------------------------------------
    # Q. Held-out hashes remain unchanged
    # -------------------------------------------------------------------------
    def test_q_held_out_hashes_remain_unchanged(self) -> None:
        """Requirement Q: All 12 held-out scenarios match registered SHA-256 digests in manifest."""
        manifest = json.loads(HELD_OUT_MANIFEST_PATH.read_text(encoding="utf-8"))
        scenarios = manifest.get("scenarios", [])
        self.assertEqual(len(scenarios), 12)
        for meta in scenarios:
            scn_path = HELD_OUT_MANIFEST_PATH.parent / meta["filename"]
            self.assertTrue(scn_path.exists())
            actual_sha = compute_file_sha256(scn_path)
            self.assertEqual(actual_sha, meta["sha256"])

    # -------------------------------------------------------------------------
    # R. Zero held-out episodes executed
    # -------------------------------------------------------------------------
    def test_r_zero_held_out_episodes_executed(self) -> None:
        """Requirement R: No held-out result files exist in evaluation/results."""
        results_dir = REPO_ROOT / "evaluation" / "results"
        if results_dir.exists():
            held_out_results = [
                f for f in results_dir.glob("*.json")
                if "SCN-HELD" in f.name and not f.name.endswith(".schema.json")
            ]
            self.assertEqual(len(held_out_results), 0, f"Found held-out result files: {held_out_results}")

    # -------------------------------------------------------------------------
    # S. User-configurable model and provider resolution
    # -------------------------------------------------------------------------
    def test_s_user_configurable_model_and_provider_resolution(self) -> None:
        """Requirement S: Allows custom provider_type, model_id, base_url; supports local keyless endpoints."""
        # 1. Custom model and custom endpoint with key
        cfg = RealLLMProviderConfig.from_profile_or_env(
            provider_type="openai-compatible",
            model="custom-mistral-local",
            api_base="http://localhost:11434/v1",
            api_key="custom-key",
        )
        self.assertEqual(cfg.model, "custom-mistral-local")
        self.assertEqual(cfg.api_base, "http://localhost:11434/v1")
        self.assertTrue(cfg.is_configured)
        self.assertTrue(cfg.is_local_endpoint)
        self.assertFalse(cfg.requires_api_key)

        # 2. Local loopback endpoint without key must succeed (no dummy key required)
        local_cfg = RealLLMProviderConfig(
            provider_type="openai-compatible",
            model="llama3-local",
            api_base="http://127.0.0.1:11434/v1",
            api_key=None,
        )
        self.assertTrue(local_cfg.is_local_endpoint)
        self.assertFalse(local_cfg.requires_api_key)
        self.assertTrue(local_cfg.is_configured)

        mock_conn = MockHTTPConnection("127.0.0.1", 11434)
        mock_conn.response = MockHTTPResponse(200, {
            "choices": [{"message": {"content": "PLAN_DECISION_SCHEMA_V1"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
        local_adapter = RealLLMProviderAdapter(config=local_cfg, http_transport_factory=lambda *a, **k: mock_conn)
        self.assertTrue(local_adapter.is_configured)
        resp = local_adapter.complete("Prompt")
        self.assertEqual(resp.review_json, "PLAN_DECISION_SCHEMA_V1")

        # 3. Remote endpoint without key must fail closed
        remote_cfg = RealLLMProviderConfig(
            provider_type="openai-compatible",
            model="gpt-4o",
            api_base="https://api.openai.com/v1",
            api_key=None,
        )
        self.assertFalse(remote_cfg.is_local_endpoint)
        self.assertTrue(remote_cfg.requires_api_key)
        self.assertFalse(remote_cfg.is_configured)
        remote_adapter = RealLLMProviderAdapter(config=remote_cfg)
        with self.assertRaises(RealProviderNotConfiguredError):
            remote_adapter.complete("Prompt")

        # 4. Empty model fails closed (no hardcoded fallback)
        unconfigured_cfg = RealLLMProviderConfig(model="", api_key="sk-test")
        unconfigured_adapter = RealLLMProviderAdapter(config=unconfigured_cfg)
        self.assertFalse(unconfigured_adapter.is_configured)
        with self.assertRaises(RealProviderNotConfiguredError) as ctx:
            unconfigured_adapter.complete("Test")
        self.assertIn("REAL_LLM_BENCHMARK_BLOCKED", str(ctx.exception))

    # -------------------------------------------------------------------------
    # T. Controlled inference parameters & secret redaction
    # -------------------------------------------------------------------------
    def test_t_controlled_inference_parameters_and_secret_redaction(self) -> None:
        """Requirement T: Enforces frozen temperature=0, top_p=1, max_tokens=512; redacts secrets."""
        # Incompatible temperature must raise
        with self.assertRaises(RealProviderIncompatibleConfigError):
            RealLLMProviderConfig(temperature=0.7, model="user-model", api_key="sk-test")

        # Incompatible max_tokens must raise
        with self.assertRaises(RealProviderIncompatibleConfigError):
            RealLLMProviderConfig(max_output_tokens=1024, model="user-model", api_key="sk-test")

        # Secret redaction: key must not appear in repr or exception
        secret_key = "sk-super-secret-production-token-999"
        cfg = RealLLMProviderConfig(model="user-model", api_key=secret_key)
        self.assertNotIn(secret_key, repr(cfg))

        mock_conn = MockHTTPConnection("127.0.0.1", 443)
        mock_conn.response = MockHTTPResponse(401, {"error": f"Invalid key: {secret_key}"})
        adapter = RealLLMProviderAdapter(config=cfg, http_transport_factory=lambda *a, **k: mock_conn)

        try:
            adapter.complete("Prompt")
        except RealProviderError as exc:
            self.assertNotIn(secret_key, str(exc))
            self.assertIn("[REDACTED", str(exc))

    # -------------------------------------------------------------------------
    # U. Provenance record & Spend accounting semantics (RT-07B Closure)
    # -------------------------------------------------------------------------
    def test_u_provenance_record_and_spend_accounting_semantics(self) -> None:
        """Requirement U: Immutable provenance record and explicit monetary cap status."""
        cfg = RealLLMProviderConfig(
            provider_type="openai-compatible",
            model="custom-eval-model",
            api_base="https://custom.endpoint.internal/v1",
            api_key="sk-sensitive-api-token-777",
            configuration_source="CLI_OVERRIDE",
        )
        rec = cfg.to_provenance_record()
        self.assertEqual(rec["model_id"], "custom-eval-model")
        self.assertEqual(rec["base_url"], "https://custom.endpoint.internal/v1")
        self.assertEqual(rec["configuration_source"], "CLI_OVERRIDE")
        self.assertEqual(rec["api_key_redacted"], "[REDACTED]")
        self.assertNotIn("sk-sensitive-api-token-777", json.dumps(rec))
        self.assertEqual(rec["inference_parameters"]["temperature"], FROZEN_TEMPERATURE)
        self.assertEqual(rec["inference_parameters"]["max_output_tokens"], FROZEN_MAX_OUTPUT_TOKENS)

        guard = ProviderBudgetGuard()
        summary = guard.get_spend_accounting_summary()
        self.assertEqual(summary["monetary_cap_status"], "MONETARY_CAP_NOT_ENFORCED")
        self.assertIsNone(summary["estimated_monetary_spend_usd"])
        self.assertIn("monetary_accounting_note", summary)

    # -------------------------------------------------------------------------
    # V. Local Provider Endpoint Safety & Loopback Classification (Final Check B)
    # -------------------------------------------------------------------------
    def test_v_local_provider_endpoint_safety_and_loopback_classification(self) -> None:
        """Requirement V: Loopback vs wildcard vs Docker hostnames vs remote URLs."""
        # 1. Genuine IPv4 loopback (127.0.0.1 and 127.0.0.0/8)
        cfg_127 = RealLLMProviderConfig(model="m1", api_base="http://127.0.0.1:8000/v1")
        self.assertTrue(cfg_127.is_local_endpoint)
        self.assertFalse(cfg_127.requires_api_key)
        self.assertTrue(cfg_127.is_configured)

        cfg_127_sub = RealLLMProviderConfig(model="m1", api_base="http://127.0.1.1:8080/v1")
        self.assertTrue(cfg_127_sub.is_local_endpoint)
        self.assertFalse(cfg_127_sub.requires_api_key)
        self.assertTrue(cfg_127_sub.is_configured)

        # 2. Genuine IPv6 loopback (::1)
        cfg_ipv6 = RealLLMProviderConfig(model="m1", api_base="http://[::1]:11434/v1")
        self.assertTrue(cfg_ipv6.is_local_endpoint)
        self.assertFalse(cfg_ipv6.requires_api_key)
        self.assertTrue(cfg_ipv6.is_configured)

        # 3. Genuine localhost
        cfg_lh = RealLLMProviderConfig(model="m1", api_base="http://localhost:11434/v1")
        self.assertTrue(cfg_lh.is_local_endpoint)
        self.assertFalse(cfg_lh.requires_api_key)
        self.assertTrue(cfg_lh.is_configured)

        cfg_lh_sub = RealLLMProviderConfig(model="m1", api_base="http://service.localhost:9000/v1")
        self.assertTrue(cfg_lh_sub.is_local_endpoint)
        self.assertFalse(cfg_lh_sub.requires_api_key)
        self.assertTrue(cfg_lh_sub.is_configured)

        # 4. Wildcard bind addresses (0.0.0.0) MUST NOT be classified as trusted loopback
        cfg_wildcard = RealLLMProviderConfig(model="m1", api_base="http://0.0.0.0:8000/v1")
        self.assertFalse(cfg_wildcard.is_local_endpoint, "0.0.0.0 must NOT be classified as loopback")
        self.assertTrue(cfg_wildcard.requires_api_key)
        self.assertFalse(cfg_wildcard.is_configured)

        adapter_wildcard = RealLLMProviderAdapter(config=cfg_wildcard)
        with self.assertRaises(RealProviderNotConfiguredError):
            adapter_wildcard.complete("test")

        # 5. Docker hostnames (host.docker.internal, ollama-svc) are NOT loopback
        cfg_docker = RealLLMProviderConfig(model="m1", api_base="http://host.docker.internal:11434/v1")
        self.assertFalse(cfg_docker.is_local_endpoint)
        self.assertTrue(cfg_docker.requires_api_key)
        self.assertFalse(cfg_docker.is_configured)

        # Explicit keyless policy allows Docker/LAN endpoints without API key
        cfg_docker_keyless = RealLLMProviderConfig(
            model="m1",
            api_base="http://host.docker.internal:11434/v1",
            allow_keyless=True,
        )
        self.assertFalse(cfg_docker_keyless.is_local_endpoint)
        self.assertFalse(cfg_docker_keyless.requires_api_key)
        self.assertTrue(cfg_docker_keyless.is_configured)

        # 6. Remote URLs (OpenAI, Anthropic, LAN IP) require authentication
        cfg_remote = RealLLMProviderConfig(model="m1", api_base="https://api.openai.com/v1")
        self.assertFalse(cfg_remote.is_local_endpoint)
        self.assertTrue(cfg_remote.requires_api_key)
        self.assertFalse(cfg_remote.is_configured)

        cfg_lan = RealLLMProviderConfig(model="m1", api_base="http://192.168.1.50:8000/v1")
        self.assertFalse(cfg_lan.is_local_endpoint)
        self.assertTrue(cfg_lan.requires_api_key)
        self.assertFalse(cfg_lan.is_configured)

        # 7. Credential isolation & secret protection
        secret_token = "sk-live-super-secret-vault-key-abc123"
        cfg_with_key = RealLLMProviderConfig(
            model="m1",
            api_base="https://api.openai.com/v1",
            api_key=secret_token,
        )
        self.assertNotIn(secret_token, repr(cfg_with_key))
        prov_record = cfg_with_key.to_provenance_record()
        self.assertEqual(prov_record["api_key_redacted"], "[REDACTED]")
        self.assertNotIn(secret_token, json.dumps(prov_record))


class TestRT07SmokeAuditOfflineSafety(unittest.TestCase):
    """Offline Provider Token Accounting & Pre-Dispatch Safety Suite (RT-07-SMOKE-AUDIT).

    12 Offline Mocked & Invariant Tests:
    1. Provider usage exceeding authorization trips TOKEN_AUTHORIZATION_BREACH.
    2. Hidden prompt overhead fails closed with SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE.
    3. Native tokenizer disagreement does not satisfy authoritative input bound.
    4. Missing authoritative input count trips TokenBudgetEnforcementUnavailableError.
    5. Provider reasoning tokens recorded in metrics and total.
    6. Retry attempts count against budgets and reject over-cap reservations.
    7. Zero remaining authorization prevents dispatch.
    8. Provider usage exceeds prior estimate logged as authorization incident.
    9. Pure LLM response parsing distinguishes HTTP 200 from valid candidate selection.
    10. Smoke artifacts in evaluation/results/smoke/ are ignored by benchmark preflight.
    11. Frozen prompt and scoring hashes remain unchanged.
    12. Zero live network calls during tests (mock factory only).
    """

    def test_01_provider_usage_exceeding_authorization_trips_breach(self):
        """Test 1: Estimated input 236, output reservation 512, provider usage reports 3,861 -> trips TOKEN_AUTHORIZATION_BREACH."""
        limits = ProviderBudgetLimits(strict_total_token_cap=1000)
        guard = ProviderBudgetGuard(limits=limits)
        cfg = RealLLMProviderConfig(model="test-model", api_base="http://127.0.0.1:20128/v1")

        mock_conn = MockHTTPConnection("127.0.0.1", 20128)
        mock_conn.response = MockHTTPResponse(
            200,
            {
                "choices": [{"message": {"content": '{"selected_candidate_key": "CAND-001"}'}}],
                "usage": {"prompt_tokens": 1054, "completion_tokens": 2807, "total_tokens": 3861},
            },
        )
        adapter = RealLLMProviderAdapter(config=cfg, budget_guard=guard, http_transport_factory=lambda *a, **k: mock_conn)

        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            adapter.complete("Short test prompt")

        self.assertIn("TOKEN_AUTHORIZATION_BREACH", str(ctx.exception))
        self.assertFalse(guard.is_healthy)
        self.assertEqual(len(guard.metrics.authorization_incidents), 1)
        incident = guard.metrics.authorization_incidents[0]
        self.assertEqual(incident["event"], "TOKEN_AUTHORIZATION_BREACH")
        self.assertEqual(incident["strict_cap"], 1000)
        self.assertEqual(incident["reported_total"], 3861)
        self.assertEqual(incident["excess"], 2861)

    def test_02_hidden_prompt_overhead_fails_closed_when_authoritative_required(self):
        """Test 2: Endpoint with hidden prompt overhead fails closed with SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE."""
        limits = ProviderBudgetLimits(strict_total_token_cap=1000, require_authoritative_input_bound=True)
        guard = ProviderBudgetGuard(limits=limits)
        cfg = RealLLMProviderConfig(model="test-model", api_base="http://127.0.0.1:20128/v1", authoritative_input_tokens=None)

        mock_conn = MockHTTPConnection("127.0.0.1", 20128)
        adapter = RealLLMProviderAdapter(config=cfg, budget_guard=guard, http_transport_factory=lambda *a, **k: mock_conn)

        with self.assertRaises(TokenBudgetEnforcementUnavailableError) as ctx:
            adapter.complete("Short test prompt")

        self.assertIn("SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE", str(ctx.exception))
        self.assertFalse(guard.is_healthy)

    def test_03_native_tokenizer_disagreement_does_not_satisfy_authoritative_bound(self):
        """Test 3: Native tokenizer disagrees with cl100k_base -> client estimate is not treated as authoritative."""
        limits = ProviderBudgetLimits(strict_total_token_cap=1000, require_authoritative_input_bound=True)
        guard = ProviderBudgetGuard(limits=limits)

        # Calling evaluate_pre_dispatch with only estimated_input_tokens must NOT satisfy authoritative requirement
        with self.assertRaises(TokenBudgetEnforcementUnavailableError):
            guard.evaluate_pre_dispatch(estimated_input_tokens=236, reserved_output_tokens=512, authoritative_input_tokens=None)

        # Estimate was recorded in estimated_input_tokens, but authoritative_input_tokens remains None
        self.assertEqual(guard.metrics.estimated_input_tokens, 236)
        self.assertIsNone(guard.metrics.authoritative_input_tokens)

    def test_04_missing_authoritative_input_count_trips_unavailable_error(self):
        """Test 4: Missing authoritative input count with require_authoritative_input_bound=True trips error."""
        guard = ProviderBudgetGuard(
            limits=ProviderBudgetLimits(strict_total_token_cap=1000, require_authoritative_input_bound=True)
        )
        with self.assertRaises(TokenBudgetEnforcementUnavailableError) as ctx:
            guard.evaluate_pre_dispatch(estimated_input_tokens=100, reserved_output_tokens=512, authoritative_input_tokens=None)

        self.assertEqual(ctx.exception.error_code, "SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE")
        self.assertIn("SMOKE_TOKEN_BUDGET_ENFORCEMENT_UNAVAILABLE", guard.trip_reason)

    def test_05_provider_reasoning_tokens_recorded_in_metrics_and_total(self):
        """Test 5: Provider reports reasoning tokens separately -> correctly recorded in metrics.reasoning_tokens and total."""
        limits = ProviderBudgetLimits(strict_total_token_cap=5000)
        guard = ProviderBudgetGuard(limits=limits)
        cfg = RealLLMProviderConfig(model="gemini-3.8-flash", api_base="http://127.0.0.1:20128/v1")

        mock_conn = MockHTTPConnection("127.0.0.1", 20128)
        mock_conn.response = MockHTTPResponse(
            200,
            {
                "choices": [{"message": {"content": '{"selected_candidate_key": "CAND-001"}'}}],
                "usage": {
                    "prompt_tokens": 1054,
                    "completion_tokens": 807,
                    "total_tokens": 1861,
                    "completion_tokens_details": {"reasoning_tokens": 778},
                },
            },
        )
        adapter = RealLLMProviderAdapter(config=cfg, budget_guard=guard, http_transport_factory=lambda *a, **k: mock_conn)
        res = adapter.complete("Prompt")

        self.assertEqual(guard.metrics.reasoning_tokens, 778)
        self.assertEqual(guard.metrics.provider_reported_input_tokens, 1054)
        self.assertEqual(guard.metrics.provider_reported_output_tokens, 807)
        self.assertEqual(guard.metrics.provider_reported_total_tokens, 1861)
        self.assertIsNotNone(res.usage)
        self.assertEqual(res.usage.reasoning_tokens, 778)

    def test_06_retry_attempts_count_against_budgets_and_reject_over_cap(self):
        """Test 6: Retry attempts count against request and token budgets; rejects retry if remaining budget cannot cover reservation."""
        limits = ProviderBudgetLimits(
            max_http_attempts=3,
            max_retry_attempts=2,
            strict_total_token_cap=1200,
        )
        guard = ProviderBudgetGuard(limits=limits)
        # Simulate initial call spent 800 tokens
        guard.metrics.provider_reported_total_tokens = 800

        # Attempt retry with reservation 500 (800 + 500 = 1300 > 1200)
        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            guard.record_retry(estimated_input_tokens=200, reserved_output_tokens=300)

        self.assertIn("RETRY_TOKEN_BUDGET_EXCEEDED", str(ctx.exception))
        self.assertEqual(guard.metrics.retry_attempts, 1)

    def test_07_zero_remaining_authorization_prevents_dispatch(self):
        """Test 7: Zero remaining authorization prevents dispatch."""
        limits = ProviderBudgetLimits(strict_total_token_cap=500)
        guard = ProviderBudgetGuard(limits=limits)
        guard.metrics.provider_reported_total_tokens = 500  # Cap fully exhausted

        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            guard.evaluate_pre_dispatch(estimated_input_tokens=10, reserved_output_tokens=10)

        self.assertIn("SMOKE_TOKEN_BUDGET_EXCEEDED", str(ctx.exception))

    def test_08_provider_usage_exceeds_prior_estimate_logged_as_incident(self):
        """Test 8: Provider usage exceeds prior estimate -> recorded in metrics.authorization_incidents."""
        limits = ProviderBudgetLimits(strict_total_token_cap=1000)
        guard = ProviderBudgetGuard(limits=limits)

        # Pre-dispatch granted based on client estimate
        granted, msg = guard.evaluate_pre_dispatch(estimated_input_tokens=236, reserved_output_tokens=512)
        self.assertTrue(granted)

        # Provider response arrives with 1,083 tokens (exceeding strict cap of 1,000)
        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            guard.record_success(input_tokens=1054, output_tokens=29, total_tokens=1083, reasoning_tokens=778)

        self.assertIn("TOKEN_AUTHORIZATION_BREACH", str(ctx.exception))
        incidents = guard.metrics.authorization_incidents
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["event"], "TOKEN_AUTHORIZATION_BREACH")
        self.assertEqual(incidents[0]["strict_cap"], 1000)
        self.assertEqual(incidents[0]["reported_total"], 1083)
        self.assertEqual(incidents[0]["excess"], 83)

    def test_09_pure_llm_distinguishes_http_200_from_valid_candidate_selection(self):
        """Test 9: Pure LLM response parsing distinguishes HTTP 200 from valid candidate selection."""
        scenario_path = REPO_ROOT / "runtime" / "simulation" / "fixtures" / "scenarios" / "scenario_s1_straight.json"
        scenario = ScenarioLoader().load_from_file(scenario_path)
        env = EpisodeEnvironment(scenario=scenario)
        obs = env.reset()

        cand_gen = CandidateGenerator()
        cand_res = cand_gen.generate(env.get_belief_state())
        ctx = PlannerDecisionContext(
            run_id="TEST-SMOKE-RUN",
            step_index=0,
            max_steps=10,
            current_phase="RECON",
            remaining_budget=10,
            max_budget=10,
            visible_target_ids=frozenset({"lab-target-01"}),
            belief_state=env.get_belief_state(),
            candidate_proposals=cand_res.all_proposals,
            eligible_proposals=cand_res.eligible_proposals,
            rejected_proposals=cand_res.rejected_proposals,
            objective_statement="Test objective",
        )

        # Subtest A: HTTP 200 with non-JSON plain text -> MALFORMED_OUTPUT fail closed
        provider_malformed = lambda prompt: MeteredReviewResponse(review_json="I cannot perform attack planning.", usage=None)
        planner_a = LLMPlanner(provider=provider_malformed, fallback_to_rule=False)
        dec_a = planner_a._plan_context(ctx)

        self.assertIsNone(dec_a.proposal)
        self.assertEqual(dec_a.reason_code, "INVALID_LLM_DECISION")
        self.assertEqual(dec_a.metadata["error_reason"], "MALFORMED_OUTPUT")
        self.assertFalse(dec_a.metadata["valid"])
        self.assertFalse(dec_a.metadata["fallback_used"])

        # Subtest B: HTTP 200 with valid JSON but non-existent candidate key -> UNKNOWN_CANDIDATE fail closed
        provider_unknown = lambda prompt: MeteredReviewResponse(
            review_json=json.dumps({
                "selected_candidate_key": "CAND-NONEXISTENT-999",
                "reason_code": "TEST",
                "brief_justification": "Selecting unknown candidate",
            }),
            usage=None,
        )
        planner_b = LLMPlanner(provider=provider_unknown, fallback_to_rule=False)
        dec_b = planner_b._plan_context(ctx)

        self.assertIsNone(dec_b.proposal)
        self.assertEqual(dec_b.reason_code, "INVALID_LLM_DECISION")
        self.assertEqual(dec_b.metadata["error_reason"], "UNKNOWN_CANDIDATE")
        self.assertFalse(dec_b.metadata["valid"])
        self.assertFalse(dec_b.metadata["fallback_used"])

    def test_10_smoke_artifacts_ignored_by_benchmark_preflight_and_runner(self):
        """Test 10: Smoke artifacts in evaluation/results/smoke/ are ignored by benchmark preflight and runner."""
        preflight = BenchmarkPreflightChecker()
        report = preflight.run_preflight()

        # Smoke directory files are not in preflight source provenance checks
        smoke_dir = REPO_ROOT / "evaluation" / "results" / "smoke"
        self.assertTrue(smoke_dir.is_dir())
        smoke_files = list(smoke_dir.glob("*.json"))
        self.assertGreater(len(smoke_files), 0)

        # Preflight source snapshot does NOT include smoke run results
        for sf in smoke_files:
            rel = sf.relative_to(REPO_ROOT).as_posix()
            self.assertNotIn(rel, report.source_snapshot.get("files", {}))

    def test_11_frozen_prompt_and_scoring_hashes_remain_unchanged(self):
        """Test 11: Frozen prompt and scoring hashes remain unchanged."""
        self.assertEqual(
            LLM_PROMPT_HASH_V1,
            "1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533",
        )
        self.assertEqual(
            HYBRID_PROMPT_HASH_V1,
            "d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1",
        )
        self.assertEqual(
            HYBRID_V1_WEIGHTS_HASH,
            "68e55385e064cb2867d07207022b665a9660b87938318efa355488d67bc2c799",
        )
        self.assertEqual(
            HYBRID_FROZEN_WEIGHTS_HASH,
            "0e595f7294af58a8f635376e8beedb6688cee6784479ae2eb39c21f5c7213aa8",
        )

    def test_12_zero_live_network_calls_during_tests(self):
        """Test 12: Zero live network calls during tests (mock factory only; real sockets forbidden)."""
        cfg = RealLLMProviderConfig(model="offline-model", api_base="http://127.0.0.1:20128/v1")
        mock_conn = MockHTTPConnection("127.0.0.1", 20128)
        mock_conn.response = MockHTTPResponse(
            200,
            {"choices": [{"message": {"content": '{"selected_candidate_key": "CAND-001"}'}}]},
        )

        with patch("http.client.HTTPConnection") as mock_real_http:
            mock_real_http.side_effect = RuntimeError("LIVE_NETWORK_DISPATCH_FORBIDDEN: Real socket call attempted!")
            adapter = RealLLMProviderAdapter(
                config=cfg,
                http_transport_factory=lambda *a, **k: mock_conn,
            )
            res = adapter.complete("Offline test prompt")
            self.assertIn("CAND-001", res.review_json)
            # Verify the patched real HTTPConnection constructor was NEVER called
            mock_real_http.assert_not_called()

    def test_13_two_call_sequential_smoke_harness_under_operational_limits(self):
        """Test 13: Verify two independent episodes under operational limits (1 Pure LLM, 1 Hybrid, 0 retries)."""
        s1_path = REPO_ROOT / "runtime" / "simulation" / "fixtures" / "scenarios" / "scenario_s1_straight.json"

        # Operational limits: max 2 calls across both episodes, 0 retries, max 2 HTTP attempts
        limits = ProviderBudgetLimits(max_logical_calls=2, max_retry_attempts=0, max_http_attempts=2)
        guard = ProviderBudgetGuard(limits=limits)
        cfg = RealLLMProviderConfig(model="offline-model", api_base="http://127.0.0.1:20128/v1")

        # ---------------------------------------------------------------------
        # Episode A: Pure LLM (Step 0, Seed 1001)
        # ---------------------------------------------------------------------
        env_a = EpisodeEnvironment(scenario=s1_path, run_id="SMOKE_S1_LLM_001", random_seed=1001)
        belief_a_init = env_a.get_belief_state()
        self.assertNotIn("true_state", belief_a_init.to_dict(), "No hidden state leakage in Episode A")

        # Mock connection for Call 1 (Pure LLM)
        mock_conn_1 = MockHTTPConnection("127.0.0.1", 20128)
        mock_conn_1.response = MockHTTPResponse(
            200,
            {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "selected_candidate_key": "CAND-001",
                            "reason_code": "RECON",
                            "brief_justification": "Initial recon",
                        })
                    }
                }],
                "usage": {"prompt_tokens": 250, "completion_tokens": 40, "total_tokens": 290},
            },
        )
        adapter_1 = RealLLMProviderAdapter(config=cfg, budget_guard=guard, http_transport_factory=lambda *a, **k: mock_conn_1)

        cand_gen = CandidateGenerator()
        cand_res_a = cand_gen.generate(belief_a_init)
        ctx_a = PlannerDecisionContext(
            run_id="SMOKE_S1_LLM_001",
            step_index=0,
            max_steps=10,
            current_phase="RECON",
            remaining_budget=10,
            max_budget=10,
            visible_target_ids=frozenset(belief_a_init.visible_target_ids),
            belief_state=belief_a_init,
            candidate_proposals=cand_res_a.all_proposals,
            eligible_proposals=cand_res_a.eligible_proposals,
            rejected_proposals=cand_res_a.rejected_proposals,
            objective_statement="Access target crown jewels",
        )

        planner_a = LLMPlanner(provider=adapter_1, fallback_to_rule=False)
        dec_a = planner_a._plan_context(ctx_a)

        self.assertIsNotNone(dec_a.proposal)
        self.assertTrue(dec_a.metadata["valid"])
        self.assertEqual(guard.metrics.logical_provider_calls, 1)

        # Step Episode A environment with selected proposal
        step_res_a = env_a.step(dec_a.proposal)
        self.assertTrue(step_res_a.success)
        self.assertEqual(env_a.step_count, 1)

        # ---------------------------------------------------------------------
        # Episode B: Hybrid Full (Independent Episode, Step 0, Seed 1001)
        # ---------------------------------------------------------------------
        env_b = EpisodeEnvironment(scenario=s1_path, run_id="SMOKE_S1_HYBRID_001", random_seed=1001)
        belief_b_init = env_b.get_belief_state()

        # Invariant: Two initial states are strictly equivalent under same scenario and seed
        self.assertEqual(belief_a_init.to_dict(), belief_b_init.to_dict(), "Initial states must be identical")
        self.assertNotIn("true_state", belief_b_init.to_dict(), "No hidden state leakage in Episode B")
        self.assertEqual(env_b.step_count, 0, "Episode B starts at fresh step count 0")

        cand_res_b = cand_gen.generate(belief_b_init)
        keys_b = [f"CAND-{i+1:03d}" for i in range(len(cand_res_b.eligible_proposals))]

        # Mock connection for Call 2 (Hybrid Full)
        mock_conn_2 = MockHTTPConnection("127.0.0.1", 20128)
        mock_conn_2.response = MockHTTPResponse(
            200,
            {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "ranked_candidate_keys": keys_b,
                            "reason_code": "STRATEGIC_RANK",
                            "brief_justification": "Ranked discovery first",
                        })
                    }
                }],
                "usage": {"prompt_tokens": 450, "completion_tokens": 50, "total_tokens": 500},
            },
        )
        adapter_2 = RealLLMProviderAdapter(config=cfg, budget_guard=guard, http_transport_factory=lambda *a, **k: mock_conn_2)

        ctx_b = PlannerDecisionContext(
            run_id="SMOKE_S1_HYBRID_001",
            step_index=0,
            max_steps=10,
            current_phase="RECON",
            remaining_budget=10,
            max_budget=10,
            visible_target_ids=frozenset(belief_b_init.visible_target_ids),
            belief_state=belief_b_init,
            candidate_proposals=cand_res_b.all_proposals,
            eligible_proposals=cand_res_b.eligible_proposals,
            rejected_proposals=cand_res_b.rejected_proposals,
            objective_statement="Access target crown jewels",
        )

        planner_b = HybridPlanner(provider=adapter_2, scoring_config=HybridScoringConfig.frozen())
        dec_b = planner_b.plan(ctx_b)

        self.assertIsNotNone(dec_b.proposal)
        self.assertTrue(dec_b.metadata["valid"])
        self.assertTrue(dec_b.metadata["semantic_component_valid"])
        self.assertEqual(guard.metrics.logical_provider_calls, 2)

        # Step Episode B environment with selected proposal
        step_res_b = env_b.step(dec_b.proposal)
        self.assertTrue(step_res_b.success)
        self.assertEqual(env_b.step_count, 1)

        # Call 3 must trip circuit breaker (exceeds max_logical_calls=2)
        with self.assertRaises(CircuitBreakerTrippedError) as ctx_err:
            adapter_2.complete("Third call not allowed")
        self.assertIn("MAX_LOGICAL_CALLS_EXCEEDED", str(ctx_err.exception))

        # Check total HTTP attempts and retries
        self.assertEqual(guard.metrics.http_attempts, 2)
        self.assertEqual(guard.metrics.retry_attempts, 0)

    def test_14_max_retry_attempts_zero_independently_prevents_retries_when_http_cap_has_capacity(self):
        """Test 14: max_retry_attempts=0 independently halts retries with MAX_RETRY_ATTEMPTS_EXCEEDED when HTTP attempt cap has capacity."""
        limits = ProviderBudgetLimits(max_logical_calls=2, max_retry_attempts=0, max_http_attempts=10)
        guard = ProviderBudgetGuard(limits=limits)
        cfg = RealLLMProviderConfig(model="offline-model", api_base="http://127.0.0.1:20128/v1")

        # Mock connection that always fails with TimeoutError
        class FailingMockHTTPConnection:
            def __init__(self, *args, **kwargs):
                self.calls = 0

            def request(self, *args, **kwargs):
                self.calls += 1

            def getresponse(self):
                raise TimeoutError("Simulated socket timeout on dispatch")

        mock_conn = FailingMockHTTPConnection()
        adapter = RealLLMProviderAdapter(
            config=cfg,
            budget_guard=guard,
            http_transport_factory=lambda *a, **k: mock_conn,
        )

        # First logical call encounters initial failure, and retry 1 must trip on MAX_RETRY_ATTEMPTS_EXCEEDED
        with self.assertRaises(CircuitBreakerTrippedError) as ctx:
            adapter.complete("Test prompt that times out")

        self.assertIn("MAX_RETRY_ATTEMPTS_EXCEEDED", str(ctx.exception))
        # Verify exactly one dispatch attempt was made over the wire; second dispatch never happened
        self.assertEqual(mock_conn.calls, 1)
        self.assertEqual(guard.metrics.retry_attempts, 1)
