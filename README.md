# AI Planner Cyber Range

Status: `VALIDATED` foundation contracts, safety gate, autonomous runtime, dashboard control center, and tests. Real LLM Provider E2E: `NOT RUN (CREDENTIAL NOT CONFIGURED)`. Results: `SPEC_ONLY`.

## Project Overview

Study bounded AI planning in an isolated Web Cyber Range. The system investigates autonomous, assisted, and manual security assessment workflows within strict safety boundaries. Scope: SQL injection, cross-site scripting, and path traversal in isolated lab targets. Planner modes: `RULE`, `LLM`, `RL`, `HYBRID`.

### Key Capabilities
- **One-Command Launch**: Zero-friction startup with idempotent service orchestration (`scripts/demo/start_control_center.ps1`).
- **Autonomous & Assisted Execution**: Closed-loop recon, active verification, and human-in-the-loop operator approval.
- **Centralized Safety Gate**: Strict target/action allowlisting, budget tracking, rate limiting, and zero-dispatch refusal guarantee.
- **Durable Cryptographic Evidence**: SHA-256 hashed, immutable append-only evidence recording and independent verifier.
- **Timeline Replay & Experiment Comparison**: 100% read-only run replay with zero network activity and side-by-side strategy diffing.

## Research Problem

Compare planner behavior under one typed action boundary, one safety policy, controlled scenarios, and evidence-backed evaluation. Prior research shows autonomous LLM agents risk jailbreaks, hallucinations, and unconstrained network dispatches. This project evaluates whether a Centralized Safety Gate can strictly enforce zero unauthorized network activity while maintaining autonomous goal progression.

## Research Questions

- How do `RULE`, `LLM`, `RL`, and `HYBRID` planners differ within one bounded action space?
- How does policy enforcement affect planner safety and refusal behavior?
- Which evidence-backed metrics support reproducible comparison?

## Scope

Isolated lab targets, approved scenarios, typed state, allowlisted actions, policy checks, planner proposals, evidence records, and reproducible comparison for SQLi, XSS, and path traversal.

## Out of Scope

Public targets, Internet scanning, production systems, credentials, arbitrary shell, dynamic actions, executable exploit payloads, autonomous deployment, live containment, and unverified results.

## Threat and Safety Boundary

Lab mode, target allowlist, action allowlist, input validation, approval, rate/order checks, refusal, audit, and restore are mandatory boundaries.

### Zero Network Dispatch Guarantee
Every action proposal must pass through the `CentralizedSafetyGate`. If a proposal targets an unapproved host, attempts prompt injection, or exceeds rate limits, the Gate denies the action and terminates dispatch immediately. In all denial scenarios, the invariant `network_dispatches == 0` is strictly maintained and verified by automated test suites.

## Architecture

The system follows a strict pipeline architecture ensuring that AI planners generate proposal data only, with all network dispatches governed by the Centralized Safety Gate:

```text
                    UI Control Center
                           │
                     REST / SSE
                           │
                      RunManager
                           │
                   AutonomousRunner
                    /      |      \
               State    Planner   Control
                          │
                     RULE / LLM
                          │
                     Typed Proposal
                          │
                     Safety Gate
                          │
                       Executor
                          │
                       ShopLab
                          │
                     Observation
                       /       \
                    State    Evidence
                               │
                            Verifier
                               │
                             Replan
```

### Component Roles
- **UI Control Center**: Web-based operator console providing real-time telemetry, presentation mode, run history, and comparison.
- **REST / SSE**: FastAPI control plane providing bidirectional telemetry and command endpoints.
- **RunManager**: Server-side run lifecycle orchestrator managing process states, approvals, and event queues.
- **AutonomousRunner**: Closed-loop execution engine coordinating state updates, planning, gating, and dispatch.
- **Planner (RULE / LLM)**: Generates typed action proposals conforming to `plan.schema.json`.
- **Manual Approval Boundary**: In `MANUAL` or `ASSISTED` mode, proposals pause before execution awaiting operator confirmation.
- **Safety Gate**: Independent policy engine evaluating identity, target, action, order, rate, and budget.
- **Executor & ShopLab**: Dispatches HTTP actions strictly to the isolated Docker cyber range (`lab-ecommerce`).
- **Evidence & Verifier**: Computes SHA-256 digests and validates cryptographic integrity of observations.

### Quick Start
```powershell
# Khởi chạy toàn bộ hệ thống (1 lệnh duy nhất)
.\scripts\demo\start_control_center.ps1

# Dừng an toàn hệ thống (chỉ kill process do session sở hữu)
.\scripts\demo\stop_control_center.ps1
```

## Planner Types

