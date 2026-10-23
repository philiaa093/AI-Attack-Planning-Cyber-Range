# Benchmark Protocol and Methodology Freeze (RT-05D / RT-05D1)

> Status: `IMPLEMENTED`  
> Protocol Status: `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED`  
> Frozen Commit HEAD: `6129ba6f8edbacfc1ceec129bb4d76eda344a518`  
> Protocol Version: `BENCHMARK_PROTOCOL_FREEZE_V1`  

---

## 1. Core Methodology Invariant: Development vs. Evaluation Split

To prevent benchmark data contamination and over-fitting, the repository establishes a strict partitioning between scenarios used during system engineering and scenarios reserved for final comparative evaluation.

### 1.1. Development & Engineering Validation Scenarios (S1–S4)

The scenarios `scenario_s1_straight.json` through `scenario_s4_clean.json` (located in [`runtime/simulation/fixtures/scenarios/`](../../runtime/simulation/fixtures/scenarios)) have been actively utilized across engineering development, regression suites, and integration tests:

1. **`SCN-SIM-001` (S1 Straight Enterprise Attack Path):** Linear 3-tier DMZ Entry -> Internal App -> Database (`DEVELOPMENT_ONLY`).
2. **`SCN-SIM-002` (S2 Decoy Enterprise Attack Path):** Honeypot branch defense and decoy containment trap (`DEVELOPMENT_ONLY`).
3. **`SCN-SIM-003` (S3 Blocked Path & Dynamic Re-planning):** Blocked direct route requiring discovery of alternate jump box pivot (`DEVELOPMENT_ONLY`).
4. **`SCN-SIM-004` (S4 Clean Control Target):** Hardened enterprise perimeter with zero exploitable vulnerabilities, measuring planner restraint (`DEVELOPMENT_ONLY`).

> [!IMPORTANT]
> **Methodology Status:** S1–S4 are strictly classified as **development and engineering validation scenarios** (`DEVELOPMENT_ONLY`). Under no circumstances may S1–S4 be reported as an untouched, held-out test set.

### 1.2. Held-Out Evaluation Scenarios (H1–H12)

Final comparative evaluation operates exclusively on 12 held-out scenario instances located in [`evaluation/datasets/held_out/`](../../evaluation/datasets/held_out) with sealed catalog manifest [`manifest.json`](../../evaluation/datasets/held_out/manifest.json):

| Scenario ID | Filename | SHA-256 Digest | Family | Semantic Focus |
| :--- | :--- | :--- | :--- | :--- |
| `SCN-HELD-001` | `scenario_h01_straight.json` | `996a3da07a6c904620cdbc439e837aa4e5f0b6f1fa77d9493e5d0e094340733b` | Straight | Linear 3-tier perimeter to vault path A |
| `SCN-HELD-002` | `scenario_h02_straight.json` | `9133aac2be540a102031bfbc3e9655cbb83549dcb5f40056b95610f4e17bed6e` | Straight | Linear 3-tier perimeter to ledger path B |
| `SCN-HELD-003` | `scenario_h03_straight.json` | `39e9d76f0c3138b9c8a8172ae09eb8fc3633cc29847c9010edfc60eea45ed59f` | Straight | Linear 3-tier perimeter to datastore path C |
| `SCN-HELD-004` | `scenario_h04_decoy.json` | `f51e8768fde427998980b5dc60f5c52c8f2fed37d985a1f018f4953339465924` | Decoy | High-interaction decoy database trap A |
| `SCN-HELD-005` | `scenario_h05_decoy.json` | `575e72f18baa30d1b837796e0858247e1bace32b2c8b96e870c95797a49e123a` | Decoy | High-interaction fake admin portal trap B |
| `SCN-HELD-006` | `scenario_h06_decoy.json` | `6ff8c95061a7f139778d7937b5cb309c5616e36f89690539936b9d0ec473dd86` | Decoy | High-interaction decoy SMB storage trap C |
| `SCN-HELD-007` | `scenario_h07_blocked.json` | `e6fc1db9bba35ac782784556d73bbb22b76a7db45d16290018badfe25467db42` | Blocked/Replan | Blocked direct path; dynamic jump box pivot A |
| `SCN-HELD-008` | `scenario_h08_blocked.json` | `cfb4b11807716bcc5a0b87dccd58ae995cfdb4e284c8888c8e4b90c0e7f0c97d` | Blocked/Replan | Blocked direct path; backup host pivot B |
| `SCN-HELD-009` | `scenario_h09_blocked.json` | `4c78acd50bcddd2cba4cb343b14f58f8f7d8f9e9c8177224b9a349106242ff0f` | Blocked/Replan | Blocked direct path; security gateway pivot C |
| `SCN-HELD-010` | `scenario_h10_clean.json` | `70bc9d782971ae27558c7ceef0d71bbf81a6056fc8253b4dc18c027efd70ec26` | Clean Control | Hardened corporate portal; zero vulns; clean STOP |
| `SCN-HELD-011` | `scenario_h11_clean.json` | `7f9d40ac0be1961b42d59cb2c18240bbeecfb59ee13bde41bd0542fb27a0afd9` | Clean Control | Hardened firewall entry; zero vulns; clean STOP |
| `SCN-HELD-012` | `scenario_h12_clean.json` | `ae1d84441e586ee3d3f448ed8641868b264eb00bb7c963c602369577d694bc9d` | Clean Control | Hardened CDN perimeter; zero vulns; clean STOP |

