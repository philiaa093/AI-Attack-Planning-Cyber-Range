"""Pure validation for the supported JSON Schema subset."""
from __future__ import annotations

import datetime as dt
import json
import math
import re


def _actual_type(value) -> str:
    if value is None: return "null"
    if isinstance(value, bool): return "boolean"
    if isinstance(value, int): return "integer"
    if isinstance(value, float): return "number"
    if isinstance(value, str): return "string"
    if isinstance(value, list): return "array"
    return "object"


def _format_errors(value, schema, path):
    fmt = schema.get("format")
    if fmt != "date-time" or not isinstance(value, str):
        return []
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return [f"{path}: invalid date-time"]
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return [f"{path}: date-time must be UTC"]
    return []


def _resolve_ref(schema, root):
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    if not ref or not ref.startswith("#/"):
        return schema
    value = root
    for part in ref[2:].split("/"):
        value = value[part]
    return value


def validate_shape(value, schema, path="$", _root=None) -> list[str]:
    """Validate supported JSON Schema keywords without imports or network access."""
    if not isinstance(schema, dict):
        return []
    _root = schema if _root is None else _root
    schema = _resolve_ref(schema, _root)
    errors: list[str] = []
    for branch_key in ("oneOf", "anyOf"):
        if branch_key in schema:
            results = [validate_shape(value, branch, path, _root) for branch in schema[branch_key]]
            valid = [result for result in results if not result]
            if branch_key == "oneOf" and len(valid) != 1:
                errors.append(f"{path}: oneOf mismatch")
            elif branch_key == "anyOf" and not valid:
                errors.append(f"{path}: anyOf mismatch")
            return errors
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected]
    if expected is not None:
        actual = _actual_type(value)
        if actual not in types and not (actual == "integer" and "number" in types):
            return [f"{path}: expected {types}, got {actual}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum mismatch")
    errors.extend(_format_errors(value, schema, path))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        errors.extend(f"{path}: missing required {key}" for key in sorted(missing))
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}: unknown property {key}" for key in sorted(set(value) - set(properties)))
        for key, subschema in properties.items():
            if key in value:
                errors.extend(validate_shape(value[key], subschema, f"{path}.{key}", _root))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]: errors.append(f"{path}: fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]: errors.append(f"{path}: more than maxItems")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value): errors.append(f"{path}: duplicate items")
        for index, item in enumerate(value):
            errors.extend(validate_shape(item, schema.get("items", {}), f"{path}[{index}]", _root))
    if isinstance(value, str):
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value): errors.append(f"{path}: pattern mismatch")
        if "minLength" in schema and len(value) < schema["minLength"]: errors.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]: errors.append(f"{path}: longer than maxLength")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            errors.append(f"{path}: number must be finite")
        elif "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        elif "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    return errors
