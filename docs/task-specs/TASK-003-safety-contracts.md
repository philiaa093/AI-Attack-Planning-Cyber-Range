# TASK-003 — Safety contracts

## Status

`VALIDATED`.

## Purpose

Deliver safety contracts for bounded AI planning in isolated Web Cyber Range.

## Background

Project covers SQL injection, cross-site scripting, and path traversal with RULE, LLM, RL, and HYBRID planners.

## Scope

Topic-specific artifact for safety contracts.

## Out of Scope

Public targets, Internet scanning, credentials, arbitrary shell, dynamic actions, executable exploit payloads, runtime claims, and fabricated results.

## Inputs

Approved source documents, typed contracts, and dependency outputs.

## Outputs

Reviewable safety contracts artifact with explicit status and evidence boundary.

## Interfaces

Canonical root docs, typed planner/policy boundaries, and evidence references.

## Data Contracts

Typed IDs, canonical fields, explicit status, and redacted or append-only evidence where applicable.

## Dependencies

TASK-001
## Implementation Requirements

Produce allowlists/budget/rate schemas; preserve source hierarchy and status vocabulary.

## Safety Requirements

Validate trust-boundary input. Enforce lab target/action allowlists, budget, rate, approval, refusal, and evidence preservation.

## Testing Requirements

Focused check covers allowlists/budget/rate schemas; validated by scaffold, contract, safety, planner, and evaluation tests recorded in `EV-FOUNDATION-001-001` through `EV-FOUNDATION-001-004`.

## Acceptance Criteria

Allowlists/budget/rate schemas exists as topic-specific reviewable artifact; validated by required checks, immutable hashed receipts, and final read-only approval.

## Evidence Required

Evidence manifest: `../../evidence/foundation/FOUNDATION-001/manifest.json`.

## Failure Conditions

Missing dependency, malformed contract, unsupported claim, scope mismatch, broken link, or data-loss risk blocks completion.

## Related Guides

See matching exact guide under docs/guides/.

## Related Runbooks

See applicable exact runbook under docs/runbooks/; no runtime authorization.

## Related ADRs

See applicable decision under docs/adr/.
