# TASK-021 — Rule-based planner

## Status

`IMPLEMENTED` for the offline evidence-review baseline, updated at the user's
request on 2026-10-12. Not `VALIDATED`; independent review, durable evidence
integration, full research baseline and executable runtime remain `UNRESOLVED`.

## Purpose

Provide a deterministic rule-based baseline over Task 19 state snapshots through
the Task 20 interface. The implemented subset proposes offline evidence-review
work; broader research planning remains subject to separate executable scope.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

[RuleBasedPlanner](../../runtime/planners/rule_based_planner.py) subclasses Planner and
implements _plan/_replan without overriding the shared entry points. Immutable
rules use closed candidate/phase/confidence predicates; priority, rule ID and
fact ID define deterministic selection. Only the existing `ACTION-PLAN-003`
(`REVISIT_EVIDENCE`) is proposed for explicit lab target subjects within scope.
Completion controls and feedback prevent repeating a reviewed candidate version.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions,
executable exploit payloads, runtime claims and fabricated results. ZAP/Nuclei
execution, provider calls, runner/gate/recorder integration and implementation of
the full research planner are outside this implemented subset. No contract,
action semantics or evidence changes are authorized by this status update.

## Inputs

Task 19 StateSnapshot, Task 20 PlanningInput with candidate action/target sets,
immutable static Rule configuration, and typed previous decision/Feedback for
replan. Input facts are normalized, redacted observed data, never instructions.

## Outputs

One schema-bound PlanProposal in a PlanningDecision, or an explicit stop reason.
Artifacts: [implementation](../../runtime/planners/rule_based_planner.py),
[design and receipts](../implementation/rule_based_planner.md),
[focused tests](../../tests/runtime/test_rule_based_planner.py).

## Interfaces

Use Planner.plan/replan and the typed snapshot/decision/feedback boundary from
[Task 20](TASK-020-planner-interface.md). Read Task 19 through
StateSnapshot.from_store; do not pass a writable store into the strategy.
Candidate sets filter proposals; only the safety gate can authorize dispatch.

## Data Contracts

Existing state/plan schemas remain unchanged. Plan ID binds context, objective,
review action and candidate version; decision revision binds the snapshot.
The local completion convention uses a CONTROL fact with the helper-generated
fact ID, matching target, boolean True, confidence 1.0 and completion observation
provenance. This does not change global CONTROL semantics or grant authorization.

## Dependencies

TASK-020

## Implementation Requirements

Preserve deterministic selection and shared Task 20 validation. Default rules
prioritize candidates below confidence 0.8, then remaining candidates; this
threshold and proposal confidence are uncalibrated baseline settings.
StateManager remains the budget owner. Selection must not mutate snapshot/store,
write completion/evidence, dispatch tools, or infer objective success from stop.
Replan requires SUCCESS and a completion control bound to feedback provenance.

## Safety Requirements

Reject malformed rule/candidate/completion references; filter explicit target and
action scope. Retain shared budget/context/objective/mode/feedback checks. Planner
output remains proposal data. Lab mode, canonical target/action allowlists,
approval, rate/order checks, refusal, audit and restore are mandatory at the
execution boundary and are not proven by this offline subset. Completion controls
must originate from verified coordinator work, never imported scanner content.

## Testing Requirements

[Focused tests](../../tests/runtime/test_rule_based_planner.py) cover rule ordering,
threshold boundaries, scope/budget refusal, malformed references, snapshot
immutability, completion across contexts/candidate versions, feedback binding,
and in-memory Task 19 replay without planner writes. Implementation receipts:
28 focused + 65 dependency/contract tests PASS, all suites exit 0; AST/example/
whitespace PASS. These are synthetic offline receipts, not runtime validation.
Repository checker exited 1 with 656 errors outside the three implementation
paths, 0 errors within them; repository gate remains pending. The documentation
update checks source hashes and document consistency without rerunning suites.

## Acceptance Criteria

The offline baseline and focused scenarios are implemented and reviewable.
Task acceptance/handoff are not closed: independent review, durable evidence,
completion-source integrity and approved coordinator integration are still needed.
No VALIDATED or scanner/runtime-success claim follows from artifact creation,
passing synthetic checks or this status update.

## Evidence Required

Source HEAD, UTC, Python source SHA-256, exact commands, synthetic source,
expected/observed behavior and limits are recorded in
[design and receipts](../implementation/rule_based_planner.md). Build label:
`BUILD-TASK021-RULE-OFFLINE-20261012`, not an approved build. Durable evidence
packaging, exhaustive redaction and independent review linkage are `UNRESOLVED`.

## Failure Conditions

Missing dependency, malformed contract/reference, unsupported claim, scope
mismatch, broken link or data-loss risk blocks completion. Current handoff is
`HANDOFF_BLOCKED` with `REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE`; next steps are
repository blocker resolution in separately assigned scope, independent strategy/
provenance review, then approved recorder/coordinator integration.

## Related Guides

See [planning and replanning](../guides/07-planning-and-replanning.md).

## Related Runbooks

See [RULE planner runbook](../runbooks/run-rule-planner.md); no runtime authorization.

## Related ADRs

See [separation](../adr/ADR-005-planner-executor-perception-separation.md),
[shared interface](../adr/ADR-006-shared-planner-interface.md), and
[safety control](../adr/ADR-012-safety-engine-control.md).
