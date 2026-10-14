# Task 21 — Rule-based planner ngoai tuyen

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

Implementation artifact: `IMPLEMENTED` for offline evidence-review selection.
Canonical TASK-021 is `IMPLEMENTED` for this offline subset, updated at the user's
request on 2026-10-12; not `VALIDATED`. Independent review, durable evidence
integration, full research baseline and executable runtime remain `UNRESOLVED`.

## Scope and sources

[Implementation](../../runtime/planners/rule_based_planner.py) subclasses the
[Task 20 interface](../../runtime/planners/planner_interface.py). [Focused tests](../../tests/runtime/test_rule_based_planner.py)
include a synthetic SQLite integration through the [Task 19 store](../../runtime/state/knowledge_state_store.py).
This is an offline baseline for review work, not the full research planner or a
scanner strategy. It only proposes the existing `ACTION-PLAN-003`
(`REVISIT_EVIDENCE`) from the [canonical catalog](../../actions/catalog/action-catalog.json).

Sources: [project context](../../PROJECT_CONTEXT.md), [project plan](../../PROJECT_PLAN.md),
[task status](../../TASKS.md), [Task 21 specification](../task-specs/TASK-021-rule-based-planner.md),
[state schema](../../agent/planner/contracts/state.schema.json),
[plan schema](../../agent/planner/contracts/plan.schema.json),
[separation](../adr/ADR-005-planner-executor-perception-separation.md),
[shared interface](../adr/ADR-006-shared-planner-interface.md),
[ground-truth isolation](../adr/ADR-009-ground-truth-isolation.md),
[equal budgets](../adr/ADR-011-same-budgets-across-planners.md),
[evidence immutability](../adr/ADR-010-evidence-immutability.md), and
[safety control](../adr/ADR-012-safety-engine-control.md).

Contracts/catalog/configurations, existing runner, adapters and historical evidence
are unchanged. No writable store is passed to the strategy, no budget is charged
by the planner, and no evidence is written by this module.

## Rules and decision behavior

`Rule` is a frozen dataclass with a typed ID, integer priority, immutable phase
set and optional confidence threshold. The closed predicate matches only
`CANDIDATE_FINDING`. Phases are restricted to `ANALYSIS` and `REPLAN`.
No eval, external callbacks, shell, tool names, template selection or dynamic
action is accepted. Rule configuration must come from trusted application code.

Default rules:

| Rule ID | Priority | Predicate |
|---|---|---|
| REVIEW_LOW_CONFIDENCE | 100 | Candidate confidence strictly below 0.8 |
| REVIEW_CANDIDATE | 50 | Any remaining candidate |

The 0.8 threshold is a baseline setting, not a calibrated probability.
Zero confidence means unevaluated; it is not a negative result. Proposal
confidence is a fixed uncalibrated 0.5 and never confirms a vulnerability.
Confirmed facts alone do not generate new work in this baseline.

Rules sort by descending priority then ascending rule ID. Candidates sort by
fact ID. A candidate subject must be an explicit typed lab target and must belong
to the caller's candidate target set; no target/endpoint is guessed. Malformed
candidate references or review controls raise ValueError. Fact values remain data;
they are hashed for identity but never become instructions or output text.

`Planner.plan/replan` remain the validated Task 20 entry points. Budget, terminal
state, scope, context, objective, mode and feedback checks retain Task 20 semantics.
No candidate returns `NO_VALID_CANDIDATE`, never an objective-success claim.
An empty rule tuple deliberately gives no candidate. Up to 64 rules are supported.

## Completion and replan

Proposal `plan_id` hashes the run/session/episode context, objective, review action
and full candidate fact. Input revision remains in `PlanningDecision`. Budget-only
updates, rule ordering and unrelated facts do not change the review identity;
changed candidate content/confidence/provenance or context creates new work.
This hash is an identity, not a signature or authorization.

After verified completion, the coordinator may normalize a planner-specific
`CONTROL` fact using the existing schema:

- fact_id: `review_control_id(previous.proposal)`;
- subject: the proposal target;
- value: boolean True; confidence: 1.0;
- source_observation_id: assigned from the completion observation by the store.

