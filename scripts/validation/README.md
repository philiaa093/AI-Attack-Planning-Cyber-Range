# Scaffold validator repair

## Status and scope

`IMPLEMENTED` at the user's request on 2026-10-12; independent review pending.
This repair addresses the 613 scaffold-gate errors diagnosed in this chat. It does
not extend runtime permissions, change canonical task status vocabulary, approve
training or transfer historical foundation validation to the modified validator.

Sources: AGENTS.md, PROJECT_CONTEXT.md, PROJECT_PLAN.md, TASKS.md, TASK-001,
ADR-010/012, the existing validator and its scaffold/safety tests.
Working tree was already dirty; unrelated edits are preserved. No files deleted.
No contracts, catalog, safety configuration, scenarios or evidence were edited.

## Cause and changes

The initial observed gate had 613 unique error messages: 604 inside installed
frontend node_modules, five in dashboard-owned files and four in the preserved
Task-015 report. They were 268 external-URL errors, 190 forbidden-field matches,
118 malformed/missing-link errors, 34 JSON-read errors, two status errors and one
dependency binary error. These are validation messages, not vulnerability findings.

[validate_scaffold.py](validate_scaffold.py) now uses one deterministic owned-file
walker for generic Markdown, structured-data and artifact scans. It prunes only
these exact workspace-relative trees:

- .git, .venv and venv at the workspace root;
- dashboards/app/frontend/node_modules;
- dashboards/app/frontend/dist.

Names elsewhere remain in scope: configs/node_modules and agent/.venv are not
exempt. The walker fails on directory-read errors and does not obey .gitignore,
so an ignore pattern cannot suppress
contract validation. The new .gitignore entries prevent dependency/build files
from being added inadvertently; they are not the validator's source of authority.

The generic action-field and task-status rules distinguish runtime/contract data
from JSON reports and the three reserved frontend package/lock/tsconfig files.
These metadata/report files still undergo JSON syntax checks. Report command
receipts and handoff/worktree states are documentation data; they do not authorize
execution. Role is determined by path, so a forged document_type under configs,
actions, agent, scenarios, evidence or tools cannot bypass the original rules.
Canonical safety, schemas, IDs, dependencies, budgets, ground-truth isolation,
evidence retention and runtime public-target checks remain active.

Only the frontend tsconfig accepts line/block comments, with string contents and
line/column positions preserved. Malformed JSON, unterminated comments, non-finite
numbers and trailing commas remain rejected. Other JSON and JSON-compatible YAML
stay strict; this patch introduces no general YAML parser or parser dependency.

The two dashboard README loopback hyperlinks are now inline-code addresses,
consistent with the existing external-link policy. That policy and real missing
or escaping source links remain enforced. No dependency contents were rewritten.

## Tests and command receipts

The initial repaired gate returned SCAFFOLD VALID, exit 0:
files_checked=6525; schemas_checked=10; actions_checked=13; tasks_checked=35;
adrs_checked=13. File count reflects owned workspace files at check time.

| Exact command | Exit | Observed result |
|---|---:|---|
| `python -B scripts/validation/validate_scaffold.py` | 0 | SCAFFOLD VALID, 0 errors |
| `python -B -m unittest discover -s tests/scaffold -p test_*.py -v` | 0 | 46 tests PASS, including 15 new regressions |
| `python -B -m unittest discover -s tests/safety -p test_*.py -v` | 0 | 31 tests PASS |
| `python -B -m unittest discover -s tests/contracts -p test_*.py -v` | 0 | 12 tests PASS |
| `python -B -m unittest discover -s tests/planner -p test_*.py -v` | 0 | 16 tests PASS |
| `python -B -m unittest discover -s tests/evaluation -p test_*.py -v` | 0 | 7 tests PASS |

New regression tests are in
[test_scan_scope.py](../../tests/scaffold/test_scan_scope.py). They verify exclusion
boundaries, live contract checks despite .gitignore, path-based role assignment,
syntax checking of reports/npm metadata, strict parsing outside tsconfig, real
source AST/cache/binary failures, directory-read errors and continued Markdown-link
restrictions. The first scaffold run passed 45 tests; one final fail-closed walker
regression was added, and the repeated scaffold run passed 46 tests.

Receipt UTC: 2026-10-11T23:55:13.6617063Z (local date 2026-10-12 Asia/Saigon).
AST parsing of the two changed/new Python files passed. Source hashes:

```text
scripts/validation/validate_scaffold.py
68b4f6ac21f3eccfd46860771d27265afb6a419885899248200aaaf26d0299b3
tests/scaffold/test_scan_scope.py
af992d4d6c84a98ff74e26f23a0d4ce9e384f467cbd8b634f1fadaa3e421977d
```

The baseline validator hash was
957805634997508c747633a2baf5ca5a08cd8fc79090a761eaf74b6ec593897c.
Hash comparison confirmed the following sources were preserved:

```text
reports/TASK-015-offline-contracts.json
2462e0e9353a8f2646d3a34478a4fef27fcc6d46aefa6c383e4a400e9eb34af6
dashboards/app/frontend/tsconfig.json
d3f293f50d6811619052d86c22d7a3c05314e999702100fcd046a72db6e0b46d
dashboards/app/frontend/package-lock.json
cc71e2cf47cbea869265408151949ba7a2008a129aede1d87ca399cd06ccc12c
runtime/reward_model.py
88017247c6f67d82ff5f4510801a75f935f1f7d43bc19a0bf7ba9fb1730ae162
tests/runtime/test_reward_model.py
f729b86e9bf8c80f0fb84cb17e60adbeb2a24a2bf6855f5b94e1a74b0c46f4d7
```

