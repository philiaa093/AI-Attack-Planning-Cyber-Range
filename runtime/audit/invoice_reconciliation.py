"""Reconcile a pinned request-level billing CSV with a sealed usage ledger.

Numerical agreement with a simulated or user-supplied CSV is not proof of an
authentic paid invoice. No actual-cost or independent-approval status is lifted.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

from runtime.audit.audit_support import pinned_read, publish_receipt
from runtime.evaluation.usage_costs import identifier, read_verified, summarize_ledger, utc_now

COLUMNS = ("invoice_id", "run_id", "provider", "response_id", "currency",
           "token_subtotal_usd", "tax_usd", "total_usd")


def money(value):
    if type(value) is not str or not re.fullmatch(r"\d{1,12}(?:\.\d{1,12})?", value):
        raise ValueError("bounded nonnegative decimal amount string required")
    return Decimal(value)


def _reconcile(ledger_path, ledger_sha256, billing_path, billing_sha256, receipt_parent,
              *, source_kind="SIMULATED_BILLING_EXPORT", quantum="0.000001", tolerance="0"):
    if source_kind not in ("SIMULATED_BILLING_EXPORT", "EXTERNAL_UNVERIFIED_EXPORT"):
        raise ValueError("explicit simulated or unverified billing source required")
    if quantum not in ("0.01", "0.000001"):
        raise ValueError("declared cent or micro-dollar rounding unit required")
    unit, allowed = Decimal(quantum), money(tolerance)
    if allowed > unit / 2:
        raise ValueError("tolerance cannot exceed half the declared rounding unit")
    summary = summarize_ledger(ledger_path, ledger_sha256)
    expected, unknown = {}, summary["unknown_calls"]
    for call in summary["calls_detail"]:
        ref = call["source_ref"]
        event = read_verified(Path(ledger_path).parent / ref["name"], ref["sha256"])
        if event["usage"] is not None:
            usage = event["usage"]
            key = usage["provider"], usage["response_id"]
            expected[key] = None if call["quote"] is None else Decimal(call["quote"]["token_cost_usd"])
    raw = pinned_read(billing_path, billing_sha256)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if reader.fieldnames != list(COLUMNS):
        raise ValueError("request-level CSV must have the exact declared columns")
    seen, rows, out_of_scope, totals = set(), [], 0, [Decimal(0), Decimal(0), Decimal(0)]
    for index, row in enumerate(reader):
        if index >= 100_000 or set(row) != set(COLUMNS) or any(type(v) is not str for v in row.values()):
            raise ValueError("malformed/oversized billing CSV")
        for key in ("invoice_id", "run_id", "response_id"):
            identifier(row[key])
        if row["provider"] not in ("openai", "anthropic") or row["currency"] != "USD":
            raise ValueError("supported provider and USD currency required")
        net, tax, gross = (money(row[k]) for k in ("token_subtotal_usd", "tax_usd", "total_usd"))
        # Validate arithmetic even for unrelated monthly-export rows.
        arithmetic_delta = gross - (net + tax).quantize(unit, rounding=ROUND_HALF_UP)
        if row["run_id"] != summary["run_id"]:
            out_of_scope += 1
            if abs(arithmetic_delta) > allowed:
                raise ValueError("out-of-scope invoice arithmetic is malformed")
            continue
        key = row["provider"], row["response_id"]
        if key in seen:
            raise ValueError("duplicate billed response")
        seen.add(key)
        calculated = expected.get(key)
        rounded = None if calculated is None else calculated.quantize(unit, rounding=ROUND_HALF_UP)
        difference = None if rounded is None else net - rounded
        match = (key in expected and calculated is not None
                 and abs(difference) <= allowed and abs(arithmetic_delta) <= allowed)
        rows.append(dict(invoice_id=row["invoice_id"], provider=key[0], response_id=key[1],
                         calculated_usd=None if calculated is None else format(calculated, "f"),
                         rounded_expected_usd=None if rounded is None else format(rounded, "f"),
                         exported_net_usd=format(net, "f"), exported_tax_usd=format(tax, "f"),
                         exported_total_usd=format(gross, "f"),
                         net_difference_usd=None if difference is None else format(difference, "f"),
                         arithmetic_difference_usd=format(arithmetic_delta, "f"), matches=match))
        totals = [value + extra for value, extra in zip(totals, (net, tax, gross))]
    if not rows:
        raise ValueError("billing export contains no rows for the ledger run")
    missing = sorted(expected.keys() - seen)
    extra = sorted(seen - expected.keys())
    complete = not unknown and not missing and not extra
    comparison = "INCOMPLETE" if not complete else ("MATCHED" if all(r["matches"] for r in rows) else "MISMATCH")
    receipt = dict(schema_version=1, document_type="INVOICE_RECONCILIATION_RECEIPT", created_at_utc=utc_now(),
                   source=source_kind, redaction="BILLING_METADATA_ONLY",
                   expected_state=dict(usage_ledger_sha256=ledger_sha256, billing_export_sha256=billing_sha256,
                                       rounding_quantum_usd=quantum, tolerance_usd=tolerance,
                                       taxes="EXPLICIT_EXPORT_AMOUNTS; NO_TAX_RATE_ASSUMED"),
                   observed_state=dict(run_id=summary["run_id"], usage_source=summary["source"], comparison_state=comparison,
                                       calls_in_ledger=summary["calls"], unknown_calls=unknown,
                                       missing_billed_responses=missing, extra_billed_responses=extra,
                                       excluded_other_run_rows=out_of_scope,
                                       calculated_token_total_usd=summary["token_cost_usd"],
                                       reported_token_subtotal_usd=format(totals[0], "f"),
                                       reported_tax_usd=format(totals[1], "f"), reported_total_usd=format(totals[2], "f"),
                                       rows=rows, actual_billed_usd=None, actual_invoice_reconciled=False),
                   billing_authenticity="UNRESOLVED", independent_review="UNRESOLVED", task_status_changed=False)
    return publish_receipt(receipt_parent, "RECONCILIATION", receipt)


def reconcile(*args, **kwargs):
    with localcontext() as context:
        context.prec = 60
        return _reconcile(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--ledger-sha256", required=True)
    parser.add_argument("--billing-csv", type=Path, required=True)
    parser.add_argument("--billing-sha256", required=True)
    parser.add_argument("--source", choices=("simulated", "provided"), default="simulated")
    parser.add_argument("--quantum", choices=("0.01", "0.000001"), default="0.000001")
    parser.add_argument("--tolerance", default="0")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--receipts", type=Path, default=root / "runtime/audit-artifacts")
    args = parser.parse_args()
    if not args.receipts.resolve().is_relative_to(root / "runtime/audit-artifacts"):
        parser.error("receipts must stay within runtime/audit-artifacts")
    try:
        path, checksum = reconcile(args.ledger, args.ledger_sha256, args.billing_csv, args.billing_sha256,
                                   args.receipts, source_kind="SIMULATED_BILLING_EXPORT" if args.source == "simulated"
                                   else "EXTERNAL_UNVERIFIED_EXPORT", quantum=args.quantum, tolerance=args.tolerance)
        document = read_verified(path, checksum)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Reconciliation stopped; no invoice approval issued: {exc}\n")
    print(f"Reconciliation receipt: {path}; SHA-256: {checksum}")
    if document["observed_state"]["comparison_state"] != "MATCHED":
        parser.exit(1, "Comparison is not fully matched; retained receipt records the discrepancy.\n")


if __name__ == "__main__":
    main()