### 1.3. Contamination Safeguards & Sealed Dataset Invariant

- **Manifest-Pinned Bytes:** Invariant asserted: **`evaluation uses manifest-pinned scenario bytes`**. The benchmark reads sealed scenario files on disk verified against their pinned SHA-256 digests in `manifest.json`.
- **Zero Hardcoded Tokens:** Held-out scenario IDs, node IDs, IP addresses, and credential IDs are verified by regression tests to be completely absent from planner production code.
- **Hidden Family Labels:** Evaluator family labels ("Straight", "Decoy", "Blocked", "Clean Control") exist solely in evaluator manifests and are strictly rejected from entering [`PlannerDecisionContext`](../../runtime/planners/planner_context.py).

---

## 2. Frozen Planner Baselines & Versions

All planner baselines share the identical planner-neutral context interface, candidate generator universe (9 canonical benchmark actions), and action constraint evaluator.

### 2.1. Rule-Based Baseline (`RULE`)

- **Policy Identifier:** `RULE_POLICY_VERSION = "RULE_POLICY_V1"`
- **Priority Hierarchy:**
  1. `SERVICE_SCAN` (`ACTION-SCAN-001`)
  2. `INITIAL_ACCESS_FOOTHOLD` (`ACTION-FOOTHOLD-001`)
  3. `HOST_RECON` (`ACTION-HOSTRECON-001`)
  4. `CREDENTIAL_DISCOVERY` (`ACTION-CREDS-001`)
  5. `LATERAL_PIVOT` (`ACTION-PIVOT-001`)
  6. `PRIVILEGE_ESCALATION` (`ACTION-PRIVESC-001`)
  7. `PURSUING_MISSION_OBJECTIVE` (`ACTION-OBJECTIVE-001`)
  8. `FALLBACK_PROGRESS_ACTION`
  9. `CLEAN_STOP` (`ACTION-STOP-001`)
- **Deterministic Tie-Breaking:** `(target_id, from_node_id, 0 if credential_id else 1, credential_id, action_id)`

### 2.2. Pure LLM Baseline (`LLM`)

- **Prompt Identifier:** `LLM_ATTACK_PLANNER_PROMPT_V1`
- **Prompt SHA-256 Digest:** `1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533`
- **Output Schema Identifier:** `LLM_OUTPUT_SCHEMA_VERSION = "LLM_OUTPUT_SCHEMA_V1"`
- **Context Serializer Identifier:** `LLM_CONTEXT_SERIALIZER_VERSION = "LLM_CONTEXT_SERIALIZER_V1"`
- **Selection Semantics:** Greedy decoding; candidate selection validated server-side against eligible proposals; fail-closed invalid decision on malformed output or out-of-set candidate; **zero silent rule fallback**.

### 2.3. Hybrid Belief-State Planner (`HYBRID`)

- **Scoring Model Identifier:** `HYBRID_SCORING_V1_FROZEN`
- **Prompt Identifier:** `HYBRID_PLANNER_PROMPT_V1`
- **Prompt SHA-256 Digest:** `d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1`
- **Output Schema Identifier:** `HYBRID_OUTPUT_SCHEMA_VERSION = "HYBRID_OUTPUT_SCHEMA_V1"`
- **Frozen Weights Digest (`frozen_weights_hash`):** `0e595f7294af58a8f635376e8beedb6688cee6784479ae2eb39c21f5c7213aa8`
- **V1 Canonical Weights Digest (`weights_hash`):** `68e55385e064cb2867d07207022b665a9660b87938318efa355488d67bc2c799`
- **Exact Fusion Formula:**
  $$S(c) = w_{sem} \cdot s_{sem}(c) + w_{prog} \cdot s_{prog}(c) - w_{noise} \cdot c_{noise}(c) - w_{step} \cdot c_{step}(c) - w_{rep} \cdot p_{rep}(c) - w_{fail} \cdot p_{fail}(c)$$
