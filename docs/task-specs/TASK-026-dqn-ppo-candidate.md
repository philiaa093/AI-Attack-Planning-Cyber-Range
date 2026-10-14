# TASK-026 — DQN/PPO candidate

## Status

`DEFERRED` for the full DQN/PPO candidate, as required by AGENTS.md.
At the user's request on 2026-10-12, the preparatory offline reward/mask wrapper,
evaluation helper/protocol and focused tests are `IMPLEMENTED`, not `VALIDATED`.
See [implementation, receipts and handoff](../implementation/offline_rl_protocol.md).
No learned model, training result or checkpoint exists. Independent review,
SB3/PyTorch compatibility, actual benchmark and durable evidence are `UNRESOLVED`.
Handoff is `HANDOFF_BLOCKED`: the final implementation gate exited 1 with 27
outside-scope errors; the earlier PASS receipt does not supersede that result.

## Purpose

Deliver dqn/ppo candidate for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Topic-specific artifact for dqn/ppo candidate.
Implemented preparation is limited to runtime/replay_wrappers.py,
runtime/offline_evaluation.py and their offline protocol/tests. They adapt Task-023
metadata replay without scanner, provider, executor or network integration.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.
Learned candidate implementation/training, new configuration/contracts/scenarios,
immutable experiment writer and full Task-028/030 evaluation are outside this subset.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable dqn/ppo candidate artifact with explicit status and evidence boundary.
Preparation artifacts: [wrapper](../../runtime/evaluation/replay_wrappers.py),
[evaluator](../../runtime/evaluation/offline_evaluation.py),
[protocol/receipts](../implementation/offline_rl_protocol.md),
[wrapper tests](../../tests/runtime/test_replay_wrappers.py) and
[evaluation tests](../../tests/runtime/test_offline_evaluation.py).
The seeded DQN/PPO model artifact remains absent.

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.
ReplayRewardMaskWrapper.reset/step/action_masks/close and
evaluate_offline(protocol, selector, candidate_id, split) are offline interfaces.
Selectors receive detached public observation/mask plus seeded RNG, not simulator
handles or unrevealed facts. Caller Python code is trusted, not sandboxed.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.
Adapter observation version replay-normalized-v1 has normalized counts/budget,
observed asset flags, action mask and read age; flattened dimension is 7N+3.
Task-024 outcome reward replaces only the wrapper's returned reward. Intrinsic
budget exhaustion is terminal in the wrapper, with base termination flags in info.
Canonical schemas/action IDs and Task-023's original return semantics are unchanged.

## Dependencies

TASK-023, TASK-024
## Implementation Requirements

Produce seeded candidate; preserve source hierarchy and status vocabulary.
The preparation implements fixed normalization, one score per committed transition,
validated masks and split/budget/seed checks. It does not fulfill the seeded-model
requirement. The full task remains deferred until that scope is explicitly opened.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.
Mask does not authorize dispatch or bypass simulator policy. Malformed/audit/scorer
failures stop processing; failed committed transitions are not retried or rescored.
The evaluator stops on empty masks/errors, retains failure denominators and never
replaces an invalid proposal. Audit/results remain in memory, not durable evidence.

## Testing Requirements

Preparation receipts: 29 focused + 53 Task-023/024/025 regressions + 17 safety
tests PASS (99 tests, each suite exit 0); AST/example/document/whitespace PASS.
Final implementation repository gate exited 1 (27 outside-scope errors, 0 scoped).
Four source hashes match during documentation synchronization; suites are not rerun
for that update. New docs/status/link/gate checks have separate receipts in
runtime/offline_rl_protocol.md. Seeded learned-model tests remain unperformed.

## Acceptance Criteria

Seeded candidate exists as topic-specific reviewable artifact; no VALIDATED claim without required review and evidence.
Wrapper/protocol preparation exists, but seeded DQN/PPO candidate acceptance is
still open. No full-task IMPLEMENTED/VALIDATED or Task-030 completion claim.

## Evidence Required

Source record, check receipt, and immutable evidence or explicit UNRESOLVED marker.
Source hashes and exact command receipts are in runtime/offline_rl_protocol.md;
synthetic selectors do not prove learned-policy performance or live defense.
Earlier gate PASS and final gate FAIL are both preserved. Durable experiment/
checkpoint evidence and independent review remain UNRESOLVED.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

[DQN](../guides/12-dqn.md) and [PPO](../guides/13-ppo.md).

## Related Runbooks

[Train agent](../runbooks/train-agent.md) is a future workflow, not training or
runtime authorization from the preparatory subset.

## Related ADRs

[Simulator first](../adr/ADR-007-simulator-before-cyber-range-rl.md),
[held-out scenarios](../adr/ADR-008-held-out-scenarios.md),
[ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md),
[immutable evidence](../adr/ADR-010-evidence-immutability.md),
[same budgets](../adr/ADR-011-same-budgets-across-planners.md) and
[safety control](../adr/ADR-012-safety-engine-control.md).
