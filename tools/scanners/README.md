# Isolated ZAP and Nuclei integration

Implementation scope: bounded, unauthenticated HTTP lab checks. This does not
implement a comprehensive pentest, authenticated workflows, POST submissions,
business-logic testing, or confirmed exploitation. Independent review remains pending.

## Web workflow

In the run dialog, approve bounded active lab checks, then select one ZAP mode
and/or Nuclei. Preview and deny-demo runs cannot select external scanners.
The backend checks local pinned images before creating the run; it never pulls
images automatically or falls back to an internal verifier under a scanner name.
Restart the dashboard backend after installing this code.

The planner receives ACTION-SCAN-002 only when scanners are selected and the
action is allowed by canonical policy and run approval. Discovery and passive
analysis precede the scan. The runner refuses a second execution of the batch.
Scanner seeds preserve observed query values, including repeated and blank values.
GET form text/search fields without observed values use an empty value. Discovery
records up to 16 explicit option values (128 characters each) per enabled single
select in GET forms. Seeds prefer a nonempty selected option, otherwise the first
nonempty observed option, and retain these values alongside text/search fields.
Disabled options/groups, sensitive values and POST form values are excluded.
Option labels without a value attribute and multi-select controls are unsupported.
An observed value is a starting input, not proof that the server accepts it.
Every retained select option now receives a seed URL, including the empty option,
with other controls held at their observed defaults. This varies one select at a
time, not all combinations. The 16-option and 100-seed limits remain explicit:
overflow and unrequested seeds prevent a complete-coverage claim. ZAP accesses
all queued seeds before active probes. Results include seed_coverage counts for
observed, selected, requested, successful (HTTP 2xx) and unrequested seeds.
The LLM can still stop before proposing it; such selections are NOT_RUN, not clean.
Assisted/manual mode retains the existing per-proposal approval step.

## Tools and limits

Images are locked by immutable local image ID in configs/tools/scanners.json; image IDs,
repository digests and local worker/template SHA-256 hashes are recorded per scan.
The installed versions used for compatibility checks are ZAP 2.16.1 and Nuclei 3.4.10.
The local IDs were obtained from these official repository digests:

- python@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111
- ghcr.io/zaproxy/zaproxy@sha256:7840969c7c9fead565bf9734b12f49f6886db90b1d35b1f74d79710bbd081dab
- projectdiscovery/nuclei@sha256:aeb5ea2db32a252b8135707d2ad0e89b90e19a18ea7816d38759bc51efb46b97

- ZAP passive: access only observed URLs, then wait for passive analysis.
- ZAP active: enable only reflected-XSS rule 40012 and SQL-injection rule 40018.
- Nuclei: only the two bundled, fixed HTTP templates lab-sql-error and
  lab-sentinel-disclosure. These observe response signals; they do not prove
  injection or traversal. No community template download, code/headless/DNS/OAST
  execution, broad template directory, arbitrary command, or new research family.

Only the existing three research families are imported by the strict parsers.
Other ZAP alerts are outside the current normalized finding contract. Raw scanner
reports are hashed in memory, then discarded; immutable evidence stores minimized
candidates and execution provenance, not raw response bodies from the scanner.
The original raw report hash is an identifier, not independently replayable evidence.

## Enforcement

A Python bridge container runs with `--network=none`; each scanner shares only
that network namespace. Neither container mounts the Docker socket, target data,
credentials, evidence directory, or project root. The only bind mount is this
scanner-assets directory, read-only. Both run unprivileged with dropped capabilities,
read-only root filesystems, bounded memory/CPU/processes and bounded temporary storage.

The proxy listens only on container loopback and transports requests over Docker
stdio. On the host, ScannerRelay accepts only the exact lab alias (default port
80 canonicalized), GET/HEAD, observed paths and observed query parameter names.
No scanner-supplied headers or bodies cross the boundary. Every accepted request
passes CentralizedSafetyGate with its original run/target/action approval, rate,
request budget, kill switch and durable intent/result recording. Redirect requests
must pass the same checks. Cookies/authentication and compressed-body handling are
not supported. Refusals are bounded and recorded.

Each tool has a 180-second deadline, a 1 MiB report limit, and shares the run's
HTTP budget. Stop revokes dispatch via the gate and removes only the uniquely named
scanner/bridge containers created for this execution. No target teardown or restore
is performed. Target volumes and old evidence are untouched.

