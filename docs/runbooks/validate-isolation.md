# Validate isolation

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

Isolation test, offline and reviewable:

1. Input target set must contain only `lab-sqli-001`, `lab-xss-001`, `lab-path-001`, and `lab-clean-001`.
2. Expected policy state must be `lab_mode=true`, `public_targets=false`, `external_network=false`, and `deny_external_hosts=true`.
3. Expected route state must contain no public or external route; any public endpoint, DNS name, or unresolved route is a failure.
4. Expected segmentation state must deny target-to-target access unless explicitly approved by scenario contract.
5. Expected refusal state must stop on unknown target, missing approval, budget/rate violation, or isolation uncertainty.
6. Record each check as `PASS`, `FAIL`, or `UNRESOLVED`; `PASS` requires observed runtime evidence, not prose or configuration inference.

No live commands. This procedure defines checks only; it does not authorize runtime.

## Expected Artifacts

Procedure record, manifest reference, isolation-test check receipt, status, and evidence reference or `UNRESOLVED`.

Check receipt fields: UTC timestamp, run ID, scenario ID, check ID, expected state, observed state, status, source, and evidence reference. Preserve append-only; stop if evidence is missing or mutable.

## Validation

Focused check: verify all five isolation controls and refusal conditions are listed, each result has a closed status (`PASS`, `FAIL`, or `UNRESOLVED`), and no `PASS` appears without observed evidence. Current receipt: `UNRESOLVED` because no runtime is authorized or observed.

Runtime validation needs approval and observed evidence.

## Failure Handling

Stop on malformed input, scope mismatch, missing approval, isolation uncertainty, policy denial, or evidence-loss risk.

## Cleanup

Preserve evidence and use approved restore process only.

## Evidence

UTC, run ID, source, hash, redaction, expected state, observed state. None claimed.

## Related Tasks

See `TASKS.md` and named task specifications.
