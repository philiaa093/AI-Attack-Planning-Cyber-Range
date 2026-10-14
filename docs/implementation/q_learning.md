# TASK-025 — Offline Q-learning baseline

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

## Scope and source

Implementation subset: `IMPLEMENTED`; independent review and durable evidence:
`UNRESOLVED`. Canonical [Task 25](../task-specs/TASK-025-q-learning-baseline.md)
now records `IMPLEMENTED` for this offline subset, synchronized with root documents
at the user's explicit request on 2026-10-12. It is not `VALIDATED`.
The user's request on 2026-10-12 authorizes this offline baseline using Task 23/24.
It does not grant per-run or per-action approval for live execution.

Sources read: AGENTS.md, PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md,
Task 23/24/25 specs, docs/mdp-pomdp-model.md, guide 11, ADR-004/005/006/007/009/010/
011/012, configs/rl/environment.yaml and configs/rl/reward.yaml, and dependency
implementations. Primary mathematical source consulted: Watkins and Dayan (1992),
Q-learning. Farama's Handling Time Limits documentation informs the finite-horizon
interpretation. External URLs are omitted here under repository reference policy.

[q_learning.py](../../runtime/evaluation/q_learning.py) trains only the exact existing
[ReplayAssessmentEnv](../../runtime/evaluation/rl_environment.py): READ_INVENTORY, REVIEW_REPORT, FINISH.
These operations inspect simulator metadata. They do not perform security tests
on a target, and their integer indices are not canonical action IDs. The original
Task 23 illustrative reward and [Task 24 scorer](../../runtime/evaluation/reward_model.py) are unchanged.
The runner discards the illustrative reward and calls Task 24 once after each
committed step, using only the returned trusted outcome. RESET earns no reward.

## Initialization and Bellman update

The Q-table is a sparse dictionary from immutable ReplayState to float64 arrays
of length 2*N+1. Unseen values are zero. A row is allocated when first updated;
reading values or greedy evaluation does not allocate rows. Detached values/table
snapshots prevent caller writes from changing learned values.

State contains visible asset flags, inventory counts, remaining budget, action mask
and read age. Read age starts at -1 and is reconstructed from committed public
read outcomes, including duplicates, to represent tick-based rate history. No private
fixtures, hidden report conclusions, ground truth or source-state internals are read.
Exact array dtypes/shapes, bounds, closed observation keys, finite numerical inputs,
boolean stop flags, hyperparameters and table capacity are checked.

For a continuing admissible next decision:

`target = reward + gamma * max(Q(next_state, a) for admissible a)`

`Q(state, action) += alpha * (target - Q(state, action))`

For an ended episode or empty next mask, target is reward alone. The bootstrap max
excludes masked actions, even when their zero values exceed valid negative values.
Defaults are alpha=0.2, gamma=0.95, epsilon_start=1.0, epsilon_min=0.05,
epsilon_decay=0.99, seed=25, max_states=100000. Epsilon for episode k is
`max(epsilon_min, epsilon_start * epsilon_decay**k)`.

Here the intrinsic decision budget is part of the finite-horizon task and visible
state. Budget exhaustion is an absorbing learning boundary, although Task 23 returns
truncated=True. The runner preserves the original terminated/truncated flags in
traces and stops bootstrapping at that boundary. This follows the repository's
finite-horizon model; it is not a generic rule to suppress bootstrapping on Gymnasium
truncation. External time limits for continuing tasks need a different adapter and
an admissible final-state mask.

## Replanning and safety

Epsilon-greedy explores only the current mask. Seeded random ties avoid favoring
the first index. After each observation the learner updates Q and selects anew.
Poor reward moves Q toward a lower target; a negative TD error decreases its value.
The next decision also depends on changed coverage, budget and rate history, so
one failure need not immediately force a different action in every new state.