`git diff --check -- scripts/validation/validate_scaffold.py .gitignore` returned
exit 0. The final check also covers the README/doc edits and new test file explicitly.
No immutable evidence/run record is claimed by this documentation receipt.

## Final check receipts

Gate repeated on the final code after document synchronization: exit 0,
SCAFFOLD VALID, files_checked=6606, schemas_checked=10, actions_checked=13,
tasks_checked=35, adrs_checked=13. Receipt UTC: 2026-10-12T00:01:26.8431425Z.
The workspace file count changed between checks; receipts retain the actual counts
observed at each check and do not attribute all workspace changes to this repair.

The final scaffold suite passed 46 tests. Safety was rerun after adding the
directory-read-error regression: 31 tests PASS, exit 0. The latest suite receipts
total 112 tests (46 scaffold + 31 safety + 12 contracts + 16 planner + 7 evaluation).
None of these receipts grants independent review or runtime validation.

Scoped document check: exit 0, eight documents, 100 local links, zero document
errors. Exact command:

```powershell
python -B -c "from pathlib import Path; import re; import scripts.validation.validate_scaffold as v; paths=['PROJECT_CONTEXT.md','PROJECT_PLAN.md','TASKS.md','docs/task-specs/TASK-024-reward-model.md','runtime/reward_model.md','scripts/validation/README.md','dashboards/app/README.md','dashboards/app/frontend/README.md']; errors=[]; [v._check_markdown(v.ROOT/p,errors,v.TASK_HEADINGS if p.startswith('docs/task-specs/') else v.ROOT_HEADINGS.get(p)) for p in paths]; links=[(p,target) for p in paths for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',(v.ROOT/p).read_text(encoding='utf-8')) if not target.startswith('#') and not re.match(r'[a-z]+://',target)]; assert all(((v.ROOT/p).parent/target.split('#',1)[0]).resolve().is_relative_to(v.ROOT) and ((v.ROOT/p).parent/target.split('#',1)[0]).resolve().exists() for p,target in links); print('scoped_document_errors='+str(len(errors))); print('local_links_checked='+str(len(links))); print('\n'.join(errors).encode('ascii','backslashreplace').decode()); raise SystemExit(1 if errors else 0)"
```

AST/source hashes: exit 0. Exact command:

```powershell
python -B -c "from pathlib import Path; import ast,hashlib; paths=['scripts/validation/validate_scaffold.py','tests/scaffold/test_scan_scope.py']; [ast.parse(Path(p).read_text(encoding='utf-8'),filename=p) for p in paths]; [print(p+' SHA256='+hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in paths]; print('AST: PASS')"
```

Final preservation check: exit 0, five hashes match. Exact command:

```powershell
python -B -c "from pathlib import Path; import hashlib; expected={'reports/TASK-015-offline-contracts.json':'2462e0e9353a8f2646d3a34478a4fef27fcc6d46aefa6c383e4a400e9eb34af6','dashboards/app/frontend/tsconfig.json':'d3f293f50d6811619052d86c22d7a3c05314e999702100fcd046a72db6e0b46d','dashboards/app/frontend/package-lock.json':'cc71e2cf47cbea869265408151949ba7a2008a129aede1d87ca399cd06ccc12c','runtime/reward_model.py':'88017247c6f67d82ff5f4510801a75f935f1f7d43bc19a0bf7ba9fb1730ae162','tests/runtime/test_reward_model.py':'f729b86e9bf8c80f0fb84cb17e60adbeb2a24a2bf6855f5b94e1a74b0c46f4d7'}; assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in expected.items()); print('preserved_hashes=5 PASS')"
```

`git diff --check -- scripts/validation/validate_scaffold.py .gitignore PROJECT_CONTEXT.md PROJECT_PLAN.md TASKS.md docs/task-specs/TASK-024-reward-model.md`
returned exit 0. `git check-ignore dashboards/app/frontend/node_modules/.package-lock.json dashboards/app/frontend/dist`
returned exit 0 and listed both paths. These checks include pre-existing edits in
tracked documents; they do not assert ownership of those earlier changes.

## Current handoff

The 613-error repository-checker blocker is resolved by the passing gate. Task-024
remains IMPLEMENTED for its standalone scorer subset, with independent review,
config acceptance, durable evidence, environment integration and calibration still
pending. Old failed gate receipts in task documentation and reports are historical
observations and are not rewritten as PASS. Other tasks need their own handoff
assessment; this repair does not grant global acceptance or runtime approval.

Exact changed files in this repair: scripts/validation/validate_scaffold.py,
.gitignore, tests/scaffold/test_scan_scope.py, dashboards/app/README.md,
dashboards/app/frontend/README.md, scripts/validation/README.md, PROJECT_CONTEXT.md,
PROJECT_PLAN.md, TASKS.md, docs/task-specs/TASK-024-reward-model.md and
runtime/reward_model.md. No deleted files.
