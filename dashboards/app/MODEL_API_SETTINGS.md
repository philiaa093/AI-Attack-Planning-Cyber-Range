# Model & API settings

Scope: configuration UI, optional local .env persistence and saved-profile planner integration.

## Persistence handoff

Changed files for optional persistence:
- `dashboards/app/backend/model_profiles.py`
- `dashboards/app/backend/control_api.py`
- `dashboards/app/frontend/src/api/modelProfiles.ts`
- `dashboards/app/frontend/src/components/controls/ModelSettings.tsx`
- `dashboards/app/frontend/src/__tests__/ModelSettings.test.tsx`
- `tests/backend/test_model_profiles.py`
- `dashboards/app/MODEL_API_SETTINGS.md`

Deleted files: none. Frontend build also regenerated ignored `dist/` assets.
The earlier timeout change in `runtime/planners/observed_planner.py` remains 60 seconds.

Checks:
- `python -B -m unittest discover -s tests/backend -p 'test_*profile*.py' -v`: exit 0, 20 tests PASS.
- `npm.cmd test -- --maxWorkers=1 --minWorkers=1 src/__tests__/ModelSettings.test.tsx`
  in `dashboards/app/frontend`: exit 0, 4 tests PASS.
- `npm.cmd run build` in `dashboards/app/frontend`: exit 0.
- Scoped `git diff --check` for the seven files above: exit 0.
- `python -B scripts/validation/validate_scaffold.py`: SCAFFOLD INVALID,
  34 forbidden `__pycache__/*.pyc` artifacts; not removed by this change.
- Git ignore check confirms `.env` is ignored and is not tracked.

Pending: backend restart and operator re-entry of the API key with persistence
selected, then live provider verification. The user authorized restart, but
automatic command policy rejected the restart before execution (`blocked by policy`).
No actual user key has been saved to `.env` by this change. Persistence/reload
checks used temporary files and fixture keys. Independent review and live
provider execution remain unverified; no project/task validation status changed.

Open **Model & API** in the dashboard header. Choose the API format
(`OpenAI-compatible` or `Anthropic`), then enter a display name, any model ID,
the provider's base endpoint, and an optional API key. Use **Save settings**.
The most recently saved profile is selected for the next `llm` run. Edit and
save an existing profile to select it again. The list marks the selected profile.
The list supports editing, replacing/removing a key, and deleting a profile.
An empty key during editing keeps the existing key. Local models may omit a key.

Endpoints must use HTTPS; HTTP is accepted only for localhost, 127.0.0.1 or ::1.
Endpoint URLs cannot contain user credentials, query parameters or fragments.
Saving does not fetch models, call providers, test connectivity, change
environment variables, or start agents. A subsequent LLM run captures a private
immutable snapshot and uses the saved endpoint, model and key. OpenAI-compatible
chat completions and Anthropic messages are supported. Enter the API base URL
(for example, ending in `/v1`), not the final `/chat/completions` or `/messages` URL.
Provider requests have a timeout, bounded response and no redirect following.
Provider failure keeps the run's existing fallback/stop policy.

By default profiles, including keys, exist only in backend process memory.
Select **Save API and model to .env (keep after restart)** to persist one profile
in the repository-root `.env`. Saving another persistent profile replaces that
saved profile. Unchecking the option on its edit form or deleting it removes
the saved entry. Other environment variables and comments are preserved.
The backend restores and selects the saved profile at startup, including its
API protocol, endpoint, model and key. Session-only profiles are lost on restart.
The UI never retrieves an existing key, and inputs are
cleared on save, failure and closing the dialog. Persistent keys are plain text
in `.env`, which is Git-ignored; this is not an encrypted credential vault.
No keys are written to localStorage, evidence, reports or telemetry.
The managed entry is `DASHBOARD_MODEL_PROFILE`, a quoted JSON value; it does not
replace legacy environment variables or mutate the running process environment.
Writes use a temporary file and atomic replacement. Invalid saved data fails
startup with a generic error; a failed write leaves in-memory settings unchanged.

The new API accepts local peers/hosts and trusted local browser origins. Writes
require an Origin header. The limits are 20 profiles and a 16 KiB request body.
Responses expose only `has_api_key`, with `connection_status=NOT_TESTED`.
Malformed inputs receive a generic error rather than echoed secret-bearing
validation details. Responses use `Cache-Control: no-store`.

Endpoints:

- `GET /api/model-profiles`: redacted list.
- `POST /api/model-profiles`: create.
- `POST /api/model-profiles/{id}`: update; blank key preserves the existing key.
- `POST /api/model-profiles/{id}/remove`: remove.

`execution_integration=CONNECTED` describes wiring, not verified connectivity.
Saving settings is not evidence that the LLM planner used that configuration.
Existing runs retain their snapshot; RULE and outage-demo runs ignore profiles.
Removing the selected profile clears selection; other profiles are not selected
silently. With no selection, the existing environment configuration is used.
Target/action policy and approvals are unchanged. Provider connectivity and
live end-to-end execution require separate verification.

