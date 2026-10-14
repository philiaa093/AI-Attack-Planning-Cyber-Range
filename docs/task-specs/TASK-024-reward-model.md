# TASK-024 — Reward model

## Status

`IMPLEMENTED` for the standalone offline metadata-review reward scorer and tests,
at the user's request on 2026-10-12. Not `VALIDATED`; independent review, config
acceptance and environment/evidence integration remain unresolved. The repository
checker blocker is resolved by the [validator repair](../../scripts/validation/README.md),
which returned SCAFFOLD VALID, exit 0, without modifying scorer/tests or evidence.
See [implementation and receipts](../implementation/reward_model.md).

## Purpose

Deliver reward model for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Pure scorer in runtime/reward_model.py for closed trusted TASK-023 replay outcomes,
with separate step/progress/penalty/completion terms and offline trace tests.
It does not replace the illustrative reward currently returned by TASK-023.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.
Planner/training/executor integration, new ground-truth interfaces and changing
configuration are outside the implemented subset. Candidate presence is not
confirmation evidence or a bonus input.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable [scorer](../../runtime/evaluation/reward_model.py),
[design and receipts](../implementation/reward_model.md) and
[focused tests](../../tests/runtime/test_reward_model.py).

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.
score_replay_reward(outcome) returns an immutable RewardBreakdown with total.
The scorer accepts only closed outcome labels from a trusted committed replay
decision; it neither verifies provenance nor deduplicates transitions itself.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.

## Dependencies

TASK-023
## Implementation Requirements

Produce config/tests; preserve source hierarchy and status vocabulary.
The current subset fixes coefficients in Python and includes focused tests.
configs/rl/reward.yaml remains TBD and unchanged; config scope/acceptance is pending.
Review progress is earned once per slot by the simulator's existing tracking.
Refusal penalties do not replace safety checks; declaring replan earns no bonus.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.

## Testing Requirements

Implementation receipts: 11 focused tests and 23 TASK-023 regressions PASS, each
suite exit 0; source AST/local links/whitespace PASS. Source hashes were matched
when synchronizing documents; suites were not rerun for the status update.
Repository gate receipt: exit 1, 613 errors outside the implementation scope and
0 errors in its three paths. This failed receipt predates the passing validator
repair and is preserved as an observation. Record current gate/document checks
separately from those receipts.

## Acceptance Criteria

Config/tests exists as topic-specific reviewable artifact; no VALIDATED claim without required review and evidence.
Scorer/design/tests exist for the offline subset. Config acceptance remains open;
this IMPLEMENTED status does not close full acceptance, independent review or integration.

## Evidence Required

Source record, check receipt, and immutable evidence or explicit UNRESOLVED marker.
Source SHA-256 hashes and exact command receipts are in runtime/reward_model.md.
They describe synthetic offline traces; durable evidence and observed runtime
integration remain UNRESOLVED. No live vulnerability or learned-policy claim.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

[Reinforcement learning](../guides/09-reinforcement-learning.md).

## Related Runbooks

[Train agent](../runbooks/train-agent.md), still a planning artifact; no training
or runtime authorization is granted by this status update.

## Related ADRs

[Simulator before range RL](../adr/ADR-007-simulator-before-cyber-range-rl.md),
[ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md),
[evidence immutability](../adr/ADR-010-evidence-immutability.md),
[same budgets](../adr/ADR-011-same-budgets-across-planners.md) and
[safety-engine control](../adr/ADR-012-safety-engine-control.md).
