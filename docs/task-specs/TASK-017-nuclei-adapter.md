# TASK-017 — Nuclei adapter

## Status

`SPEC_ONLY`.

## Purpose

Deliver nuclei adapter for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Topic-specific artifact for nuclei adapter.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable nuclei adapter artifact with explicit status and evidence boundary.

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.

## Dependencies

TASK-004, TASK-006, TASK-011
## Implementation Requirements

Produce allowlisted templates; preserve source hierarchy and status vocabulary.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.

## Testing Requirements

Focused check covers allowlisted templates; main validator and unit tests deferred to validator repair.

## Acceptance Criteria

Allowlisted templates exists as topic-specific reviewable artifact; no VALIDATED claim without required review and evidence.

## Evidence Required

Source record, check receipt, and immutable evidence or explicit UNRESOLVED marker.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

See matching exact guide under docs/guides/.

## Related Runbooks

See applicable exact runbook under docs/runbooks/; no runtime authorization.

## Related ADRs

See applicable decision under docs/adr/.
