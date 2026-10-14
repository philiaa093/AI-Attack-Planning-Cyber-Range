# Offline replay reward, masks and evaluation

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

## Status and scope

`IMPLEMENTED` for the wrapper/evaluation subset requested on 2026-10-12;
not `VALIDATED`. [TASK-026](../task-specs/TASK-026-dqn-ppo-candidate.md)
remains `DEFERRED`. No DQN/PPO model, training result or checkpoint is provided.
Independent review, durable evidence, learned-model/library integration and full
research evaluation remain `UNRESOLVED`. TASK-030 is not completed by this helper.
Handoff is `HANDOFF_BLOCKED`: the final repository gate failed on unrelated
workspace artifacts after the earlier passing gate; see the final receipt below.

Implementation-build changes were five new files: [wrapper](../../runtime/evaluation/replay_wrappers.py),
[evaluator](../../runtime/evaluation/offline_evaluation.py), this document,
[wrapper tests](../../tests/runtime/test_replay_wrappers.py) and
[evaluation tests](../../tests/runtime/test_offline_evaluation.py). Deleted files: none.
Existing source, evidence, task statuses, configuration, catalog, contracts and
scenarios were preserved in that build. The starting working tree already had
unrelated changes. The later documentation-only synchronization is scoped below.

Sources read: PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md; TASK-023/024/026,
TASK-010/030, docs/experiment-design.md; ADR-004/005/006/007/008/009/010/011/012/013;
Task-023 environment, Task-024 scorer and Task-025 public-state design.
Gymnasium and NumPy use the existing [dependency declaration](../../runtime/evaluation/requirements.txt).
No dependency was installed. The SB3-contrib MaskablePPO and SB3 vector-environment
official documentation was consulted for the mask API and terminal bootstrapping;
consult [source register](../references.md) for project reference governance.

## Wrapper contract

`ReplayRewardMaskWrapper` accepts only the exact TASK-023 `ReplayAssessmentEnv`.
No scanner, provider, executor or transport adapter is accepted. Replay operation
indices are not canonical action IDs. Caller Python code is trusted; the type check
is not a sandbox or proof of OS isolation. Underlying replay approval/order/rate/
budget/audit checks remain authoritative even if an action ignores its mask.

`reset(seed, options)` preserves the base API and emits no reward.
`step(action)` first calls the base step; after its audit and state commit succeed,
it calls `score_replay_reward(info["outcome"])` exactly once and replaces the
illustrative reward. First reads earn progress once; repeated reads get Task-024's
NO_PROGRESS penalty. Report candidate values and declared replanning earn no bonus.
Malformed actions retain base refusal/stop behavior and are not scored as committed
steps. Reset and mask queries never invoke the scorer.

If audit fails, no reward is scored. If validation/scoring fails after base commit,
the wrapper invalidates its cached mask and refuses another step until reset.
It cannot undo the committed base transition and never retries/rescores it.
Close permanently invalidates the wrapper and closes the simulator. Reset only
restores simulator memory; earlier base audit records remain intact.

Observation version: `replay-normalized-v1`; reward version: `task024-fixed-v1`.
Trust-boundary observations have closed keys, exact array dtypes, matching shapes,
binary masks and valid ranges. NaN/Inf, out-of-range values and malformed masks are
rejected, not clipped. All observations, info masks and mask queries are detached.

| Key | Shape / dtype | Encoding |
|---|---|---|
| assets | N x 4, int8 | Original observed binary flags |
| inventory_counts | N, float32 | log1p(count) / log1p(10000) |
| remaining_budget | 1, float32 | Original fraction in [0, 1] |
| action_mask | 2N+1, int8 | Next-decision admissibility, 0/1 |
| read_age | 1, float32 | -1 before any successful read; otherwise ticks since read / 10000 |

Read age comes only from committed outcomes. A permitted repeated read resets age;
denials increment elapsed age without resetting it. It distinguishes rate histories
that could otherwise have identical masks. Unknown report and observed negative
metadata remain distinguishable through review/availability flags. No ID, raw report,
ground truth, secret or unrevealed candidate is added to the observation.

