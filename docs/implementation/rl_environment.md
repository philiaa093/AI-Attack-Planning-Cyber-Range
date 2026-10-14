# TASK-023 — Gymnasium replay environment

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

## Status and scope

`IMPLEMENTED` for offline metadata replay at the user's request on 2026-10-12;
not `VALIDATED`. Canonical task: [TASK-023](../task-specs/TASK-023-rl-environment.md).
Implementation: [rl_environment.py](../../runtime/evaluation/rl_environment.py); focused tests:
[test_rl_environment.py](../../tests/runtime/test_rl_environment.py).

The simulator reads fixed synthetic report metadata or a minimized TASK-019/020
state snapshot. It does not call scanners, the planner, providers, executors or
network transports. Report imports/normalization remain upstream responsibilities.
These local replay operations are not canonical actions and cannot be used as
execution approval. Configuration/contracts/catalog/scenarios/evidence are unchanged.

Sources: PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md, TASK-023 and dependencies
TASK-004/005/006/009; ADR-004/005/007/009/010/011/012/013;
configs/rl/environment.yaml (`network: false`); TASK-019 KnowledgeStateStore and
TASK-020 StateSnapshot. APIs were checked against Farama's official Gymnasium Env
and environment-checker documentation; external references follow repository policy.

## Installation and minimal example

Direct dependency declarations: [rl_requirements.txt](../../runtime/evaluation/requirements.txt).
Gymnasium is pinned to 1.4.0; the NumPy range and transitive dependencies are not a
complete lockfile. Tested on Windows with Python 3.14.5 and NumPy 2.5.3.
Gymnasium 1.4.0 and farama-notifications 0.0.6 were installed in the Python user site;
existing NumPy/cloudpickle/typing-extensions were retained.

```powershell
python -B -m pip install -r runtime/rl_requirements.txt
python -B -m unittest discover -s tests/runtime -p test_rl_environment.py -v
```

```python
from gymnasium.utils.env_checker import check_env
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv

env = ReplayAssessmentEnv(
    [ReplayAsset("lab-fixture", inventory_items=3, candidate_reported=True)],
    approved_targets=["lab-fixture"],
    approved_operations=OPERATIONS,
    max_steps=10,
)
check_env(env, skip_render_check=True)
obs, info = env.reset(seed=23)
assert info["action_mask"].tolist() == [1, 0, 1]
obs, reward, terminated, truncated, info = env.step(0)  # inventory
obs, reward, terminated, truncated, info = env.step(1)  # report metadata
obs, reward, terminated, truncated, info = env.step(2)  # finish
assert terminated and not truncated
assert info["outcome"] == "REVIEW_COMPLETE"
assert info["network_dispatches"] == 0
env.close()
```

## Action and observation spaces

For N immutable fixture slots, `action_space = Discrete(2*N + 1)`:

| Index | Fixed replay operation |
|---|---|
| 0 through N-1 | READ_INVENTORY for that slot |
| N through 2*N-1 | REVIEW_REPORT for that slot |
| 2*N | FINISH |

These names define simulator operations only. No URL, command, payload, tool name,
dynamic action or canonical action-ID mapping is accepted. Slot IDs must be bounded
canonical lab identifiers, unique, with 1-64 assets. Slot inventory represents declared
replay scope, not network discovery. Approval may narrow that scope, never extend it.
Missing target/operation approval denies the relevant replay operation.

Observation is a Dict with three arrays:

| Key | Space | Meaning |
|---|---|---|
| assets | MultiBinary((N, 4)) | inventory reviewed, report reviewed, report available, candidate observed |
| inventory_counts | Box(0, 10000, (N,), int32) | revealed inventory item count |
| remaining_budget | Box(0, 1, (1,), float32) | simulator decision budget fraction |

Initial arrays are zero. Report availability/candidate flags are revealed only by
REVIEW_REPORT. `candidate_reported=None` means unknown/unavailable, False means the
provided report metadata contains no candidate, and True means candidate observed.
Neither False nor a completed review proves absence of vulnerabilities. Outputs are
detached copies. `info` exposes only outcome, provenance, zero network dispatch count
and the next-decision action mask; no truth labels, raw facts, source hashes or audit IDs.

## Step, reset and accounting

Each well-formed decision consumes one simulator tick and one decision-budget unit,
including refusals and repeated reads. Lab mode, replay operation/target approval,
minimum read interval and inventory-before-report order are checked in step regardless
of action mask. Rate uses simulated ticks, not wall-clock time or HTTP request rate.
FINISH still requires lab mode and operation approval. It is not rate-limited because
it performs no read. Masks show admissibility, so repeated reads may remain admissible.