Task 23 independently checks approval, target/action scope, lab mode, rate, order
and budget inside step. The mask grants no authority. If it contains no admissible
action the runner stops without calling step. Exceptions from audit or malformed
input propagate, with no fabricated successful transition or reward. Reset preserves
prior simulator audit. Each agent binds to one exact environment instance; changed
fixtures, target ordering or a different environment require a fresh agent.

The fixed simulator has no WAIT operation. With a long read interval, FINISH may be
the only admissible action and can terminate review early; the learner cannot create
a new wait action or intentionally bypass rate restrictions. Training uses existing
simulator policy; it does not create approvals. Candidate presence is not confirmed
vulnerability evidence and does not increase Task 24 reward.

## Runnable example

Run from repository root with the existing Task 23 dependencies. All rows below
are synthetic metadata; approval applies only to this simulator.

```python
from runtime.evaluation.q_learning import train_replay, run_replay_episode
from runtime.evaluation.rl_environment import OPERATIONS, ReplayAsset, ReplayAssessmentEnv

env = ReplayAssessmentEnv(
    [ReplayAsset("lab-fixture", inventory_items=3, candidate_reported=True)],
    approved_targets=["lab-fixture"], approved_operations=OPERATIONS,
    max_steps=6,
)
agent, episodes = train_replay(env, episodes=500)
evaluation = run_replay_episode(env, agent, seed=25)  # Greedy; does not update Q.
assert [step.action for step in evaluation.steps] == [0, 1, 2]
assert evaluation.stop_reason == "REVIEW_COMPLETE"
assert abs(evaluation.total_reward - 1.27) < 1e-12
env.close()
```

## Check receipts

Receipt UTC: 2026-10-11T23:55:56.236074Z; user-facing local date: 2026-10-12
Asia/Saigon. Source HEAD: d9ae6ca0d5bb03ce381d7249665237f272eeddc9; pre-existing
dirty files were preserved. Build label: BUILD-TASK025-REPLAY-20261012, a session
label, not an approved build contract. Tests use SIMULATED_FIXTURE metadata only.

| Exact command | Exit | Observed result |
|---|---:|---|
| `python -B -m unittest discover -s tests/runtime -p test_q_learning.py -v` | 0 | 19 tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_rl_environment.py -v` | 0 | 23 regression tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_reward_model.py -v` | 0 | 11 regression tests PASS |

Initial focused run exited 1 because a test compared 0.09000000000000001 to 0.09
with exact equality. The assertion was corrected to floating-point tolerance; all
19 tests passed on the rerun. Scoring coefficients were unchanged.

Tests cover zero initialization, numeric Bellman targets, masked negative maxima,
episode boundaries, refusal/no permitted action, replan after poor repeat reward,
one score per committed step, audit failure, capacity/input rejection, environment
binding, reproducibility, greedy evaluation without Q writes and audit preservation.
Socket/create_connection/Popen sentinels observed no calls during synthetic training;
this is focused coverage, not an OS sandbox proof. The three-step learned sequence
and 1.27 return concern one tiny fixture, not held-out evaluation or convergence.

AST/hash command (exit 0, two Python sources parsed):

```powershell
python -B -c "from pathlib import Path; import ast,hashlib; paths=['runtime/q_learning.py','tests/runtime/test_q_learning.py']; [ast.parse(Path(p).read_text(encoding='utf-8'), filename=p) for p in paths]; print('AST PASS: 2 files'); [print(p+' SHA256='+hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in paths+['runtime/rl_environment.py','runtime/reward_model.py']]; import datetime; print('receipt_utc='+datetime.datetime.now(datetime.timezone.utc).isoformat())"
```

| Source path | SHA-256 |
|---|---|
| runtime/q_learning.py | 17393e60e14db1c74cb1ac35ec2d509acb6cb66e5b1c5d86c5d00f95dfe54538 |
| tests/runtime/test_q_learning.py | a7feed79f2da7f33e3eea1c7fb167efb9597e217eee4cae887dcdde29ccaa145 |
| runtime/rl_environment.py (unchanged dependency) | da3e3c53b8b4b11b77ba6c1ad47538ea40c996a7e2fcd916b661c0a7fedb899b |
| runtime/reward_model.py (unchanged dependency) | 88017247c6f67d82ff5f4510801a75f935f1f7d43bc19a0bf7ba9fb1730ae162 |

