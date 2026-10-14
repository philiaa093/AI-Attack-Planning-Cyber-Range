# Historical restoration, billing comparison and signed review submission

> Đường dẫn source đã chuyển ngày 2026-10-14; xem [bản đồ thư mục](../repository-layout.md). Receipts, command invocations và hash/path lịch sử bên dưới thuộc source trước khi chuyển. Các liên kết tới source và ví dụ import Python đã theo vị trí mới.

Implementation subset: `IMPLEMENTED`; original recovery, real invoice proof and
independent approval remain `UNRESOLVED`. No task promotion or history edit.

## Observed inputs and limits

`cyber-range/snapshots/golden-snapshot.json` is a target-reset configuration with
three target definitions. It contains no historical run bytes or hash ledger.
The user confirmed there is no original backup/ledger available. The original
three RUN-EVAL directories remain missing; a different run under
`reports/evaluation-runs` cannot substitute for them. No original evidence was
restored in this session, and no replacement experiment was run.

The working tree already contains many changes belonging to the user. A passing
repository validator is not a clean Git worktree. These scripts record the
observed state rather than accepting a claim that prerequisites were completed.

## 1. Restore original bytes

[restore_historical_runs.py](../../runtime/audit/restore_historical_runs.py) accepts a JSON or ZIP
backup **and an independently pinned original ledger**. Both require SHA-256
values obtained from a trusted record outside the supplied, unverified archive.
Matching self-computed hashes from a newly invented ledger do not establish an
original historical record. The script never creates an original ledger.

Original ledger schema, repeated for exactly the three required run IDs:

```json
{
  "schema_version": 1,
  "source_kind": "ORIGINAL_LEDGER",
  "runs": [
    {"run_id": "RUN-EVAL-28f2ce10b1e24f0c867f3980e0212c5a",
     "files": [{"path": "configuration.json", "size": 123,
                "sha256": "<original-64-character-sha256>"}]}
  ]
}
```

The shortened example is a schema illustration, not valid recovery data. The
other IDs are `RUN-EVAL-2c8fc0463d9144419e2de854d5e76d84` and
`RUN-EVAL-db2d8184ca0449abb358a3f7646f91cb`. Every original file, including any
original manifest, must be listed with its original size/hash. The first run was
partial; do not fabricate a completion manifest for it.

JSON backup schema: `schema_version: 1`, `runs: [{run_id, files: [{path,
data_base64}]}]`. Base64 encodes the original byte stream without newline/JSON
reformatting. ZIP member names are `RUN-EVAL-.../<original-relative-path>`.
Fixtures must identify the ledger as `SIMULATED_FIXTURE`; they cannot be treated
as recovered history in a review submission.

```powershell
python -B -m runtime.restore_historical_runs --archive backup.zip --archive-sha256 ARCHIVE_SHA256 --ledger original-ledger.json --ledger-sha256 LEDGER_SHA256
```

Replace uppercase arguments with externally trusted hashes. CLI destination is
exactly `evidence/runtime`; receipts go to new UUID directories under
`runtime/audit-artifacts`. The original bytes and original file manifests stay
unchanged even though the custody location is different.

The entire archive is pinned, decoded and checked against the original ledger
before any destination write. Traversal, absolute paths, ADS/device names,
case collisions, duplicate entries, links/junctions, special/encrypted ZIP
entries and resource overruns are rejected. Limits: 16 MiB/file, 64 MiB total.
Existing matching bytes are reused; a conflicting existing file blocks all
writes. Publication uses exclusive creation and fsync. Partial restores remain
available for inspection and may resume only if existing bytes still match.
Operation requires a stable trusted single writer; hostile concurrent filesystem
replacement and power-loss directory durability are not claimed.

Cleanup can explicitly inspect the new location:

```powershell
python -B -m runtime.repository_cleanup --historical-root evidence/runtime
```

Its default remains `runtime/evaluation-runs`, preserving existing behavior.
Restoring original v1 artifacts may bring back their status/citation gate errors.
That calls for a separately reviewed validator/receipt-role compatibility repair;
do not rewrite historical bytes to hide it.

## 2. Reconcile billing numbers

[invoice_reconciliation.py](../../runtime/audit/invoice_reconciliation.py) reads a sealed usage ledger
and a SHA-256-pinned CSV. The **explicit request-level schema** is a local adapter
format, not a universal OpenAI/Anthropic monthly invoice format:

```csv
invoice_id,run_id,provider,response_id,currency,token_subtotal_usd,tax_usd,total_usd
INV-MOCK-1,RUN-BILLING-1,openai,resp-example-1,USD,0.000410,0.000041,0.000451
```

The row is illustrative simulated data, not an actual invoice or a complete
matched ledger. An aggregate-only monthly export needs a separately reviewed
adapter/allocation rule; it must not be guessed into per-response charges.

```powershell
python -B -m runtime.invoice_reconciliation --ledger ledger.json --ledger-sha256 LEDGER_SHA256 --billing-csv billing.csv --billing-sha256 BILLING_SHA256 --source simulated
```