The helper returns an ID only; it neither creates a receipt nor marks completion.
This convention is local to this offline consumer; it does not change global
CONTROL semantics or authorize an executor. A valid completion suppresses all
rules for that candidate version even after creating a new planner instance.
Value 1/False, malformed IDs, wrong target or insufficient receipt confidence
are rejected. Facts unrelated to this convention are not completion receipts.

`replan` advances only on SUCCESS feedback from a RULE decision with an objective
matching the new snapshot and a matching completion CONTROL sourced from one of
the feedback observation IDs. DENIED/ERROR/FAILURE/PARTIAL, absent completion,
unrelated state changes and feedback from another backend stop safely. The shared
interface also checks feedback context/revision/action. Strategy switching and
retry policy are separate coordinator work. The planner never writes completion.

Receipt source integrity, authenticity, evidence-before-state ordering, stale-state
checks before dispatch and authorization are coordinator/gate responsibilities.
Imported scanner data must never be allowed to fabricate completion controls.
The store's source/hash metadata and caller scope alone do not prove approval.
Direct repeated plan calls return the same unresolved intent until a verified
completion is present; the coordinator must still enforce its no-progress limit.

## Synthetic example without dispatch

```python
from agent.memory.state.state_manager import StateManager
from runtime.state.knowledge_state_store import StoreContext
from runtime.planners.planner_interface import PlanningInput, StateSnapshot
from runtime.planners.rule_based_planner import RuleBasedPlanner, REVIEW_ACTION

context = StoreContext("RUN-021-EXAMPLE", "SESSION-1", "EPISODE-1")
state = StateManager(context.run_id, "SCN-001", "OBJ-021",
                     dict(actions=5, requests=10, seconds=60.0)).get_state()
state["phase"] = "ANALYSIS"
state["observed_facts"] = [{
    "fact_id": "F-1", "fact_type": "CANDIDATE_FINDING",
    "subject": "lab-fixture", "value": "synthetic_candidate",
    "confidence": 0.5, "source_observation_id": "OBS-FIXTURE",
}]
request = PlanningInput(StateSnapshot.from_state(state, context=context),
                        {REVIEW_ACTION}, {"lab-fixture"})
decision = RuleBasedPlanner().plan(request)
assert decision.proposal.to_dict()["reason_code"] == "REVIEW_LOW_CONFIDENCE"
assert request.state.to_dict() == state
```

For Task 19, replace `StateSnapshot.from_state` with
`StateSnapshot.from_store(store, context)`. The planner only receives the snapshot.
ZAP/Nuclei report import/normalization is upstream offline work; this strategy
does not start scanners, call adapters or integrate with the runner/gate.

## Checks and pending handoff

Build label: `BUILD-TASK021-RULE-OFFLINE-20261012`, not an approved build.
Observed source HEAD: `d9ae6ca0d5bb03ce381d7249665237f272eeddc9`.
Working tree contained pre-existing user changes. Source: synthetic RUN-021
fixtures and an in-memory SQLite journal; not a live scanner or lab run.
Durable evidence packaging/redaction/review linkage remain `UNRESOLVED`.

Receipt UTC: `2026-10-11T20:36:52.100867+00:00`; local date Asia/Saigon is
2026-10-12. Initial check had 26 new tests; final check has 28 after adding
context/objective completion isolation and scope-revocation cases. Dependency
checks have 65 tests. All four suites exit 0; 93 tests total on final code.
No runtime, independent approval or VALIDATED claim.

| Exact command | Exit | Observed |
|---|---|---|
| `python -B -m unittest discover -s tests/runtime -p test_rule_based_planner.py -v` | 0 | 28 tests PASS; initial 26 PASS |
| `python -B -m unittest discover -s tests/runtime -p test_planner_interface.py -v` | 0 | 28 tests PASS |
| `python -B -m unittest discover -s tests/runtime -p test_knowledge_state_store.py -v` | 0 | 21 tests PASS |
| `python -B -m unittest discover -s tests/planner -p test_planner_contracts.py -v` | 0 | 16 tests PASS |
| `git diff --check -- runtime/rule_based_planner.py runtime/rule_based_planner.md tests/runtime/test_rule_based_planner.py` | 0 | Tracked diff clean; new files checked explicitly below |
| AST/example/whitespace command below | 0 | AST PASS 2 files; DOCUMENT EXAMPLE PASS; WHITESPACE PASS 3 files |
| Full repository checker command below | 1 | repository_errors=656; task021_errors=0; HANDOFF_BLOCKED |

