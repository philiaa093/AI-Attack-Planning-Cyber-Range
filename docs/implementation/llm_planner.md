# TASK-022 offline evidence-review planner

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

## Scope and status

Implementation artifact for the authorized offline subset, not an acceptance or
validation decision. Canonical TASK-022 is IMPLEMENTED for this subset in TASKS.md,
updated at the user's request on 2026-10-12; not VALIDATED. The original code build
did not edit root status documents. Independent review, real provider behavior,
tokenizer compatibility, reference integrity and consumer integration are
UNRESOLVED. TASK-026 and TASK-032 remain DEFERRED.

Build ID: BUILD-TASK022-REVIEW-OFFLINE-20261012.
Plan ID: PLAN-TASK022-REVIEW-OFFLINE-20261012.
Base HEAD: d9ae6ca0d5bb03ce381d7249665237f272eeddc9.
Authorization: user requested implementation of the preceding offline
evidence-review design. Allowlist and exact added files:

- runtime/llm_planner.py
- runtime/llm_planner.md
- tests/runtime/test_llm_planner.py

Deleted files: none. Preserve pre-existing dirty/untracked files. No contracts,
catalog, configuration, evidence, history, target or runner changes.

## Interface and context

[LLMPlanner](../../runtime/planners/llm_planner.py) inherits the [Task 20 ABC](../../runtime/planners/planner_interface.py)
without overriding plan/replan. Read-only [Task 19](../../runtime/state/knowledge_state_store.py)
snapshots carry run/session/episode isolation, revision, objective, phase and
remaining budget. StateManager retains sole ownership of accounting.

Only ANALYSIS/REPLAN candidate metadata with explicit allowed lab target subjects
can yield ACTION-PLAN-003. Candidate ID, target ID and source observation ID are
validated before selection. No scanner or executor is exposed. Dispatcher must
still check canonical action/target scope, lab mode, approval, rate/order/budget,
kill switch, audit and restore; caller candidate sets grant no authority.

The immutable provider request includes system instructions, JSON control
context, minimized candidate metadata, coverage and replan feedback. Raw fact
values, HTML, target source and ground truth are omitted. The fingerprint binds
context, objective, fixed review action and the full candidate record; it is a
digest, not a signature. Do not treat fingerprint availability as proof of
authenticity or vulnerability. Candidate confidence is uncalibrated metadata;
proposal confidence is fixed at 0.0 (unassessed usefulness).

Candidates sort by fact ID. Trimming removes whole records and updates coverage.
The injected trusted token counter measures the complete serialized request,
including instructions, tool schema, candidate enums and feedback. Output space
is reserved independently; inability to fit mandatory context plus one candidate
fails before the provider. The byte-count counters in tests are synthetic and do
not prove real model token accounting. No tokenizer or network library is added.

## Tool calling and provider boundary

The one function is submit_review_decision. strict is true, all properties are
required and additionalProperties is false. Forced tool choice and disabled
parallel calls restrict the request to one proposal. input_revision must echo the
current snapshot revision (a singleton enum), even if the candidate version did
not change. REVIEW_EVIDENCE selects a
supplied version; STOP requires a null selection. Python independently validates
the cross-field rules and exact enum membership.

ReviewProvider.complete receives request JSON and returns a minimized response
JSON envelope with exactly status and output. On completion, output contains
exactly one object with type=function_call, name=submit_review_decision and
arguments as a JSON string. An API-specific adapter is not implemented. Such an
adapter must preserve incomplete responses/refusals, remove only irrelevant
provider metadata, enforce its own transport/time/size/identity limits and never
repair invalid arguments into success. The module has no provider endpoint,
credential lookup, SDK client, network dispatch, subprocess or import side effects.

Reject duplicate keys at both envelope and argument boundaries, non-finite
numbers, unknown fields, wrong/multiple/missing calls, stale or omitted candidate
versions, invalid cross-field decisions and oversized output. ProviderFailure
exposes a static reason code and never copies raw output or exception text into
the plan. Refusal/incomplete/malformed responses never trigger fallback.

Only unavailable provider or TimeoutError can use an explicitly permitted local
deterministic fallback selecting the first included eligible candidate. Its
envelope records requested_mode=LLM, actual_mode=RULE and fallback_reason. This
is not a call to the Task 21 backend. Other provider exceptions fail closed.
Do not relabel fixture or fallback runs as a real LLM run. The generic provider
interface is trusted Python code and is not a sandbox or runtime authorization.

