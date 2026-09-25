# Start cyber range

## Status

`IMPLEMENTED` local runtime procedure.

## Purpose

Start fixed local lab targets for bounded health, reset, and mapped action checks.

## Preconditions

Docker daemon available. No public target, credential, arbitrary payload, shell, or external network.

## Required Configuration

Use `cyber-range/compose.yaml`. Published ports use Docker Desktop host publishing: 18081 SQLi, 18082 XSS, 18083 path traversal, 18084 clean control. Executor accepts loopback URLs only; host firewall must restrict these ports to local use.

## Safety Checks

Confirm exact target IDs, loopback ports, internal Docker network, and fixed action mapping. Stop on mismatch.

## Inputs

No user payload. Executor target IDs and action IDs must match allowlists.

## Procedure

```text
docker compose -f cyber-range/compose.yaml up -d --build
GET  http://127.0.0.1:18081/health
POST http://127.0.0.1:18081/reset
POST http://127.0.0.1:18081/action?action=ACTION-WEB-001
```

Repeat mapped actions for XSS (`ACTION-WEB-002`) and path traversal (`ACTION-WEB-003`).

## Expected Artifacts

Deterministic JSON observations containing target ID, action ID, family, fixed fixture evidence, vulnerability result, and reset count.

## Validation

Run `python -B -m unittest discover -s tests -p "test_*.py" -v`, then compose health/reset/action checks. Run compose down after checks.

## Failure Handling

Stop on non-loopback binding, unknown ID, invalid action, HTTP failure, malformed JSON, or evidence-loss risk.

## Cleanup

```text
docker compose -f cyber-range/compose.yaml down
```

## Evidence

Record exact commands and JSON responses. No credentials or external network.

## Related Tasks

Runtime vertical slice replaces prior SPEC_ONLY placeholder for local lab behavior.
