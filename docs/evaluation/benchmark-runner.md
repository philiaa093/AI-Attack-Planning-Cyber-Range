# Benchmark Execution Framework & Preflight Runner Guide (RT-07A)

> Protocol: `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED`  
> Architecture: Planner-Neutral POMDP Episode Loop  
> Scope: Preflight, Source Provenance, Safety Guards & Development Dry-Run  

---

## 1. Overview

RT-07A establishes a reproducible, planner-neutral, fail-closed benchmark execution framework before running comparative experiments across RULE, LLM, HYBRID, and diagnostic ablations.

The framework consists of three tightly coupled components:
1. **`evaluation/experiments/source_snapshot.py`**: Cryptographic provenance and source snapshot manifest capturing git commit HEAD, dirty worktree status, untracked files, and per-file SHA-256 digests over all 47 relevant executable benchmark files.
2. **`evaluation/experiments/benchmark_preflight.py`**: Full preflight verification suite checking protocol seals, scenario byte digests, matrix cardinality, paired seed coupling, inference configurations, provider readiness, and cyber-range security boundaries.
3. **`evaluation/experiments/run_benchmark.py`**: Thin, neutral experiment runner using the canonical `PlannerEpisodeRunner(env, planner)` loop with idempotent checkpointing, failure taxonomy, and development-only dry-runs.

---

## 2. Command Line Usage

### Preflight Verification Only
Inspect all protocol seals, scenario hashes, matrix dimensions, seed couplings, and provenance without executing any episodes:
```bash
python -B evaluation/experiments/benchmark_preflight.py
```
To test whether a real LLM provider is available for comparative evaluation:
```bash
python -B evaluation/experiments/benchmark_preflight.py --require-real-provider
```

### Validate Benchmark Matrix & Protocol Integrity
Using the benchmark runner interface:
```bash
python -B evaluation/experiments/run_benchmark.py --validate-only
```

### Development Dry-Run (S1–S4 Only)
Execute an engineering validation episode on development scenarios using scripted/fake providers:
```bash
# Linear attack path on S1 Straight with Rule baseline
python -B evaluation/experiments/run_benchmark.py --dry-run --scenario S1 --planner RULE

# Clean control restraint test on S4 Clean with Rule baseline
python -B evaluation/experiments/run_benchmark.py --dry-run --scenario S4 --planner RULE

# Hybrid planner fusion execution on S1 Straight
python -B evaluation/experiments/run_benchmark.py --dry-run --scenario S1 --planner HYBRID_FULL
```

### Safety Guard against Premature Execution
Invoking `run_benchmark.py` without `--dry-run` or `--validate-only` automatically halts execution with a fail-closed guard:
```
[RT-07A MANDATORY SAFETY GUARD]:
Comparative benchmark execution on the 420 held-out episodes is strictly BLOCKED during RT-07A.
Use '--dry-run' for development preflight or '--validate-only' to inspect protocol readiness.
Comparative execution will be scheduled in RT-07B after formal approval.
```

---

## 3. Supported Configurations & Ablations

All configurations are instantiated through `BenchmarkRunner.instantiate_planner(planner_id)`:

| Configuration ID | Class | Policy / Scoring Version | Description |
| :--- | :--- | :--- | :--- |
| `RULE` | `RuleBasedPlanner` | `RULE_POLICY_V1` | Deterministic symbolic heuristic baseline. |
| `LLM` | `LLMPlanner` | `LLM_ATTACK_PLANNER_PROMPT_V1` | Pure semantic candidate selection under controlled inference. |
| `HYBRID_FULL` | `HybridPlanner` | `HYBRID_SCORING_V1_FROZEN` | Proposed semantic-symbolic fusion with frozen heuristic weights. |
| `HYBRID_NO_NOISE` | `HybridPlanner` | `HYBRID_NO_NOISE` | Ablation setting $w_{noise} = 0.0$. |
| `HYBRID_NO_PENALTIES` | `HybridPlanner` | `HYBRID_NO_PENALTIES` | Ablation setting $w_{repeat} = 0.0, w_{failure} = 0.0$. |
| `HYBRID_SEMANTIC_ONLY` | `HybridPlanner` | `HYBRID_SEMANTIC_ONLY` | Ablation setting $w_{semantic} = 1.0$, symbolic progression zeroed. |
| `HYBRID_SYMBOLIC_ONLY` | `HybridPlanner` | `HYBRID_SYMBOLIC_ONLY` | Ablation setting $w_{semantic} = 0.0$, running purely symbolically. |

---

## 4. Result Persistence & Schema

Episode results are saved to `evaluation/results/{experiment_id}.json` following the schema defined in `evaluation/results/result.schema.json`.

Key recorded telemetry fields:
- **Identifiers:** `experiment_id`, `protocol_version`, `source_commit`, `source_tree_digest`
- **Scenario:** `scenario_id`, `scenario_sha256`, `replicate_id`, `simulator_seed`, `requested_provider_seed`
- **Planner:** `planner_id`, `planner_version`, `prompt_hash`, `weights_hash`
- **Execution:** `start_time_utc`, `finish_time_utc`, `episode_status`, `termination_reason`, `steps_executed`
- **Outcomes:** `objective_completed`, `is_clean_control`, `clean_restraint_success`, `encountered_dead_end`, `recovered_from_dead_end`
- **Diagnostics:** `invalid_decisions`, `observable_failed_progressions`, `provider_errors`, `retry_count`, `symbolic_fallback_count`, `planning_latencies_ms`
