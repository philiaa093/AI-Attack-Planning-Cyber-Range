# Tasks

Status vocabulary: `SPEC_ONLY`, `TBD`, `UNRESOLVED`, `IMPLEMENTED`, `VALIDATED`, `DEFERRED`, `BLOCKED`.

Tasks 001-010 are `VALIDATED` by foundation evidence `EV-FOUNDATION-001-001` through `EV-FOUNDATION-001-004`. A local-only runtime vertical slice covers bounded clean-control health/reset and dry-run; runtime evidence review remains `UNRESOLVED`. Tasks 012-014 are `VALIDATED` by runtime target evidence. Tasks 015-017 are `VALIDATED` by adapter evidence `EV-ADAPTERS-015-001` through `EV-ADAPTERS-017-003`; scaffold validator passes, 87 unit tests pass (27 adapter-specific), all Python files compile, schema-conformant output verified. Tasks 011, 018-025, 027-031, and 033-035 remain `SPEC_ONLY`. Tasks 026 and 032 are `DEFERRED`; no result claim exists.

| ID | Descriptive name | Status | Dependencies |
|---|---|---|---|
| TASK-001 | Foundation validator | `VALIDATED` | none |
| TASK-002 | Root governance docs | `VALIDATED` | TASK-001 |
| TASK-003 | Safety contracts | `VALIDATED` | TASK-001 |
| TASK-004 | Action catalog | `VALIDATED` | TASK-003 |
| TASK-005 | State contract | `VALIDATED` | TASK-001 |
| TASK-006 | Observation contract | `VALIDATED` | TASK-001 |
| TASK-007 | Evidence contract | `VALIDATED` | TASK-001 |
| TASK-008 | Scenario contract | `VALIDATED` | TASK-001, TASK-003 |
| TASK-009 | Ground-truth contract | `VALIDATED` | TASK-008 |
| TASK-010 | Experiment contract | `VALIDATED` | TASK-007, TASK-008 |
| TASK-011 | Cyber range network | `SPEC_ONLY` | TASK-003 |
| TASK-012 | Web target A | `VALIDATED` | TASK-011 |
| TASK-013 | Web target B | `VALIDATED` | TASK-011 |
| TASK-014 | Clean control target | `VALIDATED` | TASK-011 |
| TASK-015 | Discovery adapter | `VALIDATED` | TASK-004, TASK-006, TASK-011 |
| TASK-016 | ZAP adapter | `VALIDATED` | TASK-004, TASK-006, TASK-011 |
| TASK-017 | Nuclei adapter | `VALIDATED` | TASK-004, TASK-006, TASK-011 |
| TASK-018 | Observation normalizer | `SPEC_ONLY` | TASK-006, TASK-015 |
| TASK-019 | Knowledge-state store | `SPEC_ONLY` | TASK-005, TASK-018 |
| TASK-020 | Planner interface | `SPEC_ONLY` | TASK-004, TASK-005, TASK-019 |
| TASK-021 | Rule-based planner | `SPEC_ONLY` | TASK-020 |
| TASK-022 | LLM planner | `SPEC_ONLY` | TASK-020, TASK-003 |
| TASK-023 | RL environment | `SPEC_ONLY` | TASK-004, TASK-005, TASK-006, TASK-009 |
| TASK-024 | Reward model | `SPEC_ONLY` | TASK-023 |
| TASK-025 | Q-learning baseline | `SPEC_ONLY` | TASK-023, TASK-024 |
| TASK-026 | DQN/PPO candidate | `DEFERRED` | TASK-023, TASK-024 |
| TASK-027 | Hybrid planner | `SPEC_ONLY` | TASK-021, TASK-022, TASK-025 |
| TASK-028 | Experiment runner | `SPEC_ONLY` | TASK-010, TASK-020 |
| TASK-029 | Metrics engine | `SPEC_ONLY` | TASK-009, TASK-028 |
| TASK-030 | Held-out evaluation | `SPEC_ONLY` | TASK-028, TASK-029 |
| TASK-031 | Statistical analysis | `SPEC_ONLY` | TASK-030 |
| TASK-032 | Dashboard | `DEFERRED` | TASK-028, TASK-029 |
| TASK-033 | Report artifact generator | `SPEC_ONLY` | TASK-029 |
| TASK-034 | Reproducibility package | `SPEC_ONLY` | TASK-030, TASK-031, TASK-033 |
| TASK-035 | Final foundation audit | `SPEC_ONLY` | all-required |

## Blockers

Foundation blockers: none. Runtime authorization, isolated network deployment, target health/reset evidence, tool versions, planner implementations, and experiments remain `SPEC_ONLY` or `UNRESOLVED`. No public-target work is permitted.
