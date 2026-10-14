"""Bounded, offline Nuclei report normalization. No execution or evidence writes."""

import hashlib
import json
import math
import re
from datetime import datetime
from urllib.parse import urlsplit

from tools.parsers.nuclei_parser import (
    parse_nuclei_results, validate_lab_target, validate_template_manifest,
)

from .observation_normalizer import _make_fact_id

MAX_BYTES = 1_048_576
MAX_RECORDS = 1000
MAX_DEPTH = 16
MAX_NODES = 50_000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_TARGET = re.compile(r"lab-[a-z0-9-]+")
_EVIDENCE = re.compile(r"EV-[A-Za-z0-9._-]{1,125}")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
_FIELDS = {
    "schema_version", "source", "report_id", "run_id", "action_id", "target_id",
    "timestamp_utc", "status", "evidence_refs",
}
_OUTCOMES = {
    "SUCCESS": "PARTIAL", "PARTIAL": "PARTIAL", "FAILURE": "FAILURE",
    "DENIED": "DENIED", "ERROR": "ERROR", "TIMEOUT": "ERROR",
}
_FAMILIES = frozenset({"sqli", "xss", "path-traversal"})


class NormalizationError(ValueError):
    """Static error codes keep untrusted data out of exception text."""


def _require(condition, code):
    if not condition:
        raise NormalizationError(code)


def _token(value, pattern=_ID):
    return type(value) is str and pattern.fullmatch(value) is not None


def _bounded_json(value):
    """Validate the JSON tree before serialization, including cycles and size."""
    nodes = 0
    estimated_bytes = 0

    def visit(item, depth):
        nonlocal nodes, estimated_bytes
        nodes += 1
        estimated_bytes += 1
        _require(nodes <= MAX_NODES and depth <= MAX_DEPTH, "INPUT_COMPLEXITY")
        kind = type(item)
        if kind is dict:
            for key, child in item.items():
                _require(type(key) is str, "NON_JSON_INPUT")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif kind is list:
            for child in item:
                visit(child, depth + 1)
        elif kind is str:
            _require(len(item) <= MAX_BYTES, "INPUT_TOO_LARGE")
            try:
                estimated_bytes += len(item.encode("utf-8"))
            except UnicodeError:
                raise NormalizationError("NON_JSON_INPUT") from None
        elif kind is int:
            _require(item.bit_length() <= 1024, "INPUT_COMPLEXITY")
        elif kind is float:
            _require(math.isfinite(item), "NON_JSON_INPUT")
        else:
            _require(item is None or kind is bool, "NON_JSON_INPUT")
        _require(estimated_bytes <= MAX_BYTES, "INPUT_TOO_LARGE")

    visit(value, 0)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    _require(len(encoded) <= MAX_BYTES, "INPUT_TOO_LARGE")
    return encoded


def _sha(encoded):
    return hashlib.sha256(encoded).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise NormalizationError("NON_JSON_INPUT")


def _load(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=_invalid_constant)
    except NormalizationError:
        raise
    except (ValueError, RecursionError):
        raise NormalizationError("INVALID_RAW_JSON") from None


def _records(raw):
    if type(raw) is str:
        stripped = raw.strip()
        if not stripped:
            records = []
        elif stripped.startswith("["):
            records = _load(stripped)
        else:
            records = []
            for line in stripped.split("\n"):
                if line.strip():
                    _require(len(records) < MAX_RECORDS, "TOO_MANY_RECORDS")
                    records.append(_load(line))
    else:
        records = raw
    _require(type(records) is list, "INVALID_RAW_OUTPUT")
    _require(len(records) <= MAX_RECORDS, "TOO_MANY_RECORDS")
    _bounded_json(records)
    _require(all(type(item) is dict for item in records), "INVALID_RECORD")
    return records


def _origin(value):
    """No DNS lookup, URL following, credentials, or ambiguous URL syntax."""
    _require(type(value) is str and 0 < len(value) <= 2048, "INVALID_ORIGIN")
    _require(not any(ord(c) <= 32 or ord(c) >= 127 for c in value), "INVALID_ORIGIN")
    _require("\\" not in value, "INVALID_ORIGIN")
    try:
        parts = urlsplit(value)
        _require(parts.scheme in {"http", "https"} and parts.hostname is not None,
                 "INVALID_ORIGIN")
        _require("%" not in parts.netloc, "INVALID_ORIGIN")
        _require(parts.username is None and parts.password is None, "INVALID_ORIGIN")
        _require(_token(parts.hostname, _TARGET), "INVALID_ORIGIN")
        port = parts.port
        _require(port is None or 1 <= port <= 65535, "INVALID_ORIGIN")
        _require(not parts.netloc.endswith(":"), "INVALID_ORIGIN")
    except (ValueError, IndexError):
        raise NormalizationError("INVALID_ORIGIN") from None
    return (parts.scheme, parts.hostname, port or (443 if parts.scheme == "https" else 80)), parts


