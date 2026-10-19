import json
import unittest
from pathlib import Path

from scripts.validation.validate_scaffold import validate_shape
from shared import schema_validation

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
    def test_legacy_validator_exports_share_implementation(self):
        from scripts.validation import validate_scaffold
        for name in ("_actual_type", "_format_errors", "_resolve_ref", "validate_shape"):
            with self.subTest(name=name):
                self.assertIs(getattr(validate_scaffold, name), getattr(schema_validation, name))

    def test_planner_catalog_imports_share_legacy_metadata(self):
        from agent.planner.action_catalog import ACTION_CATALOG
        from agent.planner.llm import planner
        from runtime.planners import observed_planner
        self.assertIs(planner.ACTION_CATALOG, ACTION_CATALOG)
        self.assertIs(observed_planner.ACTION_CATALOG, ACTION_CATALOG)
        self.assertEqual(len(ACTION_CATALOG), 13)
        self.assertEqual(ACTION_CATALOG["ACTION-SCAN-002"], {"name": "ACTIVE_WEB_SCAN", "class": "SCAN"})
        self.assertEqual(ACTION_CATALOG["ACTION-WEB-003"], {"name": "TEST_PATH_TRAVERSAL", "class": "WEB_TEST"})

    def test_boolean_is_not_a_schema_integer(self):
        self.assertEqual(validate_shape(True, {"type": "integer"}),
                         ["$: expected ['integer'], got boolean"])
        self.assertEqual(validate_shape(1, {"type": "number"}), [])

    def test_local_refs_preserve_paths_and_missing_ref_exception(self):
        schema = {"$defs": {"count": {"type": "integer", "minimum": 1}},
                  "type": "object", "properties": {"count": {"$ref": "#/$defs/count"}}}
        self.assertEqual(validate_shape({"count": 0}, schema), ["$.count: below minimum"])
        with self.assertRaises(KeyError):
            validate_shape(1, {"$ref": "#/$defs/missing", "$defs": {}})
        self.assertEqual(validate_shape(None, False), [])

    def test_closed_object_error_order_and_array_bounds(self):
        schema = {"type": "object", "required": ["z", "a"], "additionalProperties": False,
                  "properties": {"n": {"type": "integer", "maximum": 2}}}
        self.assertEqual(validate_shape({"z_extra": 1, "b_extra": 2, "n": 3}, schema),
                         ["$: missing required a", "$: missing required z",
                          "$: unknown property b_extra", "$: unknown property z_extra",
                          "$.n: above maximum"])
        self.assertEqual(validate_shape([1, 1], {"type": "array", "maxItems": 1, "uniqueItems": True}),
                         ["$: more than maxItems", "$: duplicate items"])
        self.assertEqual(validate_shape([], {"type": "array", "minItems": 1}), ["$: fewer than minItems"])

    def test_branch_subset_preserves_exact_matches_and_early_return(self):
        self.assertEqual(validate_shape(1, {"oneOf": [{"type": "number"}, {"type": "integer"}]}),
                         ["$: oneOf mismatch"])
        self.assertEqual(validate_shape(False, {"anyOf": [{"type": "string"}, {"type": "null"}]}),
                         ["$: anyOf mismatch"])
        # Existing subset returns after branches, before evaluating sibling keywords.
        self.assertEqual(validate_shape("x", {"anyOf": [{"type": "string"}], "minLength": 2}), [])

    def _all_contract_schemas(self):
        planner_schemas = sorted((ROOT / "agent/planner/contracts").glob("*.schema.json"))
        evaluation_schema = ROOT / "evaluation/ground_truth/ground-truth.schema.json"
        return planner_schemas, evaluation_schema

    def test_all_ten_schemas_are_closed_objects(self):
        planner_schemas, evaluation_schema = self._all_contract_schemas()
        self.assertEqual(len(planner_schemas), 9)
        self.assertFalse((ROOT / "agent/planner/contracts/ground-truth.schema.json").exists())
        self.assertTrue(evaluation_schema.is_file())
        for path in planner_schemas + [evaluation_schema]:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["type"], "object")
            self.assertIs(schema["additionalProperties"], False)

    def test_unknown_property_rejected(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {}, "required": []}
        self.assertTrue(validate_shape({"unexpected": True}, schema))

    def test_each_schema_accepts_generated_minimal_fixture(self):
        planner_schemas, evaluation_schema = self._all_contract_schemas()
        for path in planner_schemas + [evaluation_schema]:
            schema = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(schema=path.name):
                self.assertEqual(validate_shape(minimal(schema), schema), [])

    def test_each_schema_rejects_unknown_property(self):
        planner_schemas, evaluation_schema = self._all_contract_schemas()
        for path in planner_schemas + [evaluation_schema]:
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

    def test_discovery_observation_accepts_structured_facts(self):
        schema = json.loads((ROOT / "agent/planner/contracts/observation.schema.json").read_text(encoding="utf-8"))
        observation = {
            "observation_id": "OBS-DISCOVERY-001",
            "run_id": "RUN-DISCOVERY-001",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2026-08-29T00:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-SERVICE-001",
                "fact_type": "SERVICE",
                "subject": "target.example",
                "value": "https",
                "confidence": 0.95,
            }],
            "evidence_refs": ["EV-DISCOVERY-001"],
        }
        self.assertEqual(validate_shape(observation, schema), [])

        for mutation in (
            lambda fact: fact.pop("fact_id"),
            lambda fact: fact.pop("confidence"),
            lambda fact: fact.update(fact_type="NOT_A_FACT_TYPE"),
        ):
            invalid = json.loads(json.dumps(observation))
            mutation(invalid["new_facts"][0])
            with self.subTest(mutation=mutation):
                self.assertTrue(validate_shape(invalid, schema))

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

    def test_enterprise_observation_schema_vocabulary_and_provenance(self):
        schema = json.loads((ROOT / "agent/planner/contracts/observation.schema.json").read_text(encoding="utf-8"))
        fact_types = schema["$defs"]["fact"]["properties"]["fact_type"]["enum"]
        expected_types = [
            "TARGET", "HOST", "SERVICE", "ENDPOINT", "PARAMETER",
            "CANDIDATE_FINDING", "CONFIRMED_FINDING", "ACCESS", "CREDENTIAL",
            "SESSION", "REACHABILITY", "ACTION_OUTCOME", "DETECTION_SIGNAL",
            "OBJECTIVE", "CONTROL"
        ]
        self.assertEqual(sorted(fact_types), sorted(expected_types))

        # Check full provenance properties exist in schema
        for prop in ("source_kind", "source_target", "source_session", "confidence", "sequence_num", "evidence_refs"):
            self.assertIn(prop, schema["properties"])


if __name__ == "__main__":
    unittest.main()
