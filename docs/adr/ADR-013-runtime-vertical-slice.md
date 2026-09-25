# Runtime vertical slice

## Status

`IMPLEMENTED` documentation decision; runtime evidence review pending.

## Context

Repository foundation is validated, but runtime was previously `SPEC_ONLY`. A bounded local slice is needed before adding adapters, planners, or vulnerability execution.

## Decision

Implement a stdlib-only clean-control slice with these boundaries:

- `lab-clean-001` is only target enabled by in-process runtime.
- Docker targets use one internal network and loopback-only host bindings.
- Runtime accepts typed allowlisted actions only; no shell, command, payload, credential, or dynamic action fields.
- Planner output remains proposal data until safety approval.
- `DRY_RUN=true` is default; executor supports only harmless clean-control actions.
- Health/reset fail closed and evidence is append-only with hash-chain verification.
- SQLi, XSS, path-traversal behavior, adapters, planners, and public/external endpoints remain out of scope.

## Alternatives Considered

Public or external targets, unpinned third-party runtime images, arbitrary command execution, and enabling exploit actions were rejected.

## Consequences

Local Docker health/reset checks and clean-control dry-run are executable. Runtime status remains `SPEC_ONLY` or `UNRESOLVED` until independent review and observed evidence support each exact claim. Vulnerability target implementation requires separate approved tasks.

## Risks

Docker daemon availability, image provenance, target reset semantics, evidence retention, and network isolation still need recorded runtime receipts. A passing config check does not prove isolation.

## Revisit Conditions

Revisit through approved source change, safety review, pinned image digest/version record, isolation receipt, target health/reset receipt, and append-only evidence review.