## Previous integration handoff (before .env persistence)

Implementation checked offline; independent review and live provider verification
are pending. No live provider, lab or pentest run was started. The existing
backend process must reload the code; restarting loses session profiles, so
enter and save the profile again, then select `llm` for the next run.
No persistent key storage was added.

Changed files:

- `dashboards/app/MODEL_API_SETTINGS.md`
- `dashboards/app/backend/control_api.py`
- `dashboards/app/backend/model_profiles.py`
- `dashboards/app/backend/run_manager.py`
- `dashboards/app/frontend/src/api/modelProfiles.ts`
- `dashboards/app/frontend/src/components/controls/ModelSettings.tsx`
- `dashboards/app/frontend/src/__tests__/ModelSettings.test.tsx`
- `runtime/orchestration/autonomous_runner.py`
- `runtime/planners/observed_planner.py`
- `tests/backend/test_model_profiles.py`
- `tests/backend/test_profile_planner.py` (new)

Deleted files: none. Frontend build generated ignored `dist/` output.

Command receipts (repository root unless specified):

| Command | Result |
| --- | --- |
| `python -B -m unittest discover -s tests/backend -p 'test_*profile*.py' -v` | Exit 0; 15 PASS |
| `python -B -m unittest discover -s tests/runtime -p 'test_observed_planner.py' -v` | Exit 0; 14 PASS |
| `python -B -m unittest discover -s tests/runtime -p 'test_autonomous_runner.py' -v` | Exit 0; 12 PASS |
| `npm run build` in `dashboards/app/frontend` | Exit 0; TypeScript and Vite build PASS |
| `npm test -- --maxWorkers=1 --minWorkers=1` in `dashboards/app/frontend` | Exit 0; 37 PASS |
| `python -B scripts/validation/validate_scaffold.py` | Exit 0; SCAFFOLD VALID, 9022 files |
| `git diff --check` | Exit 0 |

Pending handoff: reload backend, re-save session profile, verify provider
connectivity and run provenance in an approved lab run; independent review.
No blockers observed in the focused offline checks. These checks do not establish
live runtime success or upgrade project/task validation status.

## Original configuration UI files

1. `dashboards/app/backend/model_profiles.py` (added)
2. `dashboards/app/backend/control_api.py` (modified: router registration)
3. `dashboards/app/frontend/src/api/modelProfiles.ts` (added)
4. `dashboards/app/frontend/src/api/client.ts` (modified: configuration requests)
5. `dashboards/app/frontend/src/components/controls/ModelSettings.tsx` (added)
6. `dashboards/app/frontend/src/components/layout/Header.tsx` (modified: entry button)
7. `tests/backend/test_model_profiles.py` (added)
8. `dashboards/app/frontend/src/__tests__/ModelSettings.test.tsx` (added)
9. `dashboards/app/MODEL_API_SETTINGS.md` (added)

Deleted files: none. Build output under the existing ignored frontend `dist/`
directory is generated, not a source/evidence change. Existing unrelated working
tree modifications are preserved; no commit, task status or history update.

## Original configuration UI checks (before planner integration)

Base HEAD: `d9ae6ca0d5bb03ce381d7249665237f272eeddc9`.

- `python -B -m unittest discover -s tests/backend -p test_model_profiles.py -v`:
  exit 0, 8 tests PASS; no provider, target, Docker or historical-evidence I/O.
- Frontend `npm.cmd test -- --maxWorkers=1 --minWorkers=1`: exit 0,
  13 tests PASS across all three frontend suites, including 3 new feature tests.
- Frontend `npm.cmd run typecheck`: exit 0.
- Frontend `npm.cmd run build`: exit 0; Vite transformed 1592 modules and
  produced the bundle under ignored `dist/`.
- `python -B scripts/validation/validate_scaffold.py`: exit 0, `SCAFFOLD VALID`;
  7759 files, 10 schemas, 13 actions, 35 tasks and 13 ADRs checked.
- AST parse of the three changed Python files: PASS.
- Full-app in-process TestClient `GET /api/model-profiles`: HTTP 200, registry present.
- Scoped `git diff --check`: exit 0; added files receive separate whitespace checks.
- Explicit whitespace/EOF checks for all nine changed files: PASS.
- Existing frontend Phase6 tests emit missing EventSource warnings while passing;
  no SSE behavior was changed. TestClient emits a dependency deprecation warning.
- Browser inspection was attempted; UI automation timed out, so actual visual
  inspection and provider connectivity remain unverified.

Original handoff: configuration interface implemented and checked; review pending.
Profiles were session-only and not connected to autonomous execution. Provider
success, actual invoice reconciliation, missing historical evidence and independent
sign-off remain unverified. This feature does not lift `HANDOFF_BLOCKED` or
change TASK-032 from `DEFERRED`.