Additional checks: repository gate PASS (exit 0, 0 repository errors, 0 Task 25
errors); document/headings/local links and runnable example PASS (exit 0, 4 local
links, 0 document errors, 0 trailing-whitespace errors); scoped git diff --check
PASS (exit 0). The three files are untracked, so explicit whitespace checks cover
them in addition to Git. This is a new gate receipt, not a rewrite of historical
Task 23/24 gate failures recorded elsewhere.

Exact additional commands:

```powershell
python -B -c "import scripts.validation.validate_scaffold as v; paths=['runtime/q_learning.py','runtime/q_learning.md','tests/runtime/test_q_learning.py']; errors=v.validate(); scoped=[e for e in errors if any(p in e for p in paths)]; print('repository_errors='+str(len(errors))); print('task025_errors='+str(len(scoped))); print('\n'.join(scoped).encode('ascii','backslashreplace').decode()); print('sample_outside_scope='+repr([e for e in errors if e not in scoped][:3]).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; p='runtime/q_learning.md'; errors=[]; v._check_markdown(v.ROOT/p,errors,None); links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',Path(p).read_text(encoding='utf-8')); assert all(((v.ROOT/p).parent/t).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/t).resolve().exists() for t in links); fence=chr(96)*3; example=Path(p).read_text(encoding='utf-8').split(fence+'python\n',1)[1].split('\n'+fence,1)[0]; exec(compile(example,p,'exec')); paths=[p,'runtime/q_learning.py','tests/runtime/test_q_learning.py']; whitespace=[f+':'+str(i) for f in paths for i,line in enumerate(Path(f).read_text(encoding='utf-8').splitlines(),1) if line.rstrip()!=line]; print('document_errors='+str(len(errors))); print('local_links='+str(len(links))); print('whitespace_errors='+str(len(whitespace))); print('example PASS'); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); assert not errors and not whitespace"
git diff --check -- runtime/q_learning.py runtime/q_learning.md tests/runtime/test_q_learning.py
```

## Documentation synchronization checks

At the user's request on 2026-10-12, TASK-025 is synchronized to IMPLEMENTED for
the offline baseline subset. Receipt UTC: 2026-10-12T00:04:29.582042Z. The four source
SHA-256 values in the table above matched the current agent, focused tests and
Task 23/24 dependencies. No code/tests changed; the 53 implementation tests were
not rerun for this documentation update.

Observed checks: seven documents/headings/UTF-8 and 114 local links PASS; zero
document/whitespace errors; all 35 task IDs/names/dependencies preserved, with only
Task 25 status changing from SPEC_ONLY to IMPLEMENTED. Task 23/24 remain
IMPLEMENTED; Task 26/32 remain DEFERRED. Source-hash and document checks exited 0.
Fresh repository gate exited 0 with 0 repository errors and 0 scoped document
errors. Scoped git diff --check exited 0; LF/CRLF notices are not whitespace errors.
These checks confirm documentation consistency, not independent acceptance.

Exact document/status/link/whitespace and repository-gate commands:

