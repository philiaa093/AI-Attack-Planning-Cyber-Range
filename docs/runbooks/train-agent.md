# Train agent

## Status

`SPEC_ONLY`.

## Purpose

Define safe, reviewable procedure; this runbook does not authorize runtime.

## Preconditions

Approved isolated lab scope, scenario, contracts, and safety review. No public target or production system.

## Required Configuration

Approved manifest, target/action allowlists, policy, planner identity, and run ID. Versions remain `UNRESOLVED`.

## Safety Checks

Validate identity, scope, approval, action, order, budget, rate, refusal, isolation, and evidence preservation.

## Inputs

Scenario ID, planner mode, approved manifest, policy, and run identity.

## Procedure

Read contracts; confirm scope; apply policy before any future executor; record expected/observed state; stop on mismatch. No live commands.

## Expected Artifacts

Procedure record, manifest reference, status, and evidence reference or `UNRESOLVED`.

## Validation

Focused documentation check only. Runtime validation needs approval and observed evidence.

## Failure Handling

Stop on malformed input, scope mismatch, missing approval, isolation uncertainty, policy denial, or evidence-loss risk.

## Cleanup

Preserve evidence and use approved restore process only.

## Evidence

UTC, run ID, source, hash, redaction, expected state, observed state. None claimed.

## Related Tasks

See `TASKS.md` and named task specifications.
