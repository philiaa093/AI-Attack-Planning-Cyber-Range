# Cyber Range/Reset

> Status: IMPLEMENTED

Shared reset and health-check scripts for all cyber-range targets.

## Scripts

- `reset-all-targets.sh` — POST /reset to all targets, report pass/fail
- `health-check-all.sh` — GET /health on all targets, report pass/fail

## Usage

```bash
./reset-all-targets.sh localhost
./health-check-all.sh localhost
```

Runtime vertical slice implements internal-network health/reset. No runtime deployment claim beyond this slice. Status is IMPLEMENTED, not VALIDATED.