Malformed actions raise ValueError, record refusal and stop the episode before any
observation/budget change. Before reset, after stop/truncation or after close, step
raises RuntimeError. Reset rejects unsupported options and invalid seeds; it seeds
Gymnasium, records a restore event and clears only simulator memory. Prior audit
records, source snapshots and store histories are preserved. Close is permanent.

FINISH sets terminated=True, including early stop. Reaching max_steps without FINISH
sets truncated=True. Finishing on the last permitted step takes terminal precedence.
REVIEW_COMPLETE means every report slot was reviewed, including unavailable reports;
it never means all security checks succeeded or the target is safe.

Reward is a fixed illustrative shaping rule: -0.01 per decision, +0.1 for first
inventory read, +0.2 for first report review, -0.5 for refusal, +1.0 for complete
FINISH or -0.5 for early FINISH. Repeats earn no discovery reward. Candidate contents
do not change reward. TASK-024 now has an IMPLEMENTED standalone
[offline reward scorer](reward_model.md), synchronized at the user's request on
2026-10-12; it has not replaced this illustrative reward or been integrated here.
[TASK-025](q_learning.md) is now IMPLEMENTED for offline replay training; its runner
discards this illustrative step reward and calls TASK-024 once per committed outcome.
This does not change the environment or its policy. TASK-026/032 remain DEFERRED;
independent review, durable evidence and research evaluation remain UNRESOLVED.

## TASK-019 integration and evidence boundary

`ReplayAssessmentEnv.from_snapshot(snapshot, targets=[...], **replay_options)` requires
a validated TASK-020 StateSnapshot. Create it using
`StateSnapshot.from_store(store, context=context)` for TASK-019. The adapter counts
observed TARGET/SERVICE/ENDPOINT facts per explicit target and detects observed
CANDIDATE_FINDING presence. It does not copy raw values, routes, secrets or confirmed
truth into the replay. Lack of candidates becomes None, never False. The hash binds
to snapshot JSON; source report authenticity, evidence-reference integrity and journal
integrity are not independently verified by this adapter.

No store context is created or changed. Simulator budget is independent of source
StateManager budget; replay decisions never decrement source actions/requests/seconds.
This is not an equivalence claim for experimental planner budgets under ADR-011.

`audit_records()` returns detached metadata-only records retained across resets with
UTC, unique run ID, episode ID, sequence, source/hash, redaction marker, expected and
observed state, and a per-record SHA-256. Audit happens before step state commit;
audit failure stops processing without committing state. Storage is volatile, hashes
are not signatures, and no durable/immutable evidence integration is claimed.
Durable evidence, scanner/gate/executor integration, live restore, dynamic revocation
and independent review remain `UNRESOLVED`. Any future dispatch must retain the
existing centralized safety gate, canonical approval, budgets/rate/order, kill switch,
intent/result recording and restore boundaries; this class provides no dispatch path.

## Checks and handoff

Build label: BUILD-TASK023-REPLAY-OFFLINE-20261012 (session label, not an approved
build contract). Source HEAD: d9ae6ca0d5bb03ce381d7249665237f272eeddc9; working tree
was dirty beforehand. Check receipt UTC: 2026-10-11T21:14:54.048588Z, local date
2026-10-12 in Asia/Saigon. Sources are synthetic fixtures, not a live lab run.

