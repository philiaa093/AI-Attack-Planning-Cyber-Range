# RT-07 Controlled V2 Protocol Amendment

Status: `IMPLEMENTED`; proposal only, not sealed or approved for RT-07B.
Authorization: user request dated 2026-10-20, based on source defects and development-only offline checks.

## Scope and explicit edit allowlist

- `runtime/planners/llm_planner.py`
- `runtime/planners/hybrid_planner.py`
- `runtime/planners/real_provider_adapter.py` (request hash provenance only)
- `evaluation/experiments/source_snapshot.py`
- `evaluation/experiments/benchmark_preflight.py`
- `evaluation/experiments/run_benchmark.py`
- `evaluation/experiments/protocol_amendment_v2.json` (new)
- `evaluation/results/result_v2.schema.json` (new)
- `tests/runtime/test_protocol_amendment_v2.py` (new)
- `docs/evaluation/protocol-amendment-v2.md` (this specification and offline handoff)

No other edits are authorized by this tranche. Preserve existing uncommitted test 14,
all historical results, V1 manifests, the registered matrix, seeds, scenarios,
candidate generation, scoring weights/formula, provider/model configuration and
controlled inference parameters. No commit/push, real inference, H01-H12 execution
or RT-07B execution. V2 is explicit opt-in; V1 remains reproducible.

## Required amendment

Keep the Pure LLM request byte-for-byte identical. Replace only the Hybrid footer
in V2 with:

> Rank candidates from 'eligible_candidates' above from best to worst and return your ranking JSON.

Require a JSON object, a nonempty ranked list of unique eligible string keys,
and required string `reason_code` and `brief_justification` fields. Partial rankings
remain supported; no new ranking-completeness restriction is introduced. Invalid
output has no semantic contribution and uses explicit SYMBOLIC_ONLY fallback.
V1 parsing/validation stays separately selectable. The single-candidate shortcut
must not fabricate a provider-derived semantic contribution in V2.

## Verification and handoff

Use development-only mock contexts and injected transports; store exact V1/V2
request hashes in the amendment and assert them in automated tests. Run focused
and broad offline regression with no real inference or held-out initialization.
Record exclusions, receipts, source provenance, preservation checks, reviewed diff,
proposed commit allowlist and the separate freeze/live-smoke requirements here.

## Version selection and exact changes

V1 remains the default. `HybridPlanner(prompt_version="HYBRID_ATTACK_PLANNER_V2")`
selects the V2 footer and validation. `BenchmarkRunner`, `BenchmarkPreflightChecker`
and `build_source_snapshot` accept explicit
`protocol_version="BENCHMARK_PROTOCOL_FREEZE_V2"`. Their V1 defaults are unchanged.
Both benchmark CLIs expose the same explicit `--protocol-version` choice.

The exact footer change is:

```diff
-Select exactly one candidate from 'eligible_candidates' above and return your decision JSON.
+Rank candidates from 'eligible_candidates' above from best to worst and return your ranking JSON.
```

The shared serializer adds a keyword-only footer argument whose default is the
original text. Hybrid V2 supplies the ranking footer; Pure LLM does not. System
prompt constants stay byte-identical. The adapter still sends a single `user`
message containing the system instruction text, context, and footer. No role,
context, candidate, generation-parameter or provider/model change is made.

V2 parses one JSON object, with optional JSON fences. It rejects surrounding
prose, repeated JSON fields, nonfinite JSON constants/numbers, malformed input,
empty/non-list rankings, non-string IDs, unknown IDs, duplicate IDs, and missing
or non-string auxiliary fields. Empty auxiliary strings satisfy the declared
string types. Extra finite JSON fields are ignored. Partial rankings remain
valid; unranked candidates retain zero semantic score under the original fusion.

V1's tolerant parser, empty-list acceptance, optional/coerced auxiliary fields,
and single-candidate score remain available through the V1 choice. V2 invalid
responses increment semantic-validation counters, not provider-error counters,
and contribute zero semantic score through documented SYMBOLIC_ONLY fallback.
A V2 single-candidate skip records no provider-derived ranking, no semantic
contribution and no failure fallback; scoring weights/formula stay unchanged.

