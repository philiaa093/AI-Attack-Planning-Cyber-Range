# TASK-024 — Offline defensive review reward design

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

## Status and scope

`IMPLEMENTED` for the standalone offline metadata-review scorer and tests;
canonical [TASK-024](../task-specs/TASK-024-reward-model.md) was synchronized
at the user's request on 2026-10-12. Not `VALIDATED`; see
[TASKS.md](../../TASKS.md#task-024--bộ-chấm-điểm-đánh-giá-metadata-ngoại-tuyến).
This delivery answers the reward-design request with a pure Python scorer and
offline trace tests. It does not change TASK-023 step/reset behavior or install
the scorer in an environment, planner, training loop or executor.
The separate [TASK-025 replay runner](q_learning.md) now calls this scorer once for
each committed TASK-023 step, without replacing the environment's returned reward.
TASK-025 is IMPLEMENTED for that offline subset. Independent review, durable evidence
and full planner/executor integration remain `UNRESOLVED`. The
current repository gate is PASS after the [validator repair](../../scripts/validation/README.md):
SCAFFOLD VALID, exit 0, 0 errors. The earlier failed gate receipts below remain
historical observations; the scorer and tests were not changed or rerun by that repair.

Sources: PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md, TASK-023/024,
[TASK-023 implementation](rl_environment.md), guide 09 and ADR-007/009/010/011/012.
Configuration, contracts, catalog, scenarios and evidence are outside this diff.
No existing evidence is overwritten. These receipts describe synthetic replay
checks, not observed vulnerability findings or live-range behavior.

## Reward function

[score_replay_reward](../../runtime/evaluation/reward_model.py) scores one outcome supplied by the trusted
simulator after a committed decision. Its return exposes separate step, progress,
penalty and completion terms. Inputs must be exact strings from the closed table;
unknown labels fail closed. The coefficients are fixed in this design version.

`r = -0.01 + progress + penalty + completion`

| Trusted outcome | Additional term | Total |
|---|---:|---:|
| First inventory review | +0.10 progress | +0.09 |
| First report review, including unavailable report | +0.20 progress | +0.19 |
| Repeated read with no progress | -0.10 penalty | -0.11 |
| Rejected rate/order proposal | -0.50 penalty | -0.51 |
| Rejected lab/target/approval proposal | -2.00 penalty | -2.01 |
| Malformed proposal, evaluator diagnostic only | -2.00 penalty | -2.01 |
| Complete review followed by FINISH | +1.00 completion | +0.99 |
| Early FINISH | -0.50 penalty | -0.51 |

These are initial design choices, not calibrated or experimentally optimal values.
The constant step cost discourages unnecessary decisions. First-review progress
is earned once per slot per episode because TASK-023 emits NO_PROGRESS on repeat
reads. Counts and severity do not multiply the reward. FINISH requires environment
approval and ends the episode, so completion cannot repeat within that episode.
An unavailable report earns the review-progress term for establishing an unknown
state; this is not a clean-result bonus or proof of completed security testing.

For one slot: inventory -> report -> finish totals 1.27. Adding two duplicate
reads yields 1.05. A report-before-inventory refusal followed by the efficient
sequence totals 0.76. A successful recovery earns ordinary progress, with no
extra bonus for manufacturing an initial failure.

## Findings, noise and replanning

The implemented reward deliberately does not depend on candidate presence.
TASK-023 observes report metadata, not confirmed vulnerability ground truth.
Reports containing candidates, no candidates and unknown conclusions earn equal
review-progress returns. HTTP status, reflection, errors and agent confidence
are insufficient confirmation evidence.

For a separate future defensive classifier of static labeled reports, a reasonable
starting evaluation design is +1 for a correct diagnosis and -1 for a false alarm,
once per report identity, with independently adjudicated labels. Keep precision,
recall and false-negative counts as separate evaluation metrics, so abstaining on
every report cannot appear successful. That classifier/label interface is not
implemented here and does not extend planner actions or authorize execution.

Noise in the implemented replay means repeated reads or rate-rejected proposals.
It is not measured network traffic or service disruption: TASK-023 has no transport.
Do not invent latency/error/disruption inputs or punish missing infrastructure as
if the agent caused it. Any future operational noise measurement needs its own
approved observation contract and independently observed receipts.

There is no reward for declaring REPLAN or changing a plan ID. Progress after a
failure earns the ordinary first-review term. Switching endlessly among already
reviewed slots therefore remains costly. A reward function alone cannot implement
replanning: the policy still needs visible outcomes, admissible-operation masks and
coverage state. TASK-023 currently supports only its fixed replay operations.
No learned policy, adaptive planner or convergence claim is made here.

If preserving the optimum of a specified base MDP becomes necessary, assess
potential-based shaping `F(s,s') = gamma * Phi(s') - Phi(s)` under its assumptions,
using the learner's discount and correct terminal handling. The fixed progress
bonuses here do not claim policy invariance. Primary source consulted:
Ng, Harada and Russell (1999), Policy invariance under reward transformations:
Theory and application to reward shaping, ICML. External URLs are omitted here
because the repository restricts them to docs/references.md, outside this diff.

## Trust and integration boundary

```python
from runtime.evaluation.reward_model import score_replay_reward

# Mathematical example for a trusted first-review outcome, not a dispatch.
result = score_replay_reward("REPORT_REVIEWED")
assert abs(result.total - 0.19) < 1e-12
```

The scorer does not verify event provenance or deduplicate transitions by itself.
A valid label supplied by a planner is still untrusted. Any integration must
call it exactly once for each committed simulator decision, retain episode/step
identity and use the simulator's first-review tracking; replaying a receipt must
not add another training reward. No caller-supplied success flag is accepted as
authorization. Reward penalties never replace refusal before dispatch, allowlists,
approval, order/rate/budget enforcement, audit or restore.

Malformed TASK-023 actions raise ValueError and stop the episode. The diagnostic
score must not swallow that exception or fabricate a returned transition. RESET
does not earn a score. This model leaves termination decisions with the environment.
Reaching the replay budget does not manufacture REVIEW_COMPLETE or a completion
bonus. Preserve terminated versus truncated: they have distinct learning semantics
in the Farama Foundation's Gymnasium Terminated-Truncated Step API explanation
(primary documentation consulted during this design).

## Checks and command receipts

Receipt time UTC: 2026-10-11T21:27:25.6424497Z; local date 2026-10-12 Asia/Saigon.
Source HEAD: d9ae6ca0d5bb03ce381d7249665237f272eeddc9. The worktree was already dirty.
Source: SIMULATED_FIXTURE; redaction: metadata only. No lab run ID or durable
evidence record is claimed. SHA-256 source hashes are recorded below after checks.

| Exact command | Exit | Observed result |
|---|---:|---|
| `python -B -m unittest discover -s tests/runtime -p test_reward_model.py -v` | 0 | 11 tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_rl_environment.py -v` | 0 | 23 tests PASS, including check_env |

Source SHA-256 hashes:

```text
runtime/reward_model.py
88017247c6f67d82ff5f4510801a75f935f1f7d43bc19a0bf7ba9fb1730ae162
tests/runtime/test_reward_model.py
f729b86e9bf8c80f0fb84cb17e60adbeb2a24a2bf6855f5b94e1a74b0c46f4d7
```

AST/source-hash/whitespace check: exit 0, 2 files parsed, 0 trailing-whitespace
errors. Exact command:

```powershell
python -B -c "from pathlib import Path; import ast, hashlib; paths=['runtime/reward_model.py','tests/runtime/test_reward_model.py']; [ast.parse(Path(p).read_text(encoding='utf-8'),filename=p) for p in paths]; print('AST: PASS (2 files)'); [print(p+' SHA256='+hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in paths]; paths+=['runtime/reward_model.md']; errors=[p+':'+str(i) for p in paths for i,line in enumerate(Path(p).read_text(encoding='utf-8').splitlines(),1) if line.rstrip()!=line]; print('trailing_whitespace_errors='+str(len(errors))); assert not errors"
```

Initial repository gate: exit 1, 614 errors, including 1 scoped error for external
URLs in this document. Those links were removed in place to respect repository
policy. Exact gate command, reused for the post-fix check:

```powershell
python -B -c "import scripts.validation.validate_scaffold as v; paths=['runtime/reward_model.py','runtime/reward_model.md','tests/runtime/test_reward_model.py']; errors=v.validate(); scoped=[e for e in errors if any(p in e for p in paths)]; print('repository_errors='+str(len(errors))); print('task024_errors='+str(len(scoped))); print('\n'.join(scoped).encode('ascii','backslashreplace').decode()); print('sample_outside_scope='+repr([e for e in errors if e not in scoped][:3]).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

An initial document-check invocation passed an empty expected-heading tuple and
reported a template mismatch; runtime documents have no mandated source template.
The corrected check uses None and still checks UTF-8, H1 and local link containment.

Post-fix gate: exit 1, 613 repository errors, 0 scoped TASK-024 errors. Sample
blockers are external URLs in dashboards/app/README.md and frontend/README.md,
and a forbidden field in frontend/node_modules/.package-lock.json. These are
outside this delivery's allowlist. Repository gate/handoff remains BLOCKED.

Corrected document check: exit 0, 0 document errors, 3 local links checked. Exact
command:

```powershell
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; p='runtime/reward_model.md'; errors=[]; v._check_markdown(v.ROOT/p,errors,None); links=[target for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for target in links); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

`git diff --check -- runtime/reward_model.py runtime/reward_model.md tests/runtime/test_reward_model.py`
returned exit 0. All three files are new/untracked, so the explicit source
whitespace check above is needed in addition to Git's tracked-diff check.

The focused tests cover candidate-independent scoring, negative duplicate returns,
recovery after an order refusal, rate rejection, early finish, hard-boundary refusal,
malformed exceptions and budget truncation without a completion bonus. Replay
checks guard socket construction and subprocess launch. This is bounded offline
test coverage, not a general sandbox proof.

## Documentation synchronization checks

At the user's request on 2026-10-12, status was synchronized to IMPLEMENTED for
the standalone scorer/tests subset. Receipt UTC: 2026-10-11T21:35:23.3855341Z.
Source scorer/test hashes match the implementation receipt above. No code or
configuration changed; the 34 implementation tests were not rerun for this
documentation update.

Observed: scoped headings/UTF-8 and 98 local links PASS, 35 task IDs preserved,
TASK-024 IMPLEMENTED, TASK-025 SPEC_ONLY and TASK-026/032 DEFERRED; exit 0.
An initial task-table check had an assertion failure because shell quoting removed
Markdown delimiters from comparison literals; the corrected check normalizes those
delimiters with chr(96). This was a check-invocation correction, not a status rollback.
Exact corrected command:

```powershell
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-024-reward-model.md','runtime/reward_model.md','runtime/rl_environment.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); rows=re.findall(r'^\| (TASK-\d{3}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|',Path('TASKS.md').read_text(encoding='utf-8'),re.M); assert len(rows)==35 and len({r[0] for r in rows})==35; statuses={r[0]:r[2].strip().strip(chr(96)) for r in rows}; assert statuses['TASK-024']=='IMPLEMENTED' and statuses['TASK-025']=='SPEC_ONLY' and all(statuses[p]=='DEFERRED' for p in ('TASK-026','TASK-032')); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('task_table: PASS (35 IDs, Task 24 IMPLEMENTED, Task 25 SPEC_ONLY, Task 26/32 DEFERRED)'); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

