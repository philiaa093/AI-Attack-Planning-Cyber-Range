"""Bounded, append-only artifact helpers for restore/reconcile/review preparation."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path, PurePosixPath

from runtime.evaluation.usage_costs import canonical, load_json_bytes, no_links, sha

FILE_LIMIT = 16 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", re.I)


def digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("externally pinned lowercase SHA-256 required")
    return value


def safe_relative(value):
    if type(value) is not str or not 1 <= len(value) <= 240:
        raise ValueError("bounded relative path required")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or len(path.parts) > 8:
        raise ValueError("noncanonical archive path")
    for part in path.parts:
        if (part in (".", "..") or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", part)
                or part.endswith(".") or _RESERVED.fullmatch(part)):
            raise ValueError("unsafe path, Windows device/ADS or traversal")
    return value


def bounded_read(path, limit=FILE_LIMIT):
    path = Path(path).absolute()
    no_links(path)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("artifact exceeds resource limit")
    return data


def pinned_read(path, expected_sha256, limit=FILE_LIMIT):
    digest(expected_sha256)
    data = bounded_read(path, limit)
    if sha(data) != expected_sha256:
        raise ValueError("pinned artifact hash mismatch")
    return data


def pinned_json(path, expected_sha256):
    return load_json_bytes(pinned_read(path, expected_sha256))


def exclusive_bytes(path, data):
    path = Path(path).absolute()
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    no_links(path)
    with path.open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    if bounded_read(path, max(FILE_LIMIT, len(data))) != data:
        raise ValueError("published artifact differs; retained for inspection")
    return dict(name=path.name, sha256=sha(data))


def publish_receipt(parent, prefix, document):
    parent = Path(parent).absolute()
    no_links(parent)
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / (prefix + "-" + uuid.uuid4().hex)
    directory.mkdir(exist_ok=False)
    path = directory / "receipt.json"
    ref = exclusive_bytes(path, canonical(document))
    return path, ref["sha256"]


def closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("closed artifact schema required")
    return value


def version_one(value):
    if type(value) is not int or value != 1:
        raise ValueError("schema version 1 required")