def normalize_nuclei_report(envelope, *, allowed_target_ids, target_origin,
                           template_families):
    """Return canonical observation plus a minimized audit sidecar.

    Scope arguments come from the trusted importer, never the raw report.
    This validates report scope; it grants no permission to execute any action.
    """
    input_bytes = _bounded_json(envelope)
    _require(type(envelope) is dict, "INVALID_ENVELOPE")
    payload_fields = set(envelope) - _FIELDS
    _require(payload_fields in ({"raw_output"}, {"scanner_results"})
             and _FIELDS <= set(envelope), "INVALID_ENVELOPE")
    raw_mode = "raw_output" in envelope
    _require(envelope["schema_version"] == "1.0" and envelope["source"] == "NUCLEI",
             "UNSUPPORTED_INTERFACE")
    _require(_token(envelope["report_id"]) and _token(envelope["run_id"]), "INVALID_ID")
    _require(envelope["action_id"] == "ACTION-SCAN-002", "INVALID_ACTION")
    target_id = envelope["target_id"]
    _require(_token(target_id, _TARGET), "INVALID_TARGET")
    _require(type(allowed_target_ids) in {list, tuple, set, frozenset}
             and all(_token(item, _TARGET) for item in allowed_target_ids), "INVALID_SCOPE")
    _require(target_id in allowed_target_ids, "TARGET_OUT_OF_SCOPE")
    try:
        validate_lab_target(target_id)
        manifest = validate_template_manifest(template_families)
    except ValueError:
        raise NormalizationError("INVALID_CANONICAL_SCOPE") from None
    expected_origin, parsed_origin = _origin(target_origin)
    _require(expected_origin[1] == target_id and parsed_origin.path in {"", "/"}
             and not parsed_origin.query and not parsed_origin.fragment, "INVALID_SCOPE")
    timestamp = envelope["timestamp_utc"]
    _require(type(timestamp) is str and _UTC.fullmatch(timestamp) is not None, "INVALID_TIMESTAMP")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise NormalizationError("INVALID_TIMESTAMP") from None
    status = envelope["status"]
    _require(type(status) is str and status in _OUTCOMES, "INVALID_STATUS")
    refs = envelope["evidence_refs"]
    _require(type(refs) is list and len(refs) <= 64
             and all(_token(ref, _EVIDENCE) for ref in refs), "INVALID_EVIDENCE_REFS")
    _require(len(set(refs)) == len(refs), "INVALID_EVIDENCE_REFS")
    payload = envelope["raw_output" if raw_mode else "scanner_results"]
    _require(type(payload) in ({list, str} if raw_mode else {list}), "INVALID_RAW_OUTPUT")
    records = _records(payload)
    _require(not records or status in {"SUCCESS", "PARTIAL"}, "STATUS_RECORD_CONFLICT")
    if raw_mode:
        try:
            # Share TASK-017's exact template/metadata/matcher validation.
            parse_nuclei_results(records, target_id, allowed_templates=manifest)
        except ValueError:
            raise NormalizationError("INVALID_NUCLEI_RECORDS") from None

    facts = {}
    record_sources = []
    matched_count = 0
    for index, item in enumerate(records):
        if raw_mode:
            for field in ("host", "matched-at", "url"):
                if field in item:
                    actual_origin, _ = _origin(item[field])
                    _require(actual_origin == expected_origin, "RECORD_OUT_OF_SCOPE")
            template_id = item["template-id"]
            matched = item["matcher-status"]
            family = manifest[template_id]
        else:
            _require(set(item) == {"source", "target_id", "endpoint_id", "finding_type", "confidence"},
                     "INVALID_SCANNER_RESULT")
            _require(item["source"] == "NUCLEI" and item["target_id"] == target_id
                     and item["endpoint_id"] is None, "INVALID_SCANNER_RESULT")
            _require(type(item["finding_type"]) is str and item["finding_type"] in _FAMILIES
                     and type(item["confidence"]) in {int, float} and item["confidence"] == 0.0,
                     "INVALID_SCANNER_RESULT")
            template_id, matched, family = None, True, item["finding_type"]
        fact_id = None
        if matched:
            matched_count += 1
            fact_id = _make_fact_id("CANDIDATE_FINDING", target_id, family)
            facts.setdefault(fact_id, {
                "fact_id": fact_id, "fact_type": "CANDIDATE_FINDING", "subject": target_id,
                "value": family, "confidence": 0.0,
            })
        record_sources.append({
            "record_index": index, "record_sha256": _sha(_bounded_json(item)),
            "template_id": template_id, "matcher_status": matched, "fact_id": fact_id,
        })

    # Include trusted interpretation in identity to prevent conflicting replay.
    interpretation = {
        "input_sha256": _sha(input_bytes), "normalizer_version": "1.0",
        "origin": list(expected_origin), "template_families": manifest if raw_mode else {},
    }
    observation_id = "OBS-NORM-" + _sha(_bounded_json(interpretation))
    return {
        "schema_version": "1.0",
        "observation": {
            "observation_id": observation_id, "run_id": envelope["run_id"],
            "action_id": envelope["action_id"], "timestamp_utc": timestamp,
            "outcome": _OUTCOMES[status], "new_facts": list(facts.values()),
            "evidence_refs": list(refs),
        },
        "provenance": {
            "source": "NUCLEI", "report_id": envelope["report_id"],
            "input_kind": "RAW_OUTPUT" if raw_mode else "SCANNER_RESULTS",
            "input_sha256": _sha(input_bytes), "adapter_status": status,
            "normalizer_version": "1.0", "redacted": True,
            "redaction_policy": "metadata-only-v1",
            "confidence_basis": "not-assessed",
            "evidence_status": "REFERENCED_UNVERIFIED" if refs else "UNRESOLVED",
            "input_record_count": len(records), "matched_record_count": matched_count,
            "fact_count": len(facts), "coalesced_record_count": matched_count - len(facts),
            "record_sources": record_sources,
        },
    }
