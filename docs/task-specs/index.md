# Task Specifications

`TASKS.md` is status source of truth.

- [TASK-001-foundation-validator.md](TASK-001-foundation-validator.md) — `VALIDATED`; dependency: none
- [TASK-002-root-governance-docs.md](TASK-002-root-governance-docs.md) — `VALIDATED`; dependency: TASK-001
- [TASK-003-safety-contracts.md](TASK-003-safety-contracts.md) — `VALIDATED`; dependency: TASK-001
- [TASK-004-action-catalog.md](TASK-004-action-catalog.md) — `VALIDATED`; dependency: TASK-003
- [TASK-005-state-contract.md](TASK-005-state-contract.md) — `VALIDATED`; dependency: TASK-001
- [TASK-006-observation-contract.md](TASK-006-observation-contract.md) — `VALIDATED`; dependency: TASK-001
- [TASK-007-evidence-contract.md](TASK-007-evidence-contract.md) — `VALIDATED`; dependency: TASK-001
- [TASK-008-scenario-contract.md](TASK-008-scenario-contract.md) — `VALIDATED`; dependency: TASK-001, TASK-003
- [TASK-009-ground-truth-contract.md](TASK-009-ground-truth-contract.md) — `VALIDATED`; dependency: TASK-008
- [TASK-010-experiment-contract.md](TASK-010-experiment-contract.md) — `VALIDATED`; dependency: TASK-007, TASK-008
- [TASK-011-cyber-range-network.md](TASK-011-cyber-range-network.md) — `SPEC_ONLY`; dependency: TASK-003
- [TASK-012-web-target-a.md](TASK-012-web-target-a.md) — `SPEC_ONLY`; dependency: TASK-011
- [TASK-013-web-target-b.md](TASK-013-web-target-b.md) — `SPEC_ONLY`; dependency: TASK-011
- [TASK-014-clean-control-target.md](TASK-014-clean-control-target.md) — `SPEC_ONLY`; dependency: TASK-011
- [TASK-015-discovery-adapter.md](TASK-015-discovery-adapter.md) — `SPEC_ONLY`; dependency: TASK-004, TASK-006, TASK-011
- [TASK-016-zap-adapter.md](TASK-016-zap-adapter.md) — `SPEC_ONLY`; dependency: TASK-004, TASK-006, TASK-011
- [TASK-017-nuclei-adapter.md](TASK-017-nuclei-adapter.md) — `SPEC_ONLY`; dependency: TASK-004, TASK-006, TASK-011
- [TASK-018-observation-normalizer.md](TASK-018-observation-normalizer.md) — `SPEC_ONLY`; dependency: TASK-006, TASK-015
- [TASK-019-knowledge-state-store.md](TASK-019-knowledge-state-store.md) — `SPEC_ONLY`; dependency: TASK-005, TASK-018
- [TASK-020-planner-interface.md](TASK-020-planner-interface.md) — `SPEC_ONLY`; dependency: TASK-004, TASK-005, TASK-019
- [TASK-021-rule-based-planner.md](TASK-021-rule-based-planner.md) — `SPEC_ONLY`; dependency: TASK-020
- [TASK-022-llm-planner.md](TASK-022-llm-planner.md) — `SPEC_ONLY`; dependency: TASK-020, TASK-003
- [TASK-023-rl-environment.md](TASK-023-rl-environment.md) — `SPEC_ONLY`; dependency: TASK-004, TASK-005, TASK-006, TASK-009
- [TASK-024-reward-model.md](TASK-024-reward-model.md) — `SPEC_ONLY`; dependency: TASK-023
- [TASK-025-q-learning-baseline.md](TASK-025-q-learning-baseline.md) — `SPEC_ONLY`; dependency: TASK-023, TASK-024
- [TASK-026-dqn-ppo-candidate.md](TASK-026-dqn-ppo-candidate.md) — `DEFERRED`; dependency: TASK-023, TASK-024
- [TASK-027-hybrid-planner.md](TASK-027-hybrid-planner.md) — `SPEC_ONLY`; dependency: TASK-021, TASK-022, TASK-025
- [TASK-028-experiment-runner.md](TASK-028-experiment-runner.md) — `SPEC_ONLY`; dependency: TASK-010, TASK-020
- [TASK-029-metrics-engine.md](TASK-029-metrics-engine.md) — `SPEC_ONLY`; dependency: TASK-009, TASK-028
- [TASK-030-held-out-evaluation.md](TASK-030-held-out-evaluation.md) — `SPEC_ONLY`; dependency: TASK-028, TASK-029
- [TASK-031-statistical-analysis.md](TASK-031-statistical-analysis.md) — `SPEC_ONLY`; dependency: TASK-030
- [TASK-032-dashboard.md](TASK-032-dashboard.md) — `DEFERRED`; dependency: TASK-028, TASK-029
- [TASK-033-report-artifact-generator.md](TASK-033-report-artifact-generator.md) — `SPEC_ONLY`; dependency: TASK-029
- [TASK-034-reproducibility-package.md](TASK-034-reproducibility-package.md) — `SPEC_ONLY`; dependency: TASK-030, TASK-031, TASK-033
- [TASK-035-final-foundation-audit.md](TASK-035-final-foundation-audit.md) — `SPEC_ONLY`; dependency: all-required
