# Project Context

## Purpose

Study bounded AI planning in an isolated Web Cyber Range. Target classes: SQL injection, cross-site scripting, and path traversal. Planner modes: `RULE`, `LLM`, `RL`, `HYBRID`.

## Architecture

Scenario supplies typed state and target scope. Planner proposes bounded actions. Safety policy validates identity, target, action, order, rate, and approval. Future executor performs only approved actions. Evidence recorder stores immutable run metadata and observations. Evaluation compares evidence with approved ground truth.

## Planner model

`RULE` is deterministic baseline. `LLM` proposes schema-bound plans subject to policy. `RL` learns in finite state/action space. `HYBRID` combines candidates without bypassing policy.

## Current state

Foundation contracts, safety, validator, tests, and full requested scaffold tree are `VALIDATED` by `evidence/foundation/FOUNDATION-001/manifest.json` and `evidence/foundation/FOUNDATION-001-COMPLETENESS/manifest.json`. Final read-only reviews approved both foundation safety and tree completeness. Runtime and results remain `SPEC_ONLY`; runtime observations, metrics, deployment, model training, and result claims remain `UNRESOLVED`.

## Boundaries

No public target, Internet scanning, autonomous attack runtime, arbitrary shell, dynamic action, credential, production log, exploit payload, or deployment approval. Exact versions, endpoints, thresholds, latency, model weights, and measured metrics are `UNRESOLVED`.

## Source hierarchy

User source of truth and approved contracts outrank derivative guides. `PROJECT_PLAN.md` governs phases. `TASKS.md` governs work state. ADRs govern durable decisions. Evidence governs observed claims.
