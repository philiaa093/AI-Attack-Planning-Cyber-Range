# Restore Remote Enterprise Range

## Status

`IMPLEMENTED` bounded restore procedure; matching-infrastructure evidence pending.

## Preconditions

- No active episode or dispatch.
- Existing approved current snapshot for every configured workload VM.
- Snapshot provenance, creation time, expected hash/manifest, and restore owner recorded.
- Evidence from the preceding run is durable and outside mutable target storage.

## Procedure

1. Clear provider-local session tracking without deleting evidence.
2. Revert each configured VM to its approved current snapshot in reverse target order and require its vSphere task to reach terminal `success` before continuing.
3. Power on configured VMs in canonical order.
4. Reopen/start the approved GNS3 project and nodes if required.
5. Validate clean health, reset counters/state, route policy, egress denial, and planner zero-knowledge boundaries.

## Failure Handling

Any missing snapshot, revert error, unexpected power state, health mismatch, or target-state mismatch halts restore and blocks the next run. VMware snapshots are operational rollback points, not backups; maintain separate platform and application backups.