The source snapshot also preserves Git's two status columns rather than stripping
the leading worktree-status space. This fixes dirty-source provenance detection;
it does not change planner or benchmark methodology.

Unsupported Hybrid prompt versions fail before provider use. Completed V2 result
re-saves compare prompt provenance as well as the existing result fields: identical
re-saves preserve bytes, and conflicting request hashes raise `FileExistsError`
before any write. Independent read-only review identified these two issues; both
were corrected, re-reviewed with no remaining actionable source findings, and
covered by offline regressions. This review does not approve a protocol freeze.

## Validator behavior comparison

| Response/condition | V1 behavior retained | V2 behavior |
|---|---|---|
| Nonempty eligible unique ranking with both string auxiliary fields | Valid semantic ranking | Valid; consumed by frozen fusion |
| Partial ranking / JSON fences | Supported | Supported |
| Empty ranked list | Marked semantic-valid despite no ranks | Invalid; zero semantics; SYMBOLIC_ONLY fallback |
| Missing auxiliary fields | Optional | Invalid |
| Non-string auxiliary fields | Tolerated/coerced | Invalid |
| Missing ranked list / Pure LLM selection object / truncated JSON | Invalid fallback | Invalid fallback |
| Unknown or duplicated candidate keys | Invalid fallback | Invalid fallback |
| Non-string/unhashable candidate keys | Can reach broad exception/provider-error branch | Explicit validation rejection; zero provider errors |
| Prose around JSON / repeated JSON object fields | Tolerant parsing | Invalid |
| Single eligible candidate | Synthetic valid semantic rank/score without a call | Explicit skip; no semantic rank/contribution or failure fallback |

All invalid V2 mock cases assert `semantic_component_valid=false`,
`semantic_contribution_used=false`, zero per-candidate semantic scores and
`semantic_fallback_mode=SYMBOLIC_ONLY`. They do not inflate provider-error counts.
No provider response was invented, and these checks do not establish the cause of
any historical generation failure. Missing raw responses remain
`INSUFFICIENT_RESPONSE_EVIDENCE`; completion-token count alone does not prove
truncation. The amendment corrects a demonstrated source-level prompt defect.

## Hashes and their meaning

All hashes are SHA-256. System hashes cover the UTF-8 constants only. Effective
prompt hashes cover the complete planner string. Effective request hashes cover
the exact adapter `json.dumps(payload).encode("utf-8")` body, without headers or a
trailing newline. These fixture hashes describe the committed test-13 S1 context,
not a historical wire capture or every possible context.

| Scope | V1 | V2 |
|---|---|---|
| Pure system | `1d35855b6167b0ce151f400c4fb2b292d3e57779689da4a0273fed8a51ac3533` | identical |
| Hybrid system | `d1280d0b3329c261344f8206fb2a9f61218b55262b0bf9d121c511d83a9e6ec1` | identical |
| Pure effective prompt | `72d12d91bda5b0989f6c231b229decb21d0f4742d34f173e0840b5de5ea94059` | identical |
| Hybrid effective prompt | `9a3428f2c8df14d2507b0faa6cfa46261b21b8e942a73e373181c62c9e8bd0a3` | `13773c11256632e5fd41c518b692f6e1d6287879da43e0b623e7f787547e0b90` |
| Pure effective request | `d492a8db9c075b76147854500d5b13eb34a75bce29d225727851acb15f68bffd` | identical |
| Hybrid effective request | `6f2e9917eab3a3c0d8696e3340f698b5c45fd102442b622828835f2785d95870` | `c69ca183bd82d24e90af45282ee23a299c1a247f57d9b47e11be47975c308a64` |

The complete fixture recipe and hashes are stored in
`evaluation/experiments/protocol_amendment_v2.json` and asserted against actual
injected-transport request bodies by `tests/runtime/test_protocol_amendment_v2.py`.

Unchanged scoring hashes:

