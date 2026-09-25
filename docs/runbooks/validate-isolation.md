# Validate isolation

## Status

`IMPLEMENTED` static configuration validation; runtime evidence remains `UNRESOLVED`.

## Purpose

Validate Docker network isolation without authorizing public scanning or runtime deployment.

## Preconditions

Approved isolated lab scope, scenario, contracts, and safety review. No public target or production system.

## Required Configuration

`cyber-range/compose.yaml` must define approved target IDs, one Docker network named `lab` with `internal: true`, and loopback-only published ports.

## Safety Checks

Stop on unknown target, unrestricted network, non-loopback port, malformed input, scope mismatch, or evidence-loss risk.

## Inputs

Repository root, Compose file, target allowlist, and isolation test.

## Procedure

Run from repository root. Checks inspect configuration only; they do not start containers or authorize runtime.

```text
python -m unittest tests.integration.test_network_isolation -v
docker compose -f cyber-range/compose.yaml config
```

## Expected Artifacts

Test output and Compose config output. Configuration checks do not produce runtime evidence.

## Validation

1. Every service uses only `lab` network.
2. `lab` network is internal.
3. Every published port starts with `127.0.0.1:`.
4. Every service target ID is allowlisted.
5. No host network, default network, public bind, external route, or unrestricted network appears.

Mark runtime status `UNRESOLVED` until approved observed evidence exists.

## Failure Handling

Fail closed on any mismatch. Do not start or scan targets after failed isolation checks.

## Cleanup

No containers are started by this runbook. Preserve test output.

## Evidence

Record UTC timestamp, run ID, command, expected state, observed result, status, source, and evidence reference. Static checks do not prove runtime isolation.

## Related Tasks

TASK-011 Cyber range network.