The expanded flattened size is **7N+3**. The earlier illustrative 5N+1 extractor is
not compatible with this version. Future `MultiInputPolicy` must consume every key
(the standard combined extractor or an explicit new extractor). N stays fixed
within an experiment; varying N requires a separately reviewed model design.
Normalization uses constants, with no fitting or updates on validation/test data.

`action_masks()` returns a boolean array where True means admissible. It requires
an active episode. An empty mask must cause the coordinator to stop before model
sampling; no fallback FINISH or uniform random action is synthesized. Future
MaskablePPO inference must pass this mask, and training must handle empty masks.
Subprocess/vectorized mask access and mask-aware SB3 callbacks remain untested.
Standard DQN/PPO do not consume masks automatically. Masked DQN would need consistent
selection/exploration/target masking and is outside this implementation.

## Finite-horizon semantics

Decision budget is part of the TASK-023 state and intrinsic task horizon. On budget
exhaustion, the wrapper emits terminated=True, truncated=False so a future SB3
adapter does not bootstrap beyond that horizon. It preserves base_terminated and
base_truncated in info and records budget_exhausted. It only supports truncation
at zero remaining base budget; an external continuing-task TimeLimit needs a
different explicit contract. TASK-023 itself is unchanged.

FINISH on the last permitted tick retains base terminal precedence. Completion
requires the observed REVIEW_COMPLETE outcome; reviewing the final report without
FINISH, early FINISH and budget exhaustion do not count as completion. Neither
REVIEW_COMPLETE nor negative report metadata establishes target security.

## Evaluation protocol

`ReplayFixture` contains immutable minimized synthetic metadata and explicit replay
approval. `OfflineEvaluationProtocol` requires nonempty train/validation/test tuples,
globally unique fixture IDs and disjoint family IDs/content across splits. Its content
hash ignores target names and slot permutations to reject simple renamed/reordered
copies. Family IDs are declared grouping, not independently verified provenance.
Human review must group every variant of one source fixture into the same split.

Every fixture has the same N, decision budget and tick-rate interval. Every candidate
uses the same fixture objects, seed list, wrapper/reward version and masking mode.
Changing any of these creates a new protocol fingerprint. Fixture order and asset
order are bound to that fingerprint. Approval variations can define negative controls
but must be the same for all compared candidates.

The following is the pinned proposed candidate study, not an executed experiment:

| Parameter | Initial setting |
|---|---|
| Core replay | N=8, max_steps=40, min_interval_ticks=1 |
| Split sizes | 60 train, 20 validation, 20 test, grouped before any tuning |
| Future training seeds | 26, 27, 28, 29, 30 |
| Future training budget | 50000 committed replay transitions per candidate/seed |
| Evaluation episode seeds | 101, 102, 103, 104, 105 |
| Normalization / reward | Fixed versions above, no reward normalization |
| Primary comparison | Same masking=True and identical public observations |
| Separate ablation | masking=False, its own protocol fingerprint |
| Selection | Highest validation completion, then lower mean decisions on completed episodes, then higher mean return; final tie uses declared candidate ID |

Protocol objects permit other explicitly frozen N/budget/seed/split sizes for unit
checks and separately declared studies. No 100-fixture benchmark has been created.
Protocol hashes must be frozen before training. For a future learned-model study,
store selected model identity, dependency lock, source/checkpoint hashes and matching
training transition counts before final test. PPO rollout rounding/DQN warm-up must
not silently exceed a claimed matched budget. Epoch/gradient counts are separately
reported, not equated to environment-transition budgets.

Reserve test for one final evaluation of the validation-selected checkpoint per
training seed; do not tune architecture/reward on test output. The helper checks split
disjointness but does not seal data, enforce one-time access or verify frozen weights.
Those controls and durable receipts need a reviewed experiment runner. No runtime
training permission or Task-028/030 completion is implied by this document.

`evaluate_offline(protocol, selector, candidate_id, split)` only accepts validation
or test. The trusted inference selector gets copies of public observation, boolean
mask and a seeded RNG; it never receives fixture IDs, simulator handles or hidden
metadata through this API. A selector may capture external state or perform I/O;
the function is not a Python sandbox. Future SB3 selectors should call predict with
deterministic=True and explicitly convert its scalar output to int. No learn/update
method is called by the helper. Q-learning needs an explicit compatible state adapter;
the existing raw-state runner is not automatically compatible with normalized input.