`--source provided` labels an external file as **unverified**, not authenticated.
The script recomputes prices from verified ledger entries, deduplicates billed
provider/response IDs, checks exact run coverage and includes failed-call charges.
Unknown usage/rates or missing/extra billed responses make comparison INCOMPLETE.
Other-run monthly rows are counted as excluded and never charged to this run.

`Decimal` precision 60 prevents floating-point currency errors. Declare rounding
unit `0.000001` (default, request export) or `0.01` (cent-rounded rows); use
ROUND_HALF_UP. Tolerance defaults to zero and cannot exceed half that unit.
Original deltas are retained. Explicit CSV tax amounts are checked with gross
arithmetic; no jurisdiction/tax rate is inferred. Refunds, credits, currency
conversion, pooled discounts or tool fees need explicit additional adapters.

Receipts report MATCHED/MISMATCH/INCOMPLETE, coverage, calculated net, exported
net/tax/gross and per-call deltas. A discrepancy produces a retained receipt and
CLI exit 1. A matched simulated CSV remains `SIMULATED_BILLING_EXPORT`:
`actual_billed_usd=null`, `actual_invoice_reconciled=false`, billing authenticity
UNRESOLVED. Simulated numerical agreement cannot prove actual paid money.

## 3. Capture checks and seal a submission

[generate_audit_package.py](../../runtime/audit/generate_audit_package.py) supports:

```powershell
python -B -m runtime.generate_audit_package capture-checks
python -B -m runtime.generate_audit_package build --checks checks-receipt.json --checks-sha256 CHECKS_SHA256 --restore restore-receipt.json --restore-sha256 RESTORE_SHA256 --reconciliation billing-receipt.json --reconciliation-sha256 BILLING_SHA256 --private-key submitter-key.pem
python -B -m runtime.generate_audit_package verify --package submission.zip --public-key-sha256 TRUSTED_PUBLIC_KEY_SHA256
```

The filenames are operator-supplied inputs; these commands do not fabricate
missing evidence, a key, an invoice or an auditor verdict. `capture-checks` runs
only fixed offline suites: 17 accounting/operations + 31 Planner + 13 pipeline
tests, plus the repository gate and read-only Git status/HEAD. It records actual
return codes, parsed counts, unique passed IDs, output digests and declared source
hashes. Source changes during collection abort publication. Failed checks remain
explicitly failed; existing user changes are not committed/reset to force clean.

The source manifest covers a declared set, not a complete transitive dependency
closure or remote attestation. A receipt is a producer's report; a hash/signature
does not independently prove the producer actually ran its claimed commands.
The independent reviewer still evaluates those claims and source binding.

`build` pins receipts, rejects stale source hashes/inconsistent passing flags,
rechecks restored bytes and copies declared sources/receipts/history into a ZIP
with a signed canonical manifest. Missing restore/invoice receipts, simulated
inputs, failed checks, dirty Git state and invoice-authenticity gaps remain
blockers. A sealed package may be `PREPARED_WITH_BLOCKERS`; it is not approval.

Ed25519 signs a domain-separated manifest. Each member has SHA-256 and size;
verification rejects changes, unlisted/duplicate members, links, compression and
untrusted keys. The verifier must get the public-key fingerprint through a
trusted channel; the bundled public key alone is not a trust anchor. The signer
is always **SUBMITTER**, never an independent auditor. Even a valid signature
cannot turn the package into `approval_granted=true`.

The private Ed25519 key is supplied by the operator and is never generated or
included in the package. Encrypted PEM passwords may be supplied using
`--password-env NAME`; secrets are neither logged nor packaged. This is a signed
plaintext ZIP, not encryption or an ACL/immutability guarantee. Independent
review remains PENDING, `HANDOFF_BLOCKED` is unchanged, and task files are never
modified. There is no automatic sign-off or workflow-unblock endpoint.

Signing API was checked against the official Cryptography Ed25519 documentation;
installed library observed: 50.0.2. The direct reference is provided in chat.

## Exact scope and handoff

Added files:

```text
E:/PBL6_FINAL/runtime/audit_support.py
E:/PBL6_FINAL/runtime/restore_historical_runs.py
E:/PBL6_FINAL/runtime/invoice_reconciliation.py
E:/PBL6_FINAL/runtime/generate_audit_package.py
E:/PBL6_FINAL/runtime/audit_pipeline.md
E:/PBL6_FINAL/tests/runtime/test_audit_pipeline.py
```

Modified: `E:/PBL6_FINAL/runtime/repository_cleanup.py` only for explicit historical
root selection. Deleted files: none. No backup, original ledger, actual invoice,
signing key or reviewer approval was invented. No writes to historical evidence
occurred; all restore/reconcile/signing acceptance tests use disposable fixtures.

Two actual check receipts were added (not historical run replacements):

```text
E:/PBL6_FINAL/runtime/audit-artifacts/CHECKS-21b9a31f426844319e56bed584b88902/receipt.json
E:/PBL6_FINAL/runtime/audit-artifacts/CHECKS-8f7cc9bb237b4ce4b5fd1d7abafc1a5f/receipt.json
```

