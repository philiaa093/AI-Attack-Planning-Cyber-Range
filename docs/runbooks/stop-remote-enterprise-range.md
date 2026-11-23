# Stop Remote Enterprise Range

## Status

`IMPLEMENTED` operator procedure; external execution and validation pending.

## Preconditions

The run is terminal or an authorized kill/stop decision exists. Evidence intent and final observed state must be durable before lifecycle shutdown.

## Procedure

1. Prevent new planner proposals and activate the run stop boundary.
2. Persist the final observation/result and verify evidence references.
3. Stop configured GNS3 nodes, then close the approved project.
4. Power off configured workload VMs through the provider.
5. Verify target/control endpoints are no longer reachable and preserve provider failure codes.

## Failure Handling

Aggregate partial-stop failures and escalate to the range owner. Do not delete VMs, projects, snapshots, evidence, or datastore files. Do not report the range stopped while any configured component remains active.
