# Sequential implementation handoff

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

Implementation subset: `IMPLEMENTED`; independent review: `UNRESOLVED`.
Canonical task statuses remain unchanged, including TASK-026 and TASK-032.

User request: implement the five proposed follow-ups in order, starting with
truthful dashboard reporting. Scope: dashboard reporting/UI and focused tests,
read-only historical inventory, offline normalizer/store/planner integration,
offline evaluation/report preparation. Existing evidence, contracts, configuration,
action catalog, target implementations and historical task receipts are preserved.

## 1. Dashboard reporting

History now verifies record schemas, run identity, bounded payload paths, SHA-256
and reference membership before counting verified records. This check does not
authenticate the producer or certify policy adherence. Missing measurements remain
null; absent report metadata cannot imply RULE, zero dispatches or completion.
Missing event ledgers no longer generate synthetic starts, permits or completion.
Comparisons and exports disclose descriptive scope; provider configuration never
implies provider E2E verification.

Checks: 12 reporting regressions PASS; frontend typecheck PASS; frontend 16 tests
PASS; production build PASS. The first historical API regression run had 8 PASS
and 1 FAIL because an old test required fabricated events for a directory without
a ledger. The test now uses an actual temporary event ledger; the final rerun is
recorded separately: 9 API history tests PASS, exit 0. No historical evidence was
changed to satisfy the test.

## 2. Historical inventory and review prerequisites

Preservation checkpoint observed during this build (before new integration work):

| Root | Files | SHA-256 of sorted relative-path/file-hash inventory |
|---|---:|---|
| evidence/runtime | 739 | 5f72f1d44a5106e1eded60552b1e70d4de641dd492cf7be16554f08d291a5844 |
| scripts/demo/demo-output | 3246 | 2e3c9494a20158601d343cf57bde9f53efb3713b85a966c6e71c26218d5ec40a |
| reports/evaluation-runs | 12 | 0e9879172c245687427ee9f194ca0c23373256d9c8b68c6fba46cd151eb7c8f6 |

These are current preservation observations, not proof of pre-run source binding.
The three original RUN-EVAL directories recorded in [audit_pipeline.md](audit_pipeline.md)
remain missing. No historical recovery or substitute experiment was performed.

Repository gate at the first check returned exit 1 with 27 generated-bytecode
errors outside the reporting diff. All Python checks in this build used `-B`.
No unrelated cache, user process or evidence directory was removed. Missing
original evidence and repository gate failure remain distinct blockers.

Project Context currently contains conflicting ShopLab/Oscar direction statements.
Target adoption/migration is not implemented from those conflicting statements.
This does not change the proposal-only/offline reporting scope.

Independent review has not occurred. No available local review tool can certify
this dirty build; the supplied Code Review tool only reads pull-request CI.
Preparing this handoff does not satisfy the independent-review acceptance.

## 3. Offline perception, evidence and planner integration

[offline_review_pipeline.py](../../runtime/evaluation/offline_review_pipeline.py) loads a pinned local
Nuclei envelope under an explicit input root. The existing Task-018 normalizer
produces minimized observations; the recorder persists them before Task-019
ingestion. StateManager remains the budget owner: ingest consumes its existing
one-observation action cost, zero imported network requests; proposing does not
charge it a second time. Identical retries, including consumer restarts, retain
the original receipt. Hash/reference/source/context mismatch or write failure
halts the consumer; partial records are retained.

Task-020 snapshots feed the fixed Task-021 RULE metadata reviewer. Proposal
evidence references and the proposal record bind back to the ingested observation.
No scanner, target transport, provider, autonomous dispatch or LLM/RL/HYBRID
execution was added. Full multi-planner integration remains `UNRESOLVED`.
Seven focused tests PASS; dependency regressions PASS: normalizer 24, store 21,
interface 28 and RULE planner 28. No canonical contract or policy was edited.

## 4. Evaluation protocol and package verification

[evaluation_protocol_io.py](../../runtime/evaluation/evaluation_protocol_io.py) serializes/loads the
existing immutable replay protocol. Loading requires a supplied file hash,
approved input root, closed fields and bounded data. Existing protocol checks
reject split-content contamination and unequal spaces/budgets. CLI adds the
paired `--protocol` / `--protocol-sha256` options under runtime; policy choices
remain the two fixed synthetic selectors. The input pin is stored in the run
configuration and the parser/support source hashes are captured.

[evaluation_package.py](../../runtime/evaluation/evaluation_package.py) checks a pinned completion manifest
and all 11 required artifact hashes/envelopes read-only. It does not authenticate
the producer or certify experimental conclusions. Seven protocol/package tests
and 13 runner regressions PASS, plus 7 metrics tests PASS.

One new run was executed with `python -B -m runtime.evaluate_all --demo`, exit 0:
RUN-EVAL-9741738ab7bd41de9cff2d40311352bd report (local artifact, gitignored: `../../runtime/evaluation-runs/RUN-EVAL-9741738ab7bd41de9cff2d40311352bd/report.md`).
It contains 20 synthetic metadata-review episodes, five seeds, one scenario per
evaluation split, and six planned statistical comparisons. It is not a restored
historical run or a RULE/LLM/RL/HYBRID research benchmark. Its manifest SHA-256 is
ac5e0dd39643217b9e7521775592c529d4c868f4f0a3c5c4bc45a6188fcbc3c1;
11 artifacts passed the new package verifier. Live evaluation, canonical EXP/SCN
acceptance, dependency lock and independent review remain `UNRESOLVED`.

