# TASK-018: offline Nuclei normalization interface v1

Implementation: `IMPLEMENTED` for the bounded offline API below; independent
review pending. Runtime and durable evidence integration: `UNRESOLVED`.
Historical TASK-018 validation does not validate this extension.

## Data structure

The strict API is `ObservationNormalizer.normalize_nuclei(envelope, *,
allowed_target_ids, target_origin, template_families)`. The legacy `normalize`
and `normalize_observation` helpers remain compatible; they are not strict raw
report ingestion boundaries. No scanner execution, network access, state update,
or evidence write is performed by this new API. Canonical target configuration
is read through TASK-017's target validator.

Input is a closed, versioned object described by
[nuclei-report.schema.json](schemas/nuclei-report.schema.json). Required fields:

| Field | Meaning |
|---|---|
| `schema_version`, `source` | Exactly `1.0`, `NUCLEI` |
| `report_id` | Unique identity assigned by the trusted importer for each import attempt |
| `run_id`, `action_id`, `target_id` | Run context, exactly `ACTION-SCAN-002`, canonical allowlisted lab ID |
| `timestamp_utc` | Caller-supplied observation time, UTC ending in `Z`, optional 1–6 fractional digits |
| `status` | Import lifecycle: `SUCCESS`, `PARTIAL`, `FAILURE`, `DENIED`, `ERROR`, `TIMEOUT` |
| `evidence_refs` | Unique evidence IDs; empty means evidence is unresolved |
| `raw_output` OR `scanner_results` | Exactly one payload, as described below |

Run/report identifiers and evidence references are trusted importer metadata,
not values inferred from scanner content. Do not copy raw request values into
these identifiers. Missing fields, extra fields, or both payload fields reject
the entire envelope.

`raw_output` accepts decoded record lists, JSON array text, or JSONL text already
in memory. No string is treated as a file path. The HTTP subset requires exact
template IDs, `host`, `matched-at`, `type=http`, boolean `matcher-status`, and
`info.severity`; `info.tags` is optional. TASK-017's parser validates the complete
list, including nonmatching records, metadata, and per-record tool errors.
TASK-018 additionally requires all recognized locations (`host`, `matched-at`,
optional `url`) to match the trusted origin. Other bounded JSON metadata is
discarded and does not confer authority. Field provenance was checked against
the upstream `ResultEvent` definition in ProjectDiscovery Nuclei's
`pkg/output/output.go`; the supported subset still needs a pinned real-report
fixture. No compatibility claim is made for every Nuclei version/protocol.

`scanner_results` accepts the exact minimized list returned by TASK-017's
`NucleiAdapter.import_report`. Every item must obey the existing scanner-result
contract, with `source=NUCLEI`, the envelope's target ID, `endpoint_id=null`,
supported family, and `confidence=0.0`. Extra fields or any other confidence
reject the batch. TASK-017 has already discarded unmatched records, raw origin,
template identity, and endpoint locations; those cannot be reconstructed here.
Their source linkage remains unresolved unless the caller retained evidence.

The scope arguments come from a trusted caller. `allowed_target_ids` should be
the intersection of canonical targets and approved run targets; TASK-018 also
checks canonical membership through TASK-017. `target_origin` must identify the
same lab hostname, HTTP(S) scheme and port, with no credentials, query or path
other than `/`. URLs are compared without DNS or redirects. TASK-018 accepts
ASCII location strings only; this is stricter than TASK-017. `template_families`
is the same exact template-ID → family manifest used by TASK-017 (at most 100
entries, families `sqli`, `xss`, `path-traversal`). Empty mappings permit only
empty raw reports; minimized candidate input can use an empty mapping. The
manifest is classification data and grants no execution permission.

## Output and semantics

[normalization-result.schema.json](schemas/normalization-result.schema.json)
defines a closed object containing `schema_version`, `observation`, and
`provenance`. It references the existing observation/scanner-result schemas;
the ten canonical contracts are unchanged. Relative `$ref` identifiers resolve
against each schema's `$id`, rather than being filesystem paths. JSON Schema validates structure;
runtime code additionally enforces resource bounds, canonical target membership,
same-origin consistency, template membership and cross-field consistency.
For offline schema validation, register the referenced canonical schemas in a
local JSON Schema registry; never fetch `$ref` URLs over the network.

`observation` is the sole state/planner-facing format. Facts contain only target
ID, canonical family, deterministic fact ID and `CANDIDATE_FINDING` type.
`confidence=0.0` means **not assessed**, following TASK-017; it is neither a
negative assessment nor a calibrated probability. Severity, tags, HTTP status,
reflection and report presence never establish confidence or confirmed impact.
Only matched records create facts. An empty list does not assert absence of
vulnerabilities or scanner completion.

| Input import status | Observation outcome | Meaning |
|---|---|---|
| `SUCCESS`, `PARTIAL` | `PARTIAL` | Offline report information only; no verified scan execution |
| `FAILURE` | `FAILURE` | Failed import context; payload must be empty |
| `DENIED` | `DENIED` | Refused context; payload must be empty |
| `ERROR`, `TIMEOUT` | `ERROR` | Exact original status remains in provenance; payload must be empty |