- `RULE`: Deterministic, contract-verified baseline implementing PTES/discovery workflows. Fully verified in unit and live tests.
- `LLM`: Schema-bound proposal generator using `PlannerStateAdapter`. Automatically activates fallback to `RULE` when external provider keys are absent.
- `RL`: Learns bounded action selection within finite state and action spaces.
- `HYBRID`: Combines deterministic heuristics with stochastic proposals without bypassing policy.

> [!NOTE]
> **LLM Provenance Disclosure**: `LLM PROVIDER E2E NOT RUN — CREDENTIAL NOT CONFIGURED (RULE BASELINE ACTIVE)`. The LLM planner architecture, adapter, validation, and fallback are fully tested; production provider credentials are intentionally omitted from source code.

## Cyber Range

Range is isolated and lab-only. Running on Docker Compose (`cyber-range/compose.yaml`), providing `gateway-ecommerce` (HAProxy on port 18088) and `lab-ecommerce` (OWASP Juice Shop / isolated target surface). Scenarios, resets, and evidence handling require explicit contracts before execution.

## Action Catalog

Actions are typed, finite, allowlisted, and policy-checked. Catalog contents (`ACTION-RECON-001`, `ACTION-RECON-002`, `ACTION-WEB-001`, etc.), IDs, parameters, ordering, and refusal behavior remain contract-owned; no arbitrary shell command or raw payload is permitted.

## Vulnerability Families

Study families are SQL injection, cross-site scripting, and path traversal within bounded laboratory targets.

## Evaluation Methodology

Plan, gate, execute only after approval, observe, record, evaluate, and reproduce. Compare planners using declared metrics and ground truth.

### Demonstration & Evaluation Modes
1. **Safe Recon (Autonomous)**: Deterministic closed-loop discovery (`RULE + AUTONOMOUS`).
2. **Safety Gate Refusal (Deny Demo)**: Injected malicious target triggers gate denial with 0 network dispatches.
3. **Assisted Approval**: Human-in-the-loop workflow requiring explicit operator approval before sensitive actions.
4. **Historical Timeline Replay**: 100% read-only event replay executing 0 live HTTP calls.
5. **Planner Comparison**: Quantitative strategy comparison between RULE and LLM proposals.

## Repository Structure

- `runtime/`: Executable Python packages grouped by responsibility: orchestration, discovery, safety, planners, state, evidence, evaluation, audit, and lab.
- `agent/`, `actions/`, `tools/`: Canonical planner contracts, state/perception components, action catalog, safety, and tool adapters.
- `dashboards/app/`: React frontend and FastAPI control plane; designs, exports, and screenshots stay under `dashboards/`.
- `cyber-range/`: Isolated lab targets, gateway, Compose, and restore assets.
- `scripts/demo/`: One-command launcher (`start_control_center.ps1`), safe shutdown (`stop_control_center.ps1`), runbook (`PROFESSOR_DEMO_V2.md`).
- `configs/`: Safety policies, action allowlists, target scopes, and budgets.
- `scenarios/`, `evaluation/`: Scenario definitions, evaluation contracts, metrics, and isolated ground truth.
- `tests/`: Runtime, backend, integration, safety, contracts, and focused unit checks.
- `docs/`: Canonical guides, task specifications, runbooks, ADRs, implementation notes, thesis drafts, and local literature.
- `evidence/`: Cryptographic runtime evidence logs and SHA-256 ledgers.
- `reports/`: Generated audit reports, defense receipts, and evaluation archives. Academic report sources live in `docs/thesis/`.

See [the folder map and placement rules](docs/repository-layout.md). Historical evidence, receipts, and frozen source archives retain their original paths and bytes; references inside them describe the recorded source version.

See [what belongs in Git](docs/git-policy.md) before adding generated runs, documents, or local configuration.

## Development Workflow

Read canonical context and plan first. Make smallest scoped change. Keep lab and status boundaries. Link claims to artifacts or evidence. Run unit test suites and scaffold validator before handoff; preserve exact receipts.

## Validation

All 468 Python tests across `tests/backend`, `tests/runtime`, `tests/planner`, `tests/safety`, and `scripts/demo` pass cleanly (0 failures, 0 errors). Frontend passes TypeScript check, Vitest suite, and production Vite build. Scaffold contracts validated via `scripts/validation/validate_scaffold.py`.

## Current Status

- Foundation contracts, safety, validator, and tests: `VALIDATED`.
- Autonomous Penetration Testing Runtime & Control Plane: `VALIDATED`.
- Real LLM Provider Live Execution: `NOT RUN (CREDENTIAL NOT CONFIGURED)`.
- Interactive Control Center & Demo Suite: `VALIDATED`.
- `TASK-026` and `TASK-032`: `DEFERRED`.

## Reproducibility

Reproduction requires approved manifests, exact dependency versions, target digest, model identity, action catalog, safety policy, ground truth, immutable evidence, and replay checks.

## References

See [`docs/references.md`](docs/references.md) and [`docs/versions.md`](docs/versions.md).
