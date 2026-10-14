"""Restore original bytes from a pinned JSON/ZIP backup and independent ledger.

No backup generation, ledger regeneration, target reset or execution replay.
All selected bytes and existing destination files are checked before any write.
"""
from __future__ import annotations

import argparse
import base64
import io
import stat
import zipfile
from pathlib import Path

from runtime.audit.audit_support import (
    FILE_LIMIT, TOTAL_LIMIT, bounded_read, closed, digest, exclusive_bytes,
    pinned_json, pinned_read, publish_receipt, safe_relative, version_one,
)
from runtime.audit.repository_cleanup import HISTORICAL_RUNS
from runtime.evaluation.usage_costs import load_json_bytes, no_links, sha, utc_now


def original_inventory(ledger, required_runs=HISTORICAL_RUNS):
    closed(ledger, {"schema_version", "source_kind", "runs"})
    version_one(ledger["schema_version"])
    if ledger["source_kind"] not in ("ORIGINAL_LEDGER", "SIMULATED_FIXTURE"):
        raise ValueError("original ledger provenance required")
    runs = ledger["runs"]
    if type(runs) is not list or len(runs) != len(required_runs):
        raise ValueError("ledger must cover exactly the required historical runs")
    inventory, seen_runs, folded, total = {}, set(), set(), 0
    for run in runs:
        closed(run, {"run_id", "files"})
        run_id = run["run_id"]
        if type(run_id) is not str or run_id not in required_runs or run_id in seen_runs:
            raise ValueError("unknown/duplicate historical run")
        seen_runs.add(run_id)
        if type(run["files"]) is not list or not 1 <= len(run["files"]) <= 512:
            raise ValueError("bounded nonempty file inventory required")
        for ref in run["files"]:
            closed(ref, {"path", "size", "sha256"})
            relative = safe_relative(run_id + "/" + safe_relative(ref["path"]))
            digest(ref["sha256"])
            size = ref["size"]
            if type(size) is not int or not 0 <= size <= FILE_LIMIT:
                raise ValueError("bounded original file size required")
            if relative.casefold() in folded:
                raise ValueError("duplicate/case-colliding archive path")
            folded.add(relative.casefold()); total += size
            if total > TOTAL_LIMIT:
                raise ValueError("restore exceeds total resource budget")
            inventory[relative] = ref
    # Reject a file that is also the parent of another file.
    for relative in inventory:
        parts = relative.split("/")
        if any("/".join(parts[:i]).casefold() in folded for i in range(1, len(parts))):
            raise ValueError("file/directory collision")
    return inventory