Empty masks, malformed proposals, mask violations and selector exceptions stop an
episode and remain in the completion denominator. They are not silently replaced.
Masked proposal errors occur before base step and are coordinator outcomes, not base
refusals. In the unmasked ablation, well-formed inadmissible actions reach base policy
and consume decision budget with genuine refusal outcomes. Simulator/audit/scorer
errors abort the whole evaluation rather than manufacture successful result rows.

| Metric | Definition |
|---|---|
| completion_rate | REVIEW_COMPLETE episodes / every scheduled returned episode |
| mean_return / return_std | Task-024 undiscounted returns; population SD over fixture x episode seed |
| mean_decisions | Committed base decisions, including refusals/repeats |
| mean_decisions_completed | Conditional on completion; None if no episode completes |
| refusals / repeated_reads | DENIED_* / NO_PROGRESS committed outcomes |
| invalid_proposals / policy_errors | Pre-step malformed or masked proposals / selector exceptions |
| budget_exhaustions / empty_masks | Explicit bounded stopping reasons |

Per-episode IDs/seeds/outcomes are retained; failures are not discarded. Aggregate
means pool fixtures and should be stratified externally for approval-negative controls.
No confirmed-vulnerability or live-defense metric is produced. Repeating seeds on this
deterministic simulator measures selector randomness, not independent environment
replicates. For learned-model research, compare paired fixture rows within each
training seed, then report mean/SD across the five independent training seeds;
do not treat pooled episode SD as a confidence interval or five training runs.

## Runnable synthetic example

This smoke example checks the interface only. It has one slot and one fixture per
split, not the proposed benchmark or a learned agent.

```python
from runtime.evaluation.rl_environment import ReplayAsset
from runtime.evaluation.offline_evaluation import (
    ReplayFixture, OfflineEvaluationProtocol, evaluate_offline,
)

def fixture(name, count, report):
    return ReplayFixture(
        name, name, (ReplayAsset("lab-fixture", count, report),),
        ("lab-fixture",),
    )

protocol = OfflineEvaluationProtocol(
    train=(fixture("train", 3, True),),
    validation=(fixture("validation", 5, False),),
    test=(fixture("test", 7, None),),
)

def synthetic_review(observation, mask, rng):
    flags = observation["assets"]
    n = len(flags)
    for slot in range(n):
        if not flags[slot, 0] and mask[slot]:
            return slot
        if not flags[slot, 1] and mask[n + slot]:
            return n + slot
    return 2 * n

result = evaluate_offline(
    protocol, synthetic_review, candidate_id="synthetic-rule",
)
assert result.metrics()["completion_rate"] == 1.0
assert result.metrics()["mean_decisions_completed"] == 3.0
```

## Evidence and handoff boundary

Results and base audit are in memory only. The helper closes each fresh simulator
without writing evidence or checkpoints. Base audit has UTC/run/source/hash/redaction/
expected/observed fields; hashes are not signatures or a durable evidence chain.
Returned episode tuples are diagnostic summaries, not immutable experiment evidence.
No evidence path is written, removed or replaced. A future evidence writer must use
exclusive run creation and stop on write failure, preserving all prior records.

Pending handoff: independently review reward provenance, normalization/read-age,
finite-horizon behavior, split grouping and failure denominators; then approve scope
for SB3 dependency lock/compatibility and immutable experiment/checkpoint receipts.
Missing SB3/PyTorch does not block this wrapper/protocol subset but blocks a claim
of learned candidate integration. No self-approval, finalize or history append.

## Checks and receipts

Build label: BUILD-OFFLINE-RL-WRAPPERS-20261012 (session label, not an approved build
contract). Base HEAD: d9ae6ca0d5bb03ce381d7249665237f272eeddc9.
Observed checks below were executed during this build. AST/example receipt UTC:
2026-10-12T09:06:37.461531Z; whitespace receipt UTC:
2026-10-12T09:08:39.053138Z (local date 2026-10-12 Asia/Saigon).
They are local synthetic receipts, not runtime validation.