- `HYBRID_SCORING_V1`: `68e55385e064cb2867d07207022b665a9660b87938318efa355488d67bc2c799`.
- `HYBRID_SCORING_V1_FROZEN`: `0e595f7294af58a8f635376e8beedb6688cee6784479ae2eb39c21f5c7213aa8`.

## Results, provenance and the registered matrix

V1 result JSON and `evaluation/results/result.schema.json` are unchanged. New V2
results use `result_v2.schema.json`, explicit V2 protocol identity and distinct
`DEV_V2_` development IDs. V2 Hybrid planner versions identify the V2 prompt
contract alongside the unchanged scoring version. The legacy `prompt_hash` field
retains its system-hash meaning; V2 adds `prompt_provenance` with prompt, serializer,
output-contract and system-hash identities, and per-request effective hashes.

The adapter retains hashes only in a separate request history, including failed
dispatch attempts. Each V2 result slices only its own episode's request history.
Scripted providers can record prompt hashes, but report a null wire-request hash;
they do not fabricate an adapter/provider request. Historical V1 results are never
read and relabeled as V2.

V1's 65-file executable-source closure stays available. V2 adds its amendment and
result schema to that closure (67 files). Dirty relevant source remains BLOCKED.

The original 420 assignments, seeds, scenario bytes and matrix experiment IDs are
unchanged. V2 references the matrix's byte hash rather than rewriting it. V2 matrix
scheduling, held-out authorization and noncanonical development paths are rejected
before an environment or provider runs. A proposal cannot bypass this restriction
by changing its JSON `freeze_status`. The V2 preflight always reports
`V2_PROTOCOL_NOT_SEALED`, independently of dirty-source blockers.

## Proposed freeze procedure (not performed)

1. Review the exact allowlisted diff, validator behavior comparison, effective
   request hashes, source manifest and offline receipts. Resolve review findings.
2. Review V2 compatibility with all 420 unchanged assignments and approve a distinct
   V2 execution-identity mapping that links each future result to its V1 base matrix
   assignment. No historical ID/result is relabeled and no assignment is retuned.
3. After explicit commit authorization, commit only the agreed amendment files,
   preserving the unrelated existing test-14 change separately. Bind reviewed V2
   hashes and source-tree digest to that commit through a new immutable V2 seal.
   Never replace the V1 seal or reuse historical evidence.
4. Separately authorize any narrowly scoped code change enabling the sealed V2
   execution path. This implementation deliberately has no V2 held-out enablement.
5. Obtain separate live-smoke authorization and, later, separate RT-07B authorization.
   Neither review, implementation, commit nor a seal alone authorizes inference or
   held-out execution.

## Requirements for the next development-only live Hybrid smoke

No live smoke is performed by this tranche. A later user authorization must pin
the reviewed V2 source and hashes, retain the selected Provider/Model, use only S1
seed 1001 step 0, and allow one Hybrid logical call/HTTP attempt with zero retries.
Keep frozen temperature, top-p, output limit and 30-second timeout. Token-budget
enforcement must be established for the selected provider; an unsupported estimate
must not be presented as an authoritative total-token ceiling.

Use a fresh immutable run/evidence location under `evaluation/results/smoke/`.
Capture UTC, run/source identities, full redacted request or reproducible context,
system/effective hashes, raw redacted response, `finish_reason` when available,
response hash, actual validation reason, semantic/fallback flags and both client
and upstream token accounting. Never infer truncation from token count alone.
Confirm ranking consumption by the unchanged frozen fusion. A valid fallback
decision is not semantic smoke success. Do not access H01-H12 or initiate RT-07B.

## Proposed commit allowlist

Only the ten paths in the explicit allowlist above belong to the V2 amendment.
`tests/runtime/test_real_provider_adapter.py` already contained uncommitted test 14
at entry (31 added lines); this tranche does not edit it. Its preserved SHA-256 is
`6e4ab46eb0858ff3db8437d5fad690bdec1c47bf2a0d6cdb4482d679fabd1076`.
Exclude that pre-existing diff and all development/smoke/sample artifacts from a
future V2-only commit unless separately instructed. No files are deleted.

