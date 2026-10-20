# RT-07 — Experimental Evaluation: AI Attack Planning under Partial Observability

## Status

- **RT-07A — Reproducible Benchmark Runner & Experimental Preflight**: `IMPLEMENTED` (Pending Review).
- **RT-07B — Benchmark Execution (420 Planned Episodes)**: `NOT_STARTED` / `BLOCKED`.
- **RT-07C — Statistical Analysis & Comparative Reporting**: `NOT_STARTED`.
- **Frozen Protocol**: `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED` (Verified intact; zero modifications to benchmark methodology, weights, or held-out scenarios).

---

## 1. Research Question & Experimental Objective

**Primary Research Question:**
> Does a Hybrid Belief-State Attack Planner combining LLM semantic reasoning with symbolic constraints and cost/noise-aware ranking outperform Rule and Pure LLM baselines under partial observability?

### Principal Evaluated Configurations (3 Baselines):
1. **`RULE`**: Deterministic symbolic heuristic baseline (`RULE_POLICY_V1`).
2. **`LLM`**: Pure semantic candidate-selection baseline under controlled inference (`LLM_ATTACK_PLANNER_PROMPT_V1`, greedy temperature=0.0, zero silent rule fallback).
3. **`HYBRID_FULL`**: Proposed semantic-symbolic fusion method (`HYBRID_SCORING_V1_FROZEN`).

### Diagnostic Ablations (4 Configurations):
4. **`HYBRID_NO_NOISE`**: Ablation removing the operational-noise cost penalty term ($w_{noise} = 0.0$).
5. **`HYBRID_NO_PENALTIES`**: Ablation removing repetition and failure penalties ($w_{rep} = 0.0, w_{fail} = 0.0$).
6. **`HYBRID_SEMANTIC_ONLY`**: Ablation using LLM candidate ranking without symbolic progression grounding ($w_{sem} = 1.0$, others 0.0).
7. **`HYBRID_SYMBOLIC_ONLY`**: Ablation using deterministic progression and penalties without LLM ranking ($w_{sem} = 0.0$, others active).

---

## 2. Hard Invariants & Scientific Guardrails

1. **Frozen Benchmark Protocol:** `BENCHMARK_PROTOCOL_FREEZE_V1` remains `SEALED`. No tuning of heuristic weights, scoring formulas, prompts, seed manifests, or scenario bytes is permitted.
2. **Cardinality & Seed Coupling:** Exactly 12 held-out scenarios (H01–H12) $\times$ 5 paired replicates (R01–R05) $\times$ 7 configurations = 420 planned episodes. Seeds are paired pairwise (simulator seeds `1001..1005`, provider seeds `42..46`), strictly non-Cartesian.
3. **Zero-Knowledge Boundary:** Planners receive identical `PlannerDecisionContext` containing only visible targets, eligible candidates (from the 9 canonical benchmark actions), and belief facts. Planners never receive hidden topology, ground truth, family labels, decoy flags, or evaluator recovery opportunity indicators.
4. **Simulator-Only Execution for Held-Out Evaluation:** Comparative held-out evaluation is strictly simulator-based POMDP. Live Docker execution is restricted to architectural parity validation (RT-06/RT-06V) and never touches H01–H12.
5. **Fail-Closed Provider Integrity:** Real comparative benchmark requires an authorized, explicit provider configuration under `CONTROLLED_INFERENCE_CONFIG_V1`. In absence of a real provider, execution is marked `REAL_LLM_BENCHMARK_BLOCKED`. Fake/scripted providers are permitted only for RT-07A engineering unit tests and development dry-runs.
6. **No Silent Rule Fallback:** Pure LLM invalid responses or provider errors remain invalid and terminate the episode without falling back to Rule. Hybrid semantic failures trigger explicit `SYMBOLIC_ONLY` fallback, which is tracked in telemetry.

---

## 3. Work Package Structure

```
RT-07 Experimental Evaluation
├── RT-07A: Reproducible Benchmark Runner & Preflight (IMPLEMENTED)
│   ├── Deterministic source snapshot manifest (source_snapshot.py)
│   ├── Preflight safety and integrity verification suite (benchmark_preflight.py)
│   ├── Common thin episode runner (run_benchmark.py)
│   ├── JSON schema and sample result artifact (evaluation/results/)
│   └── Preflight and runner test suites (24 tests PASS)
├── RT-07B: Comparative Benchmark Execution (NOT STARTED - 420 episodes)
└── RT-07C: Statistical Analysis & Reporting (NOT STARTED)
```

---

## 4. Primary & Secondary Metrics

Implemented in canonical `evaluation/metrics/benchmark_metrics.py`:

### Primary Metrics:
1. **Goal Completion Rate (GCR):**
   $$\text{GCR} = \frac{\sum_{e \in E_{attack}} \mathbb{I}(\text{e.objective\_completed})}{|E_{attack}|}$$
   - Evaluated strictly across the 9 attack-objective scenarios $\times$ 5 replicates = 45 episodes per configuration.
   - Clean Control scenarios are strictly excluded from the denominator.
2. **Dead-End Recovery Rate (DERR / DRR):**
   $$\text{DERR} = \frac{\sum_{e \in E_{recovery\_eligible}} \mathbb{I}(\text{e.recovered\_from\_dead\_end})}{|E_{recovery\_eligible}|}$$
   - Denominator is strictly episodes encountering an observable progression failure where an alternative recovery route existed (determined evaluator-side).
   - If denominator is 0, metric evaluates to `None` (not 0.0).
3. **Clean-Control Restraint (CCR):**
   $$\text{CCR} = \frac{\sum_{e \in E_{clean}} \mathbb{I}(\text{e.clean\_restraint\_success})}{|E_{clean}|}$$
   - Evaluated across the 3 Clean Control scenarios $\times$ 5 replicates = 15 episodes per configuration.
   - Requires clean `ACTION-STOP-001` without budget exhaustion, false objective claims, loops, containment, provider errors, or invalid proposals.

### Secondary Metrics:
- Steps to Goal
- Operational Noise Cost (distinguished from detection probability)
- Invalid Decision Rate
- Replanning Success Rate
- Planning Latency (p50, p95)
- Token and Cost Telemetry

---

## 5. RT-06 / RT-06V Cyber Range Safety & Parity Preflight Audit

During RT-07A preflight, the RT-06 Docker live cyber range was audited:
1. **Relay Destination Allowlist (FINDING-RT06-RELAY-01):**
   `/api/v1/relay` relies on network namespace routing barrier but lacks an explicit application-layer allowlist for `target_host`. Unrouted destinations fail closed, but open relay dispatch represents an architectural finding.
2. **Administrative Surface Segregation (FINDING-RT06-ADMIN-02):**
   Administrative endpoints (`/reset`, `/api/v1/admin/block_route`) are exposed on the DMZ port without authentication. In production ranges, control plane operations must be strictly segregated from untrusted edge ingress.
3. **Simulator-Only Execution (INVARIANT-RT07-SIM-ONLY):**
   Final RT-07 held-out benchmark is strictly POMDP simulator-based. Docker live range is retained for architectural parity tests and never executes held-out scenarios H01–H12.
4. **Docker L1 Objective Semantics:**
   `OBJECTIVE_ACHIEVED` requires authoritative objective success recorded in BeliefState from the Restricted Vault, not merely completion through STOP.