Facts coalesce by `(CANDIDATE_FINDING, target_id, family)`. This intentionally
produces at most three family-level candidates per report, with no invented
endpoint identity. All input records retain indexed source hashes and fact
linkage in `provenance.record_sources`. Unmatched records have `fact_id=null`;
minimized candidate records have `template_id=null`. Coalescing does not raise
confidence. This is a summary of signals, not a count of distinct vulnerabilities.

The provenance sidecar includes report identity, input kind, SHA-256, original
status, normalizer version, redaction policy, confidence basis, evidence status,
counts and record linkage. Paths, queries, request/response bodies, cookie
values, extracted data, arbitrary names, raw timestamps and raw metadata never
leave the API. Evidence IDs are copied, never marked verified:
`REFERENCED_UNVERIFIED` with references, otherwise `UNRESOLVED`.

Input and record digests use UTF-8 JSON with sorted keys, compact separators,
`ensure_ascii=False` and finite numbers. They hash canonical JSON, not original
file bytes, and do not authenticate the report. `observation_id` hashes the
input digest plus normalizer version and trusted interpretation. Identical
input/context replays identically; a new report ID, changed record content or
changed interpretation changes observation identity. Equivalent list/JSONL
encodings can have different observation IDs but the same facts. Calls neither
mutate input nor persist cross-run deduplication state.

## Integration example

This in-memory example consumes Task 17's offline import result; fixture names
are synthetic metadata IDs and contain no executable templates.

```python
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from tools.adapters.nuclei.adapter import NucleiAdapter

manifest = {"fixture-sqli": "sqli"}
adapter = NucleiAdapter(allowed_templates=manifest)
records = [{
    "template-id": "fixture-sqli", "type": "http",
    "host": "http://lab-sqli-001", "matched-at": "http://lab-sqli-001/observed",
    "matcher-status": True, "info": {"severity": "high", "tags": ["sqli"]},
}]
candidates = adapter.import_report(records, target_id="lab-sqli-001")
result = ObservationNormalizer().normalize_nuclei({
    "schema_version": "1.0", "source": "NUCLEI",
    "report_id": "REPORT-FIXTURE-001", "run_id": "RUN-FIXTURE-001",
    "action_id": "ACTION-SCAN-002", "target_id": "lab-sqli-001",
    "timestamp_utc": "2026-10-11T08:00:00Z", "status": "SUCCESS",
    "scanner_results": candidates, "evidence_refs": [],
}, allowed_target_ids={"lab-sqli-001"},
   target_origin="http://lab-sqli-001", template_families=manifest)
observation = result["observation"]  # outcome PARTIAL; unconfirmed family signals
audit_metadata = result["provenance"]
```

Alternatively replace `scanner_results` with `raw_output=records` to retain raw
record/template/matcher linkage. This uses TASK-017's parser directly and does
not consume the adapter instance's import quota. TASK-018 imposes bounded local
processing limits; it provides no rate limit, execution approval or durable
cross-instance quota. The trusted caller still owns admission controls.

Limits: 1 MiB for the canonical envelope, at most 1,000 records, nesting depth
16 and 50,000 nodes for each checked JSON tree, 2,048 characters per location,
64 unique evidence references. The envelope consumes some size/depth budget,
so a maximum-sized raw report accepted by TASK-017 may exceed TASK-018's bound.
Duplicate JSON keys, cycles, non-finite values, invalid Unicode, malformed text,
unsupported records or any out-of-scope record raise `NormalizationError` with
a static code and return no observation. No sensitive input appears in errors.

## Evidence and pending handoff

Before any downstream state update, the approved caller must persist the input
source record and minimized normalization result using the existing append-only
recorder, with UTC/run/source/hash/redaction and expected/observed states kept
separate. Stop on recorder failure or conflicting provenance. This API does not
implement that durable write or certify supplied evidence references.

Pending handoff: review the two schemas and exact API, retain source provenance
before Task 17 discards it, verify a pinned real Nuclei report, integrate the
approved durable recorder and state replay/conflict handling, and resolve the
repository validation failures in their own scopes. No live commands, scanner
execution, runtime success, status promotion or approval are supplied here.
No file was deleted and no existing evidence record was changed.

## Offline check receipts

Receipt context: `RUN-TASK018-OFFLINE-20261011-01`, source HEAD
`d9ae6ca0d5bb03ce381d7249665237f272eeddc9` plus the working-tree hashes below;
receipt assembled after checks at `2026-10-11T15:24:46Z`. These are observed
diagnostic receipts, not authenticated scanner evidence or independent review.
Inputs were synthetic metadata; sensitive values were sentinel strings, not
real credentials. No raw report or existing evidence file was written.