COMPLETED means the bounded tool invocation completed, not full coverage. ERROR,
INCOMPLETE, PARTIAL and NOT_RUN are preserved in events and report.json. Candidates
never become VERIFIED_IN_LAB merely because a scanner reported them. Scanner
outcomes and unconfirmed family signals feed the next planner observation.
Dashboard findings counts include CANDIDATE, SIGNAL and VERIFIED_IN_LAB only;
negative checks and request observations remain available in the detail list.
History counts describe recorded classifications; the evidence view checks
whether recorded verification claims have valid supporting references.

## Runnable checks

From the repository root:

```powershell
python -B -m unittest discover -s tests/runtime -p test_external_scanners.py -v
```

Opt-in compatibility test: this starts only an ephemeral localhost fixture, not
ShopLab or any public website. The test uses temporary evidence and the installed
pinned Docker images. Repeat with zap-passive or zap-active for the other modes.

```powershell
$env:SCANNER_DOCKER_TESTS='1'
$env:SCANNER_TEST_TOOL='nuclei'
python -B -m unittest discover -s tests/runtime -p test_external_scanners.py -v
```

Remaining handoff: independent safety/code review, approved real-lab assessment,
real provider end-to-end coverage and restore validation. Fixture checks do not
validate any target's security or the research objective.

## Change inventory and check receipts

New files in this integration:

- configs/tools/scanners.json
- runtime/lab/external_scanners.py
- tools/scanners/stdio_proxy.py
- tools/scanners/zap_worker.py
- tools/scanners/templates/lab-sql-error.yaml
- tools/scanners/templates/lab-sentinel-disclosure.yaml
- tools/scanners/README.md
- tests/runtime/test_external_scanners.py
- dashboards/app/frontend/src/__tests__/ExternalScanners.test.tsx

Existing files updated, preserving edits already present in the worktree:

- runtime/safety/discovery_gate.py
- runtime/lab/capability_registry.py
- runtime/orchestration/autonomous_runner.py
- runtime/planners/observed_planner.py
- dashboards/app/backend/models.py
- dashboards/app/backend/run_manager.py
- dashboards/app/backend/run_history.py
- dashboards/app/frontend/src/api/types.ts
- dashboards/app/frontend/src/components/controls/StartRunModal.tsx
- dashboards/app/frontend/src/components/activity/CurrentActivity.tsx
- dashboards/app/frontend/src/hooks/useEventStream.ts
- dashboards/app/frontend/src/pages/RunDetailPage.tsx

Deleted source files: none. Frontend build regenerates ignored dist output.
Other dirty files are pre-existing work and are not part of this inventory.

The seed/count correction touches runtime/lab/external_scanners.py,
dashboards/app/backend/models.py, dashboards/app/backend/run_manager.py,
dashboards/app/backend/run_history.py, tests/runtime/test_external_scanners.py,
tests/backend/test_run_budget_verification.py and this README. No source files
were deleted. Focused correction checks: scanner suite 16 tests (14 passed,
2 Docker checks skipped); opt-in ZAP active suite 16 tests (15 passed,
1 isolation check skipped); budget/verification suite 6 passed; history truthfulness
12 passed; pagination 2 passed. The old run's evidence is unchanged; its detail,
history and summary counters read as zero security findings with 111 detail items
retained. A new lab scan and independent review remain pending for this correction.

The select-option extension changes exactly runtime/discovery/discovery_engine.py,
runtime/lab/external_scanners.py, tests/runtime/test_external_scanners.py and this
README, preserving other existing edits. Deleted files: none. Its focused receipts:

- `python -B -m unittest discover -s tests/runtime -p test_external_scanners.py -v`:
  18 tests, 16 passed and 2 opt-in Docker checks skipped, exit 0.
- The same command with `SCANNER_DOCKER_TESTS=1` and `SCANNER_TEST_TOOL=zap-active`:
  18 tests, 17 passed and 1 isolation check skipped, exit 0.
- The same command with `SCANNER_DOCKER_TESTS=1` and `SCANNER_TEST_TOOL=nuclei`:
  18 tests, 17 passed and 1 isolation check skipped, exit 0.
- `python -B -m unittest discover -s tests/runtime -p test_discovery_safety.py -v`:
  9 passed, exit 0.
- `python -B -m unittest discover -s tests/runtime -p test_observed_planner.py -v`:
  16 passed, exit 0.

Both real-scanner fixture checks assert that the HTTP server actually receives
the category option extracted from fixture HTML together with the search field.
Pending for this extension: backend reload, a new approved lab run, and independent
review. Existing lab evidence is preserved and does not validate the new code.

Observed command receipts for this implementation session (exit 0 unless noted):

