# Validate Remote Enterprise Range Isolation

## Status

`IMPLEMENTED` validation checklist; observed infrastructure receipts pending.

## Required Checks

1. GNS3 and vCenter are reachable only from the management VPN/bastion.
2. Target data VLANs cannot reach GNS3, vCenter, control endpoints, evidence storage, or the public Internet unless a separately approved update path exists.
3. Management control endpoints require a valid bearer token and do not echo it.
4. Data endpoints return no reset/admin functionality.
5. DMZ cannot directly reach Restricted or Decoy; Internal is the only approved pivot boundary.
6. Control port `9090` cannot be reached through data-plane relay policy.
7. Safety Gate denial and kill switch produce zero provider/data dispatch.
8. Planner observations contain no full topology, VM IDs, GNS3 node IDs, management URLs, provider credentials, or raw secrets.
9. Restore returns every target to the approved expected state without changing evidence.
10. Packet-level and provider audit evidence bind to the exact configuration ID and source hash.

## Acceptance

All checks must have observed PASS evidence on the matching deployment and independent review. Offline unit tests, configuration parsing, API mocks, or successful login alone do not validate isolation.
