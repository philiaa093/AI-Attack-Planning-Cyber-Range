# Validate isolation

## Status

`IMPLEMENTED` static configuration validation; runtime evidence remains `UNRESOLVED`.

## Preconditions

Approved isolated lab scope, scenario, contracts, and safety review. No public target or production system.

## Required configuration

`cyber-range/compose.yaml` must define only approved target IDs, one Docker network named `lab` with `internal: true`, and loopback-only published ports.

## Procedure

Run from repository root. These checks inspect configuration only; they do not start containers or authorize runtime.

```text
python -m unittest tests.integration.test_network_isolation -v
docker compose -f cyber-range/compose.yaml config
```

Stop on unknown target, unrestricted network, non-loopback port, malformed input, scope mismatch, or evidence-loss risk.

## Checks

1. Every service uses only `lab` network.
2. `lab` network is internal.
3. Every published port starts with `127.0.0.1:`.
4. Every service target ID is in `lab-sqli-001`, `lab-xss-001`, `lab-path-001`, `lab-clean-001`, `lab-webapp-a`, `lab-webapp-b`, or `lab-clean-control`.
5. No host network, default network, public bind, external route, or unrestricted network appears.

## Evidence

Record UTC timestamp, run ID, command, expected state, observed result, status, source, and evidence reference. Configuration checks do not produce runtime evidence; mark runtime status `UNRESOLVED` until approved observed evidence exists.
