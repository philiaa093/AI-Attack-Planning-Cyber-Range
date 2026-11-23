"""Reproducible Benchmark Runner and Episode Coordinator (RT-07A).

Coordinates planner-neutral comparative benchmark evaluation:
1. Loads the pre-registered 420-episode experiment matrix (12 held-out x 5 paired replicates x 7 configs).
2. Validates held-out scenario byte digests and contracts before any access.
3. Enforces Zero-Knowledge Fog-of-War and information boundary isolation.
4. Instantiates planner configurations:
   - RULE (RuleBasedPlanner)
   - LLM (LLMPlanner, fallback_to_rule=False)
   - HYBRID_FULL (HybridPlanner with frozen weights)
   - Diagnostic ablations: HYBRID_NO_NOISE, HYBRID_NO_PENALTIES, HYBRID_SEMANTIC_ONLY, HYBRID_SYMBOLIC_ONLY
5. Executes episodes using the common canonical PlannerEpisodeRunner(env, planner).
6. Fail-closed error handling (distinguishes OBJECTIVE_ACHIEVED, PLANNER_STOP, MAX_STEPS,
   BUDGET_EXHAUSTED, CONTAINED, SAFETY_KILL_SWITCH, INVALID_LLM_DECISION, PROVIDER_ERROR, etc.).
7. Computes frozen primary (GCR, DERR, CCR) and secondary metrics via benchmark_metrics.py.
8. Supports idempotent checkpointing, resume, --dry-run (S1-S4 only), and --validate-only.

HARD INVARIANTS:
- RT-07A is strictly PREFLIGHT & DRY-RUN. The 420 held-out comparative episodes are BLOCKED.
- Held-out benchmark is strictly simulator-based POMDP; zero live Docker dispatch.
- Fake providers permitted ONLY for development dry-runs.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

_MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = _MODULE_PATH.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from actions.catalog.action_registry import (
    CANONICAL_BENCHMARK_ACTION_IDS,
    get_canonical_action_id,
)
from evaluation.experiments.benchmark_preflight import (
    BENCHMARK_MATRIX_PATH,
    HELD_OUT_DIR,
    HELD_OUT_MANIFEST_PATH,
    PROTOCOL_FREEZE_PATH,
    SEED_MANIFEST_PATH,
    BenchmarkPreflightChecker,
    PreflightReport,
)
from evaluation.experiments.source_snapshot import (
    FROZEN_PROTOCOL_ID,
    PROPOSED_PROTOCOL_ID_V2,
    validate_protocol_version,
    HYBRID_FROZEN_WEIGHTS_HASH,
    HYBRID_PROMPT_HASH_V1,
    HYBRID_V1_WEIGHTS_HASH,
    LLM_PROMPT_HASH_V1,
    build_source_snapshot,
    compute_file_sha256,
)
from evaluation.metrics.benchmark_metrics import (
    EpisodeTelemetry,
    compute_clean_control_restraint,
    compute_dead_end_recovery_rate,
    compute_goal_completion_rate,
    compute_invalid_decision_rate,
    compute_operational_noise_cost,
    compute_planning_latency,
    compute_replanning_success_rate,
    compute_steps_to_goal,
    compute_token_and_cost_metrics,
)
from runtime.orchestration.planner_runner import EpisodeRunResult, PlannerEpisodeRunner
from runtime.planners.candidate_generator import CandidateGenerator
from runtime.planners.hybrid_planner import (
    FakeHybridRankingProvider,
    HybridPlanner,
    HYBRID_PLANNER_PROMPT_V1,
    HYBRID_PLANNER_PROMPT_V2,
    HYBRID_OUTPUT_SCHEMA_V2,
)
from runtime.planners.llm_planner import (
    ATTACK_PLANNER_SYSTEM_PROMPT,
    FakeAttackPlannerProvider,
    LLMPlanner,
    LLM_ATTACK_PLANNER_PROMPT_V1,
    LLM_CONTEXT_SERIALIZER_VERSION,
    LLM_CONTEXT_SERIALIZER_V2,
    LLM_OUTPUT_SCHEMA_VERSION,
)
from runtime.planners.real_provider_adapter import (
    CircuitBreakerTrippedError,
    RealLLMProviderAdapter,
    RealLLMProviderConfig,
)
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.planners.symbolic_scorer import HybridScoringConfig
from runtime.simulation.environment import EpisodeEnvironment
from runtime.simulation.loader import ScenarioLoader
from runtime.simulation.models.step_result import TerminationReason

logger = logging.getLogger(__name__)

RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
DEV_SCENARIOS_DIR = REPO_ROOT / "runtime" / "simulation" / "fixtures" / "scenarios"

DEV_SCENARIOS: dict[str, str] = {
    "S1": "scenario_s1_straight.json",
    "S2": "scenario_s2_decoy.json",
    "S3": "scenario_s3_blocked.json",
    "S4": "scenario_s4_clean.json",
    "SCN-SIM-001": "scenario_s1_straight.json",
    "SCN-SIM-002": "scenario_s2_decoy.json",
    "SCN-SIM-003": "scenario_s3_blocked.json",
    "SCN-SIM-004": "scenario_s4_clean.json",
}


class BenchmarkExecutionError(RuntimeError):
    """Raised when benchmark execution constraints or safety guards are violated."""


class BenchmarkAuthorizationError(BenchmarkExecutionError):
    """Raised when RT-07B execution authorization is missing or invalid."""


@dataclasses.dataclass(frozen=True)
class BenchmarkEpisodeResult:
    """Immutable result record for a single benchmark episode (Section 13 schema)."""

    experiment_id: str
    protocol_version: str
    source_commit: str
    source_tree_digest: str
    scenario_id: str
    scenario_sha256: str
    replicate_id: str
    simulator_seed: int
    requested_provider_seed: int
    actual_provider_seed_supported: bool
    planner_id: str
    planner_version: str
    model_provider_id: str
    prompt_hash: str
    weights_hash: str
    start_time_utc: str
    finish_time_utc: str
    episode_status: str  # "COMPLETED", "FAILED", "ERROR"
    termination_reason: str
    objective_completed: bool
    is_clean_control: bool
    clean_restraint_success: bool
    encountered_dead_end: bool
    recovered_from_dead_end: bool
    recovery_opportunity_exists: bool  # strictly evaluator-side
    steps_executed: int
    canonical_action_sequence: tuple[str, ...]
    total_operational_noise: float
    invalid_decisions: int
    observable_failed_progressions: int
    provider_errors: int
    retry_count: int
    symbolic_fallback_count: int
    input_tokens: int
    output_tokens: int
    planning_latencies_ms: tuple[float, ...]
    error_details: str = ""
    prompt_provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "experiment_id": self.experiment_id,
            "protocol_version": self.protocol_version,
            "source_commit": self.source_commit,
            "source_tree_digest": self.source_tree_digest,
            "scenario_id": self.scenario_id,
            "scenario_sha256": self.scenario_sha256,
            "replicate_id": self.replicate_id,
            "simulator_seed": self.simulator_seed,
            "requested_provider_seed": self.requested_provider_seed,
            "actual_provider_seed_supported": self.actual_provider_seed_supported,
            "planner_id": self.planner_id,
            "planner_version": self.planner_version,
            "model_provider_id": self.model_provider_id,
            "prompt_hash": self.prompt_hash,
            "weights_hash": self.weights_hash,
            "start_time_utc": self.start_time_utc,
            "finish_time_utc": self.finish_time_utc,
            "episode_status": self.episode_status,
            "termination_reason": self.termination_reason,
            "objective_completed": self.objective_completed,
            "is_clean_control": self.is_clean_control,
            "clean_restraint_success": self.clean_restraint_success,
            "encountered_dead_end": self.encountered_dead_end,
            "recovered_from_dead_end": self.recovered_from_dead_end,
            "recovery_opportunity_exists": self.recovery_opportunity_exists,
            "steps_executed": self.steps_executed,
            "canonical_action_sequence": list(self.canonical_action_sequence),
            "total_operational_noise": round(self.total_operational_noise, 4),
            "invalid_decisions": self.invalid_decisions,
            "observable_failed_progressions": self.observable_failed_progressions,
            "provider_errors": self.provider_errors,
            "retry_count": self.retry_count,
            "symbolic_fallback_count": self.symbolic_fallback_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "planning_latencies_ms": [round(lat, 2) for lat in self.planning_latencies_ms],
            "error_details": self.error_details,
        }

        if self.prompt_provenance is not None:
            payload["prompt_provenance"] = self.prompt_provenance
        return payload

    def to_telemetry(self) -> EpisodeTelemetry:
        """Convert into benchmark_metrics.EpisodeTelemetry for primary/secondary metric computation."""
        return EpisodeTelemetry(
            episode_id=self.experiment_id,
            scenario_id=self.scenario_id,
            is_clean_control=self.is_clean_control,
            objective_completed=self.objective_completed,
            terminated_cleanly=self.termination_reason in ("OBJECTIVE_ACHIEVED", "PLANNER_STOP"),
            budget_exhausted=self.termination_reason == "BUDGET_EXHAUSTED",
            containment_tripped=self.termination_reason == "CONTAINED",
            step_count=self.steps_executed,
            operational_noise_cost=self.total_operational_noise,
            total_decisions=self.steps_executed,
            invalid_decisions=self.invalid_decisions,
            replanning_events=self.observable_failed_progressions,
            successful_replans=1 if self.recovered_from_dead_end else 0,
            encountered_dead_end=self.encountered_dead_end,
            recovered_from_dead_end=self.recovered_from_dead_end,
            planning_latencies=list(self.planning_latencies_ms),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            estimated_cost_usd=0.0,
            experiment_id=self.experiment_id,
            replicate_id=self.replicate_id,
            simulator_seed=self.simulator_seed,
            requested_provider_seed=self.requested_provider_seed,
            llm_provider_errors=self.provider_errors,
            llm_retries=self.retry_count,
            hybrid_symbolic_only_fallback_count=self.symbolic_fallback_count,
        )


class BenchmarkRunner:
    """Thin, neutral benchmark execution and checkpointing coordinator."""

    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        results_dir: Path = RESULTS_DIR,
        provider: Any = None,
        provider_config: RealLLMProviderConfig | None = None,
        require_real_provider: bool = False,
        *,
        protocol_version: str = FROZEN_PROTOCOL_ID,
    ) -> None:
        self.protocol_version = validate_protocol_version(protocol_version)
        self.repo_root = repo_root
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.require_real_provider = require_real_provider
        self.provider_config = provider_config

        # Lock provider configuration across all episodes
        if provider is not None:
            self.provider = provider
        elif provider_config is not None:
            self.provider = RealLLMProviderAdapter(config=provider_config)
        else:
            self.provider = None

        self.preflight_checker = BenchmarkPreflightChecker(repo_root=self.repo_root, protocol_version=self.protocol_version)
        self.loader = ScenarioLoader()
        self._source_snapshot = build_source_snapshot(self.repo_root, protocol_version=self.protocol_version)

    def load_pre_registered_matrix(self) -> list[dict[str, Any]]:
        """Load the frozen 420 planned episode matrix; reject missing/duplicate IDs."""
        if self.protocol_version == PROPOSED_PROTOCOL_ID_V2:
            raise BenchmarkAuthorizationError("V2_PROTOCOL_NOT_SEALED: V2 matrix scheduling is not authorized.")
        if not BENCHMARK_MATRIX_PATH.exists():
            raise FileNotFoundError(f"Missing benchmark matrix: {BENCHMARK_MATRIX_PATH}")

        matrix = json.loads(BENCHMARK_MATRIX_PATH.read_text(encoding="utf-8"))
        episodes = matrix.get("planned_episodes", [])
        if len(episodes) != 420:
            raise ValueError(f"Expected exactly 420 planned episodes, found {len(episodes)}")

        seen_ids: set[str] = set()
        for ep in episodes:
            exp_id = ep.get("experiment_id")
            if not exp_id:
                raise ValueError(f"Planned episode missing experiment_id: {ep}")
            if exp_id in seen_ids:
                raise ValueError(f"Duplicate experiment_id detected in matrix: {exp_id}")
            seen_ids.add(exp_id)

        return episodes

    def instantiate_planner(
        self,
        planner_id: str,
        provider: Any = None,
    ) -> tuple[Any, str, str, str]:
        """Instantiate canonical planner baseline or diagnostic ablation.

        Returns:
            (planner_instance, version_string, prompt_hash, weights_hash)
        """
        active_provider = provider if provider is not None else self.provider
        hybrid_prompt_version = (
            HYBRID_PLANNER_PROMPT_V2 if self.protocol_version == PROPOSED_PROTOCOL_ID_V2
            else HYBRID_PLANNER_PROMPT_V1
        )

        if planner_id == "RULE":
            planner = RuleBasedPlanner()
            return planner, "RULE_POLICY_V1", "N/A", "N/A"

        elif planner_id == "LLM":
            planner = LLMPlanner(
                provider=active_provider or FakeAttackPlannerProvider(),
                fallback_to_rule=False,  # strictly fail closed
            )
            return planner, "LLM_ATTACK_PLANNER_PROMPT_V1", LLM_PROMPT_HASH_V1, "N/A"

        elif planner_id == "HYBRID_FULL":
            cfg = HybridScoringConfig.frozen()
            planner = HybridPlanner(
                provider=active_provider or FakeHybridRankingProvider(),
                scoring_config=cfg,
                prompt_version=hybrid_prompt_version,
            )
            return planner, "HYBRID_SCORING_V1_FROZEN", HYBRID_PROMPT_HASH_V1, cfg.weights_hash()

        elif planner_id == "HYBRID_NO_NOISE":
            cfg = HybridScoringConfig.without_noise()
            planner = HybridPlanner(
                provider=active_provider or FakeHybridRankingProvider(),
                scoring_config=cfg,
                prompt_version=hybrid_prompt_version,
            )
            return planner, "HYBRID_NO_NOISE", HYBRID_PROMPT_HASH_V1, cfg.weights_hash()

        elif planner_id == "HYBRID_NO_PENALTIES":
            cfg = HybridScoringConfig.without_penalties()
            planner = HybridPlanner(
                provider=active_provider or FakeHybridRankingProvider(),
                scoring_config=cfg,
                prompt_version=hybrid_prompt_version,
            )
            return planner, "HYBRID_NO_PENALTIES", HYBRID_PROMPT_HASH_V1, cfg.weights_hash()

        elif planner_id == "HYBRID_SEMANTIC_ONLY":
            cfg = HybridScoringConfig.semantic_only()
            planner = HybridPlanner(
                provider=active_provider or FakeHybridRankingProvider(),
                scoring_config=cfg,
                prompt_version=hybrid_prompt_version,
            )
            return planner, "HYBRID_SEMANTIC_ONLY", HYBRID_PROMPT_HASH_V1, cfg.weights_hash()

        elif planner_id == "HYBRID_SYMBOLIC_ONLY":
            cfg = HybridScoringConfig.symbolic_only()
            # Symbolic only has w_sem = 0.0; requires no LLM provider
            planner = HybridPlanner(
                provider=None,
                scoring_config=cfg,
                prompt_version=hybrid_prompt_version,
            )
            return planner, "HYBRID_SYMBOLIC_ONLY", "N/A", cfg.weights_hash()

        else:
            raise ValueError(f"Unknown planner_id: '{planner_id}'")

    def run_episode(
        self,
        experiment_spec: Mapping[str, Any],
        scenario_file_path: Path,
        expected_scenario_sha256: str | None = None,
        custom_provider: Any = None,
    ) -> BenchmarkEpisodeResult:
        """Run a single episode under strict Fog-of-War and record the result."""
        spec_protocol = experiment_spec.get("protocol_version")
        if spec_protocol is not None and spec_protocol != self.protocol_version:
            raise BenchmarkAuthorizationError("Experiment protocol identity mismatch")
        if self.protocol_version == PROPOSED_PROTOCOL_ID_V2:
            # Fail before file reads, simulator initialization or provider dispatch.
            allowed_paths = {(DEV_SCENARIOS_DIR / name).resolve() for name in DEV_SCENARIOS.values()}
            if Path(scenario_file_path).resolve() not in allowed_paths:
                raise BenchmarkAuthorizationError("V2_PROTOCOL_NOT_SEALED: Only canonical S1-S4 development files are allowed.")
            exp_id_value = experiment_spec.get("experiment_id")
            if spec_protocol != self.protocol_version or not isinstance(exp_id_value, str) or not re.fullmatch(r"DEV_V2_[A-Za-z0-9_-]+", exp_id_value):
                raise BenchmarkAuthorizationError("V2 development result requires explicit V2 protocol and DEV_V2_ identity")
            scenario_id_value = experiment_spec.get("scenario_id")
            matching_keys = {
                key for key, name in DEV_SCENARIOS.items()
                if (DEV_SCENARIOS_DIR / name).resolve() == Path(scenario_file_path).resolve()
            }
            allowed_ids = matching_keys | {f"SCN-DEV-{key}" for key in matching_keys}
            if not isinstance(scenario_id_value, str) or scenario_id_value not in allowed_ids:
                raise BenchmarkAuthorizationError("V2 development scenario identity does not match canonical file")
        t_start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        exp_id = str(experiment_spec["experiment_id"])
        planner_id = str(experiment_spec["planner_id"])
        scenario_id = str(experiment_spec["scenario_id"])
        replicate_id = str(experiment_spec.get("replicate_id", "R01"))
        sim_seed = int(experiment_spec.get("simulator_seed", 1001))
        prov_seed = int(experiment_spec.get("requested_provider_seed", 42))

        # 1. Verify scenario file integrity before reading
        if not scenario_file_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_file_path}")

        actual_sha = compute_file_sha256(scenario_file_path)
        if expected_scenario_sha256 and actual_sha != expected_scenario_sha256:
            raise ValueError(
                f"Scenario SHA-256 mismatch for {scenario_file_path.name}: "
                f"expected {expected_scenario_sha256}, got {actual_sha}"
            )

        # 2. Fresh, isolated EpisodeEnvironment
        env = EpisodeEnvironment(
            scenario=scenario_file_path,
            run_id=exp_id,
            random_seed=sim_seed,
            max_steps=50,
            max_budget=20,
        )

        # 3. Instantiate Planner
        planner, p_ver, p_hash, w_hash = self.instantiate_planner(
            planner_id=planner_id,
            provider=custom_provider or self.provider,
        )

        episode_provider = getattr(planner, "_provider", None) or getattr(planner, "provider", None)
        request_history_start = len(getattr(episode_provider, "request_history", []))
        call_history_start = len(getattr(episode_provider, "call_history", []))

        # 4. Execute using standard PlannerEpisodeRunner
        runner = PlannerEpisodeRunner(env=env, planner=planner)

        action_seq: list[str] = []
        latencies: list[float] = []
        failed_progressions = 0
        error_details = ""
        encountered_dead_end = False
        recovered_from_dead_end = False

        try:
            run_res: EpisodeRunResult = runner.run()

            # Process decision traces
            for tr in run_res.traces:
                latencies.append(tr.planning_latency_ms)
                if tr.chosen_proposal:
                    act_id = tr.chosen_proposal.get("action_id", "")
                    canon_act = get_canonical_action_id(act_id)
                    action_seq.append(canon_act)

                # Check if previous outcome was an observable progression failure
                if tr.observable_prior_outcome and not tr.observable_prior_outcome.get("success", True):
                    failed_progressions += 1
                    encountered_dead_end = True

            # Determine authoritative objective status
            # For attack scenarios, authoritative objective achievement is derived from TrueState / belief
            is_clean = getattr(env.scenario, "is_clean_control", False)
            obj_achieved = env.executor.is_objective_achieved()

            # Evaluator-only dead-end recovery analysis
            eval_view = run_res.evaluator_view
            recovery_opp_exists = False
            if eval_view is not None:
                # Evaluator view knows if recovery opportunity existed
                recovery_opp_exists = bool(getattr(eval_view, "recovery_opportunity_exists", False))

            if encountered_dead_end and obj_achieved:
                recovered_from_dead_end = True

            # Clean control restraint success determination
            clean_restraint_success = False
            if is_clean:
                clean_restraint_success = (
                    run_res.termination_reason == TerminationReason.PLANNER_STOP
                    and not obj_achieved
                    and run_res.traces
                )

            # Failure category mapping
            term_reason_str = run_res.termination_reason.value if run_res.termination_reason else "UNKNOWN"

            # Check if planner recorded invalid decisions or provider errors
            p_metrics = getattr(planner, "metrics", {})
            invalid_decisions = p_metrics.get("invalid_decisions", 0) + p_metrics.get("invalid_semantic_rankings", 0)
            provider_errors = p_metrics.get("provider_errors", 0)
            fallback_count = p_metrics.get("symbolic_fallback_count", 0)

            # Map planner failure if planner returned None proposal due to error
            if invalid_decisions > 0 and term_reason_str in ("UNKNOWN", "PLANNER_STOP"):
                if provider_errors > 0:
                    term_reason_str = "PROVIDER_ERROR"
                else:
                    term_reason_str = "INVALID_LLM_DECISION"

            # Compute operational noise from true state
            true_state = env.executor.get_true_state()
            total_noise = true_state.defender_state.accumulated_noise

            status = "COMPLETED"
            if term_reason_str in ("PROVIDER_ERROR", "INVALID_LLM_DECISION"):
                status = "FAILED"

        except CircuitBreakerTrippedError as exc:
            logger.error(f"Circuit breaker tripped during episode execution {exp_id}: {exc}")
            status = "FAILED"
            term_reason_str = "PROVIDER_ERROR"
            error_details = str(exc)
            obj_achieved = False
            is_clean = False
            clean_restraint_success = False
            encountered_dead_end = False
            recovered_from_dead_end = False
            recovery_opp_exists = False
            total_noise = 0.0
            invalid_decisions = 1
            provider_errors = 1
            fallback_count = 0

        except Exception as exc:
            logger.exception(f"Exception during episode execution {exp_id}: {exc}")
            status = "ERROR"
            term_reason_str = "INTERNAL_ERROR"
            error_details = str(exc)
            obj_achieved = False
            is_clean = False
            clean_restraint_success = False
            encountered_dead_end = False
            recovered_from_dead_end = False
            recovery_opp_exists = False
            total_noise = 0.0
            invalid_decisions = 1
            provider_errors = 0
            fallback_count = 0

        t_finish_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        model_prov_id = getattr(self.provider, "model_name", "standard_benchmark_provider")

        total_input_tokens = 0
        total_output_tokens = 0
        total_retries = 0

        # Extract tokens and retries from active provider and planner metrics
        active_prov = getattr(planner, "_provider", None) or getattr(planner, "provider", None) or self.provider
        if active_prov is not None:
            if hasattr(active_prov, "budget_guard") and hasattr(active_prov.budget_guard, "metrics"):
                total_input_tokens = active_prov.budget_guard.metrics.input_tokens
                total_output_tokens = active_prov.budget_guard.metrics.output_tokens
                total_retries = active_prov.budget_guard.metrics.retry_attempts
            elif hasattr(active_prov, "call_history") and active_prov.call_history:
                for entry in active_prov.call_history:
                    if isinstance(entry, Mapping):
                        tok = entry.get("tokens") or {}
                        total_input_tokens += int(tok.get("input_uncached") or tok.get("prompt_tokens") or 0)
                        total_output_tokens += int(tok.get("output_tokens") or tok.get("completion_tokens") or 0)
                        total_retries += int(entry.get("retries") or 0)

        p_metrics = getattr(planner, "metrics", {})
        total_retries = max(total_retries, p_metrics.get("retries", 0))

        prompt_provenance = None
        if self.protocol_version == PROPOSED_PROTOCOL_ID_V2:
            prompt_provenance = self._prompt_provenance(
                planner_id, p_hash, episode_provider, request_history_start, call_history_start,
            )
            if planner_id.startswith("HYBRID"):
                p_ver += ":" + HYBRID_PLANNER_PROMPT_V2

        result = BenchmarkEpisodeResult(
            experiment_id=exp_id,
            protocol_version=self.protocol_version,
            source_commit=self._source_snapshot.source_commit,
            source_tree_digest=self._source_snapshot.source_tree_digest,
            scenario_id=scenario_id,
            scenario_sha256=actual_sha,
            replicate_id=replicate_id,
            simulator_seed=sim_seed,
            requested_provider_seed=prov_seed,
            actual_provider_seed_supported=False,
            planner_id=planner_id,
            planner_version=p_ver,
            model_provider_id=model_prov_id,
            prompt_hash=p_hash,
            weights_hash=w_hash,
            start_time_utc=t_start_utc,
            finish_time_utc=t_finish_utc,
            episode_status=status,
            termination_reason=term_reason_str,
            objective_completed=obj_achieved,
            is_clean_control=is_clean,
            clean_restraint_success=clean_restraint_success,
            encountered_dead_end=encountered_dead_end,
            recovered_from_dead_end=recovered_from_dead_end,
            recovery_opportunity_exists=recovery_opp_exists,
            steps_executed=len(action_seq),
            canonical_action_sequence=tuple(action_seq),
            total_operational_noise=total_noise,
            invalid_decisions=invalid_decisions,
            observable_failed_progressions=failed_progressions,
            provider_errors=provider_errors,
            retry_count=total_retries,
            symbolic_fallback_count=fallback_count,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            planning_latencies_ms=tuple(latencies),
            error_details=error_details,
            prompt_provenance=prompt_provenance,
        )

        # Idempotent persistence to results directory
        self.save_episode_result(result)
        return result

    def _prompt_provenance(
        self, planner_id: str, system_prompt_hash: str, provider: Any,
        request_start: int, call_start: int,
    ) -> dict[str, Any]:
        is_hybrid = planner_id.startswith("HYBRID")
        uses_prompt = planner_id != "RULE" and planner_id != "HYBRID_SYMBOLIC_ONLY"
        requests = [dict(entry) for entry in getattr(provider, "request_history", [])[request_start:]]
        if not hasattr(provider, "request_history"):
            # Scripted providers retain prompt text but have no adapter wire body.
            requests = [
                {"effective_prompt_sha256": hashlib.sha256(entry.encode("utf-8")).hexdigest(),
                 "effective_request_sha256": None}
                for entry in getattr(provider, "call_history", [])[call_start:] if isinstance(entry, str)
            ]
        return {
            "prompt_version": (HYBRID_PLANNER_PROMPT_V2 if is_hybrid else LLM_ATTACK_PLANNER_PROMPT_V1) if uses_prompt else "N/A",
            "serializer_version": (LLM_CONTEXT_SERIALIZER_V2 if is_hybrid else LLM_CONTEXT_SERIALIZER_VERSION) if uses_prompt else "N/A",
            "output_schema_version": (HYBRID_OUTPUT_SCHEMA_V2 if is_hybrid else LLM_OUTPUT_SCHEMA_VERSION) if uses_prompt else "N/A",
            "system_prompt_sha256": system_prompt_hash,
            "requests": requests,
            "wire_request_hashes_available": hasattr(provider, "request_history"),
        }

    def save_episode_result(
        self,
        result: BenchmarkEpisodeResult,
        allow_overwrite_completed: bool = False,
    ) -> Path:
        """Save episode result to disk idempotently without silently overwriting completed runs."""
        out_file = self.results_dir / f"{result.experiment_id}.json"
        temp_file = self.results_dir / f"{result.experiment_id}.tmp"

        payload = result.to_dict()

        if out_file.exists():
            existing = None
            try:
                with open(out_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

            if existing is not None and existing.get("episode_status") == "COMPLETED":
                core_fields = (
                    "experiment_id",
                    "protocol_version",
                    "scenario_id",
                    "scenario_sha256",
                    "replicate_id",
                    "simulator_seed",
                    "requested_provider_seed",
                    "planner_id",
                    "planner_version",
                    "prompt_hash",
                    "weights_hash",
                    "episode_status",
                    "termination_reason",
                    "objective_completed",
                    "is_clean_control",
                    "clean_restraint_success",
                    "steps_executed",
                    "canonical_action_sequence",
                    "total_operational_noise",
                )
                if result.protocol_version == PROPOSED_PROTOCOL_ID_V2:
                    core_fields += ("prompt_provenance",)
                is_consistent = all(existing.get(k) == payload.get(k) for k in core_fields)
                if is_consistent:
                    return out_file
                if not allow_overwrite_completed:
                    raise FileExistsError(
                        f"Refusing to silently overwrite completed benchmark result at {out_file}. "
                        "Completed experimental records must remain immutable."
                    )

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        # Atomic replace
        temp_file.replace(out_file)
        return out_file

    def check_held_out_execution_authorization(
        self,
        authorize_rt07b: bool = False,
        require_real_provider: bool = True,
        is_simulator_only: bool = True,
    ) -> PreflightReport:
        """Enforces all RT-07B execution authorization guards before any held-out episode runs.

        Must satisfy:
        1. Explicit authorize_rt07b flag is True.
        2. require_real_provider is True for final LLM/Hybrid evaluation.
        3. Preflight runs and must have zero blockers (report.has_blockers == False) and all_passed == True.
        4. Protocol version must be exactly BENCHMARK_PROTOCOL_FREEZE_V1.
        5. Source snapshot must not have any missing relevant files or dirty relevant files.
        6. Simulator-only execution is strictly enforced (is_simulator_only == True).
        7. Held-out scenario manifest hash matches expected bytes.
        """
        if self.protocol_version == PROPOSED_PROTOCOL_ID_V2:
            raise BenchmarkAuthorizationError("V2_PROTOCOL_NOT_SEALED: Held-out execution is forbidden for proposed V2.")
        if not authorize_rt07b:
            raise BenchmarkAuthorizationError(
                "RT-07B comparative execution on held-out scenarios (H01-H12) is BLOCKED. "
                "Explicit separate authorization via '--authorize-rt07b' is required."
            )

        if not is_simulator_only:
            raise BenchmarkExecutionError(
                "Held-out benchmark execution is strictly simulator-based POMDP. "
                "Live Docker dispatch for held-out evaluation is strictly forbidden."
            )

        # Refuse fake/scripted or unconfigured providers for final LLM/Hybrid results
        if require_real_provider:
            if self.provider is None or isinstance(self.provider, FakeAttackPlannerProvider) or "Fake" in type(self.provider).__name__:
                raise BenchmarkExecutionError(
                    "REAL_LLM_BENCHMARK_BLOCKED: Fake/scripted providers are strictly prohibited for held-out evaluation."
                )

        report = self.preflight_checker.run_preflight(
            require_real_provider=require_real_provider,
            provider=self.provider,
        )

        if report.protocol_version != FROZEN_PROTOCOL_ID:
            raise BenchmarkExecutionError(
                f"Protocol identity mismatch: expected {FROZEN_PROTOCOL_ID}, found {report.protocol_version}"
            )

        if report.has_blockers or not report.all_passed:
            blocker_msgs = "; ".join(report.blockers)
            raise BenchmarkExecutionError(
                f"Cannot authorize held-out benchmark execution due to preflight blockers: {blocker_msgs}"
            )

        # Verify complete source provenance
        snapshot_dict = report.source_snapshot
        if snapshot_dict.get("provenance_status") not in ("CLEAN_REPRODUCIBLE", "DIRTY_NON_RELEVANT"):
            raise BenchmarkExecutionError(
                f"Source provenance must be CLEAN_REPRODUCIBLE or DIRTY_NON_RELEVANT, got {snapshot_dict.get('provenance_status')}. "
                f"Blockers: {snapshot_dict.get('blockers')}"
            )

        return report

    def run_development_dry_run(
        self,
        scenario_key: str = "S1",
        planner_id: str = "RULE",
        custom_provider: Any = None,
    ) -> BenchmarkEpisodeResult:
        """Run an engineering validation episode strictly on a development scenario (S1-S4).

        HARD INVARIANT: Held-out scenarios (H01-H12) are NEVER accessed in dry-run.
        """
        scn_filename = DEV_SCENARIOS.get(scenario_key)
        if not scn_filename:
            raise ValueError(f"Unknown development scenario '{scenario_key}'. Choose from {list(DEV_SCENARIOS.keys())}")

        scn_path = DEV_SCENARIOS_DIR / scn_filename
        scn_sha = compute_file_sha256(scn_path)

        exp_spec = {
            "experiment_id": f"DEV_V2_{planner_id}_{scenario_key}_{scn_sha[:8]}" if self.protocol_version == PROPOSED_PROTOCOL_ID_V2 else f"DEV_DRY_RUN_{planner_id}_{scenario_key}_{scn_sha[:8]}",
            "protocol_version": self.protocol_version,
            "planner_id": planner_id,
            "scenario_id": f"SCN-DEV-{scenario_key}",
            "replicate_id": "DEV_R01",
            "simulator_seed": 1001,
            "requested_provider_seed": 42,
        }

        return self.run_episode(
            experiment_spec=exp_spec,
            scenario_file_path=scn_path,
            expected_scenario_sha256=scn_sha,
            custom_provider=custom_provider,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducible Benchmark Runner & Preflight (RT-07A/RT-07A1)")
    parser.add_argument("--protocol-version", choices=(FROZEN_PROTOCOL_ID, PROPOSED_PROTOCOL_ID_V2), default=FROZEN_PROTOCOL_ID)
    parser.add_argument("--validate-only", action="store_true", help="Run preflight validation and exit")
    parser.add_argument("--dry-run", action="store_true", help="Run development validation on S1-S4 only")
    parser.add_argument("--scenario", default="S1", help="Development scenario key for dry-run (S1..S4)")
    parser.add_argument("--planner", default="RULE", help="Planner ID for dry run (RULE, LLM, HYBRID_FULL, etc.)")
    parser.add_argument("--require-real-provider", action="store_true", help="Require real LLM provider")
    parser.add_argument("--provider-type", choices=["openai-compatible", "anthropic"], default=None, help="User-configured provider type")
    parser.add_argument("--model-id", default=None, help="User-configured model ID (no hardcoded default)")
    parser.add_argument("--base-url", default=None, help="User-configured provider endpoint base URL")
    parser.add_argument("--execute-heldout", action="store_true", help="Authorize execution of held-out benchmark (RT-07B only, disabled by default)")
    parser.add_argument("--authorize-rt07b", action="store_true", help="Explicit separate confirmation token authorizing RT-07B execution")
    parser.add_argument("--resume", action="store_true", help="Resume benchmark execution from existing checkpoints (idempotent, never bypasses preflight)")
    args = parser.parse_args()

    # Resolve user-configured provider config if supplied or required
    cfg = None
    if args.provider_type or args.model_id or args.base_url:
        cfg = RealLLMProviderConfig.from_profile_or_env(
            provider_type=args.provider_type,
            model=args.model_id,
            api_base=args.base_url,
        )

    runner = BenchmarkRunner(
        protocol_version=args.protocol_version,
        provider_config=cfg,
        require_real_provider=args.require_real_provider,
    )

    # 1. Run Preflight
    report: PreflightReport = runner.preflight_checker.run_preflight(
        require_real_provider=args.require_real_provider,
        provider=runner.provider,
    )

    print("\n================== BENCHMARK PREFLIGHT REPORT ==================")
    print(f"Timestamp UTC       : {report.timestamp_utc}")
    print(f"Protocol Version    : {report.protocol_version}")
    print(f"Source Commit       : {report.source_snapshot.get('source_commit')}")
    print(f"Source Tree Digest  : {report.source_snapshot.get('source_tree_digest')}")
    print(f"Readiness Status    : {report.benchmark_readiness}")
    print(f"All Checks Passed   : {report.all_passed}")
    print(f"Blockers Count      : {len(report.blockers)}")

    if report.blockers:
        print("\n[PREFLIGHT BLOCKERS]:")
        for b in report.blockers:
            print(f"  - {b}")

    if report.docker_audit_findings:
        print("\n[DOCKER & RELAY AUDIT FINDINGS]:")
        for f in report.docker_audit_findings:
            print(f"  - {f}")

    if args.validate_only:
        return 1 if report.has_blockers else 0

    if args.dry_run:
        print(f"\nExecuting development dry-run episode on {args.scenario} with {args.planner}...")
        res = runner.run_development_dry_run(
            scenario_key=args.scenario,
            planner_id=args.planner,
        )
        print(f"\n[DRY RUN COMPLETED]:")
        print(f"  Experiment ID     : {res.experiment_id}")
        print(f"  Status            : {res.episode_status}")
        print(f"  Termination Reason: {res.termination_reason}")
        print(f"  Objective Achieved: {res.objective_completed}")
        print(f"  Steps Executed    : {res.steps_executed}")
        print(f"  Operational Noise : {res.total_operational_noise}")
        print(f"  Action Sequence   : {' -> '.join(res.canonical_action_sequence)}")
        return 0

    if args.execute_heldout:
        # HARD INVARIANT: Held-out execution requires separate explicit --authorize-rt07b
        if not args.authorize_rt07b:
            print(
                "\n[RT-07B AUTHORIZATION BLOCKED]:\n"
                "Comparative benchmark execution on held-out scenarios requires explicit separate '--authorize-rt07b' authorization.\n"
                "RT-07A/RT-07A1 prohibits unconfirmed held-out execution.",
                file=sys.stderr,
            )
            return 1

        try:
            auth_report = runner.check_held_out_execution_authorization(
                authorize_rt07b=args.authorize_rt07b,
                require_real_provider=args.require_real_provider or True,
                is_simulator_only=True,
            )
            print(f"\n[RT-07B AUTHORIZATION GRANTED]: Preflight passed. Ready for comparative held-out execution.")
            # Note: Actual execution loop is scheduled in RT-07B tranche
            return 0
        except Exception as exc:
            print(f"\n[RT-07B EXECUTION REFUSED]: {exc}", file=sys.stderr)
            return 1

    # If neither --validate-only, --dry-run, nor --execute-heldout was supplied, enforce RT-07A protection
    print(
        "\n[RT-07A MANDATORY SAFETY GUARD]:\n"
        "Comparative benchmark execution on the 420 held-out episodes is strictly BLOCKED during RT-07A/RT-07A1.\n"
        "Use '--dry-run' for development preflight or '--validate-only' to inspect protocol readiness.\n"
        "Held-out comparative execution requires '--execute-heldout --authorize-rt07b' and will be scheduled in RT-07B after formal approval.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