Exact AST/example/whitespace command (PowerShell):

```powershell
@'
import ast, hashlib
from pathlib import Path
from datetime import datetime, timezone
paths=['runtime/rule_based_planner.py','tests/runtime/test_rule_based_planner.py']
for name in paths:
    ast.parse(Path(name).read_text(encoding='utf-8'),filename=name)
print('AST PASS: 2 files')
text=Path('runtime/rule_based_planner.md').read_text(encoding='utf-8')
fence=chr(96)*3
example=text.split(fence+'python\n',1)[1].split('\n'+fence,1)[0]
exec(compile(example,'rule_based_planner.md example','exec'))
print('DOCUMENT EXAMPLE PASS')
for name in paths+['runtime/rule_based_planner.md']:
    raw=Path(name).read_bytes()
    assert raw.endswith(b'\n')
    assert all(not line.endswith((' ',chr(9))) for line in raw.decode('utf-8').splitlines())
    if name.endswith('.py'):
        print(name+': '+hashlib.sha256(raw).hexdigest())
print('WHITESPACE PASS: 3 files')
print('receipt_utc='+datetime.now(timezone.utc).isoformat())
'@ | python -X utf8 -B -
```

Exact full repository check; filtering classifies errors and does not bypass them:

```text
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('runtime/rule_based_planner.py','runtime/rule_based_planner.md','tests/runtime/test_rule_based_planner.py'); errors=validate(); affected=[e for e in errors if any(p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task021_errors='+str(len(affected))); print('\n'.join(affected)); print('outside_scope_examples:'); print('\n'.join([e for e in errors if e not in affected][:6])); raise SystemExit(1 if errors else 0)"
```

Observed outside-scope examples: external URLs in dashboards/app/README.md and
dashboards/app/frontend/README.md; forbidden command/payload fields in
dashboards/app/frontend/node_modules/.package-lock.json; external URLs in
dependency documentation. No edits/deletions or checker bypass were made there.

Source SHA-256 from the command above:

- runtime/rule_based_planner.py: `111db40a51f76ceb6c1704b20f8cf84291ff5bce08b9c50df3fb478e138bf048`
- tests/runtime/test_rule_based_planner.py: `36001d27b4bc8f4f45bccc59ad674fdc56a1a067bfcb677b35d859d9e16ea61b`

Expected/observed: deterministic review selection; schema-bound output; explicit
target scope; malformed references rejected; no network/process dispatch in the
guarded test; immutable input and unchanged SQLite state/journal during planner
calls; budget owned by StateManager; completion linked to feedback; replay equal
to stored state. Assertions PASS. Inputs are synthetic and minimized; existing
Task 20 redaction checks apply, but exhaustive redaction is unverified. The source
fixture digest is SHA-256 of `task021-synthetic-fixture`, not a real scanner report.
These receipts are documentation and do not replace an immutable evidence package.

Implementation-session added paths: runtime/rule_based_planner.py,
runtime/rule_based_planner.md, tests/runtime/test_rule_based_planner.py.
Deleted paths: none. That session did not update canonical task status, edit
contracts, append history, self-approve or finalize. The subsequent documentation
update below changes canonical status only for the implemented offline subset.

## Documentation and task-status update — 2026-10-12

At the user's request, TASKS.md, PROJECT_CONTEXT.md, PROJECT_PLAN.md,
docs/task-specs/TASK-021-rule-based-planner.md and this document now consistently
describe TASK-021 as `IMPLEMENTED` for offline evidence-review selection.
The first four are status/context/specification documents; this artifact retains
the implementation-session receipts above. Existing dirty changes are preserved.
No Python source, test, contract, configuration, catalog, scenario or evidence
was modified; no file deleted; no history append, approval or finalization.

Source SHA-256 for both Python files was checked and matches the implementation
receipts. The 93-test result is from the implementation session, not a rerun
during the status update. Documentation checks are separate receipts; tests and
runtime do not become validated through this update. Independent review,
completion-source authenticity and evidence/coordinator integration remain pending.