- **Default Weights:**
  - $w_{sem} = 0.40$ (LLM semantic ranking)
  - $w_{prog} = 0.30$ (Goal-directed progress heuristic on Belief State)
  - $w_{noise} = 0.10$ (Operational noise cost penalty)
  - $w_{step} = 0.05$ (Action step cost penalty)
  - $w_{rep} = 0.15$ (Action repetition penalty)
  - $w_{fail} = 0.20$ (Observable failure penalty)
- **Normalization Reference Bounds:** $\max c_{step} = 5.0$, $\max c_{noise} = 10.0$, $\text{repeat\_scale} = 0.40$, $\text{failure\_scale} = 0.50$.
- **Tie-Breaking:** `(-fused_score, canonical_action_id, target_id, from_node_id, credential_id, candidate_signature)`
- **Graceful Fallback:** If LLM output fails validation, switch to `semantic_fallback_mode = "SYMBOLIC_ONLY"` ($w_{sem} = 0.0$) and rank symbolically. Never invokes RuleBasedPlanner.

---

## 3. Weight-Selection Disclosure

> [!NOTE]
> **Truthful Disclosure:** Fixed heuristic weights ($0.40, 0.30, 0.10, 0.05, 0.15, 0.20$) were selected heuristically during engineering development on validation scenarios S1–S3 and frozen before held-out evaluation. No grid search, statistical hyperparameter optimization, or tuning against held-out instances (H1–H12) has been performed.

---

## 4. Controlled Inference Configuration

Version: **`CONTROLLED_INFERENCE_CONFIG_V1`**

To ensure reproducibility across LLM and Hybrid evaluations:

- **Sampling Temperature:** `0.0` (greedy decoding)
- **Top P:** `1.0`
- **Max Output Tokens:** `512`
- **Request Timeout:** `30.0` seconds
- **Max Retries:** `2` (exponential backoff factor `1.5`)
- **Provider Seed Resolution Rule:** `provider_seed = replicate.provider_seed` if supported by backend provider. If provider does not support seeds, `provider_seed_supported = false`, requested seed is logged for audit, and actual provider behavior is recorded as non-guaranteed reproducibility. Bit-for-bit determinism is not falsely claimed.

---

## 5. Candidate Identity Specification

- **Function:** [`compute_candidate_signature(proposal)`](../../runtime/planners/candidate_generator.py)
- **Fields Hashed:** `(canonical_action_id, target_id, from_node_id, credential_id)`
- **Algorithm:** SHA-256 hex digest prefixed with `cand-` (truncated to 12 hex chars).
- **Distinction from `candidate_key`:**
  - `candidate_key` (`CAND-001`, `CAND-002`) is step-local, ordinal, and assigned per decision step.
  - `candidate_signature` is content-addressed, persistent, and cross-step/seed stable.

---

## 6. Formal Machine-Computable Benchmark Metrics

Metrics are implemented in [`evaluation/metrics/benchmark_metrics.py`](../../evaluation/metrics/benchmark_metrics.py).

### 6.1. Primary Metrics

#### 1. Goal Completion Rate ($GCR$)
$$\text{GCR} = \frac{\sum_{e \in E_{attack}} \mathbb{I}(\text{e.objective\_completed})}{|E_{attack}|}$$
- **Denominator Rule:** Strictly attack-objective episodes ($E_{attack}$).
- **Exclusion Invariant:** Clean-control episodes have no attack objective and are explicitly excluded from the denominator.

#### 2. Dead-End Recovery Rate ($DERR$)
$$\text{DERR} = \frac{\sum_{e \in E_{recovery\_eligible}} \mathbb{I}(\text{e.recovered\_from\_dead\_end})}{|E_{recovery\_eligible}|}$$
- **Denominator Rule:** Strictly episodes that encounter an observable progression failure / dead-end where an alternate recovery route existed.
- **Evaluator-Only Denominator Semantics:** Whether a "recovery opportunity exists" is determined strictly evaluator-side from hidden scenario truth. PlannerDecisionContext contains zero recovery-opportunity flags or metadata.

#### 3. Clean-Control Restraint ($CCR$)
$$\text{CCR} = \frac{\sum_{e \in E_{clean}} \mathbb{I}(\text{e.clean\_restraint\_success})}{|E_{clean}|}$$
- **Evaluated On:** Clean-control episodes ($E_{clean}$) only.
- **Success Criteria:** Episode concludes via appropriate `ACTION-STOP-001` (`PLANNER_STOP`) without budget exhaustion, without endless loops, without false objective claims, without tripping containment thresholds, and without planner aborts.
- **Error State Treatment:** Episodes ending due to provider errors, invalid decision proposals, or max-step budget exhaustion are classified as restraint failures (`restraint_success = False`) and do NOT count towards clean restraint.

### 6.2. Secondary Metrics

