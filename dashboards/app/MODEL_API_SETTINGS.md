# Model & API settings

Scope: user-requested configuration UI, 2026-10-13 (Asia/Saigon).

Open **Model & API** in the dashboard header. Choose the API format
(`OpenAI-compatible` or `Anthropic`), then enter a display name, any model ID,
the provider's base endpoint, and an optional API key. Use **Save settings**.
The list supports editing, replacing/removing a key, and deleting a profile.
An empty key during editing keeps the existing key. Local models may omit a key.

Endpoints must use HTTPS; HTTP is accepted only for localhost, 127.0.0.1 or ::1.
Endpoint URLs cannot contain user credentials, query parameters or fragments.
This screen does not fetch models, call providers, test connectivity, change
environment variables, or start agents. Protocol labels describe configuration
format only; no new provider adapter has been implemented.

Profiles, including keys, exist only in backend process memory. Restarting the
backend removes them. The UI never retrieves an existing key, and inputs are
cleared on save, failure and closing the dialog. No secrets are written to
repository files, localStorage, evidence, reports or telemetry by this feature.
Secrets still necessarily exist in browser memory while being entered and in
backend memory after submission; this is not a persistent credential vault.

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

`execution_integration=NOT_CONNECTED` is intentional and visible in the UI.
Saving settings is not evidence that the LLM planner used that configuration.
Existing runs, planner transport, target/action policy and approvals are unchanged.

## Changed files

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

## Checks and pending handoff

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

Pending handoff: configuration interface implemented and checked; review pending.
Profiles are session-only and not connected to autonomous execution. Provider
success, actual invoice reconciliation, missing historical evidence and independent
sign-off remain unverified. This feature does not lift `HANDOFF_BLOCKED` or
change TASK-032 from `DEFERRED`.