PlanProposal carries only canonical fields. Python supplies plan identity,
objective, target, fixed action and source observation from the snapshot. No
evidence record is invented; evidence_refs remains empty. Mode/fallback/context
metadata belongs to PlanningDecision. STOP maps to NO_VALID_CANDIDATE; it never
establishes OBJECTIVE_COMPLETE or scanner success.

## Replanning and completion

Task 20 validates previous decision/feedback context, revision and action before
the strategy. The current snapshot may have a new revision. Strategy requires
the same objective, a Task 22 proposal and previous actual mode LLM. A previous
fallback cannot silently switch back to LLM through this replan path.

- DENIED: stop before provider, regardless of alternative candidates.
- FAILURE/ERROR: exclude the previous unchanged version. Another eligible
  offline review item or changed candidate may be considered.
- PARTIAL: exclude the unchanged version and require a candidate source
  observation listed in feedback. Partial output does not establish completion.
- SUCCESS: require a matching completion CONTROL fact with value=true,
  confidence=1.0, matching target and observation ID present in feedback.
- No eligible progress: stop before provider; unrelated state/budget changes
  cannot change the candidate fingerprint and bypass repeat suppression.

llm_review_control_id only computes an identity. A coordinator/normalizer must
write a completion fact after verified review, never at proposal creation. A
valid completion suppresses the same candidate version across planner instances;
changed candidate data or a different context/objective has a different identity.
CONTROL facts are checked for shape and identity only; trusted source/evidence
binding remains an integration requirement. Planner never writes state/receipts.

Failure history is supplied through replan, not hidden mutable instance memory.
Calling plan afresh without stored completion/history can repeat unfinished work;
the coordinator must preserve causal feedback and use replan. Persistent failure
journaling and full history integrity are UNRESOLVED.

## Validation receipts

Source: SIMULATED_FIXTURE, synthetic run RUN-022-FIXTURE. Expected: proposal-only
offline metadata review; rejection of invalid input/output; no state mutation or
double budget charge; feedback-bound replan; no network/process dispatch. These
checks do not establish real LLM/provider/runtime execution.

Initial focused invocation below exited 1: 29 tests, 28 passed and one fixture
error because the new test used incorrect Task 19 keyword names. The fixture was
corrected to the existing budget/allowed_actions/source_sha256 API and canonical
observation fields. Preserve this failed receipt; it is not a passing attempt.

```text
python -B -m unittest discover -s tests/runtime -p test_llm_planner.py -v
```

Receipt collection UTC: 2026-10-11T20:57:12.3960969Z (local Asia/Saigon date
2026-10-12). Redaction: synthetic fixtures only; no credentials or raw provider
errors recorded. Source hashes below bind the Python files for this receipt,
not a historical runtime run or a signed approval.

| Check | Exit | Observed |
|---|---|---|
| Focused suite after fixture correction | 0 | 29 tests PASS |
| Final focused suite after revision/omitted-selection checks | 0 | 31 tests PASS |
| Task 20 interface regression | 0 | 28 tests PASS |
| Task 19 store regression | 0 | 21 tests PASS |
| Task 21 rule baseline regression | 0 | 28 tests PASS |
| Canonical planner contract regression | 0 | 16 tests PASS |
| AST and document check | 0 | AST PASS 2 files; document_errors=0 |
| Explicit untracked content/link check | 0 | Whitespace PASS 3 files; local links PASS 3 |
| Scoped git diff --check | 0 | No output; untracked content checked separately |
| Full repository checker, classified by scope | 1 | repository_errors=613; task022_errors=0 |

Final distinct test set: 31 focused + 93 regression = 124 tests PASS. The earlier
29-test runs are not added to this total. Dependency suites were run before the
final Task 22-only revision change; dependency source files were not edited.
Expected assertions listed above passed on synthetic snapshots and SQLite
in-memory store. Network/process guards cover the fixture invocation; they do not
certify arbitrary injected providers, real transport or provider timeouts.

Exact successful test commands:

```text
python -B -m unittest discover -s tests/runtime -p test_llm_planner.py -v
python -B -m unittest discover -s tests/runtime -p test_planner_interface.py
python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py
python -B -m unittest discover -s tests/runtime -p test_rule_based_planner.py
python -B -m unittest discover -s tests/planner -p test_planner_contracts.py
```

Exact structural/content commands:

```text
python -B -c "import ast; from pathlib import Path; from scripts.validation.validate_scaffold import _check_markdown; paths=('runtime/llm_planner.py','tests/runtime/test_llm_planner.py'); [ast.parse(Path(p).read_text(encoding='utf-8'),filename=p) for p in paths]; errors=[]; _check_markdown(Path('runtime/llm_planner.md'),errors); print('AST PASS: 2 files'); print('document_errors='+str(len(errors))); print('\n'.join(errors)); raise SystemExit(1 if errors else 0)"
python -B -c "from pathlib import Path; import re; paths=('runtime/llm_planner.py','runtime/llm_planner.md','tests/runtime/test_llm_planner.py'); assert all(not line.endswith((' ',chr(9))) for p in paths for line in Path(p).read_text(encoding='utf-8').splitlines()); document=Path('runtime/llm_planner.md'); links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',document.read_text(encoding='utf-8')); assert all((document.parent/target).resolve().is_relative_to(Path.cwd()) and (document.parent/target).exists() for target in links); print('WHITESPACE PASS: 3 files'); print('LOCAL LINKS PASS: '+str(len(links))); print('UNTRACKED FILE CONTENT CHECKED')"
git diff --check -- runtime/llm_planner.py runtime/llm_planner.md tests/runtime/test_llm_planner.py
```

Exact repository checker, retaining exit 1 for any repository error:

```text
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('runtime/llm_planner.py','runtime/llm_planner.md','tests/runtime/test_llm_planner.py'); errors=validate(); affected=[e for e in errors if any(p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task022_errors='+str(len(affected))); print('\n'.join(affected).encode('ascii','backslashreplace').decode()); print('outside_scope_examples:'); print('\n'.join(e for e in errors[:6] if e not in affected).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

Observed examples outside allowlist: dashboards/app/README.md,
dashboards/app/frontend/README.md and dashboards/app/frontend/node_modules/**.
Do not repair/delete these paths within this task. The observed 613 errors belong
to this invocation; do not reinterpret older checker receipts as passing.

Source SHA-256, exact command:

```text
Get-FileHash -Algorithm SHA256 runtime/llm_planner.py, tests/runtime/test_llm_planner.py
```

- runtime/llm_planner.py: 0D47635109BE1337769A1FFD520836035DBCB1A43BA1EF6030E6ACA0C864BA60
- tests/runtime/test_llm_planner.py: 9136E5C2F3F733A1452F264B19C6B2E3F5C428DA727444EADDCAE5A34EA9A82E

This document is an implementation receipt, not an immutable evidence recorder.
Existing evidence was not opened for writing or overwritten. No runtime success,
independent review, provider/model identity or deployment claim is made.

## Đồng bộ tài liệu và trạng thái ngày 2026-10-12

Người dùng yêu cầu cập nhật tài liệu/trạng thái. TASK-022 đổi SPEC_ONLY →
IMPLEMENTED chỉ cho offline metadata evidence-review subset; chưa VALIDATED.
Hai source SHA-256 phía trên khớp receipts triển khai khi đối chiếu lại; không
chạy lại 124 tests hoặc provider/model trong lần sửa tài liệu này. IMPLEMENTED
không cấp runtime/per-action approval hoặc đóng acceptance.

Receipt UTC: 2026-10-11T21:08:41.8489137Z; source là workspace documents và
implementation receipts đã đối chiếu hashes; không thêm synthetic/live run mới,
credentials hoặc raw provider data. Expected: năm tài liệu thống nhất phạm vi
offline và status; chỉ Task 22 đổi trạng thái, dependencies/source giữ nguyên.
Observed: các checks tài liệu và status/source bên dưới PASS; repository vẫn
FAIL ngoài scope.

| Check của lần cập nhật tài liệu | Exit | Observed |
|---|---|---|
| Scoped headings/link/anchor/whitespace | 0 | scoped_document_errors=0; local_links_checked=81; anchors_checked=21; whitespace PASS 5 documents |
| Status/dependencies/source hashes | 0 | 35 task IDs; chỉ TASK-022 đổi trạng thái; dependencies và 34 trạng thái khác giữ nguyên; hai source hashes khớp |
| Scoped git diff --check | 0 | Không whitespace errors; LF/CRLF warnings ở PROJECT_CONTEXT.md và PROJECT_PLAN.md |
| Full repository checker, scope tài liệu | 1 | repository_errors=613; task022_document_errors=0; HANDOFF_BLOCKED |

Exact commands:

```text
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-022-llm-planner.md','runtime/llm_planner.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not re.match(r'[a-z]+://',target)]; anchors=0; root=v.ROOT.resolve();
for p,target in links:
 filepart,separator,fragment=target.partition('#'); destination=((root/p).parent/filepart).resolve() if filepart else root/p; assert destination.is_relative_to(root) and destination.exists(),(p,target)
 if separator and fragment:
  text=destination.read_text(encoding='utf-8'); headings=re.findall(r'^#{1,6} +(.+)$',text,re.M); slugs=[re.sub(r'[^\w -]','',h.lower()).replace(' ','-') for h in headings]; assert fragment in slugs,(p,target); anchors+=1