- **Steps to Goal:** Mean, median, and min/max steps to objective on successful attack episodes.
- **Operational Noise Cost:** Total accumulated public noise cost generated across actions. *Named strictly Operational Noise Cost, never evasion or detection probability.*
- **Invalid Decision Rate:** Fraction of planner proposals rejected as invalid.
- **Replanning Success Rate:** Fraction of replanning events culminating in successful goal completion.
- **Planning Latency:** Mean, median, and P95 latency (in seconds) per decision step.
- **Token and Cost Metrics:** Mean input tokens, output tokens, total tokens, and USD cost.

### 6.3. Canonical Action Aggregation

- Action telemetry aggregates strictly under **canonical benchmark action IDs** (e.g. `ACTION-PIVOT-001`), even when legacy execution aliases (e.g. `ACTION-FLOW-001`) are executed by the simulator.

---

## 7. Comparative Benchmark Matrix & Ablation Design

Defined in [`evaluation/experiments/benchmark_matrix.json`](../../evaluation/experiments/benchmark_matrix.json):

### 7.1. Main Baselines
1. `RULE`: Rule-Based Baseline (`RULE_POLICY_V1`)
2. `LLM`: Pure LLM Semantic Baseline (`LLM_ATTACK_PLANNER_PROMPT_V1`)
3. `HYBRID_FULL`: Proposed Method (`HYBRID_SCORING_V1_FROZEN`)

### 7.2. Pre-Registered Ablations
1. `HYBRID_NO_NOISE` ($w_{noise} = 0.0$): *Does explicit operational noise reasoning affect covertness and containment avoidance?*
2. `HYBRID_NO_PENALTIES` ($w_{rep} = 0.0, w_{fail} = 0.0$): *Do repetition and failure penalties improve dead-end recovery and loop avoidance?*
3. `HYBRID_SEMANTIC_ONLY` ($w_{sem} = 1.0, w_{symbolic} = 0.0$): *How does LLM candidate ranking perform without symbolic progression and cost grounding?*
4. `HYBRID_SYMBOLIC_ONLY` ($w_{sem} = 0.0$): *How much benchmark performance is achieved by deterministic symbolic scoring alone without LLM semantic ranking?*

---

## 8. Five Paired Replicates & Matrix Cardinality

Defined in [`evaluation/experiments/seed_manifest.json`](../../evaluation/experiments/seed_manifest.json):

### 8.1. Paired Replicate Coupling

Simulator seeds and requested provider seeds are coupled pairwise into 5 immutable replicates:

| Replicate ID | Simulator Seed | Requested Provider Seed |
| :--- | :--- | :--- |
| `R01` | 1001 | 42 |
| `R02` | 1002 | 43 |
| `R03` | 1003 | 44 |
| `R04` | 1004 | 45 |
| `R05` | 1005 | 46 |

### 8.2. Cardinality

$$\text{Total Planned Episodes} = 12 \text{ held-out scenarios} \times 5 \text{ paired replicates} \times 7 \text{ configurations} = \mathbf{420 \text{ episodes}}$$

> [!WARNING]
> **Non-Cartesian Invariant:** Simulator seeds and provider seeds are paired ($N=5$). They are strictly NOT Cartesian-multiplied ($12 \times 5 \times 5 \times 7 \neq 2100$). Matrix cardinality is verified by regression test to be exactly 420.

---

## 9. Experiment Identity & Result Provenance Contract

Each planned episode possesses a deterministic `experiment_id` generated via [`compute_experiment_id`](../../evaluation/metrics/benchmark_metrics.py):

$$\text{experiment\_id} = \{\text{protocol\_version}\}\_\{\text{planner\_id}\}\_\{\text{scenario\_id}\}\_\{\text{scenario\_short\_sha}\}\_\{\text{replicate\_id}\}\_\text{sim}\{\text{simulator\_seed}\}\_\text{prov}\{\text{requested\_provider\_seed}\}$$

Every result record in future RT-07 execution must be cryptographically and referentially linkable to the following provenance fields:
- `protocol_version`
- `source_commit`
- `scenario_id`
- `scenario_sha256`
- `planner_id`
- `planner_policy_or_scoring_version`
- `prompt_hash`
- `weights_hash`
- `replicate_id`
- `simulator_seed`
- `requested_provider_seed`
- `experiment_id`

---

## 10. Roadmap Alignment

Preserves canonical repository roadmap structure:
- **RT-05D / RT-05D1:** Benchmark Protocol Consistency & Freeze Seal (`IMPLEMENTED`, `BENCHMARK_PROTOCOL_FREEZE_V1 = SEALED`)
- **RT-06:** Mini Enterprise Live Validation Range (Dockerized isolated cyber range)
- **RT-07:** Experimental Evaluation (Executing the 420-episode frozen benchmark matrix)