Expected: focused/regression checks pass without network/process/write side
effects and the full scaffold checker passes. Observed: 141 tests pass with
exit 0, AST/JSON and whitespace checks pass; full scaffold remains invalid.
The first scoped rerun found **641 repository errors, zero TASK-018 errors**.
A subsequent rerun after assembling this receipt found **652 repository errors,
zero TASK-018 errors**; the shared working tree changed outside this task while
other work continued. Both observed results are preserved here.
Outside-scope failures include dashboard dependency documents/configuration,
pre-existing forbidden cache/executable artifacts and TASK-015 report fields.
This blocks formal repository handoff; no review approval is asserted.

| Exact command | Exit | Observed |
|---|---|---|
| `python -B -m unittest discover -s tests/integration -p test_nuclei_normalizer.py -v` | 0 | 24 tests PASS; includes schema validity, source hashes, TASK-017 handoff, replay, refusal and side-effect guards |
| `python -B -m unittest discover -s tests/unit -p test_observation_normalizer.py -v` | 0 | 33 legacy normalizer/feature tests PASS |
| `python -B -m unittest discover -s tests/unit -p test_nuclei_adapter_offline.py -v` | 0 | 28 TASK-017 tests PASS |
| `python -B -m unittest discover -s tests/unit -p test_tool_adapters.py -v` | 0 | 27 adapter tests PASS |
| `python -B -m unittest discover -s tests/contracts -p test_contracts.py -v` | 0 | 12 canonical contract tests PASS |
| `python -B -m unittest discover -s tests/safety -p test_safety.py -v` | 0 | 17 safety tests PASS |
| `git diff --check -- agent/perception/normalizers tests/integration/test_nuclei_normalizer.py` | 0 | No whitespace errors; Git reports LF/CRLF advisory |
| `python -B scripts/validation/validate_scaffold.py` | 1 | SCAFFOLD INVALID; initial run also found three TASK-018 reference/link issues, subsequently repaired |

Scoped diagnostic reruns (exit 1; first 641, latest 652 total errors;
0 TASK-018 errors in both):

```text
python -B -c "from scripts.validation.validate_scaffold import validate; errors = validate(); scoped = [e for e in errors if e.startswith('agent/perception/normalizers/') or e.startswith('tests/integration/test_nuclei_normalizer.py')]; print('TOTAL_ERRORS=' + str(len(errors))); print('TASK018_ERRORS=' + str(len(scoped))); print('\n'.join(scoped)); print('\n'.join(errors[:4])); raise SystemExit(1 if errors else 0)"
```

AST/JSON check (exit 0, `AST_OK=3 JSON_OK=2`):

```text
python -B -c "import ast, json; from pathlib import Path; paths = ['agent/perception/normalizers/nuclei_normalizer.py', 'agent/perception/normalizers/observation_normalizer.py', 'tests/integration/test_nuclei_normalizer.py']; [ast.parse(Path(p).read_text(encoding='utf-8'), filename=p) for p in paths]; schemas = list(Path('agent/perception/normalizers/schemas').glob('*.schema.json')); [json.loads(p.read_text(encoding='utf-8')) for p in schemas]; print('AST_OK=3 JSON_OK=' + str(len(schemas)))"
```

Production logic uses the standard library and TASK-017's existing parser.
Schema tests use the already available `jsonschema` and `referencing` packages;
no dependency was installed in this task. Dependency installation/pinning on
another machine remains the caller's environment responsibility.

Source snapshot hashes (SHA-256; interface document excluded to avoid a
self-referential digest):

| File | SHA-256 |
|---|---|
| `observation_normalizer.py` | `b521d57b48f48d5d26117d481ed2d1c496de53d2e50defefc5dd7a1b31fcb93f` |
| `nuclei_normalizer.py` | `431163f0f879f2da19c76a3b9ef59c4323cbe4a0f94f0a8554990826f07bc86a` |
| `schemas/nuclei-report.schema.json` | `ba9c6e6c826d2f00d5201f6c077e49e6c8dff0de98e9a214d9b6939c70f3a2c6` |
| `schemas/normalization-result.schema.json` | `fa50adb550f967769141962a789e7d1e5d57c6368104a45a5b4895d1bfb36250` |
| `tests/integration/test_nuclei_normalizer.py` | `4b426dfe693e9540148b94cdf590f16986a6154d07ad955033a4b8dfba18cf5a` |
| TASK-017 dependency `tools/parsers/nuclei_parser.py` | `2235155b6594afcc8ecb5efe96c6ae996b639feac29fb51dbceef4002bcbd279` |
| TASK-017 dependency `tools/adapters/nuclei/adapter.py` | `3b5389593ba5774c9a9a54a831aa4b52a220615f0e600869cb039bd27bac088d` |

Changed-file inventory for this task: modified `observation_normalizer.py`;
added `nuclei_normalizer.py`, both schema files, this interface document and
`tests/integration/test_nuclei_normalizer.py`. Task 17 files were read/tested
without editing. Canonical schemas, configuration, task statuses, history and
existing evidence were preserved. Deleted files: none.