Source-hash comparison: exit 0, both match. Exact command:

```powershell
python -B -c "from pathlib import Path; import hashlib; paths={'runtime/reward_model.py':'88017247c6f67d82ff5f4510801a75f935f1f7d43bc19a0bf7ba9fb1730ae162','tests/runtime/test_reward_model.py':'f729b86e9bf8c80f0fb84cb17e60adbeb2a24a2bf6855f5b94e1a74b0c46f4d7'}; observed={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}; [print(p+' SHA256='+h+' match='+str(h==paths[p])) for p,h in observed.items()]; assert observed==paths"
```

Documentation repository gate: exit 1, 613 errors outside the six edited document
paths, 0 scoped document errors. Same outside-scope blocker examples as above;
HANDOFF_BLOCKED remains in effect. Exact command:

```powershell
python -B -c "import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-024-reward-model.md','runtime/reward_model.md','runtime/rl_environment.md']; errors=v.validate(); scoped=[e for e in errors if any(p in e for p in paths)]; print('repository_errors='+str(len(errors))); print('task024_document_errors='+str(len(scoped))); print('\n'.join(scoped).encode('ascii','backslashreplace').decode()); print('sample_outside_scope='+repr([e for e in errors if e not in scoped][:3]).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

`git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-024-reward-model.md runtime/reward_model.md runtime/rl_environment.md`
returned exit 0. Git displayed line-ending conversion notices for the two root
context/plan documents, not whitespace errors. Untracked runtime documents are
covered by an explicit final source whitespace check.

## Pending handoff

Changed files: runtime/reward_model.py, runtime/reward_model.md and
tests/runtime/test_reward_model.py. Deleted files: none. Preserve pre-existing
working-tree changes. The subsequent documentation synchronization updates
PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md, docs/task-specs/TASK-024-reward-model.md,
this document and runtime/rl_environment.md. No files deleted; code/tests/config
are unchanged by synchronization. TASK-024 is IMPLEMENTED for this subset only.

The repository-checker blocker is now resolved; that does not imply handoff approval.
TASK-025 now provides the separate offline scorer/runner connection described above;
the scorer source, weights and TASK-023 step reward were not changed.
Pending: independent review of weights and trusted-event boundary; an approved
durable evidence/full planner integration design; config scope and canonical task acceptance (the
existing configs/rl/reward.yaml coefficients remain TBD, so acceptance is open); durable
evidence linkage; any separate labeled-report classifier; empirical calibration
and equivalent planner-budget evaluation. No self-approval or history append.