assert all(not line.endswith((' ',chr(9))) for p in paths for line in (root/p).read_text(encoding='utf-8').splitlines()); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('anchors_checked='+str(anchors)); print('WHITESPACE PASS: 5 documents'); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
python -B -c "import hashlib,re,json; from pathlib import Path; text=Path('TASKS.md').read_text(encoding='utf-8'); rows={m[0]:[m[1],m[2]] for m in re.findall(r'^\| (TASK-\d{3}) \| [^|]+ \| .(\w+). \| ([^|]+) \|',text,re.M)}; assert len(rows)==35; assert rows['TASK-022']==['IMPLEMENTED','TASK-020, TASK-003']; assert rows['TASK-026'][0]==rows['TASK-032'][0]=='DEFERRED'; assert all(rows['TASK-'+str(n).zfill(3)][0]=='SPEC_ONLY' for n in (23,24,25,27,28,29,30,31,33,34,35)); spec=Path('docs/task-specs/TASK-022-llm-planner.md').read_text(encoding='utf-8'); assert 'IMPLEMENTED' in spec.split('## Status',1)[1].split('## Purpose',1)[0]; assert 'Tasks 022-025' not in text; expected={'runtime/llm_planner.py':'0d47635109be1337769a1ffd520836035dbcb1a43ba1ef6030e6aca0c864ba60','tests/runtime/test_llm_planner.py':'9136e5c2f3f733a1452f264b19c6b2e3f5c428da727444eaddcae5a34ea9a82e'}; assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in expected.items()); print(json.dumps(rows,sort_keys=True))"
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-022-llm-planner.md','runtime/llm_planner.md'); errors=validate(); affected=[e for e in errors if any(p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task022_document_errors='+str(len(affected))); print('\n'.join(affected).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-022-llm-planner.md
```

Bảng status/dependencies được capture trước edits bằng cùng regex trên TASKS.md,
rồi đối chiếu output JSON sau edits: changed task list đúng [TASK-022]. Các checks
này không tái xác nhận validation/runtime lịch sử của task khác.

Exact changed files của lần cập nhật tài liệu:

- PROJECT_CONTEXT.md
- PROJECT_PLAN.md
- TASKS.md
- docs/task-specs/TASK-022-llm-planner.md
- runtime/llm_planner.md

Deleted files: none. Không đổi code/tests/contracts/configuration/catalog/evidence,
không append history, tự review/approve hoặc nâng các task phụ thuộc.
Unverified/blockers và required next giữ như payload dưới đây. Repository FAIL
không được chuyển thành PASS từ các scoped checks.

## Pending handoff

Payload: task=TASK-022; scope=offline metadata evidence review; build and plan IDs
as above; status=HANDOFF_BLOCKED;
blocker=REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE; files=the three added paths;
deleted_files=none; receipts=124 distinct tests PASS, structural checks PASS,
repository exit 1; unverified=real provider/tokenizer/transport, durable evidence,
reference and history integrity, coordinator/gate integration, independent review.
Required next: repair repository blockers in separately assigned scope, then
independent interface/context/feedback review, then separately approved
reference/evidence and provider/coordinator integration. Do not
self-approve, finalize, append history or modify files outside this allowlist.