| Exact command / check | Exit | Observed result |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_replay_wrappers.py -q` | 0 | 15 tests PASS, including Gymnasium check_env |
| `python -B -m unittest discover -s tests/runtime -p test_offline_evaluation.py -q` | 0 | 14 tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_rl_environment.py -q` | 0 | 23 regression tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_reward_model.py -q` | 0 | 11 regression tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_q_learning.py -q` | 0 | 19 regression tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -q` | 0 | 17 safety tests PASS |
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID; files_checked=7346, schemas=10, actions=13, tasks=35, ADRs=13 |

Latest suites total **99 tests PASS**. Wrapper/evaluator suites were repeated after
the final constructor-validation edit; dependency suites were run once because
their sources did not change. The first two new suites exited 1 because Gymnasium's
MultiBinary rejected Discrete.n as numpy.int64. Converting that dimension to builtin
int fixed the construction bug; subsequent runs passed. Earlier failed attempts
remain failures, not retrospective PASS receipts.

Tests cover committed-event reward counts, unchanged candidate rewards, unknown
flags, detached masks/observations, intrinsic termination, repeated reads/rate age,
missing approvals, malformed input, audit/scorer failures, split leakage, matched
budgets, error denominators and seeded inference repeatability. Socket connection
and subprocess sentinels observed zero calls in the synthetic evaluation; this is
not an OS isolation proof. No learned model, checkpoint or 100-fixture study ran.

Source hashes at the AST/example receipt:

```text
runtime/replay_wrappers.py
13cfb24786c22f8c5aaf63daba9c524fadceba3f030d2667f25fed59cb6134b6
runtime/offline_evaluation.py
d35968acc3e5cc9f9e6e60477201a6a88809d3c671fe6e78e71e2f5091f986f2
tests/runtime/test_replay_wrappers.py
c07212cd0ad79385fdc353975be09d0db39c0064137569767681d99dbbebfe7f
tests/runtime/test_offline_evaluation.py
cdc5fb209701dcd95afbfe75623c49d4eaaa0c009186b9db8d90dc0da8d67624
```

AST and runnable document example: exit 0. Exact command:

```powershell
python -B -c "from pathlib import Path; import ast,hashlib,datetime; paths=['runtime/replay_wrappers.py','runtime/offline_evaluation.py','tests/runtime/test_replay_wrappers.py','tests/runtime/test_offline_evaluation.py']; [ast.parse(Path(p).read_text(encoding='utf-8'), filename=p) for p in paths]; [print(p+' SHA256='+hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in paths]; fence=chr(96)*3; source=Path('runtime/offline_rl_protocol.md').read_text(encoding='utf-8').split(fence+'python\n',1)[1].split('\n'+fence,1)[0]; exec(compile(source,'offline_rl_protocol.md example','exec')); print('AST=4 PASS; DOCUMENT_EXAMPLE=PASS'); print('receipt_utc='+datetime.datetime.now(datetime.timezone.utc).isoformat())"
```

Scoped document/link check: exit 0, zero errors and seven local links. Exact command:

```powershell
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['runtime/offline_rl_protocol.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,None) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('\n'.join(errors)); raise SystemExit(1 if errors else 0)"
```

Whitespace check covers new/untracked files directly, since git diff alone omits
them. Exit 0, five files PASS. Exact command:

```powershell
python -B -c "from pathlib import Path; import datetime; paths=['runtime/replay_wrappers.py','runtime/offline_evaluation.py','runtime/offline_rl_protocol.md','tests/runtime/test_replay_wrappers.py','tests/runtime/test_offline_evaluation.py']; bad=[(p,i) for p in paths for i,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines(),1) if line.rstrip()!=line]; assert not bad,bad; print('WHITESPACE PASS: 5 files'); print('receipt_utc='+datetime.datetime.now(datetime.timezone.utc).isoformat())"
```

Environment inspection observed Python 3.14.5, Gymnasium/NumPy installed, and
stable_baselines3/sb3_contrib/torch absent. No installation or compatibility claim.
Exact read-only command, exit 0:

```powershell
python -B -c "import sys,importlib.util; print(sys.version); print({x: importlib.util.find_spec(x) is not None for x in ['gymnasium','numpy','stable_baselines3','sb3_contrib','torch']})"
```

Final repository/whitespace checks use the exact commands above after these
receipts are added, with results returned in the handoff; test/source receipts
above are not rerun or upgraded by editing this document.
Handoff payload consists of these five paths, receipts and hashes;
unverified items are independent review, SB3 compatibility, checkpoint identity,
actual grouped benchmark provenance and durable evaluation evidence. None of these
checks closes Task 26.

## Final repository blocker

After this document's receipts were added, the exact repository command above
was run again and exited **1**, SCAFFOLD INVALID. It reported 27 errors, all outside
the five changed paths: `.demo-session.json` has invalid status READY, and forbidden
Python bytecode artifacts appeared at the following locations:

```text
agent/__pycache__/__init__.cpython-314.pyc
agent/memory/__pycache__/__init__.cpython-314.pyc
agent/memory/state/__pycache__/__init__.cpython-314.pyc
agent/memory/state/__pycache__/state_manager.cpython-314.pyc
agent/perception/__pycache__/__init__.cpython-314.pyc
agent/perception/normalizers/__pycache__/__init__.cpython-314.pyc
agent/perception/normalizers/__pycache__/observation_normalizer.cpython-314.pyc
dashboards/app/__pycache__/__init__.cpython-314.pyc
dashboards/app/backend/__pycache__/__init__.cpython-314.pyc
dashboards/app/backend/__pycache__/control_api.cpython-314.pyc
dashboards/app/backend/__pycache__/event_sink.cpython-314.pyc
dashboards/app/backend/__pycache__/models.cpython-314.pyc
dashboards/app/backend/__pycache__/range_controller.cpython-314.pyc
dashboards/app/backend/__pycache__/run_history.cpython-314.pyc
dashboards/app/backend/__pycache__/run_manager.cpython-314.pyc
runtime/__pycache__/__init__.cpython-314.pyc
runtime/__pycache__/autonomous_runner.cpython-314.pyc
runtime/__pycache__/capability_registry.cpython-314.pyc
runtime/__pycache__/discovery_engine.cpython-314.pyc
runtime/__pycache__/discovery_gate.cpython-314.pyc
runtime/__pycache__/discovery_recorder.cpython-314.pyc
runtime/__pycache__/evidence_package.cpython-314.pyc
runtime/__pycache__/observed_planner.cpython-314.pyc
runtime/__pycache__/planner_adapter.cpython-314.pyc
scripts/demo/__pycache__/run_professor_demo.cpython-314.pyc
scripts/validation/__pycache__/validate_scaffold.cpython-314.pyc
```

The cause/owner of these workspace changes was not established. Every Python
command executed for this build used -B. No unrelated session artifact or bytecode
was edited/deleted, and the validator was not weakened. The first PASS receipt
remains a historical observation; it does not supersede the final failed gate.
Final whitespace check after the receipt update passed for five files, exit 0,
at 2026-10-12T09:10:12.687573Z; scoped git diff --check also exited 0 (new files
are additionally checked directly). The final blocker is
REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE. Resolve it in its own scope before
independent review/handoff; do not self-approve or upgrade Task 26.

## Documentation synchronization

At the user's request on 2026-10-12, PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md,
docs/task-specs/TASK-026-dqn-ppo-candidate.md and this document are synchronized.
No source/test/evidence/configuration/contract/catalog/scenario file is changed;
deleted files: none. Pre-existing edits in the root documents are retained.

Full TASK-026 remains DEFERRED under AGENTS.md. Its preparation subset is recorded
as IMPLEMENTED, not VALIDATED. TASK-032 remains DEFERRED; all 35 task table IDs,
statuses and dependencies are preserved. TASKS.md's overview is corrected to agree
with the already-IMPLEMENTED Task-025 table row and receipts; that correction is
not a new implementation or status promotion. The seeded DQN/PPO artifact and full
acceptance remain open. No review approval, history entry or runtime claim is made.

The four implementation/test hashes listed above still match. The 99 tests are
implementation-session receipts and were not rerun for this documentation update.
Documentation/status/link checks returned exit 0: five documents, 117 local links,
35 unique task rows, TASK025=IMPLEMENTED and TASK026/032=DEFERRED, zero scoped
document errors. Whitespace and scoped git diff --check returned exit 0;
whitespace receipt UTC is 2026-10-12T09:18:43.805205Z.

The new repository validation returned exit 1 with 27 errors and zero errors in
these five document paths: the same READY session status and 26 forbidden bytecode
files listed in the implementation blocker receipt. Thus handoff remains
HANDOFF_BLOCKED / REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE. This is a new observation,
not a rewrite of either previous gate receipt. No outside-scope artifact was changed.

Pending handoff: resolve the repository artifacts in their own scope, independently
review the wrapper/protocol, then explicitly scope SB3 compatibility/dependency
lock and durable experiment/checkpoint evidence. Library integration, checkpoint,
real grouped benchmark and learned-policy results remain UNRESOLVED.

Exact source-hash command, exit 0 (four checked, no mismatches):

```powershell
python -B -c "from pathlib import Path; import hashlib; expected={'runtime/replay_wrappers.py':'13cfb24786c22f8c5aaf63daba9c524fadceba3f030d2667f25fed59cb6134b6','runtime/offline_evaluation.py':'d35968acc3e5cc9f9e6e60477201a6a88809d3c671fe6e78e71e2f5091f986f2','tests/runtime/test_replay_wrappers.py':'c07212cd0ad79385fdc353975be09d0db39c0064137569767681d99dbbebfe7f','tests/runtime/test_offline_evaluation.py':'cdc5fb209701dcd95afbfe75623c49d4eaaa0c009186b9db8d90dc0da8d67624'}; mismatches=[p for p,h in expected.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]; print('source_hashes_checked='+str(len(expected))); print('mismatches='+repr(mismatches)); raise SystemExit(1 if mismatches else 0)"
```

Exact documentation/status/link command, exit 0:

```powershell
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-026-dqn-ppo-candidate.md','runtime/offline_rl_protocol.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); rows=re.findall(r'^\| (TASK-\d{3}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$',Path('TASKS.md').read_text(encoding='utf-8'),re.M); assert len(rows)==35 and len({r[0] for r in rows})==35; states={r[0]:r[2].strip().strip(chr(96)) for r in rows}; assert states['TASK-025']=='IMPLEMENTED' and states['TASK-026']==states['TASK-032']=='DEFERRED'; print('documents_checked='+str(len(paths))); print('local_links_checked='+str(len(links))); print('task_rows=35; TASK025=IMPLEMENTED; TASK026/032=DEFERRED'); print('scoped_document_errors='+str(len(errors))); print('\n'.join(errors)); raise SystemExit(1 if errors else 0)"
```

An initial version of that status-check command exited 1 because PowerShell
consumed literal backticks in its regex. Replacing that parsing with a column regex
and chr(96) fixed the check command; no task-table correction was needed for it.
The failed command is not recorded as PASS. Final document updates receive the same
focused command again; this does not repeat test suites or upgrade their receipts.

Exact repository command, exit 1:

```powershell
python -B -c "import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-026-dqn-ppo-candidate.md','runtime/offline_rl_protocol.md']; errors=v.validate(); scoped=[e for e in errors if any(p in e for p in paths)]; print('repository_errors='+str(len(errors))); print('scoped_document_errors='+str(len(scoped))); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

Exact whitespace command, exit 0; tracked diff check separately exited 0:

```powershell
git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-026-dqn-ppo-candidate.md
python -B -c "from pathlib import Path; import datetime; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-026-dqn-ppo-candidate.md','runtime/offline_rl_protocol.md']; bad=[(p,i) for p in paths for i,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines(),1) if line.rstrip()!=line]; print('trailing_whitespace='+repr(bad)); print('receipt_utc='+datetime.datetime.now(datetime.timezone.utc).isoformat()); raise SystemExit(1 if bad else 0)"
```