```powershell
python -B -c "from pathlib import Path; import re,json; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-025-q-learning-baseline.md','runtime/q_learning.md','runtime/rl_environment.md','runtime/reward_model.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,t) for p in paths for t in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not t.startswith('#') and not re.match(r'[a-z]+://',t)]; assert all(((v.ROOT/p).parent/t.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/t.split('#',1)[0]).resolve().exists() for p,t in links); rows=re.findall(r'^\| (TASK-\d{3}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|',Path('TASKS.md').read_text(encoding='utf-8'),re.M); assert len(rows)==35 and len({r[0] for r in rows})==35; statuses={r[0]:r[2].strip().strip(chr(96)) for r in rows}; assert all(statuses[p]=='IMPLEMENTED' for p in ('TASK-023','TASK-024','TASK-025')) and all(statuses[p]=='DEFERRED' for p in ('TASK-026','TASK-032')); whitespace=[p+':'+str(i) for p in paths for i,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines(),1) if line.rstrip()!=line]; print('document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('whitespace_errors='+str(len(whitespace))); print('task_table PASS: 35 IDs; Task 23/24/25 IMPLEMENTED; Task 26/32 DEFERRED'); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); assert not errors and not whitespace"
python -B -c "import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-025-q-learning-baseline.md','runtime/q_learning.md','runtime/rl_environment.md','runtime/reward_model.md']; errors=v.validate(); scoped=[e for e in errors if any(p in e for p in paths)]; print('repository_errors='+str(len(errors))); print('task025_document_errors='+str(len(scoped))); print('\n'.join(scoped).encode('ascii','backslashreplace').decode()); print('sample_outside_scope='+repr([e for e in errors if e not in scoped][:3]).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-025-q-learning-baseline.md runtime/q_learning.md runtime/rl_environment.md runtime/reward_model.md
```

Exact source-hash comparison command (exit 0, all four match):

```powershell
python -B -c "from pathlib import Path; import hashlib,re; p=Path('runtime/q_learning.md'); expected=dict(re.findall(r'\| ((?:runtime|tests/runtime)/[^ |]+\.py)(?: \([^|]+\))? \| ([0-9a-f]{64}) \|',p.read_text(encoding='utf-8'))); observed={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in expected}; [print(p+' SHA256='+h+' match='+str(h==expected[p])) for p,h in observed.items()]; assert len(expected)==4 and observed==expected; print('source_hashes PASS: 4'); import datetime; print('receipt_utc='+datetime.datetime.now(datetime.timezone.utc).isoformat())"
```

Documentation handoff: changed_files=PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md,
docs/task-specs/TASK-025-q-learning-baseline.md, runtime/q_learning.md,
runtime/rl_environment.md, runtime/reward_model.md; deleted_files=none;
blockers=no source conflict or checker failure observed;
pending=independent review, full canonical acceptance, durable evidence and
research/planner integration described below; self_approval=none.

## Handoff and limits

Original implementation files added: runtime/q_learning.py, runtime/q_learning.md,
tests/runtime/test_q_learning.py. Existing files edited: none. Deleted files: none.
The subsequent documentation synchronization edits PROJECT_CONTEXT.md,
PROJECT_PLAN.md, TASKS.md, docs/task-specs/TASK-025-q-learning-baseline.md,
runtime/rl_environment.md, runtime/reward_model.md and this document. No files are
deleted; code/tests/configuration/contracts/catalog/scenarios/evidence/history are
unchanged by synchronization. No self-approval, finalization or runtime-success claim.

Training traces and simulator audit remain volatile; no immutable training-evidence
package or checkpoint is produced. Source hashes are receipts, not signatures.
Full planner-interface integration, calibrated reward configuration, held-out
evaluation, hyperparameter sensitivity, budget equivalence, durable evidence and
independent review remain `UNRESOLVED`. Constant alpha and bounded epsilon-greedy
runs provide a baseline; they do not establish convergence or an optimal policy.

Pending handoff payload: scope=Task 25 offline replay baseline;
build_label=BUILD-TASK025-REPLAY-20261012; base_head=d9ae6ca0d5bb03ce381d7249665237f272eeddc9;
changed_files=the three added files above; deleted_files=none;
checks=53 tests/AST/document/example/whitespace/repository gate PASS;
blockers=no focused or repository-checker failure observed in this receipt;
unverified=independent review, full canonical acceptance, durable
evidence, full planner integration, calibration and held-out evaluation;
required_next=independent review of state encoding, reward provenance, finite-horizon
boundaries and proposal policy; approval=none claimed.
