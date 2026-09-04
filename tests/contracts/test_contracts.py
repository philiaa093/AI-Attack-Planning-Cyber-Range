import json
import unittest
from pathlib import Path

from scripts.validation.validate_scaffold import validate_shape

ROOT = Path(__file__).resolve().parents[2]


def minimal(schema):
    if "const" in schema: return schema["const"]
    if "enum" in schema: return schema["enum"][0]
    if "oneOf" in schema: return minimal(schema["oneOf"][0])
    if "anyOf" in schema: return minimal(schema["anyOf"][0])
    kind = schema.get("type")
    if isinstance(kind, list): kind = next(item for item in kind if item != "null")
    if kind == "object":
        return {key: minimal(value) for key, value in schema.get("properties", {}).items() if key in schema.get("required", [])}
    if kind == "array": return [minimal(schema.get("items", {}))] if schema.get("minItems", 0) else []
    if kind == "string":
        pattern = schema.get("pattern", "")
        examples = {
            "^SCN-[0-9]{3}$": "SCN-001",
            "^lab-[a-z0-9-]+$": "lab-clean-001",
            "^ACTION-[A-Z]+-[0-9]{3}$": "ACTION-RECON-001",
            "^EV-[A-Za-z0-9._-]+$": "EV-001",
            "^EXP-[0-9]{4}$": "EXP-0001",
            "^[a-f0-9]{64}$": "0" * 64,
        }
        return "2026-01-01T00:00:00Z" if schema.get("format") == "date-time" else ("x" if not pattern else examples.get(pattern, "x"))
    if kind == "integer" or kind == "number": return schema.get("minimum", 0)
    if kind == "boolean": return True
    return None


class ContractTests(unittest.TestCase):
    def test_all_ten_schemas_are_closed_objects(self):
        schemas = list((ROOT / "agent/planner/contracts").glob("*.schema.json"))
        self.assertEqual(len(schemas), 10)
        for path in schemas:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["type"], "object")
            self.assertIs(schema["additionalProperties"], False)

    def test_unknown_property_rejected(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {}, "required": []}
        self.assertTrue(validate_shape({"unexpected": True}, schema))

    def test_each_schema_accepts_generated_minimal_fixture(self):
        for path in (ROOT / "agent/planner/contracts").glob("*.schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(schema=path.name):
                self.assertEqual(validate_shape(minimal(schema), schema), [])

    def test_each_schema_rejects_unknown_property(self):
        for path in (ROOT / "agent/planner/contracts").glob("*.schema.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            value = minimal(schema)
            value["unexpected"] = True
            with self.subTest(schema=path.name):
                self.assertTrue(validate_shape(value, schema))

    def test_one_of_requires_exactly_one_branch(self):
        schema = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertEqual(validate_shape("x", schema), [])
        self.assertTrue(validate_shape(True, schema))

    def test_any_of_accepts_matching_branch(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        self.assertEqual(validate_shape(None, schema), [])

    def test_numeric_and_string_bounds(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 3}, "s": {"type": "string", "pattern": "[a-z]+"}}, "required": ["n", "s"]}
        self.assertTrue(validate_shape({"n": 0, "s": "BAD"}, schema))

    def test_non_finite_numbers_are_rejected(self):
        schema = {"type": "number", "minimum": 0, "maximum": 1}
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.assertIn("$: number must be finite", validate_shape(value, schema))

    def test_utc_date_time_required(self):
        schema = {"type": "string", "format": "date-time"}
        self.assertEqual(validate_shape("2026-01-01T00:00:00Z", schema), [])
        self.assertTrue(validate_shape("2026-01-01T00:00:00+01:00", schema))

    def test_planner_visible_facts_are_closed(self):
        for name, array_field in (("state", "observed_facts"), ("observation", "new_facts")):
            schema = json.loads((ROOT / f"agent/planner/contracts/{name}.schema.json").read_text(encoding="utf-8"))
            value = minimal(schema)
            fact_schema = schema["$defs"]["fact"]
            fact = minimal(fact_schema)
            value[array_field] = [fact]
            self.assertEqual(validate_shape(value, schema), [])
            for forbidden in ("ground_truth", "truth_records", "truth", "expected_detection"):
                mutated = json.loads(json.dumps(value))
                mutated[array_field][0][forbidden] = True
                with self.subTest(schema=name, field=forbidden):
                    self.assertTrue(validate_shape(mutated, schema))

    def test_evidence_schema_accepts_governance_metadata(self):
        schema = json.loads((ROOT / "agent/planner/contracts/evidence.schema.json").read_text(encoding="utf-8"))
        record = {
            "evidence_id": "EV-FOUNDATION-001",
            "run_id": "FOUNDATION-001",
            "path": "evidence/foundation/FOUNDATION-001/validator.txt",
            "sha256": "0" * 64,
            "created_at_utc": "2026-08-29T00:00:00Z",
            "source": "VALIDATOR",
            "redacted": True,
            "expected_state": "validator exits 0",
            "observed_state": "validator exited 0",
            "derived_from": [],
        }
        self.assertEqual(validate_shape(record, schema), [])
        record["unexpected"] = True
        self.assertTrue(validate_shape(record, schema))


if __name__ == "__main__":
    unittest.main()