## 5. Presentation and reproducibility preparation

Demo view increases small-text sizes and contrast; medium-width screens use
fewer cards per row. Reduced-motion preference disables dashboard pulses.
History hides named test runs by default, with an explicit toggle. Milestone
view filters telemetry while detailed view retains it. Missing action/HTTP
metadata uses unknown markers instead of invented discovery actions or HTTP 200.

Typecheck, 16 frontend tests and production build PASS. Browser inspection of
the existing loopback frontend failed with connection refused; no development
server, lab or provider was started for visual inspection. Actual viewport QA
and browser SSE E2E remain unverified.

## Final command receipts

All final rows below are new observed checks for this build, not promotions of
historical task receipts. Duplicate reruns are not added to the 172-test total.

| Invocation | Exit | Observed result |
|---|---:|---|
| `python -B -m unittest discover -s tests/backend -p test_history_truthfulness.py -v` | 0 | 12 PASS |
| `python -B -m unittest discover -s tests/backend -p test_run_history.py -v` | 0 | 9 PASS; later duration guard covered by focused reporting test |
| `python -B -m unittest discover -s tests/runtime -p test_offline_review_pipeline.py -v` | 0 | 7 PASS |
| `python -B -m unittest discover -s tests/runtime -p test_evaluation_protocol_io.py -v` | 0 | 7 PASS |
| `python -B -m unittest discover -s tests/runtime -p test_evaluate_all.py -v` | 0 | 13 PASS |
| `python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py -v` | 0 | 21 PASS |
| `python -B -m unittest discover -s tests/runtime -p test_planner_interface.py -v` | 0 | 28 PASS |
| `python -B -m unittest discover -s tests/runtime -p test_rule_based_planner.py -v` | 0 | 28 PASS |
| `python -B -m unittest discover -s tests/integration -p test_nuclei_normalizer.py -v` | 0 | 24 PASS |
| `python -B -m unittest discover -s tests/evaluation -p test_metrics.py -v` | 0 | 7 PASS |
| `npm.cmd run test -- --maxWorkers=1 --minWorkers=1 --no-file-parallelism` | 0 | 16 PASS, frontend cwd |
| `npm.cmd run typecheck` | 0 | PASS; final production build also typechecks |
| `npm.cmd run build` | 0 | PASS, frontend cwd |
| `python -B -m runtime.evaluate_all --demo` | 0 | New synthetic run only |
| `python -B scripts/validation/validate_scaffold.py` | 1 | 27 forbidden bytecode files; no source/schema errors in this diff at last check |
| `git diff --check -- runtime/evaluate_all.py runtime/offline_review_pipeline.py runtime/evidence_readonly.py dashboards/app tests/backend tests/runtime/test_offline_review_pipeline.py tests/runtime/test_evaluation_protocol_io.py` | 0 | Scoped whitespace PASS; untracked Python files additionally inspected |
| Python AST/whitespace check using `ast.parse` | 0 | 12 edited Python files PASS |

Initial integration checks failed on a redacted context-label mismatch and an
incorrect test assumption that ingest did not consume the existing action budget.
Context binding now uses a hash and the test checks exactly one ingest charge.
These failed attempts remain failed; final seven-test PASS is a separate receipt.

## Exact source files changed or created

```text
dashboards/app/backend/models.py
dashboards/app/backend/run_history.py
dashboards/app/backend/run_manager.py
dashboards/app/frontend/src/api/recordedValue.ts
dashboards/app/frontend/src/api/types.ts
dashboards/app/frontend/src/pages/ControlCenter.tsx
dashboards/app/frontend/src/pages/RunComparisonPage.tsx
dashboards/app/frontend/src/pages/RunDetailPage.tsx
dashboards/app/frontend/src/pages/RunHistoryPage.tsx
dashboards/app/frontend/src/components/events/EventFeed.tsx
dashboards/app/frontend/src/components/presentation/PresentationHero.tsx
dashboards/app/frontend/src/index.css
dashboards/app/frontend/src/__tests__/Phase6Features.test.tsx
runtime/evidence_readonly.py
runtime/offline_review_pipeline.py
runtime/evaluation_protocol_io.py
runtime/evaluation_package.py
runtime/evaluate_all.py
runtime/sequential_work_20261013.md
tests/backend/test_history_truthfulness.py
tests/backend/test_run_history.py
tests/runtime/test_offline_review_pipeline.py
tests/runtime/test_evaluation_protocol_io.py
```

Generated outputs: the 12 files under the new evaluation run linked above, frontend
dist (generated build), and a unique source-manifest directory recorded in the
handoff response. No baseline source or evidence file was deleted. A temporary
helper created during this build was moved to runtime/evidence_readonly.py;
it was not a user baseline file. No commit, status promotion or history append.

## Pending handoff payload

```text
build_id: BUILD-SEQUENTIAL-20261013-001
base_head: d9ae6ca0d5bb03ce381d7249665237f272eeddc9
plan_id: PLAN-SEQUENTIAL-FOLLOWUPS-20261013-001
task_scope: dashboard truthfulness; SL-12 preparation; offline integration/evaluation
historical_evidence_mutation: none
deleted_files: none
independent_review: UNRESOLVED
handoff_state: HANDOFF_BLOCKED
blockers: generated bytecode at repository gate; missing original evaluation runs;
          independent reviewer unavailable; conflicting target direction documents
pending: resolve repository cache scope without losing evidence; independent review;
         original-evidence disposition; controlled four-planner protocol and browser QA
```
