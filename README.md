# AI Planner Cyber Range

Status: `VALIDATED` foundation contracts, safety, validator, and tests. Runtime: `SPEC_ONLY`. Results: `SPEC_ONLY`.

## Project Overview

Study bounded AI planning in an isolated Web Cyber Range. Scope: SQL injection, cross-site scripting, and path traversal. Planner modes: `RULE`, `LLM`, `RL`, `HYBRID`.

## Research Problem

Compare planner behavior under one typed action boundary, one safety policy, controlled scenarios, and evidence-backed evaluation. No runtime or result claim exists until approved evidence exists.

## Research Questions

- How do `RULE`, `LLM`, `RL`, and `HYBRID` planners differ within one bounded action space?
- How does policy enforcement affect planner safety and refusal behavior?
- Which evidence-backed metrics support reproducible comparison?

## Scope

Isolated lab targets, approved scenarios, typed state, allowlisted actions, policy checks, planner proposals, evidence records, and later comparison for SQLi, XSS, and path traversal.

## Out of Scope

Public targets, Internet scanning, production systems, credentials, arbitrary shell, dynamic actions, executable exploit payloads, autonomous deployment, live containment, and unverified results.

## Threat and Safety Boundary

Lab mode, target allowlist, action allowlist, input validation, approval, rate/order checks, refusal, audit, and restore are mandatory boundaries. Documentation never authorizes runtime.

## Architecture

Scenario supplies typed state and target scope. Planner proposes bounded actions. Safety policy validates identity, target, action, order, rate, and approval. A future executor remains separately approved. Evidence records metadata and observations. Evaluation compares evidence with approved ground truth.

## Planner Types

`RULE` is deterministic baseline. `LLM` proposes schema-bound plans. `RL` learns within finite state and action spaces. `HYBRID` combines candidates without bypassing policy.

## Cyber Range

Range is isolated and lab-only. Scenario identity, target scope, vulnerability family, reset behavior, and evidence handling require explicit contracts before execution.

## Action Catalog

Actions are typed, finite, allowlisted, and policy-checked. Catalog contents, IDs, parameters, ordering, and refusal behavior remain contract-owned; no arbitrary command or payload is permitted.

## Vulnerability Families

Study families are SQL injection, cross-site scripting, and path traversal. Specific targets, endpoints, thresholds, and observations remain unresolved until approved manifests and evidence exist.

## Evaluation Methodology

Plan, gate, execute only after approval, observe, record, evaluate, and reproduce. Compare planners using declared metrics and ground truth. No measured values are available.

## Repository Structure

Root governance files define source of truth. `docs/` contains canonical concepts, guides, task specifications, runbooks, ADRs, references, and versions. `report/` contains chapter and appendix scaffolds. Runtime directories are outside this documentation repair scope.

## Development Workflow

Read canonical context and plan first. Make smallest scoped change. Keep lab and status boundaries. Link claims to artifacts or evidence. Run `make validate`, `make test`, and `make compile` before handoff; preserve exact receipts.

## Validation

Foundation contracts, safety, validator, and tests are `VALIDATED`; receipts and hashes are stored under `evidence/foundation/FOUNDATION-001/`. Runtime validation is not claimed.

## Current Status

Foundation contracts, safety, validator, and tests: `VALIDATED`. Runtime: `SPEC_ONLY`. Results: `SPEC_ONLY`. Final foundation review: `APPROVE`. `TASK-026` and `TASK-032`: `DEFERRED`.

## Reproducibility

Reproduction requires approved manifests, exact dependency versions, target digest, model identity, action catalog, safety policy, ground truth, immutable evidence, and replay checks. Unresolved values remain `UNRESOLVED`.

## References

See [`docs/references.md`](docs/references.md) and [`docs/versions.md`](docs/versions.md).
