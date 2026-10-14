# Tools/Adapters/Nuclei

> Status: SPEC_ONLY (scanner runtime scaffold)
> Offline implementation: IMPLEMENTED

No runtime scanner execution is authorized by this artifact.

Offline parser/wrapper implementation; independent review pending. Canonical
TASK-017 is IMPLEMENTED for this offline scope at the user's request, not VALIDATED.
The SPEC_ONLY marker above applies to the scanner runtime scaffold, not the
implemented offline parser/wrapper. External scanner execution and durable evidence
integration remain UNRESOLVED.

`NucleiAdapter(allowed_templates=...)` copies an exact template-ID-to-family
mapping for report classification. Default mapping is empty. Only `sqli`, `xss`,
and `path-traversal` families are accepted. This is an offline input allowlist,
not proof of template provenance, hash verification, or runtime approval. No
template files or executable payloads are supplied.

`import_report(report, target_id=...)` accepts a decoded list or JSONL string
already in memory. It never reads a report path. Each record must have
`template-id`, `type="http"`, URL-valued `host`, `matched-at`, boolean
`matcher-status`, and `info.severity`. Optional `info.tags` must be a string list.
Legacy top-level severity/tags, mixed origins, malformed input, unknown IDs,
duplicate JSONL keys, non-finite numbers, and out-of-target URLs are rejected.
Nonempty or malformed per-record tool errors reject the entire import.
Every record is checked, including failed matchers; imports are all-or-nothing.
Only the declared HTTP origins are checked; DNS/IP identity, registry endpoint
mapping, scanner version, completeness, and authenticity are not established.

Limits: 1 MiB serialized JSON and input JSONL, depth 16, 1,000 records, URI length
2,048, and 100 manifest entries. Imports use the configured rate limiter and a
per-instance attempt quota capped at 100 (`max_actions`). Malformed attempts
consume quota after admission. These are offline resource limits, not measured
network-request budgets or durable cross-instance run budgets.

`execute("ACTION-SCAN-002", target_id, run_id)` accepts only absent/empty
parameters, validates IDs, and returns `(DENIED observation, [])` with empty
facts/evidence references. Supplying approval/commands/templates cannot enable
execution. No process, scanner, network dispatch, or evidence write occurs.

Handoff to TASK-018: import returns `scanner-result.schema.json` candidates only,
not an action observation. `source="NUCLEI"`, `endpoint_id=null`, and
`confidence=0.0` (confidence unassessed; neither a negative result nor calibrated
probability). Severity/tags never determine confidence. All URL paths, queries,
request/response bodies, and extracted values are discarded. Duplicate matches
retain multiplicity without confidence inflation; provenance-aware de-duplication
requires a separate evidence integration. The caller must retain immutable
source/version/hash/UTC/run/redaction and expected/observed evidence before
updating state. Neither import success nor an empty report proves scan completion,
absence of vulnerabilities, or CONFIRMED_FINDING.

Compatibility sources: ProjectDiscovery Nuclei upstream `pkg/output/output.go`
(`ResultEvent`) and official Nuclei documentation, Running Nuclei / Output.
This subset is tested with synthetic metadata fixtures, not a pinned real scanner
report. Fixture IDs grant no executable capability.

Focused checks:

```text
python -B -m unittest discover -s tests/unit -p test_nuclei_adapter_offline.py -v
python -B -m unittest discover -s tests/unit -p test_tool_adapters.py -v
python -B -m unittest discover -s tests/safety -p test_safety.py -v
```

Current self-check receipts (2026-10-11, not independent validation): 28 offline
Nuclei tests, 27 shared adapter tests, and 17 safety tests PASS, each exit 0.
Python AST parsing of the adapter, parser, new tests, and shared adapter tests
PASS; scoped `git diff --check` PASS. Full scaffold validation remains blocked:
the latest invocation of `validate()` returned 643 repository errors and zero
errors matching the five TASK-017 paths. Outside-scope issues include invalid
JSON escapes in two normalizer schemas, dashboard dependencies/configuration,
forbidden artifacts, and report fields/statuses. Independent approval, pinned
real-report compatibility, and immutable evidence receipts remain UNRESOLVED.

Pending handoff: consume minimized candidate lists via the existing TASK-018
contract without assigning endpoint IDs or confirmed status; retain evidence
separately before applying observations. Do not interpret `confidence=0.0` or
an empty list as a negative assessment. Resolve repository validation blockers
under their own scope before formal review. This change does not edit the
normalizer, StateManager, contracts, safety configuration, or canonical task
statuses other than the explicitly requested TASK-017 IMPLEMENTED update.
Existing ZAP changes in the shared test file are preserved.