| Command | Result |
| --- | --- |
| `python -B -m unittest discover -s tests/runtime -p test_external_scanners.py -v` with `SCANNER_DOCKER_TESTS=1`, `SCANNER_ISOLATION_TESTS=1`, `SCANNER_TEST_TOOL=nuclei` | 15 tests passed, including real fixture scan, container isolation and cancellation cleanup |
| Same scanner command with `SCANNER_DOCKER_TESTS=1`, `SCANNER_TEST_TOOL=zap-active` | 15 tests, 1 isolation test skipped; remaining tests passed |
| Same opt-in fixture check with `SCANNER_TEST_TOOL=zap-passive` | Passed compatibility check |
| `python -B -m unittest discover -s tests/runtime -p test_observed_planner.py -v` | 16 passed |
| `python -B -m unittest discover -s tests/runtime -p test_autonomous_runner.py -v` | 14 passed |
| `python -B -m unittest discover -s tests/runtime -p test_autonomous_pentest.py -v` | 20 passed |
| `python -B -m unittest discover -s tests/runtime -p test_discovery_safety.py -v` | 9 passed |
| `python -B -m unittest discover -s tests/backend -p test_run_budget_verification.py -v` | 5 passed |
| `python -B -m unittest discover -s tests/backend -p test_runtime_events.py -v` | 7 passed |
| `python -B -m unittest discover -s tests/backend -p test_control_api.py -v` | 14 passed |
| `npm test -- ExternalScanners.test.tsx RunBudgetAndVerification.test.tsx` in dashboards/app/frontend | 5 passed |
| `npm run build` in dashboards/app/frontend | Passed TypeScript/Vite build |
| `python -B scripts/validation/validate_scaffold.py` | Exit 1: only pre-existing forbidden Python bytecode artifacts reported; these were preserved |

Pending handoff payload: the source files above, these check receipts, the
pinned image configuration and the bounded coverage/enforcement description.
Independent review, provider-to-dashboard end-to-end assessment, target restore
validation and a real Docker deadline-expiry test remain unverified. Timeout
failure handling has simulated coverage. No research status is promoted by
these checks and no real-target assessment is claimed.

## Authenticated workflow scope pending catalog approval

The operator has authorized disposable lab accounts, simulated carts/orders and
restoration on lab-ecommerce. That authorization is retained; it is not a request
to reset existing data. The current gate still rejects POST and the canonical
catalog has no authentication or business-workflow action. Proposed additions:

- ACTION-AUTH-001: create disposable lab accounts and establish separate sessions
  using observed registration/login forms; cookies, passwords and CSRF stay in
  the executor, never planner prompts or raw evidence.
- ACTION-FLOW-001: bounded cart updates and simulated checkout using observed
  forms, fixed allowed fields and quantities, and per-run write approval.
- ACTION-FLOW-002: compare ownership/role enforcement and permitted order-state
  transitions using only objects created by that run and approved lab roles.

These require explicit edit scope for actions/catalog/action-catalog.json and
configs/safety/action-allowlist.yaml, plus associated canonical safety/contract
documentation and focused validation tests if affected. Existing SQLi/XSS/path
traversal action IDs must not be repurposed. The proposed IDs are not enabled.

Before writes: capture and verify a consistent database/invoice snapshot under
exclusive lab ownership. After the run, restore that snapshot and verify it;
retain the snapshot on any failure. The existing restore_baseline deletes the
database and invoices before recreating seed data, so it is not suitable for
preserving the state that existed before this assessment. Restore must be owned
by the run coordinator and must not become an arbitrary planner command.

This category-coverage change touches runtime/discovery/discovery_engine.py,
runtime/lab/external_scanners.py, tools/scanners/zap_worker.py,
dashboards/app/frontend/src/components/activity/CurrentActivity.tsx,
dashboards/app/frontend/src/pages/RunDetailPage.tsx,
tests/runtime/test_external_scanners.py and this README. No files deleted.
Focused receipts: `python -B -m unittest discover -s tests/runtime -p
test_external_scanners.py -v` passed 19 tests with 2 Docker skips; with
SCANNER_DOCKER_TESTS=1 and SCANNER_TEST_TOOL=zap-active, 18 passed and the isolation
test was skipped (exit 0). The fixture observed both category options over HTTP.
`python -B -m unittest discover -s tests/runtime -p test_discovery_safety.py -v`
passed 9 tests. In dashboards/app/frontend, `npm test -- ExternalScanners.test.tsx`
passed 2 tests and `npm run build` passed. These checks do not validate lab restore.
Pending handoff: category coverage review and a new lab run; approval of the
catalog/safety edit scope before implementing authenticated writes and restore.