def decode_backup(data, inventory):
    files = {}
    if data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 2048:
                raise ValueError("too many ZIP members")
            seen = set()
            for info in members:
                name = safe_relative(info.filename[:-1] if info.is_dir() else info.filename)
                if name.casefold() in seen:
                    raise ValueError("duplicate ZIP member")
                seen.add(name.casefold())
                kind = stat.S_IFMT(info.external_attr >> 16)
                if info.flag_bits & 1 or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("encrypted ZIP/link/special entry unsupported")
                if info.is_dir():
                    if kind not in (0, stat.S_IFDIR) or not any(p.startswith(name + "/") for p in inventory):
                        raise ValueError("unlisted ZIP directory")
                    continue
                if kind == stat.S_IFDIR or name not in inventory or info.file_size != inventory[name]["size"]:
                    raise ValueError("unlisted ZIP file or size mismatch")
                with archive.open(info) as stream:
                    raw = stream.read(inventory[name]["size"] + 1)
                files[name] = raw
    else:
        document = load_json_bytes(data)
        if type(document) is dict and "snapshot_version" in document and "targets" in document:
            raise ValueError("target reset configuration is not a historical evidence backup")
        closed(document, {"schema_version", "runs"})
        version_one(document["schema_version"])
        if type(document["runs"]) is not list or len(document["runs"]) > 3:
            raise ValueError("bounded backup run collection required")
        for run in document["runs"]:
            closed(run, {"run_id", "files"})
            if type(run["run_id"]) is not str or type(run["files"]) is not list or len(run["files"]) > 512:
                raise ValueError("typed backup run/files required")
            for entry in run["files"]:
                closed(entry, {"path", "data_base64"})
                name = safe_relative(run["run_id"] + "/" + safe_relative(entry["path"]))
                encoded = entry["data_base64"]
                if name not in inventory or name in files or type(encoded) is not str or len(encoded) > 4 * ((FILE_LIMIT + 2) // 3):
                    raise ValueError("unlisted/duplicate/oversized backup entry")
                files[name] = base64.b64decode(encoded, validate=True)
    if set(files) != set(inventory):
        raise ValueError("backup lacks required original files")
    for name, data in files.items():
        if len(data) != inventory[name]["size"] or sha(data) != inventory[name]["sha256"]:
            raise ValueError("backup bytes differ from original ledger")
    return files


def restore(archive_path, archive_sha256, ledger_path, ledger_sha256, destination,
            receipt_parent, *, required_runs=HISTORICAL_RUNS):
    ledger = pinned_json(ledger_path, ledger_sha256)
    inventory = original_inventory(ledger, required_runs)
    archive_data = pinned_read(archive_path, archive_sha256, TOTAL_LIMIT)
    files = decode_backup(archive_data, inventory)  # Verify every byte BEFORE writing anything.
    destination = Path(destination).absolute()
    no_links(destination)
    # Preflight all existing runs; a conflicting file blocks the entire operation.
    existing = set()
    for run_id in required_runs:
        directory = destination / run_id
        no_links(directory)
        if directory.exists():
            if not directory.is_dir():
                raise ValueError("existing run destination is not a directory")
            for path in directory.rglob("*"):
                no_links(path)
                if path.is_dir():
                    continue
                name = path.relative_to(destination).as_posix()
                if name not in files or bounded_read(path) != files[name]:
                    raise ValueError("existing historical bytes conflict; no writes permitted")
                existing.add(name)
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(files.items()):
        path = destination / name
        no_links(path)
        if name in existing:
            if bounded_read(path) != data:
                raise ValueError("destination changed during restoration")
            continue
        exclusive_bytes(path, data)  # No replacement. Partial writes survive errors.
    for name, data in files.items():
        if bounded_read(destination / name) != data:
            raise ValueError("restored file verification failed; preserve partial restore")
    receipt = dict(schema_version=1, document_type="HISTORICAL_RESTORE_RECEIPT", created_at_utc=utc_now(),
                   source=ledger["source_kind"], redaction="METADATA_ONLY",
                   expected_state=dict(archive_sha256=archive_sha256, ledger_sha256=ledger_sha256,
                                       original_inventory=ledger),
                   observed_state=dict(destination=str(destination), files_verified=len(files),
                                       files_created=len(files) - len(existing), files_already_matching=len(existing),
                                       verification="ALL_BYTES_MATCH_ORIGINAL_LEDGER"),
                   independent_review="UNRESOLVED", task_status_changed=False)
    return publish_receipt(receipt_parent, "RESTORE", receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--ledger-sha256", required=True)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--destination", type=Path, default=root / "evidence/runtime")
    parser.add_argument("--receipts", type=Path, default=root / "runtime/audit-artifacts")
    args = parser.parse_args()
    if args.destination.absolute() != (root / "evidence/runtime").absolute():
        parser.error("CLI restoration destination is exactly evidence/runtime")
    if not args.receipts.resolve().is_relative_to(root / "runtime/audit-artifacts"):
        parser.error("receipts must stay within runtime/audit-artifacts")
    try:
        path, checksum = restore(args.archive, args.archive_sha256, args.ledger, args.ledger_sha256,
                                 args.destination, args.receipts)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Restore stopped; existing evidence preserved: {exc}\n")
    print(f"Restore receipt: {path}; SHA-256: {checksum}")


if __name__ == "__main__":
    main()
