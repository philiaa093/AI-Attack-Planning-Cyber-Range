"""Restore, billing reconciliation and signed readiness; temp fixtures only."""
import base64
import csv
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from runtime.audit.audit_support import safe_relative
from runtime.audit.generate_audit_package import (
    DOMAIN, SOURCE_PATHS, SUITES, build_package, source_hashes, verify_package_bytes,
)
from runtime.audit.invoice_reconciliation import COLUMNS, reconcile
from runtime.audit.repository_cleanup import HISTORICAL_RUNS, verify_historical_runs
from runtime.audit.restore_historical_runs import decode_backup, original_inventory, restore
from runtime.evaluation.usage_costs import UsageLedger, canonical, sha
from test_evaluation_operations import usage


class AuditPipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.receipts = self.root / "runtime/audit-artifacts"

    def backup(self):
        ledger = dict(schema_version=1, source_kind="SIMULATED_FIXTURE", runs=[])
        backup = dict(schema_version=1, runs=[])
        original = {}
        for index, run in enumerate(HISTORICAL_RUNS):
            data = b'original bytes with CRLF\r\n' + bytes([index, 0, 255])
            original[run + "/nested/record.txt"] = data
            ledger["runs"].append(dict(run_id=run, files=[dict(path="nested/record.txt", size=len(data), sha256=sha(data))]))
            backup["runs"].append(dict(run_id=run, files=[dict(path="nested/record.txt", data_base64=base64.b64encode(data).decode())]))
        archive = self.root / "backup.json"
        ledger_path = self.root / "original-ledger.json"
        archive.write_bytes(canonical(backup)); ledger_path.write_bytes(canonical(ledger))
        return archive, sha(archive.read_bytes()), ledger_path, sha(ledger_path.read_bytes()), original

    def do_restore(self, inputs=None):
        archive, archive_hash, ledger, ledger_hash, originals = self.backup() if inputs is None else inputs
        path, digest = restore(archive, archive_hash, ledger, ledger_hash,
                               self.root / "evidence/runtime", self.receipts)
        return path, digest, originals

    def test_restore_exact_bytes_and_idempotent_no_overwrite(self):
        inputs = self.backup()
        receipt, digest, original = self.do_restore(inputs)
        for name, data in original.items():
            self.assertEqual((self.root / "evidence/runtime" / name).read_bytes(), data)
        second, _, _ = self.do_restore(inputs)
        observed = json.loads(second.read_text())["observed_state"]
        self.assertEqual(observed["files_created"], 0)
        self.assertEqual(observed["files_already_matching"], 3)
        self.assertEqual(sha(receipt.read_bytes()), digest)

    def test_zip_restore_same_original_hashes(self):
        archive, _, ledger, ledger_hash, original = self.backup()
        zip_path = self.root / "backup.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for name, data in original.items():
                zipped.writestr(name, data)
        receipt, _ = restore(zip_path, sha(zip_path.read_bytes()), ledger, ledger_hash,
                             self.root / "evidence/runtime", self.receipts)
        self.assertEqual(json.loads(receipt.read_text())["observed_state"]["files_verified"], 3)

    def test_tampered_backup_or_ledger_stops_before_any_write(self):
        archive, archive_hash, ledger, ledger_hash, _ = self.backup()
        with archive.open("ab") as stream:
            stream.write(b" ")
        with self.assertRaises(ValueError):
            restore(archive, archive_hash, ledger, ledger_hash, self.root / "evidence/runtime", self.receipts)
        self.assertFalse((self.root / "evidence").exists())
        self.assertFalse(self.receipts.exists())
        with self.assertRaises(ValueError):
            restore(archive, sha(archive.read_bytes()), ledger, "0" * 64, self.root / "evidence/runtime", self.receipts)

    def test_wrong_file_hash_and_conflicting_existing_run_block_all_writes(self):
        inputs = self.backup()
        document = json.loads(inputs[0].read_text())
        document["runs"][-1]["files"][0]["data_base64"] = base64.b64encode(b"different").decode()
        inputs[0].write_bytes(canonical(document))
        with self.assertRaises(ValueError):
            restore(inputs[0], sha(inputs[0].read_bytes()), inputs[2], inputs[3], self.root / "evidence/runtime", self.receipts)
        self.assertFalse((self.root / "evidence").exists())
        inputs = self.backup()
        conflicting = self.root / "evidence/runtime" / HISTORICAL_RUNS[0] / "nested/record.txt"
        conflicting.parent.mkdir(parents=True)
        conflicting.write_bytes(b"existing essential evidence")
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.do_restore(inputs)
        self.assertEqual(conflicting.read_bytes(), b"existing essential evidence")
        self.assertFalse((self.root / "evidence/runtime" / HISTORICAL_RUNS[1]).exists())

    def test_golden_config_is_not_an_evidence_backup(self):
        with self.assertRaises(ValueError):
            original_inventory(dict(snapshot_version="1.0", targets=[]))

    def test_path_traversal_devices_ads_case_and_parent_collisions(self):
        for name in ("../outside", "/absolute", "C:/drive", "nested\\record", "CON.txt", "NUL", "a:stream", "file.", "a//b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_relative(name)
        _, _, path, _, _ = self.backup()
        ledger = json.loads(path.read_text())
        entry = ledger["runs"][0]["files"][0]
        ledger["runs"][0]["files"].append(entry | {"path": "nested/RECORD.txt"})
        with self.assertRaisesRegex(ValueError, "colliding"):
            original_inventory(ledger)

    def test_zip_links_duplicates_and_unlisted_files_rejected(self):
        _, _, ledger, _, original = self.backup()
        inventory = original_inventory(json.loads(ledger.read_text()))
        for kind in ("link", "unlisted"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as zipped:
                for name, data in original.items():
                    zipped.writestr(name, data)
                info = zipfile.ZipInfo(HISTORICAL_RUNS[0] + "/extra.txt")
                if kind == "link":
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zipped.writestr(info, "../outside")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                decode_backup(buffer.getvalue(), inventory)

    def test_cleanup_can_explicitly_read_restored_evidence_root(self):
        run_id = "RUN-EVAL-" + "7" * 32
        directory = self.root / "evidence/runtime" / run_id
        directory.mkdir(parents=True)
        data = b"history"
        (directory / "result.txt").write_bytes(data)
        (directory / "manifest.json").write_bytes(canonical(dict(run_id=run_id,
            observed_state=dict(artifacts=[dict(name="result.txt", sha256=sha(data))]))))
        _, failures = verify_historical_runs(self.root, (run_id,), historical_root=self.root / "evidence/runtime")
        self.assertEqual(failures, [])
        _, failures = verify_historical_runs(self.root, (run_id,))
        self.assertTrue(failures)
        with self.assertRaises(ValueError):
            verify_historical_runs(self.root, (run_id,), historical_root=self.root / "reports")

    def billing(self, *, net="0.000410", tax="0.000041", total="0.000451", missing=False):
        ledger = UsageLedger(self.root / "usage", run_id="RUN-BILLING-1", source="SIMULATED_FIXTURE")
        ledger.record(episode_id="EP-1", usage=usage())
        if missing:
            ledger.record(episode_id="EP-2", usage=None)
        ledger_path, ledger_hash = ledger.seal()
        path = self.root / "billing.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerow(dict(invoice_id="INV-MOCK-1", run_id="RUN-BILLING-1", provider="openai",
                                 response_id="resp-example-1", currency="USD", token_subtotal_usd=net,
                                 tax_usd=tax, total_usd=total))
        return ledger_path, ledger_hash, path, sha(path.read_bytes())

    def test_mock_billing_matches_numbers_without_actual_invoice_claim(self):
        path, digest = reconcile(*self.billing(), self.receipts)
        document = json.loads(path.read_text())
        self.assertEqual(sha(path.read_bytes()), digest)
        self.assertEqual(document["observed_state"]["comparison_state"], "MATCHED")
        self.assertEqual(document["observed_state"]["reported_total_usd"], "0.000451")
        self.assertIsNone(document["observed_state"]["actual_billed_usd"])
        self.assertFalse(document["observed_state"]["actual_invoice_reconciled"])

    def test_rounding_declared_bounded_and_mismatch_retained(self):
        path, _ = reconcile(*self.billing(net="0.00", tax="0.00", total="0.00"), self.receipts, quantum="0.01")
        self.assertEqual(json.loads(path.read_text())["observed_state"]["comparison_state"], "MATCHED")
        args = self.billing(net="0.010000", tax="0.000000", total="0.010000")
        path, _ = reconcile(*args, self.receipts)
        self.assertEqual(json.loads(path.read_text())["observed_state"]["comparison_state"], "MISMATCH")
        with self.assertRaises(ValueError):
            reconcile(*args, self.receipts, tolerance="0.1")

    def test_billing_missing_usage_incomplete_and_total_arithmetic_mismatch(self):
        path, _ = reconcile(*self.billing(missing=True), self.receipts)
        self.assertEqual(json.loads(path.read_text())["observed_state"]["comparison_state"], "INCOMPLETE")
        path, _ = reconcile(*self.billing(total="0.000999"), self.receipts)
        self.assertEqual(json.loads(path.read_text())["observed_state"]["comparison_state"], "MISMATCH")

    def test_csv_hash_duplicate_currency_and_nonfinite_rejected(self):
        args = self.billing()
        with self.assertRaises(ValueError):
            reconcile(args[0], args[1], args[2], "0" * 64, self.receipts)
        raw = args[2].read_text()
        for changed in (raw + raw.splitlines()[1] + "\n", raw.replace("USD", "EUR"), raw.replace("0.000410", "NaN")):
            args[2].write_text(changed, encoding="utf-8")
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                reconcile(args[0], args[1], args[2], sha(args[2].read_bytes()), self.receipts)

    def checks_fixture(self):
        for name in SOURCE_PATHS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"# synthetic fixture source\n")
        suites = [dict(suite=name, invocation=["synthetic"], return_code=0, expected_tests=n,
                       observed_tests=n, passed=True, passed_test_ids=[f"{name}::{i}" for i in range(n)],
                       output_sha256=sha(b"fixture")) for name, n in SUITES]
        document = dict(schema_version=1, document_type="AUDIT_CHECK_RECEIPT", source="SIMULATED_FIXTURE",
                        created_at_utc="2026-10-12T00:00:00Z", started_at_utc="2026-10-12T00:00:00Z",
                        source_sha256=source_hashes(self.root), source_binding="DECLARED_SET_ONLY", suites=suites,
                        all_61_passed=True, repository_gate=dict(invocation=["synthetic"], return_code=0,
                                                               passed=True, output_sha256=sha(b"fixture")),
                        git_state=dict(head="0" * 40, worktree_clean=True, porcelain="", observed_at_utc="2026-10-12T00:00:00Z"),
                        independent_review="UNRESOLVED", approval_granted=False)
        path = self.root / "checks.json"
        path.write_bytes(canonical(document))
        return path, sha(path.read_bytes())

    def build(self, checks=None, **kwargs):
        checks = self.checks_fixture() if checks is None else checks
        key = Ed25519PrivateKey.generate()  # Ephemeral test key; never written or included.
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        with patch("runtime.audit.generate_audit_package.fixed_process", return_value=(SimpleNamespace(returncode=0), "")):
            path, digest, manifest = build_package(self.root, *checks, self.receipts, key, **kwargs)
        return path, digest, manifest, key, sha(public)

    def test_signed_package_verifies_but_keeps_missing_evidence_and_approval_blocked(self):
        path, digest, manifest, _, fingerprint = self.build()
        self.assertEqual(sha(path.read_bytes()), digest)
        self.assertEqual(verify_package_bytes(path.read_bytes(), fingerprint), manifest)
        self.assertEqual(manifest["signer_role"], "SUBMITTER")
        self.assertEqual(manifest["handoff_state"], "HANDOFF_BLOCKED")
        self.assertFalse(manifest["approval_granted"])
        self.assertIn("MISSING_HISTORICAL_RESTORE_RECEIPT", manifest["blockers"])
        with zipfile.ZipFile(path) as archive:
            self.assertFalse(any(name.endswith((".key", ".pem")) for name in archive.namelist()))

    def mutate_zip(self, raw, member, transform):
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as after:
            for name in before.namelist():
                data = before.read(name)
                after.writestr(name, transform(data) if name == member else data)
        return buffer.getvalue()

    def test_artifact_tamper_and_untrusted_public_key_fail_verification(self):
        path, _, manifest, _, fingerprint = self.build()
        raw = path.read_bytes()
        with self.assertRaises(ValueError):
            verify_package_bytes(raw, "0" * 64)
        changed = self.mutate_zip(raw, manifest["artifacts"][0]["path"], lambda data: data + b" ")
        with self.assertRaises(ValueError):
            verify_package_bytes(changed, fingerprint)
        changed = self.mutate_zip(raw, "manifest.json", lambda data: canonical(json.loads(data) | {"created_at_utc": "2026-10-13T00:00:00Z"}))
        with self.assertRaises(InvalidSignature):
            verify_package_bytes(changed, fingerprint)

    def test_signed_fake_independent_approval_is_rejected(self):
        path, _, _, key, fingerprint = self.build()
        raw = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            manifest = json.loads(archive.read("manifest.json")) | {"approval_granted": True}
            envelope = json.loads(archive.read("signature.json"))
        manifest_bytes = canonical(manifest)
        envelope["signature_base64"] = base64.b64encode(key.sign(DOMAIN + manifest_bytes)).decode()
        raw = self.mutate_zip(raw, "manifest.json", lambda _: manifest_bytes)
        raw = self.mutate_zip(raw, "signature.json", lambda _: canonical(envelope))
        with self.assertRaisesRegex(ValueError, "approval"):
            verify_package_bytes(raw, fingerprint)

    def test_stale_sources_and_inconsistent_test_flags_rejected(self):
        checks = self.checks_fixture()
        (self.root / SOURCE_PATHS[0]).write_bytes(b"changed source\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.build(checks)
        checks = self.checks_fixture()
        document = json.loads(checks[0].read_text())
        document["suites"][0]["return_code"] = 1
        checks[0].write_bytes(canonical(document))
        with self.assertRaisesRegex(ValueError, "success flag"):
            self.build((checks[0], sha(checks[0].read_bytes())))

    def test_simulated_restoration_and_billing_cannot_lift_handoff(self):
        restored, restored_hash, _ = self.do_restore()
        reconciled, reconciled_hash = reconcile(*self.billing(), self.receipts)
        path, _, manifest, _, fingerprint = self.build(restore_ref=(restored, restored_hash),
                                                      reconciliation_ref=(reconciled, reconciled_hash))
        self.assertIn("SIMULATED_RESTORE_SOURCE", manifest["blockers"])
        self.assertIn("SIMULATED_BILLING_IS_NOT_AN_ACTUAL_INVOICE", manifest["blockers"])
        self.assertFalse(verify_package_bytes(path.read_bytes(), fingerprint)["approval_granted"])


if __name__ == "__main__":
    unittest.main()
