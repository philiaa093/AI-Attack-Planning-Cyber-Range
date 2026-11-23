# Remote Enterprise Range Provider

## Status

`IMPLEMENTED` architecture decision for RT-06P. Offline contract validation is implemented; deployment and independent validation on user-owned GNS3/vSphere infrastructure remain pending.

## Context

RT-06V proves the live-range contract on loopback and Docker networks. A production-grade research range needs dedicated compute, persistent virtualization, routed network appliances, management isolation, restore, and remote lifecycle control without granting infrastructure authority to the planner.

GNS3 and vSphere have different responsibilities. GNS3 owns the approved emulated topology and network-node lifecycle. vSphere owns workload VM power and baseline snapshots. Neither API is planner-visible. The executor continues to expose only the canonical bounded action contract.

## Decision

1. Introduce a provider-neutral `RangeProvider` contract used by loopback, Docker, and remote implementations.
2. Implement `GNS3VSphereRangeProvider` as an external-infrastructure provider with fixed API paths only. Dynamic API paths, arbitrary URL forwarding, shell execution, guest process execution, VM creation, topology mutation, and snapshot creation are excluded.
3. Split target data-plane handlers from an authenticated management control plane. Reset and route-control operations are removed from target handlers and require a bearer secret supplied through an environment reference.
4. Require HTTPS URLs, exact canonical target sets, closed configuration objects, and environment-variable references instead of credential values in configuration.
5. Keep planner-visible scope observation-derived. Remote configuration, VM IDs, node IDs, management URLs, credentials, and control tokens never enter planner context or observations.
6. Restore uses an existing approved current snapshot for each configured workload VM. The provider polls the returned vSphere task to terminal `success` before continuing and halts on error, invalid state, or timeout. Snapshot existence, provenance, retention, backup, and application consistency remain operator responsibilities and must be validated before a run.
7. Authenticated provider requests are pinned to configured hostnames, bypass ambient proxy configuration, and do not follow redirects. Target data/control URLs, GNS3 node IDs, and vSphere VM IDs are unique; HTTPS public-IP literals are rejected.
8. Remote activation requires explicit per-run approval, infrastructure connectivity, certificate trust, GNS3/vSphere identities with least privilege, and isolation evidence. Offline mocks do not constitute external validation.

## Network Planes

- **Management plane**: GNS3 controller, vSphere API, target control endpoints, bastion/VPN, and operator access.
- **Data plane**: DMZ, Internal, Restricted, Decoy, and Clean target traffic processed through bounded actions.
- **Evidence/observation plane**: append-only evidence and normalized observations. It receives results but cannot mutate topology or target state.

Management traffic must not traverse the target relay. Data-plane endpoints do not implement reset or route-admin operations. The planner cannot call any management endpoint.

## Consequences

- Existing live environment and executor depend on the provider contract rather than a Docker-specific harness.
- Remote configuration is portable but intentionally contains no usable credential.
- Real deployment cannot be marked `VALIDATED` until matching-source GNS3/vSphere tests, restore evidence, VLAN/egress checks, and independent review complete.
- Failure of lifecycle, restore, authorization, TLS, or health checks stops the operation; it is not converted into a successful or synthetic run.

## Alternatives Rejected

- Exposing GNS3 or vCenter APIs directly to planners.
- Storing passwords, API sessions, or control tokens in repository configuration.
- Keeping `/reset` and admin routes on target data-plane handlers.
- Treating VMware snapshots as backups or accepting unverified snapshot provenance.
- Replacing Safety Gate authorization with network reachability or provider eligibility.

## Revisit Conditions

Revisit only through approved source/contract/safety review and evidence from the exact remote infrastructure build. Adding NSX, physical firewalls, Active Directory, new target families, or guest-process execution requires separate scope.