Documentation receipt UTC: `2026-10-11T20:47:24Z`; local date Asia/Saigon is
2026-10-12. Expected/observed: status agrees across the five documents; dependency
remains TASK-020; source hashes match; pending review/runtime boundaries remain
explicit. Inputs are repository documents and synthetic-source receipts, with no
production data or new evidence writes.

| Documentation check | Exit | Observed |
|---|---|---|
| `Get-FileHash -Algorithm SHA256 runtime/rule_based_planner.py, tests/runtime/test_rule_based_planner.py` | 0 | Both source hashes match implementation receipts |
| Scoped document/status/hash command below | 0 | Headings, local links, whitespace, status, dependency and source hashes PASS; 92 local links |
| `git diff --check -- PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-021-rule-based-planner.md runtime/rule_based_planner.md` | 0 | No whitespace errors |
| Documentation repository checker below | 1 | repository_errors=656; task021_docs_errors=0; HANDOFF_BLOCKED |

Exact scoped document/status/hash check (PowerShell):

```powershell
@'
import hashlib, re
from scripts.validation.validate_scaffold import ROOT, ROOT_HEADINGS, TASK_HEADINGS, _check_markdown, _link_target
scope=('PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-021-rule-based-planner.md','runtime/rule_based_planner.md')
errors=[]
links=0
texts={name:(ROOT/name).read_text(encoding='utf-8') for name in scope}
for name,text in texts.items():
    path=ROOT/name
    _check_markdown(path,errors,TASK_HEADINGS if name.startswith('docs/task-specs/') else ROOT_HEADINGS.get(name))
    assert path.read_bytes().endswith(b'\n')
    assert all(not line.endswith((' ',chr(9))) for line in text.splitlines())
    for raw in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',text):
        kind,target=_link_target(raw)
        if kind=='skip': continue
        destination=(path.parent/target).resolve()
        assert kind=='local' and destination.is_relative_to(ROOT) and destination.exists()
        links+=1
assert not errors, errors
assert re.search(r'^## Status\s*\n\s*`IMPLEMENTED`',texts[scope[3]],re.M)
assert re.search(r'^## Dependencies\s*\n\s*TASK-020\s*\n',texts[scope[3]],re.M)
assert '| TASK-021 | Rule-based planner | `IMPLEMENTED` | TASK-020 |' in texts['TASKS.md']
assert 'Tasks 021-025' not in texts['TASKS.md']
assert 'Canonical TASK-021 is ' + chr(96) + 'IMPLEMENTED' + chr(96) in texts[scope[4]]
for task in ('TASK-026','TASK-032'):
    assert re.search(r'\| '+task+r' \|[^\n]*`DEFERRED`',texts['TASKS.md'])
for name in ('runtime/rule_based_planner.py','tests/runtime/test_rule_based_planner.py'):
    digest=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    assert digest in texts[scope[4]], name
print('DOC/STATUS/DEPENDENCY/HASH/WHITESPACE PASS; local_links='+str(links))
'@ | python -X utf8 -B -
```

Exact full repository check for the documentation scope:

```text
python -B -c "from scripts.validation.validate_scaffold import validate; scope=('PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-021-rule-based-planner.md','runtime/rule_based_planner.md'); errors=validate(); affected=[e for e in errors if any(p in e for p in scope)]; print('repository_errors='+str(len(errors))); print('task021_docs_errors='+str(len(affected))); print('\n'.join(affected)); print('outside_scope_examples:'); print('\n'.join([e for e in errors if e not in affected][:6])); raise SystemExit(1 if errors else 0)"
```

The 656 repository errors are outside these five documents; observed examples
remain dashboard/dependency documentation and package metadata. Filtering records
scope attribution and still returns exit 1 for any repository error. No blockers
were removed or bypassed. Pending handoff and unverified items remain below.

Pending payload: scope=TASK-021 offline review-only strategy;
status=HANDOFF_BLOCKED; blocker=REPOSITORY_CHECKER_FAILED_OUTSIDE_SCOPE;
independent_review=UNRESOLVED; durable_evidence_and_coordinator_integration=UNRESOLVED;
scanner_and_full_research_baseline=UNRESOLVED;
required_next=resolve repository blockers in separately assigned scope, then
independent strategy/reference review and approved recorder/coordinator integration.
