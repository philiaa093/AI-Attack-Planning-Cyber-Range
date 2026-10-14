"""Bounded in-memory Nuclei report import; never runs a scanner.

Only an HTTP JSONL subset is supported. The explicit offline template manifest
classifies reports; it does not authorize scanner execution.
"""

import json
import math
import re
from urllib.parse import urlsplit

from tools.adapters.base import build_scanner_result, validate_target

MAX_JSON_BYTES = 1024 * 1024
MAX_DEPTH = 16
MAX_RECORDS = 1000
MAX_URI_CHARS = 2048
MAX_TEMPLATES = 100
FINDING_TYPES = frozenset({"sqli", "xss", "path-traversal"})
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
_SEVERITIES = frozenset({"info", "low", "medium", "high", "critical", "unknown"})


def validate_lab_target(target_id):
    if type(target_id) is not str or not re.fullmatch(r"lab-[a-z0-9-]+", target_id):
        raise ValueError("Invalid lab target")
    try:
        validate_target(target_id)
    except ValueError:
        raise ValueError("Target is not allowlisted") from None


def validate_template_manifest(allowed_templates):
    """Copy exact ID -> family mappings; empty by default, no bundled templates."""
    if allowed_templates is None:
        return {}
    if type(allowed_templates) is not dict or len(allowed_templates) > MAX_TEMPLATES:
        raise ValueError("Invalid offline template manifest")
    for template_id, family in allowed_templates.items():
        if (type(template_id) is not str or not _ID.fullmatch(template_id)
                or type(family) is not str or family not in FINDING_TYPES):
            raise ValueError("Invalid offline template manifest entry")
    return dict(allowed_templates)


def _check_json(value):
    """Bound JSON shape/bytes, including fields that will be discarded."""
    remaining = MAX_JSON_BYTES
    ancestors = set()

    def charge(size):
        nonlocal remaining
        remaining -= size
        if remaining < 0:
            raise ValueError("Report exceeds byte limit")

    def walk(item, depth):
        if depth > MAX_DEPTH:
            raise ValueError("Report exceeds depth limit")
        kind = type(item)
        if kind is str:
            charge(2)
            for char in item:
                number = ord(char)
                if 0xD800 <= number <= 0xDFFF:
                    raise ValueError("Invalid report Unicode")
                if char in '\"\\':
                    size = 2
                elif number < 32:
                    size = 2 if char in '\b\f\n\r\t' else 6
                else:
                    size = 1 if number < 128 else 2 if number < 2048 else 3 if number < 65536 else 4
                charge(size)
        elif kind in (dict, list):
            if id(item) in ancestors:
                raise ValueError("Cyclic report")
            ancestors.add(id(item))
            charge(2 + max(0, len(item) - 1))
            for key, child in item.items() if kind is dict else enumerate(item):
                if kind is dict:
                    if type(key) is not str:
                        raise ValueError("JSON keys must be strings")
                    walk(key, depth + 1)
                    charge(1)
                walk(child, depth + 1)
            ancestors.remove(id(item))
        elif item is None or kind is bool:
            charge(len(json.dumps(item)))
        elif kind in (int, float):
            if kind is float and not math.isfinite(item):
                raise ValueError("Non-finite report number")
            if kind is int and item.bit_length() > 4096:
                raise ValueError("Report number exceeds limit")
            charge(len(str(item)))
        else:
            raise ValueError("Report must contain plain JSON data")

    walk(value, 0)


def _origin(uri, target_id):
    if type(uri) is not str or not 1 <= len(uri) <= MAX_URI_CHARS:
        raise ValueError("Invalid report URI")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in uri) or '\\' in uri:
        raise ValueError("Ambiguous report URI")
    try:
        parts = urlsplit(uri)
        if (parts.scheme not in ("http", "https")
                or not re.fullmatch(r"lab-[a-z0-9-]+(?::[1-9][0-9]{0,4})?", parts.netloc, re.IGNORECASE)
                or parts.hostname != target_id):
            raise ValueError
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise ValueError("Report URI is outside the declared lab target") from None
    return parts.scheme, port


def parse_nuclei_results(nuclei_output, target_id, *, allowed_templates=None):
    """Validate ALL records before returning minimized, unconfirmed candidates.

    confidence=0.0 means not assessed, not a negative finding or calibrated
    probability. Endpoint identity and provenance remain unresolved here.
    """
    validate_lab_target(target_id)
    manifest = validate_template_manifest(allowed_templates)
    if type(nuclei_output) is not list or len(nuclei_output) > MAX_RECORDS:
        raise ValueError("Report must be a bounded list of records")
    _check_json(nuclei_output)
    results = []
    report_origin = None
    for item in nuclei_output:
        if type(item) is not dict:
            raise ValueError("Report record must be an object")
        template_id = item.get("template-id")
        if type(template_id) is not str or template_id not in manifest:
            raise ValueError("Report template ID is not allowlisted")
        if item.get("type") != "http" or type(item.get("matcher-status")) is not bool:
            raise ValueError("Unsupported protocol or missing matcher status")
        if "error" in item and (type(item["error"]) is not str or item["error"]):
            raise ValueError("Report record contains a tool error")
        if "severity" in item or "tags" in item:
            raise ValueError("Unsupported legacy or ambiguous report metadata")
        info = item.get("info")
        if (type(info) is not dict or type(info.get("severity")) is not str
                or info["severity"] not in _SEVERITIES):
            raise ValueError("Invalid report info")
        tags = info.get("tags", [])
        if type(tags) is not list or any(type(tag) is not str for tag in tags):
            raise ValueError("Invalid report tags")
        origin = _origin(item.get("host"), target_id)
        if _origin(item.get("matched-at"), target_id) != origin:
            raise ValueError("Inconsistent report origins")
        if report_origin is not None and origin != report_origin:
            raise ValueError("Mixed report origins")
        report_origin = origin
        if "url" in item and _origin(item["url"], target_id) != origin:
            raise ValueError("Inconsistent report URL")
        # Failed matchers are scope-validated too. Raw fields never leave parser.
        if item["matcher-status"]:
            results.append(build_scanner_result(
                "NUCLEI", target_id, manifest[template_id], 0.0, endpoint_id=None,
            ))
    return results


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant")


def parse_nuclei_jsonl(text, target_id, *, allowed_templates=None):
    """Import JSONL already in memory; never treats text as a file path."""
    validate_lab_target(target_id)
    manifest = validate_template_manifest(allowed_templates)
    if type(text) is not str or len(text) > MAX_JSON_BYTES:
        raise ValueError("Invalid or oversized JSONL text")
    try:
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            raise ValueError
    except (UnicodeError, ValueError):
        raise ValueError("Invalid or oversized JSONL text") from None
    records = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        if len(records) >= MAX_RECORDS:
            raise ValueError("JSONL exceeds record limit")
        try:
            item = json.loads(line, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            raise ValueError("Malformed JSONL record") from None
        records.append(item)
    return parse_nuclei_results(records, target_id, allowed_templates=manifest)
