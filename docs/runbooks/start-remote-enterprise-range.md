# Start Remote Enterprise Range

## Status

`IMPLEMENTED` operator procedure; external execution and validation pending.

## Preconditions

- Dedicated isolated GNS3/vSphere lab, not a production business network.
- Management access only through the approved VPN/bastion.
- Trusted TLS certificates for GNS3, vCenter, data endpoints, and control endpoints.
- Approved current snapshots and canonical VM/node identifiers.
- Least-privilege GNS3 and vSphere service identities.
- Per-run target/action approval, evidence destination, kill switch, and restore owner.

## Required Configuration

Create a deployment-specific copy of `configs/lab/remote-range.example.json` outside the repository. Keep only environment-variable names in the JSON. Supply `GNS3_USERNAME`, `GNS3_PASSWORD`, `VSPHERE_USERNAME`, `VSPHERE_PASSWORD`, and `RANGE_CONTROL_TOKEN` through the operator's secret manager. The control token must contain at least 32 characters.

## Procedure

1. Validate the closed configuration schema and exact five-target set offline.
2. Verify management endpoints are unreachable from target VLANs and public networks.
3. Verify GNS3 project/node IDs and vSphere VM IDs against the approved manifest.
4. Confirm no run is active and evidence storage is writable without overwrite.
5. Create the remote provider, validate its declared capabilities, and obtain per-run approval.
6. Start workload VMs, open the approved GNS3 project, and start only configured nodes.
7. Require all VM, node, TLS, and target health checks to pass before allowing an episode.

## Failure Handling

Stop on missing secrets, TLS failure, target-set mismatch, API authorization failure, partial start, unexpected VM/node identity, failed health check, or evidence risk. A partial start must trigger bounded rollback and a recorded operator incident; it must not start a planner run.

## Evidence

Record UTC, run ID, configuration ID, source hash, provider kind, approved manifest identity, expected/observed health, and redacted failure codes. Never record passwords, API sessions, bearer tokens, or raw provider responses containing secrets.