The first was captured before subsequent verifier hardening and is retained as
an earlier source snapshot. It is stale for the final source. The second is the
current receipt: SHA-256
`fa848cef1849152eeacbfeb9f0c626b38a1a84e89e473c15b417680538da0c8f`.
Its counts are 17/31/13, all_61_passed=true, repository_gate.passed=true,
worktree_clean=false; all declared source hashes were checked against the current
workspace and matched. Capturing facts does not approve a handoff.

## Command receipts

Observed date: 2026-10-12; handoff source checkpoint 12:16:46 UTC. All Python
commands use `-B`; subprocesses use fixed argument lists without shell execution.

| Actual command/check | Exit | Observed result |
|---|---:|---|
| `python -B -m unittest discover -s tests/runtime -p test_audit_pipeline.py -v` | 0 | Final 17 tests PASS; restore/no-overwrite, CSV coverage/rounding, signature/member tamper, no fabricated approval |
| `python -B -m unittest discover -s tests/runtime -p test_evaluation_operations.py -v` | 0 | 17 regression tests PASS for the modified cleanup root selection and accounting integration |
| `python -B -m runtime.generate_audit_package capture-checks` — first snapshot | 0 | Observed 61 passes and gate PASS; receipt retained, source later changed |
| Same command — final snapshot | 0 | Fresh 17 + 31 + 13 tests PASS, repository gate PASS; source binding matched; Git worktree dirty |
| `python -B -m runtime.restore_historical_runs --help` | 0 | CLI grammar inspected; actual restore NOT_RUN because no original backup/ledger exists |
| `python -B -m runtime.invoice_reconciliation --help` | 0 | CLI grammar inspected; real billing comparison NOT_RUN, inputs unavailable |
| `python -B -m runtime.generate_audit_package --help` | 0 | capture-checks/build/verify interfaces inspected |
| `python -B -c` AST/whitespace/EOF check | 0 | Six Python files parse; seven source/docs/tests clean whitespace and final newline |
| `git diff --check --` followed by the seven listed source/docs/tests paths | 0 | Clean; untracked files also covered by explicit Python whitespace check |
| `python -B -c` check-receipt integrity/source binding | 0 | Final receipt hash and declared sources match; counts [17,31,13], gate true, worktree_clean false |
| `python -B -c` historical-root inventory check | 0 | Observation only: three required runs still missing under evidence/runtime |

Distinct test coverage is **78 tests PASS** (17 new + 61 existing). Regression
reruns and repeated capture are not added to this count. Restore, billing and
signing tests run only on disposable synthetic fixtures; private keys are
ephemeral in memory. No actual workspace restore or signed readiness ZIP was
issued, since the original inputs and operator signing key were not supplied.
The final repository check after these receipts/docs is reported in the chat.

## Source manifest and pending handoff

```text
runtime/audit_support.py
3bb5ac7e9bce930ec0dc065f7b239464712270d5ae488eafcc0681f2554a2992
runtime/restore_historical_runs.py
b7f4e96f81288fe93c5da6fc08df24ec36168755b1a483c62bbe221c94bffd21
runtime/invoice_reconciliation.py
aa5bbf5d07115dbf488f862fc5dc95a8bd1326e2d792ccb56395bdb3155ea401
runtime/generate_audit_package.py
dd2629021255d1112b1488f913a3d7aa654e051df3b223df899f2260bc645705
runtime/repository_cleanup.py
8deeec031b076033384fd9cbb3a9ed83e0cd561bc8d23c942544bdd484964d8a
tests/runtime/test_audit_pipeline.py
c9fcc8460494068c7577ff1e112e9cf9306053585cdaf7906b99886c9b814bf0
```

```text
build_id: BUILD-HISTORICAL-AUDIT-TOOLS-20261012
user_scope: original-byte restore to evidence/runtime, billing comparison,
  signed submitter readiness package
plan_id: UNRESOLVED; no approved contract fabricated
changed_files: seven source/docs/tests paths + two new CHECKS receipts, listed above
deleted_files: none
focused_checks: 17 new + 61 existing PASS; CLI help/AST/whitespace PASS
repository_gate: PASS at captured check; no independent approval implied
check_receipt: CHECKS-8f7cc9bb237b4ce4b5fd1d7abafc1a5f/receipt.json
worktree_clean: false (observed; user changes preserved)
handoff_state: HANDOFF_BLOCKED
blockers: original backup/independent hash ledger unavailable; three runs missing;
  authentic invoice unavailable; operator signing key not supplied; review pending
original_restore: NOT_RUN
actual_invoice_reconciled: false; simulated comparisons cannot prove a paid bill
signed_workspace_package: NOT_ISSUED; only temp fixture signing was exercised
independent_review: UNRESOLVED; no verdict/approval/status mutation
pending: acquire original bytes and trusted hash record; authentic billing proof;
  stable source/custody and operator key; then prepare submission for actual review
```

No root task/status document, snapshot, original ledger, evidence record or user
change was rewritten. No self-approval, history append, commit or live execution.
