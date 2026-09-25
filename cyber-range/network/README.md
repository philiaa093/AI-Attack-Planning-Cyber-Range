# Cyber Range Network

> Status: SPEC_ONLY

## Status

`IMPLEMENTED` configuration and isolation test; runtime evidence remains `UNRESOLVED`.

## Contract

`cyber-range/compose.yaml` runs executor and allowlisted lab targets on one Docker network with `internal: true`. Published ports bind to `127.0.0.1` only. Target IDs must remain within approved lab allowlist.

## Validation

Run from repository root:

```text
python -m unittest tests.integration.test_network_isolation -v
docker compose -f cyber-range/compose.yaml config
```

No runtime authorization. No public target or external network. Stop on malformed configuration, unknown target ID, non-loopback port, or evidence-loss risk.