## Source provenance and preservation receipt

Checked 2026-10-20 13:27 UTC. HEAD remains
`5ff6f914d035333dda4a4fd9c6f5bbee1d6eee80`. Nothing is staged or committed.
Current working-tree digests (not historical V1 source identities):

- V1 closure, 65 files: `8d70af0a0c4d7ad93365cec7df3127378547c85ee9ff9acd129eb37c489b2c3a`.
- V2 closure, 67 files: `1f1fe285e4a9b3ab395648237b565ce67b054ff3b8e1f9eebdab1f00ae63d386`.

Both snapshots report `BLOCKED` because relevant source edits are uncommitted.
The V2 preflight adds `V2_PROTOCOL_NOT_SEALED`. A development test pass does not
remove either blocker.

`git diff --exit-code HEAD --` passed for the scorer, candidate generator, V1 seal,
matrix, seeds, all held-out files, V1 result schema and the unchanged regression
blocker paths. All twelve scenario hashes match the held-out manifest; only byte
integrity and static registration checks were performed, with no held-out episode
initialization or action execution. No held-out outcomes informed the correction.

The existing uncommitted test 14 and five pre-existing result artifacts match
their entry hashes:

| Path | Preserved SHA-256 |
|---|---|
| `tests/runtime/test_real_provider_adapter.py` | `6e4ab46eb0858ff3db8437d5fad690bdec1c47bf2a0d6cdb4482d679fabd1076` |
| `evaluation/results/DEV_DRY_RUN_LLM_S1_1460c826.json` | `d9c23b4ade78359f4ac019c4c2835c7418b3bd8f3ffe6c8932a248faa99eebf6` |
| `evaluation/results/sample_episode_result.json` | `1453c84fe0fb4b30dbdacf9b5bd1305b6569279106a896e7985e11f63915c716` |
| `evaluation/results/smoke/smoke_hybrid_semantic_live_run.json` | `46c4bc87b97af47be1aa0782fca09575ae8a165930ef016bba5e30677598e472` |
| `evaluation/results/smoke/smoke_s1_real_provider_run.json` | `2111b7abfa0fcb969bcfd5ed2b7cab1fd95ca716873c7d3e860b3a195dee5330` |
| `evaluation/results/smoke/smoke_s1_two_call_run.json` | `6f7795206b9ef8413b5854bcbc73822ad0f0005abf8915f2ea38fe0d61c762cc` |

## Offline command receipts and remaining blockers

All pytest receipts used an in-process guarded harness through
`python -u -B -`, disabled pytest's cache provider, and set
`PYTHONDONTWRITEBYTECODE=1`. The harness forbids real adapter dispatch without an
injected transport, non-loopback connections, the selected inference endpoint,
Docker execution, held-out environment construction and writes to preserved
result/scenario/manifest/test-14 files. The recorded forbidden-event list was
empty. Synthetic in-process loopback HTTP fixture tests are included; no inference
HTTP request occurred.

For Windows Python 3.14 temporary-directory accessibility, the harness changes
only process-local `os.mkdir` calls requesting mode `0700` to `0755`. The adapter
token estimator is mocked to avoid tokenizer network I/O. Neither workaround
changes repository source, the provider configuration or wire-payload fixtures.

Exact completed broad pytest arguments, passed to `pytest.main`, were:

```text
-p no:cacheprovider -o "pythonpath=. tests/runtime"
tests scripts/demo/test_professor_demo.py -q
--ignore=tests/runtime/test_enterprise_docker_range.py
--ignore=tests/integration/test_runtime_lifecycle.py
--deselect=tests/backend/test_control_api.py::TestControlAPI::test_stop_ownership_pid_reuse_protection
--deselect=tests/runtime/test_external_scanners.py::ExternalScannerTests::test_real_scanners_on_local_fixture
--deselect=tests/runtime/test_external_scanners.py::ExternalScannerTests::test_real_container_isolation_and_cancellation
--deselect=tests/runtime/test_benchmark_protocol.py::TestBenchmarkProtocolFreeze::test_c_held_out_family_labels_absent_from_planner_decision_context
```