| Exact command/check | Exit | Observed |
|---|---|---|
| `python -B -m pip install --user --only-binary=:all: --no-cache-dir gymnasium==1.4.0` | 0 | Installed Gymnasium 1.4.0 and farama-notifications 0.0.6 |
| `python -B -m unittest discover -s tests/runtime -p test_rl_environment.py -v` | 0 | 23 tests PASS, including real Gymnasium check_env |
| `python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py -v` | 0 | 21 regression tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_planner_interface.py -v` | 0 | 28 regression tests PASS |

Expected/observed synthetic assertions passed for API spaces and signatures, order,
approval/rate refusal, malformed input, report visibility, reward repetition, termination,
budget truncation, audit failure, reset preservation and read-only snapshot integration.
Socket/create_connection/Popen sentinels observed no calls in the synthetic episode;
this is not an OS-enforced isolation proof. Initial focused run passed 22 tests; an
episode-label correction and reset audit-failure regression produced the final 23.

AST parsing of both Python files and the runnable document example PASS, exit 0.
Scoped documents/headings and 82 local links PASS, exit 0. Scoped tracked git diff
and trailing-whitespace checks across all eight paths PASS, exit 0. Task-table check
PASS at the earlier Task-023 receipt: 35 IDs, Task 23 IMPLEMENTED, Task 24/25
SPEC_ONLY, Task 26/32 DEFERRED. Current Task-024 subset status is IMPLEMENTED as
recorded in TASKS.md; that synchronization does not rewrite the earlier receipt.

Repository validate() exited 1: 613 errors outside scope, 0 errors matching the
eight Task-023 paths. Examples are external links in dashboards/app and forbidden
command/payload fields in frontend/node_modules package metadata. Earlier validation
exited 1 with 615 errors including two introduced document errors (TASKS heading
template and external links in runtime docs); both were corrected before the final
613/0 result. Initial scoped document check exited 1 for the heading error; final
scoped check PASS. Outside-scope artifacts were not modified to make the gate pass.

Exact commands for additional receipts (from repository root):

```powershell
python -B -c "import ast,pathlib; paths=['runtime/rl_environment.py','tests/runtime/test_rl_environment.py']; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'),filename=p) for p in paths]; print('AST PASS: 2 files'); from pathlib import Path; fence=chr(96)*3; s=Path('runtime/rl_environment.md').read_text(encoding='utf-8'); example=s.split(fence+'python\n',1)[1].split('\n'+fence,1)[0]; exec(compile(example,'rl_environment.md example','exec')); print('DOCUMENT EXAMPLE PASS')"
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-023-rl-environment.md','runtime/rl_environment.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
python -B -c "import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-023-rl-environment.md','runtime/rl_environment.py','runtime/rl_environment.md','runtime/rl_requirements.txt','tests/runtime/test_rl_environment.py']; errors=v.validate(); scoped=[e for e in errors if any(p in e for p in paths)]; print('repository_errors='+str(len(errors))); print('task023_errors='+str(len(scoped))); print('\n'.join(scoped).encode('ascii','backslashreplace').decode()); print('sample_outside_scope='+repr([e for e in errors if e not in scoped][:4]).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-023-rl-environment.md
python -B -c "from pathlib import Path; import hashlib; paths=['runtime/rl_environment.py','tests/runtime/test_rl_environment.py','runtime/rl_requirements.txt']; [print(p+' SHA256='+hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in paths]; allpaths=paths+['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-023-rl-environment.md','runtime/rl_environment.md']; errors=[p+':'+str(i) for p in allpaths for i,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines(),1) if line.rstrip()!=line]; print('trailing_whitespace_errors='+str(len(errors))); assert not errors"
```

The completed implementation document was also checked after receipt insertion:
82 local links, document headings, whitespace, executable example and source hashes
PASS. Documentation synchronization rechecks hashes and task/status/dependency
consistency; the 72 test receipts belong to the implementation session and are not
new test runs. Task 23 remains IMPLEMENTED, with independent review and durable/live
integration UNRESOLVED. The historical repository-gate receipt remains 613 errors
outside scope, 0 Task-023 errors; no gate repair or runtime execution is claimed.

Current documentation-only synchronization receipts: the exact scoped document/link
command above exited 0 with 0 document errors and 89 local links checked; the exact
hash/whitespace command and scoped git diff --check above exited 0 with 0 trailing
whitespace errors. All three source SHA-256 values below still match. A before/after
comparison of the 35 TASKS table rows matched exactly, including statuses/dependencies.
No code, tests, dependency declaration, evidence or historical gate receipt changed.
The repository gate and the 72 implementation tests were not rerun for this update.
The five files changed in this documentation-only update are PROJECT_CONTEXT.md,
PROJECT_PLAN.md, TASKS.md, docs/task-specs/TASK-023-rl-environment.md and this document;
no files were deleted. Pending handoff below remains applicable.

Source SHA-256 after final code/test changes:

- runtime/rl_environment.py: da3e3c53b8b4b11b77ba6c1ad47538ea40c996a7e2fcd916b661c0a7fedb899b
- tests/runtime/test_rl_environment.py: 77bccbd147666ec150d2cd1b03b142a92d04df3c9a50fb8dcfffb0ae11119f12
- runtime/rl_requirements.txt: 0283c0f30dc214f2253af89a74344288c25ab47069d1a30a7e8c32ddfcc17d68

Exact files added: runtime/rl_environment.py, runtime/rl_environment.md,
runtime/rl_requirements.txt, tests/runtime/test_rl_environment.py.
Exact existing files changed: PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md,
docs/task-specs/TASK-023-rl-environment.md. Deleted files: none. Pre-existing changes
were retained; no evidence/history/contracts/catalog/configuration was edited.

Pending handoff payload: scope=offline Gymnasium replay; status=HANDOFF_BLOCKED;
blocker=REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE; required_next=repository blockers
resolved in separately authorized scope, then independent review of replay policy,
state projection, accounting and evidence boundary; unverified=durable evidence,
report authenticity/reference integrity, live scanner/gate/executor/restore integration,
experimental budget equivalence, official reward model and training. No self-approval,
finalization, history append or runtime-success claim.
