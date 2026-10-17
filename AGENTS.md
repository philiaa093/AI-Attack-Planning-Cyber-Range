# Agent Governance

## Authority and Source Hierarchy

Read `PROJECT_CONTEXT.md`, `PROJECT_PLAN.md`, `TASKS.md`, relevant canonical documents, and applicable ADR before editing. User source and approved contracts outrank derivative documents. Evidence outranks prose for observed claims.

## Scope and Allowed Paths

Work only inside assigned allowlist. Do not use a fixed global code allowlist. Every task or tranche must declare its own explicit allowed paths in its approved specification. By default, agents have no repository-wide edit permissions. Documentation and governance tranches may only edit assigned governance and documentation files (`AGENTS.md`, `PROJECT_CONTEXT.md`, `PROJECT_PLAN.md`, `TASKS.md`, `docs/adr/**`). Technical and runtime tranches (e.g. RT-01..RT-07) must operate strictly within their tranche-specific allowed paths. Never edit contracts, configuration, catalog, scenario, evidence, or unrelated paths without explicit task scope.

## Trust Boundary and Input Validation

Validate and canonicalize every trust-boundary input. Safety gate rejects lab violations, target violations, action violations, malformed input, and missing approval. Planner output remains proposal data until policy approval.

## Security and Safety

Do not add public targets, credentials, production data, arbitrary shell, dynamic actions, exploit payloads, deployment claims, or live commands. Lab mode, target allowlist, action allowlist, approval, rate/order checks, refusal, audit, and restore remain mandatory.

## Evidence and Data Preservation

Evidence records UTC, run ID, source, hash, redaction, expected state, and observed state. Never overwrite existing evidence. Stop on evidence-loss risk or conflicting source.

## Status and Validation

Documentation and foundation artifacts may be `IMPLEMENTED` after creation but are not `VALIDATED` without checks and review. Runtime is `SPEC_ONLY` until approved executable scope exists and `UNRESOLVED` until observed evidence exists. `TASK-026` and `TASK-032` are `DEFERRED`.

## Change and Handoff

Make smallest reliable diff. Run required focused checks. Return exact changed files, deleted files, command receipts, unverified items, blockers, and pending handoff payload. Do not self-approve, finalize, append history, or claim runtime success.
