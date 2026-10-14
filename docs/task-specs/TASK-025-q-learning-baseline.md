# TASK-025 — Q-learning baseline

## Status

`IMPLEMENTED` for the offline metadata-replay Q-learning baseline, synchronized
at the user's request on 2026-10-12. Not `VALIDATED`; independent review, durable
training evidence, held-out evaluation and full planner integration remain
`UNRESOLVED`. See [implementation and receipts](../implementation/q_learning.md).

## Purpose

Deliver q-learning baseline for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Sparse tabular agent, masked epsilon-greedy selection, Bellman updates, seeded
training and greedy evaluation on the exact TASK-023 ReplayAssessmentEnv.
TASK-024 scores each committed replay outcome once in the training runner.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.
Live training/dispatch, new actions, changing canonical configuration/contracts,
production planner integration, checkpoint/evidence packaging and convergence
claims are outside this implemented subset.

## Inputs

Approved source documents, typed contracts, and dependency outputs.
Caller-approved offline ReplayAssessmentEnv and validated QLearningConfig.

## Outputs

Reviewable [agent and runner](../../runtime/evaluation/q_learning.py),
[design/example/receipts](../implementation/q_learning.md) and
[focused tests](../../tests/runtime/test_q_learning.py).

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.
QLearningAgent.select_action/update/values/q_table; train_replay returns an agent
and episode traces; run_replay_episode supports greedy evaluation without Q writes.
This is not a TASK-020 Planner backend or authorization to dispatch canonical actions.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.
ReplayState stores immutable visible metadata, remaining budget, action mask and
read age reconstructed from public committed outcomes. ReplayStep preserves reward
and terminated/truncated flags; EpisodeResult records stop reason and total reward.
Replay indices retain TASK-023 semantics. Candidate metadata is not confirmed truth.

## Dependencies

TASK-023, TASK-024

## Implementation Requirements

Produce reproducible training; preserve source hierarchy and status vocabulary.
Zero-initialize unseen Q rows. Restrict exploration and the bootstrap maximum to
admissible actions. Select anew after every transition. Preserve finite-horizon
budget semantics: no bootstrap after intrinsic budget exhaustion or termination.
Validate input/state/configuration and bind each agent to one environment instance.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.
TASK-023 independently checks policy inside step; masks and reward do not grant
authority. Empty mask stops before step. Audit/malformed-input exceptions propagate;
reset preserves prior simulator audit. No network, scanner, executor or provider call.

## Testing Requirements

Implementation receipts: 19 focused + 23 environment + 11 reward-model tests PASS
(53 total), each suite exit 0. AST, example, whitespace and repository gate PASS;
gate reported 0 repository errors and 0 Task-025 errors. Source hashes matched
when synchronizing documents; these suites were not rerun for this status update.
Document/status/link checks and a fresh gate receipt are recorded separately in
runtime/q_learning.md. No validator-repair deferral remains for this subset.

## Acceptance Criteria

Reproducible training exists as topic-specific reviewable artifact; no VALIDATED claim without required review and evidence.
Seeded replay training and mathematical tests implement the baseline subset.
Full acceptance remains open pending independent review and durable evidence.
The three-step sequence on one tiny fixture does not prove an optimal policy,
convergence, held-out performance or comparable planner budgets.

## Evidence Required

Source record, check receipt, and immutable evidence or explicit UNRESOLVED marker.
Exact commands and SHA-256 source receipts are in runtime/q_learning.md. Training
traces and replay audit remain volatile; durable training evidence is UNRESOLVED.
Keep synthetic expected/observed assertions separate from live-runtime claims.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

[Q-learning](../guides/11-q-learning.md) and
[MDP/POMDP](../guides/10-mdp-and-pomdp.md).

## Related Runbooks

[Train agent](../runbooks/train-agent.md), a planning artifact; this status update
grants no live training or execution authorization.

## Related ADRs

[Simulator before range RL](../adr/ADR-007-simulator-before-cyber-range-rl.md),
[ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md),
[evidence immutability](../adr/ADR-010-evidence-immutability.md),
[same budgets](../adr/ADR-011-same-budgets-across-planners.md) and
[safety-engine control](../adr/ADR-012-safety-engine-control.md).
