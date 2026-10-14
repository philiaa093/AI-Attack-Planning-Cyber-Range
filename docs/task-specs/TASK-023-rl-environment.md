# TASK-023 — RL environment

## Status

`IMPLEMENTED` for offline Gymnasium metadata replay, at the user's request on
2026-10-12. Not `VALIDATED`; independent review, durable evidence and live integration
remain `UNRESOLVED`. See [implementation and receipts](../implementation/rl_environment.md).
Handoff is `HANDOFF_BLOCKED`: the implementation repository gate exited 1 with
613 errors outside scope and 0 Task-023 errors. Source hashes still match the
implementation receipts; this documentation synchronization does not rerun 72 tests.

## Purpose

Deliver rl environment for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Fixed replay actions/observations, Gymnasium step/reset, simulation approval/order/rate/
budget checks and read-only TASK-019/020 snapshot projection in runtime/rl_environment.py.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions,
executable exploit payloads, live scanner/executor integration, training, official
reward-model design, runtime claims, and fabricated results.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable [environment](../../runtime/evaluation/rl_environment.py),
[dependency declaration](../../runtime/evaluation/requirements.txt),
[documentation](../implementation/rl_environment.md) and
[focused tests](../../tests/runtime/test_rl_environment.py).

## Interfaces

ReplayAssessmentEnv.reset(seed, options), step(action), audit_records() and close().
ReplayAssessmentEnv.from_snapshot requires TASK-020 StateSnapshot; TASK-019 integration
uses StateSnapshot.from_store. Snapshot reads do not change source state or budgets.
Replay indices are not canonical action IDs or authorization for scanner dispatch.

## Data Contracts

ReplayAsset has a bounded lab target ID, inventory_items and candidate_reported
(True, False or None). Dict observations contain asset review/availability/candidate
flags, inventory counts and remaining simulator budget. None remains unknown;
candidate metadata is not confirmed vulnerability or hidden ground truth.
Canonical state/action/observation schemas remain unchanged.

## Dependencies

TASK-004, TASK-005, TASK-006, TASK-009

Implementation integration also reads TASK-019/020 outputs; canonical dependency
IDs above and in TASKS.md remain unchanged.

## Implementation Requirements

Gymnasium Env with Discrete replay actions and Dict observations. reset returns
(observation, info); step returns (observation, reward, terminated, truncated, info).
Reports remain unknown until reviewed. Candidate metadata is not confirmed truth.

## Safety Requirements

Validate trust-boundary input. Replay enforces lab mode, fixed operation/target scope,
explicit simulation approval, decision budget, tick-based rate and inventory-before-
report order independently of action mask. Malformed action stops the episode.
Reset restores simulator memory while preserving audit records and source data.
Audit remains volatile; durable evidence and live gate/approval/restore integration
are UNRESOLVED. Replay approval never authorizes network or scanner execution.

## Testing Requirements

23 focused tests PASS including Gymnasium check_env; 21 state-store and 28 planner
interface regressions PASS in the implementation session. The repository gate exited
1 (613 outside-scope errors, 0 Task-023 errors); scoped AST/example/documents/links/
whitespace checks passed. Documentation updates check source hashes and document
consistency, without rerunning those test suites. Actual receipts and blockers are in
runtime/rl_environment.md.

## Acceptance Criteria

Offline reviewable artifact and Gymnasium step/reset checks are implemented.
Acceptance/handoff is still open until repository blockers are resolved and independent
review checks replay policy, state projection, accounting and evidence boundaries.
No VALIDATED or live-runtime claim without the required review and observed evidence.

## Evidence Required

Source record and command receipts in runtime/rl_environment.md. Audit is volatile
metadata, retained across resets, not durable immutable evidence. Durable evidence
and independent review remain UNRESOLVED; offline checks do not prove live behavior.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

[Reinforcement learning](../guides/09-reinforcement-learning.md) and
[MDP/POMDP](../guides/10-mdp-and-pomdp.md).

## Related Runbooks

[Train agent](../runbooks/train-agent.md) is a future workflow, not runtime or training
authorization from this task.

## Related ADRs

[Simulator before Cyber Range RL](../adr/ADR-007-simulator-before-cyber-range-rl.md),
[ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md),
[same budgets across planners](../adr/ADR-011-same-budgets-across-planners.md) and
[safety engine control](../adr/ADR-012-safety-engine-control.md).