| Check | Observed result |
|---|---|
| New V1/V2 contract suite after review fixes | 9 passed, 36 subtests passed; exit 0; forbidden events `[]` |
| Earlier focused Pure LLM/Hybrid batches | 73 passed, 41 subtests passed |
| Earlier provider/runner/preflight batches, including existing test 14 | 65 passed |
| Final combined planner/adapter/protocol/runner/preflight/V2 regression | 187 passed, 1 held-out test deselected, 93 subtests passed; exit 0; 18.32 seconds; forbidden events `[]` |
| Completed broad guarded regression | 1373 passed, 44 failures/subfailures, 4 deselected, 1077 subtests passed; exit 1; 396.31 seconds; forbidden events `[]` |
| Narrow rerun of affected safety/scaffold suites with `--tb=line` | 45 passed, same 44 failures/subfailures, 21 subtests passed; exit 1; every failure is the same cache access denial |
| `python -B scripts/validation/validate_scaffold.py` | Blocked by `PermissionError: [WinError 5]` on `.pytest_cache`; exit 1 |
| HEAD validator loaded read-only with `git show HEAD:scripts/validation/validate_scaffold.py` | Reproduces the identical `.pytest_cache` permission blocker |
| `git diff --check` | Exit 0; only Git LF/CRLF conversion warnings |
| Frozen/source-blocker diff and six preservation hashes | Exit 0; all unchanged |

The final combined receipt used the same harness and base flags, with these exact
test paths and the H04 test deselection above:

```text
tests/runtime/test_llm_planner.py
tests/runtime/test_llm_planner_baseline.py
tests/runtime/test_hybrid_planner_baseline.py
tests/runtime/test_hybrid_router.py
tests/runtime/test_real_provider_adapter.py
tests/runtime/test_benchmark_runner.py
tests/runtime/test_benchmark_preflight.py
tests/runtime/test_benchmark_protocol.py
tests/runtime/test_protocol_amendment_v2.py
```

The 44 failures comprise six failed test methods and 38 failed subtests, all in
`tests/safety/test_root_types.py`, `tests/scaffold/test_validator.py` and
`tests/test_scaffold.py`. No source change or permission change was made to hide
this baseline/environment blocker. The complete regression is **not green**.

Initial full collection additionally failed because unchanged
`tests/integration/test_runtime_lifecycle.py:7` imports missing `EvidenceLog` from
unchanged `runtime/evidence/__init__.py`. That file was excluded from the completed
run. Docker/live-scanner tests were excluded for scope; the protocol test that
initializes H04 was excluded to enforce zero held-out execution.

The first two broad attempts ended without a pytest summary at the unchanged
ownership test. Static independent inspection confirms it passes the current
pytest PID to the real `stop_control_center.ps1`, which can identify any Python
process as owned when CIM command-line data is unavailable and call
`Stop-Process -Force`. Self-termination is consistent with the observed exit; the
exact ownership branch is unverified. It was excluded from the completed run and
must be isolated/mocked in a separately scoped repair before any unrestricted
full-suite retry. Other tests in this legacy API file probe live range readiness;
exclude the whole file from future strict offline runs unless those dependencies
are mocked.

Those legacy API runs created three new ignored deny-demo fixture directories
under `scripts/demo/demo-output/`, preserved without cleanup and excluded from the
proposed commit:

- `RUN-DASH-61ed0ff2db17421688e8a5f1a4ec6d7e`.
- `RUN-DASH-3ab112ed3d8345649dc43832f70d7080`.
- `RUN-DASH-d1a3f39fbfce4c218ce1bb57c8751d19`.

They are test side effects, not V2 inference or benchmark evidence. Historical V1
results and all five pre-existing result artifacts remain byte-identical.

Unverified/pending handoff: baseline full-suite repairs and clean rerun;
reviewed commit authorization; immutable V2 freeze and execution-ID mapping;
separate development-only live semantic smoke; later separate RT-07B authorization.
No live compatibility, held-out performance or sealed V2 runtime claim is made.
