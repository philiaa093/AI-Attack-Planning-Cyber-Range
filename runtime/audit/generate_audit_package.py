"""Ed25519-signed audit submission; signing is never independent approval.

capture-checks runs only three fixed offline suites (61 expected tests), the
repository validator and read-only Git metadata. build seals supplied receipts.
verify requires an independently trusted public-key fingerprint.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import stat
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from runtime.audit.audit_support import (
    FILE_LIMIT, TOTAL_LIMIT, bounded_read, closed, digest, exclusive_bytes, pinned_json,
    pinned_read, publish_receipt, safe_relative, version_one,
)
from runtime.audit.restore_historical_runs import original_inventory
from runtime.evaluation.usage_costs import canonical, load_json_bytes, no_links, sha, utc_now, utc_timestamp

DOMAIN = b"PBL6-AUDIT-READINESS-V1\0"
SUITES = (("test_evaluation_operations.py", 17), ("test_llm_planner.py", 31), ("test_evaluate_all.py", 13))
SOURCE_PATHS = (
    "runtime/evaluation/evaluate_all.py", "runtime/planners/llm_planner.py", "runtime/evaluation/usage_costs.py",
    "runtime/audit/repository_cleanup.py", "runtime/evaluation/defensive_log_import.py",
    "runtime/evaluation/offline_evaluation.py", "runtime/planners/planner_interface.py", "runtime/state/knowledge_state_store.py",
    "runtime/evaluation/replay_wrappers.py", "runtime/evaluation/rl_environment.py", "runtime/evaluation/reward_model.py",
    "runtime/audit/audit_support.py", "runtime/audit/restore_historical_runs.py", "runtime/audit/invoice_reconciliation.py",
    "runtime/audit/generate_audit_package.py", "agent/memory/state/state_manager.py",
    "scripts/validation/validate_scaffold.py", "tests/runtime/test_audit_pipeline.py",
) + tuple("tests/runtime/" + name for name, _ in SUITES)


def source_hashes(root):
    return {name: sha(bounded_read(Path(root) / name)) for name in SOURCE_PATHS}


def fixed_process(argv, root, timeout=60):
    result = subprocess.run(argv, cwd=root, capture_output=True, timeout=timeout, check=False)
    if len(result.stdout) + len(result.stderr) > FILE_LIMIT:
        raise ValueError("check output too large")
    return result, (result.stdout + result.stderr).decode("utf-8", errors="replace")


def capture_checks(root, receipt_parent):
    root = Path(root).absolute()
    no_links(root)
    before, started, receipts = source_hashes(root), utc_now(), []
    for filename, expected in SUITES:
        argv = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/runtime", "-p", filename, "-v"]
        result, output = fixed_process(argv, root)
        counts = re.findall(r"^Ran (\d+) tests? in ", output, re.M)
        ids = re.findall(r"^(\S+ \([^\n]+\)) \.\.\. ok\s*$", output, re.M)
        observed = int(counts[-1]) if len(counts) == 1 else None
        passed = result.returncode == 0 and observed == expected and len(ids) == expected and len(set(ids)) == expected
        receipts.append(dict(suite=filename, invocation=argv, return_code=result.returncode,
                             expected_tests=expected, observed_tests=observed, passed=passed,
                             passed_test_ids=ids, output_sha256=sha(result.stdout + result.stderr)))
    gate_args = [sys.executable, "-B", "scripts/validation/validate_scaffold.py"]
    gate, gate_output = fixed_process(gate_args, root)
    git, git_output = fixed_process(["git", "status", "--porcelain=v1", "--untracked-files=all"], root, 10)
    head, head_output = fixed_process(["git", "rev-parse", "HEAD"], root, 10)
    if git.returncode or head.returncode:
        raise ValueError("Git state could not be observed")
    if source_hashes(root) != before:
        raise ValueError("declared sources changed during checks; no passing receipt minted")
    document = dict(schema_version=1, document_type="AUDIT_CHECK_RECEIPT", source="LOCAL_EXECUTION",
                    created_at_utc=utc_now(), started_at_utc=started,
                    source_sha256=before, source_binding="DECLARED_SET_ONLY; NOT_FULL_DEPENDENCY_CLOSURE",
                    suites=receipts, all_61_passed=all(r["passed"] for r in receipts),
                    repository_gate=dict(invocation=gate_args, return_code=gate.returncode,
                                         passed=gate.returncode == 0 and "SCAFFOLD VALID" in gate_output,
                                         output_sha256=sha(gate.stdout + gate.stderr)),
                    git_state=dict(head=head_output.strip(), worktree_clean=not git_output.strip(),
                                   porcelain=git_output, observed_at_utc=utc_now()),
                    independent_review="UNRESOLVED", approval_granted=False)
    return publish_receipt(receipt_parent, "CHECKS", document)


def build_package(root, checks_path, checks_sha256, output_parent, signing_key, *,
                  restore_ref=None, reconciliation_ref=None):
    """Prepare a signed submission even when blockers remain; never approve it."""
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise ValueError("caller-supplied Ed25519 submitter key required")
    root = Path(root).absolute()
    no_links(root)
    checks_raw = pinned_read(checks_path, checks_sha256)
    checks = load_json_bytes(checks_raw)
    closed(checks, {"schema_version", "document_type", "source", "created_at_utc", "started_at_utc",
                    "source_sha256", "source_binding", "suites", "all_61_passed", "repository_gate",
                    "git_state", "independent_review", "approval_granted"})
    version_one(checks["schema_version"])
    utc_timestamp(checks["created_at_utc"]); utc_timestamp(checks["started_at_utc"])
    if checks["document_type"] != "AUDIT_CHECK_RECEIPT" or checks["approval_granted"] is not False:
        raise ValueError("a non-approval check receipt is required")
    if type(checks["suites"]) is not list or len(checks["suites"]) != len(SUITES):
        raise ValueError("exact three-suite check receipt required")
    all_passed = True
    for receipt, (filename, expected) in zip(checks["suites"], SUITES):
        closed(receipt, {"suite", "invocation", "return_code", "expected_tests", "observed_tests", "passed",
                         "passed_test_ids", "output_sha256"})
        if receipt["suite"] != filename or receipt["expected_tests"] != expected:
            raise ValueError("check suite identity/count mismatch")
        digest(receipt["output_sha256"])
        if checks["source"] == "LOCAL_EXECUTION" and receipt["invocation"] != [sys.executable, "-B", "-m", "unittest",
                "discover", "-s", "tests/runtime", "-p", filename, "-v"]:
            raise ValueError("check invocation differs from fixed offline suite")
        ids = receipt["passed_test_ids"]
        if type(ids) is not list or any(type(i) is not str for i in ids):
            raise ValueError("typed test identities required")
        passed = (type(receipt["return_code"]) is int and receipt["return_code"] == 0
                  and type(receipt["observed_tests"]) is int and receipt["observed_tests"] == expected
                  and len(ids) == expected and len(set(ids)) == expected)
        if receipt["passed"] is not passed:
            raise ValueError("check success flag conflicts with observed receipt")
        all_passed = all_passed and passed
    if checks["all_61_passed"] is not all_passed:
        raise ValueError("aggregate test success flag conflicts with suite receipts")
    gate = checks["repository_gate"]
    closed(gate, {"invocation", "return_code", "passed", "output_sha256"})
    if type(gate["return_code"]) is not int or gate["passed"] is not (gate["return_code"] == 0):
        raise ValueError("gate success flag conflicts with receipt")
    digest(gate["output_sha256"])
    if checks["source_sha256"] != source_hashes(root):
        raise ValueError("check receipts are stale for current declared sources")
    artifacts = {"receipts/checks.json": checks_raw}
    blockers = []
    if checks["source"] != "LOCAL_EXECUTION":
        blockers.append("SIMULATED_CHECK_RECEIPT")
    if checks["all_61_passed"] is not True:
        blockers.append("REQUIRED_TESTS_NOT_PASSED")
    if checks["repository_gate"].get("passed") is not True:
        blockers.append("REPOSITORY_GATE_NOT_PASSED")
    git, git_output = fixed_process(["git", "status", "--porcelain=v1", "--untracked-files=all"], root, 10)
    if git.returncode:
        raise ValueError("current Git state unavailable")
    artifacts["receipts/current-git-state.json"] = canonical(dict(observed_at_utc=utc_now(), porcelain=git_output,
                                                                  worktree_clean=not git_output.strip()))
    if git_output.strip() or checks["git_state"].get("worktree_clean") is not True:
        blockers.append("DIRTY_WORKTREE")
    if restore_ref is None:
        blockers.append("MISSING_HISTORICAL_RESTORE_RECEIPT")
    else:
        path, checksum = restore_ref
        raw = pinned_read(path, checksum)
        document = load_json_bytes(raw)
        if document.get("document_type") != "HISTORICAL_RESTORE_RECEIPT":
            raise ValueError("restore receipt required")
        inventory = original_inventory(document["expected_state"]["original_inventory"])
        destination = Path(document["observed_state"]["destination"]).absolute()
        if destination != root / "evidence/runtime":
            raise ValueError("restore destination must bind to this workspace evidence/runtime")
        for name, ref in inventory.items():
            artifacts["historical/" + name] = pinned_read(destination / name, ref["sha256"])
            if len(artifacts["historical/" + name]) != ref["size"]:
                raise ValueError("restored evidence size mismatch")
        artifacts["receipts/restore.json"] = raw
        if document.get("source") != "ORIGINAL_LEDGER":
            blockers.append("SIMULATED_RESTORE_SOURCE")
    if reconciliation_ref is None:
        blockers.append("MISSING_INVOICE_RECONCILIATION")
    else:
        path, checksum = reconciliation_ref
        raw = pinned_read(path, checksum)
        document = load_json_bytes(raw)
        if document.get("document_type") != "INVOICE_RECONCILIATION_RECEIPT":
            raise ValueError("reconciliation receipt required")
        artifacts["receipts/reconciliation.json"] = raw
        if document["observed_state"].get("comparison_state") != "MATCHED":
            blockers.append("BILLING_NUMBERS_NOT_MATCHED")
        if document.get("source") == "SIMULATED_BILLING_EXPORT":
            blockers.append("SIMULATED_BILLING_IS_NOT_AN_ACTUAL_INVOICE")
        # Numerical agreement does not supply provider authenticity or auditor approval.
        if document.get("billing_authenticity") != "VERIFIED" or document["observed_state"].get("actual_invoice_reconciled") is not True:
            blockers.append("ACTUAL_INVOICE_AUTHENTICITY_UNRESOLVED")
    for name, checksum in checks["source_sha256"].items():
        safe_relative(name)
        artifacts["sources/" + name] = pinned_read(root / name, checksum)
    if sum(map(len, artifacts.values())) > TOTAL_LIMIT:
        raise ValueError("audit package exceeds total size limit")
    public_bytes = signing_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    manifest = dict(schema_version=1, document_type="AUDIT_READINESS_PACKAGE", created_at_utc=utc_now(),
                    signer_role="SUBMITTER", public_key_sha256=sha(public_bytes),
                    readiness_state="PREPARED_WITH_BLOCKERS" if blockers else "READY_FOR_REVIEW",
                    blockers=blockers, independent_review="PENDING", approval_granted=False,
                    handoff_state="HANDOFF_BLOCKED", task_status_changed=False,
                    source_binding=checks["source_binding"],
                    artifacts=[dict(path=name, size=len(data), sha256=sha(data)) for name, data in sorted(artifacts.items())])
    manifest_bytes = canonical(manifest)
    signature = signing_key.sign(DOMAIN + manifest_bytes)
    envelope = canonical(dict(algorithm="Ed25519", signer_role="SUBMITTER",
                               public_key_base64=base64.b64encode(public_bytes).decode(),
                               signature_base64=base64.b64encode(signature).decode()))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("signature.json", envelope)
        for name, data in sorted(artifacts.items()):
            archive.writestr(name, data)
    package = buffer.getvalue()
    verify_package_bytes(package, sha(public_bytes))  # Verify signature + every member before disk publication.
    parent = Path(output_parent).absolute()
    no_links(parent)
    path = parent / ("AUDIT-" + uuid.uuid4().hex + ".zip")
    exclusive_bytes(path, package)
    return path, sha(package), manifest


def verify_package_bytes(package, trusted_public_key_sha256):
    digest(trusted_public_key_sha256)
    if len(package) > TOTAL_LIMIT + FILE_LIMIT:
        raise ValueError("oversized audit package")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        if len(names) != len({n.casefold() for n in names}) or len(names) > 4096:
            raise ValueError("duplicate/oversized audit member inventory")
        for info in archive.infolist():
            safe_relative(info.filename)
            if (info.file_size > FILE_LIMIT or info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1
                    or info.is_dir() or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)):
                raise ValueError("unexpected compressed/oversized audit member")
        manifest_bytes = archive.read("manifest.json")
        manifest = load_json_bytes(manifest_bytes)
        closed(manifest, {"schema_version", "document_type", "created_at_utc", "signer_role", "public_key_sha256",
                          "readiness_state", "blockers", "independent_review", "approval_granted", "handoff_state",
                          "task_status_changed", "source_binding", "artifacts"})
        version_one(manifest["schema_version"])
        utc_timestamp(manifest["created_at_utc"])
        if (type(manifest["blockers"]) is not list or any(type(b) is not str for b in manifest["blockers"])
                or manifest["readiness_state"] != ("PREPARED_WITH_BLOCKERS" if manifest["blockers"] else "READY_FOR_REVIEW")
                or manifest["task_status_changed"] is not False):
            raise ValueError("readiness state conflicts with blockers/non-approval scope")
        if canonical(manifest) != manifest_bytes or manifest.get("document_type") != "AUDIT_READINESS_PACKAGE":
            raise ValueError("noncanonical audit manifest")
        if (manifest.get("signer_role") != "SUBMITTER" or manifest.get("approval_granted") is not False
                or manifest.get("independent_review") != "PENDING" or manifest.get("handoff_state") != "HANDOFF_BLOCKED"):
            raise ValueError("package cannot impersonate independent approval")
        envelope = load_json_bytes(archive.read("signature.json"))
        closed(envelope, {"algorithm", "signer_role", "public_key_base64", "signature_base64"})
        if envelope["algorithm"] != "Ed25519" or envelope["signer_role"] != "SUBMITTER":
            raise ValueError("unsupported signing role/algorithm")
        public = base64.b64decode(envelope["public_key_base64"], validate=True)
        signature = base64.b64decode(envelope["signature_base64"], validate=True)
        if sha(public) != trusted_public_key_sha256 or manifest.get("public_key_sha256") != sha(public):
            raise ValueError("untrusted signing key")
        Ed25519PublicKey.from_public_bytes(public).verify(signature, DOMAIN + manifest_bytes)
        expected_names = {"manifest.json", "signature.json"}
        if type(manifest["artifacts"]) is not list or len(manifest["artifacts"]) > 4094:
            raise ValueError("bounded audit artifact inventory required")
        for ref in manifest["artifacts"]:
            closed(ref, {"path", "size", "sha256"})
            safe_relative(ref["path"])
            digest(ref["sha256"])
            if type(ref["size"]) is not int or not 0 <= ref["size"] <= FILE_LIMIT:
                raise ValueError("bounded artifact size required")
            if ref["path"] in expected_names:
                raise ValueError("duplicate manifest artifact")
            expected_names.add(ref["path"])
            data = archive.read(ref["path"])
            if len(data) != ref["size"] or sha(data) != ref["sha256"]:
                raise ValueError("audit artifact hash mismatch")
        if set(names) != expected_names:
            raise ValueError("unlisted/missing audit artifact")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    root = Path(__file__).resolve().parents[2]
    capture = sub.add_parser("capture-checks")
    capture.add_argument("--output", type=Path, default=root / "runtime/audit-artifacts")
    build = sub.add_parser("build")
    build.add_argument("--checks", type=Path, required=True); build.add_argument("--checks-sha256", required=True)
    build.add_argument("--restore", type=Path); build.add_argument("--restore-sha256")
    build.add_argument("--reconciliation", type=Path); build.add_argument("--reconciliation-sha256")
    build.add_argument("--private-key", type=Path, required=True)
    build.add_argument("--password-env", help="name of environment variable holding key password; never stored")
    build.add_argument("--output", type=Path, default=root / "runtime/audit-artifacts")
    verify = sub.add_parser("verify")
    verify.add_argument("--package", type=Path, required=True)
    verify.add_argument("--public-key-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.mode == "verify":
            manifest = verify_package_bytes(bounded_read(args.package, TOTAL_LIMIT + FILE_LIMIT), args.public_key_sha256)
            print(f"Signature and members verified; review remains {manifest['independent_review']}.")
            return
        if not args.output.resolve().is_relative_to(root / "runtime/audit-artifacts"):
            parser.error("output must stay within runtime/audit-artifacts")
        if args.mode == "capture-checks":
            path, checksum = capture_checks(root, args.output)
            print(f"Observed check receipt: {path}; SHA-256: {checksum}")
            observed = pinned_json(path, checksum)
            if observed["all_61_passed"] is not True or observed["repository_gate"]["passed"] is not True:
                parser.exit(1, "Failed checks retained in receipt; no passing readiness claimed.\n")
            return
        for value, checksum in ((args.restore, args.restore_sha256), (args.reconciliation, args.reconciliation_sha256)):
            if bool(value) != bool(checksum):
                parser.error("each receipt path requires its pinned SHA-256")
        password = None
        if args.password_env:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", args.password_env):
                parser.error("invalid password variable name")
            value = os.environ.get(args.password_env)
            if value is None:
                parser.error("key password variable is missing")
            password = value.encode()
        key = serialization.load_pem_private_key(bounded_read(args.private_key, 16384), password=password)
        path, checksum, manifest = build_package(root, args.checks, args.checks_sha256, args.output, key,
                                                 restore_ref=None if args.restore is None else (args.restore, args.restore_sha256),
                                                 reconciliation_ref=None if args.reconciliation is None else (args.reconciliation, args.reconciliation_sha256))
    except Exception as exc:
        # Key loader/provider messages can contain sensitive context: static diagnostic only.
        parser.exit(1, f"Audit operation stopped ({type(exc).__name__}); no approval issued.\n")
    print(f"Signed submission: {path}; SHA-256: {checksum}; {manifest['readiness_state']}")
    if manifest["blockers"]:
        parser.exit(2, "Submission retained with blockers; HANDOFF_BLOCKED is unchanged.\n")


if __name__ == "__main__":
    main()
