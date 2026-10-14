"""Bounded, read-only evidence checks for dashboard history.

Integrity here means record schemas, run identity, payload hashes and references.
It does not certify provider execution, policy adherence or experiment equivalence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

from scripts.validation.validate_scaffold import ROOT, validate_shape

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_PACKAGE_FILES = 1024


def _link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def no_link_ancestors(path: Path) -> None:
    """Reject links on the lexical path before any resolve loses that identity."""
    path = Path(path).absolute()
    if any(_link(part) for part in (path, *path.parents)):
        raise ValueError("linked history entry")


def bounded_bytes(path: Path, root: Path) -> bytes:
    """Only read regular files contained in a trusted root, without link traversal."""
    path, root = Path(path).absolute(), Path(root).absolute()
    no_link_ancestors(root)
    no_link_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("file outside history root")
    current = path
    while current != root:
        if _link(current):
            raise ValueError("linked history entry")
        current = current.parent
        if current == current.parent and current != root:
            raise ValueError("file outside history root")
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("invalid or oversized history file")
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("oversized history file")
    return data


def read_object(path: Path, root: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate history field")
            result[key] = value
        return result

    value = json.loads(bounded_bytes(path, root), object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if type(value) is not dict:
        raise ValueError("history object required")
    return value


@dataclass(frozen=True)
class IntegritySummary:
    state: str
    record_count: int
    verified_count: int | None


def verify_records(directory: Path, run_id: str) -> IntegritySummary:
    records = sorted(directory.glob("record-*.json"))
    if not records:
        return IntegritySummary("NOT_VERIFIED", 0, None)
    try:
        no_link_ancestors(directory)
        # Bound the complete tree before accepting any package-level result.
        count = total = 0
        for path in directory.rglob("*"):
            count += 1
            if count > MAX_PACKAGE_FILES or _link(path):
                raise ValueError("invalid evidence tree")
            if path.is_file():
                total += path.stat().st_size
                if total > MAX_PACKAGE_BYTES:
                    raise ValueError("oversized evidence tree")
        schema = json.loads((ROOT / "agent/planner/contracts/evidence.schema.json").read_text("utf-8"))
        ids = set()
        references = []
        for path in records:
            record = read_object(path, directory)
            if validate_shape(record, schema) or record.get("run_id") != run_id or record.get("redacted") is not True:
                raise ValueError("invalid evidence record")
            timestamp = record["created_at_utc"]
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if not timestamp.endswith("Z") or parsed.utcoffset() != timedelta(0):
                raise ValueError("UTC evidence timestamp required")
            identity = record["evidence_id"]
            if identity in ids:
                raise ValueError("duplicate evidence identity")
            ids.add(identity)
            payload = Path(record["path"])
            payload = payload if payload.is_absolute() else ROOT / payload
            data = bounded_bytes(payload, directory)
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("evidence digest mismatch")
            references.extend(record.get("derived_from", []))
        if any(ref not in ids for ref in references):
            raise ValueError("missing evidence reference")
        return IntegritySummary("VERIFIED", len(records), len(ids))
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return IntegritySummary("FAILED", len(records), None)
