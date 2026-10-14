"""TASK-017/018 contract checks with offline synthetic metadata only."""

import builtins
import copy
import json
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from agent.perception.normalizers.nuclei_normalizer import NormalizationError
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from tools.adapters.nuclei.adapter import NucleiAdapter

ROOT = Path(__file__).resolve().parents[2]
TARGET = "lab-sqli-001"
MANIFEST = {"fixture-sqli": "sqli", "fixture-xss": "xss", "fixture-path": "path-traversal"}


def record(**changes):
    item = {
        "template-id": "fixture-sqli", "type": "http",
        "host": f"http://{TARGET}", "matched-at": f"http://{TARGET}/observed",
        "matcher-status": True, "info": {"severity": "high", "tags": ["sqli"]},
    }
    item.update(changes)
    return item


def envelope(**changes):
    item = {
        "schema_version": "1.0", "source": "NUCLEI", "report_id": "REPORT-FIXTURE-001",
        "run_id": "RUN-NORMALIZER-001", "action_id": "ACTION-SCAN-002",
        "target_id": TARGET, "timestamp_utc": "2026-10-11T08:00:00Z",
        "status": "SUCCESS", "evidence_refs": [], "raw_output": [record()],
    }
    item.update(changes)
    return item


class NucleiNormalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [
            ROOT / "agent/planner/contracts/observation.schema.json",
            ROOT / "agent/planner/contracts/scanner-result.schema.json",
            ROOT / "agent/perception/normalizers/schemas/nuclei-report.schema.json",
            ROOT / "agent/perception/normalizers/schemas/normalization-result.schema.json",
        ]
        schemas = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        registry = Registry().with_resources(
            (schema["$id"], Resource.from_contents(schema)) for schema in schemas
        )
        for schema in schemas:
            Draft202012Validator.check_schema(schema)
        cls.input_validator = Draft202012Validator(schemas[2], registry=registry, format_checker=FormatChecker())
        cls.output_validator = Draft202012Validator(schemas[3], registry=registry, format_checker=FormatChecker())

    def normalize(self, data=..., **scope):
        options = {
            "allowed_target_ids": {TARGET}, "target_origin": f"http://{TARGET}",
            "template_families": MANIFEST,
        }
        options.update(scope)
        return ObservationNormalizer().normalize_nuclei(envelope() if data is ... else data, **options)

    def test_schema_and_canonical_observation(self):
        data = envelope()
        self.input_validator.validate(data)
        result = self.normalize(data)
        self.output_validator.validate(result)
        fact = result["observation"]["new_facts"][0]
        self.assertEqual((fact["fact_type"], fact["value"], fact["confidence"]),
                         ("CANDIDATE_FINDING", "sqli", 0.0))
        self.assertEqual(result["observation"]["outcome"], "PARTIAL")
        self.assertEqual(result["provenance"]["evidence_status"], "UNRESOLVED")

    def test_task17_import_results_are_accepted_directly(self):
        adapter = NucleiAdapter(allowed_templates=MANIFEST)
        results = adapter.import_report([record(), record()], target_id=TARGET)
        data = envelope()
        del data["raw_output"]
        data["scanner_results"] = results
        self.input_validator.validate(data)
        result = self.normalize(data, template_families={})
        self.output_validator.validate(result)
        self.assertEqual(result["provenance"]["input_kind"], "SCANNER_RESULTS")
        self.assertEqual(result["provenance"]["coalesced_record_count"], 1)
        self.assertEqual(len(result["observation"]["new_facts"]), 1)
        self.assertIsNone(result["provenance"]["record_sources"][0]["template_id"])
        self.assertEqual(result["observation"]["new_facts"],
                         self.normalize(envelope(raw_output=[record(), record()]))["observation"]["new_facts"])

    def test_json_list_array_text_and_jsonl_have_equivalent_facts(self):
        records = [record(), record(**{"template-id": "fixture-xss"})]
        outputs = []
        for raw in (records, json.dumps(records), "\n".join(json.dumps(r) for r in records)):
            with self.subTest(raw_type=type(raw).__name__):
                data = envelope(raw_output=raw)
                self.input_validator.validate(data)
                result = self.normalize(data)
                self.output_validator.validate(result)
                outputs.append(result["observation"]["new_facts"])
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])

    def test_deduplication_preserves_all_record_sources(self):
        result = self.normalize(envelope(raw_output=[record(), record()]))
        sources = result["provenance"]["record_sources"]
        self.assertEqual(len(result["observation"]["new_facts"]), 1)
        self.assertEqual([source["record_index"] for source in sources], [0, 1])
        self.assertEqual(sources[0]["fact_id"], sources[1]["fact_id"])

    def test_failed_matcher_is_validated_and_linked_without_fact(self):
        result = self.normalize(envelope(raw_output=[record(**{"matcher-status": False})]))
        self.output_validator.validate(result)
        self.assertEqual(result["observation"]["new_facts"], [])
        self.assertIsNone(result["provenance"]["record_sources"][0]["fact_id"])
        bad = record(**{"matcher-status": False, "matched-at": "http://lab-clean-001/observed"})
        with self.assertRaises(NormalizationError):
            self.normalize(envelope(raw_output=[bad]))

    def test_redaction_and_input_preservation(self):
        data = envelope(raw_output=[record(**{
            "matched-at": f"http://{TARGET}/PRIVATE_SENTINEL?token=PRIVATE_SENTINEL#PRIVATE_SENTINEL",
            "request": "PRIVATE_SENTINEL", "response": "PRIVATE_SENTINEL",
            "extracted-results": ["PRIVATE_SENTINEL"],
            "info": {"severity": "critical", "name": "PRIVATE_SENTINEL", "tags": ["PRIVATE_SENTINEL"]},
        })])
        before = copy.deepcopy(data)
        result = self.normalize(data)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))
        self.assertEqual(before, data)
        result["observation"]["evidence_refs"].append("EV-EDIT")
        self.assertEqual(data["evidence_refs"], [])

    def test_deterministic_replay_and_unique_report_identity(self):
        first = self.normalize()
        self.assertEqual(first, self.normalize())
        changed = self.normalize(envelope(report_id="REPORT-FIXTURE-002"))
        self.assertNotEqual(first["observation"]["observation_id"], changed["observation"]["observation_id"])
        self.assertEqual(first["observation"]["new_facts"], changed["observation"]["new_facts"])
        interpreted = self.normalize(template_families={"fixture-sqli": "xss"})
        self.assertNotEqual(first["observation"]["observation_id"], interpreted["observation"]["observation_id"])

    def test_key_order_does_not_change_identity(self):
        data = envelope()
        self.assertEqual(self.normalize(data), self.normalize(dict(reversed(list(data.items())))))

    def test_outcomes_do_not_depend_on_finding_count(self):
        expected = {"SUCCESS": "PARTIAL", "PARTIAL": "PARTIAL", "FAILURE": "FAILURE",
                    "DENIED": "DENIED", "ERROR": "ERROR", "TIMEOUT": "ERROR"}
        for status, outcome in expected.items():
            with self.subTest(status=status):
                data = envelope(status=status, raw_output=[])
                self.input_validator.validate(data)
                result = self.normalize(data)
                self.output_validator.validate(result)
                self.assertEqual(result["observation"]["outcome"], outcome)
                self.assertEqual(result["provenance"]["adapter_status"], status)
                self.assertEqual(result["observation"]["new_facts"], [])

    def test_failure_records_are_rejected_all_or_nothing(self):
        for status in ("FAILURE", "DENIED", "ERROR", "TIMEOUT"):
            with self.subTest(status=status), self.assertRaises(NormalizationError):
                self.normalize(envelope(status=status))

    def test_metadata_and_exact_envelope_validation(self):
        changes = [
            {"schema_version": "2.0"}, {"source": "ZAP"}, {"report_id": ""},
            {"run_id": None}, {"action_id": "ACTION-SCAN-001"}, {"status": []},
            {"timestamp_utc": "2026-02-30T08:00:00Z"},
            {"timestamp_utc": "2026-10-11T08:00:00+07:00"},
            {"evidence_refs": ["EV-"]}, {"evidence_refs": ["EV-A", "EV-A"]},
            {"approval": True}, {"scanner_results": []}, {"raw_output": None},
        ]
        for fields in changes:
            with self.subTest(fields=fields), self.assertRaises(NormalizationError):
                self.normalize(envelope(**fields))
        for data in (None, [], {}, "text"):
            with self.subTest(data=data), self.assertRaises(NormalizationError):
                self.normalize(data)

    def test_target_and_template_scope_fail_closed(self):
        for scope in ({"allowed_target_ids": set()}, {"allowed_target_ids": TARGET},
                      {"target_origin": "http://lab-clean-001"}, {"template_families": {}},
                      {"template_families": {"fixture-sqli": "unsupported"}},
                      {"target_origin": f"http://{TARGET}/observed"}):
            with self.subTest(scope=scope), self.assertRaises(NormalizationError):
                self.normalize(**scope)
        with self.assertRaises(NormalizationError):
            self.normalize(envelope(target_id="lab-unregistered-001"),
                           allowed_target_ids={"lab-unregistered-001"}, target_origin="http://lab-unregistered-001")

    def test_trusted_origin_is_enforced_even_for_failed_matcher(self):
        for uri in (f"https://{TARGET}/observed", f"http://{TARGET}:8080/observed",
                    f"http://user@{TARGET}/observed", f"http://{TARGET}:/observed",
                    f"http://{TARGET}./observed", "/observed", "bad", f"http://{TARGET}/bad\n"):
            with self.subTest(uri=uri), self.assertRaises(NormalizationError):
                self.normalize(envelope(raw_output=[record(**{"matched-at": uri, "matcher-status": False})]))

    def test_task17_record_validation_is_shared(self):
        for fields in ({"matcher-status": 1}, {"type": "dns"}, {"info": {}},
                       {"severity": "high"}, {"error": "PRIVATE_SENTINEL"},
                       {"template-id": "not-allowlisted"}):
            with self.subTest(fields=fields), self.assertRaises(NormalizationError) as raised:
                self.normalize(envelope(raw_output=[record(), record(**fields)]))
            self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))

    def test_confidence_stays_unassessed_regardless_of_severity(self):
        for severity in ("info", "low", "medium", "high", "critical", "unknown"):
            with self.subTest(severity=severity):
                result = self.normalize(envelope(raw_output=[record(info={"severity": severity})]))
                self.assertEqual(result["observation"]["new_facts"][0]["confidence"], 0.0)

    def test_minimized_candidate_validation(self):
        candidate = {"source": "NUCLEI", "target_id": TARGET, "endpoint_id": None,
                     "finding_type": "sqli", "confidence": 0.0}
        for mutation in ({"source": "ZAP"}, {"target_id": "lab-clean-001"},
                         {"endpoint_id": "/PRIVATE_SENTINEL"}, {"confidence": True},
                         {"confidence": 0.5}, {"finding_type": "unknown"}, {"raw": "PRIVATE_SENTINEL"}):
            data = envelope()
            del data["raw_output"]
            data["scanner_results"] = [dict(candidate, **mutation)]
            with self.subTest(mutation=mutation), self.assertRaises(NormalizationError):
                self.normalize(data)

    def test_json_text_duplicate_keys_nonfinite_and_paths_rejected(self):
        for raw in ('{"template-id":"one","template-id":"two"}', '[NaN]', '[Infinity]',
                    '{"x":1e999}', 'C:/PRIVATE_SENTINEL.json', '[1]', '{}', '{bad}'):
            with self.subTest(raw=raw), self.assertRaises(NormalizationError) as raised:
                self.normalize(envelope(raw_output=raw))
            self.assertNotIn("PRIVATE_SENTINEL", str(raised.exception))

    def test_jsonl_unicode_line_separators_inside_values_are_data(self):
        for separator in ("\u2028", "\u2029", "\u0085"):
            raw = json.dumps(record(extra="before" + separator + "after"), ensure_ascii=False)
            with self.subTest(separator=repr(separator)):
                result = self.normalize(envelope(raw_output=raw))
                self.output_validator.validate(result)
                self.assertEqual(len(result["observation"]["new_facts"]), 1)

    def test_input_and_record_hashes_match_canonical_json(self):
        import hashlib

        data = envelope()
        result = self.normalize(data)
        canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.assertEqual(result["provenance"]["input_sha256"], hashlib.sha256(canonical(data)).hexdigest())
        self.assertEqual(result["provenance"]["record_sources"][0]["record_sha256"],
                         hashlib.sha256(canonical(data["raw_output"][0])).hexdigest())

    def test_size_depth_node_cycle_unicode_and_non_json_limits(self):
        nested = []
        for _ in range(18):
            nested = [nested]
        cyclic = []
        cyclic.append(cyclic)
        for value in (nested, cyclic, "x" * 1_048_577, [None] * 50_001,
                      float("nan"), float("inf"), "\ud800", object(), {1: "bad"}, 1 << 1025):
            with self.subTest(kind=type(value).__name__), self.assertRaises(NormalizationError):
                self.normalize(envelope(raw_output=[record(extra=value)]))

    def test_exact_record_limit(self):
        result = self.normalize(envelope(raw_output=[record()] * 1000))
        self.output_validator.validate(result)
        self.assertEqual(result["provenance"]["input_record_count"], 1000)
        with self.assertRaises(NormalizationError):
            self.normalize(envelope(raw_output=[record()] * 1001))

    def test_refs_are_preserved_but_never_marked_verified(self):
        result = self.normalize(envelope(evidence_refs=["EV-FIXTURE-001"]))
        self.assertEqual(result["observation"]["evidence_refs"], ["EV-FIXTURE-001"])
        self.assertEqual(result["provenance"]["evidence_status"], "REFERENCED_UNVERIFIED")

    def test_schema_rejects_extra_fields_and_confirmed_facts(self):
        data = envelope(extra=True)
        self.assertFalse(self.input_validator.is_valid(data))
        result = self.normalize()
        result["observation"]["new_facts"][0]["fact_type"] = "CONFIRMED_FINDING"
        self.assertFalse(self.output_validator.is_valid(result))
        result = self.normalize()
        result["provenance"]["raw"] = "PRIVATE_SENTINEL"
        self.assertFalse(self.output_validator.is_valid(result))

    def test_zero_network_process_and_evidence_writes(self):
        original_open = builtins.open

        def read_only(file, mode="r", *args, **kwargs):
            self.assertFalse(any(char in mode for char in "wax+"))
            return original_open(file, mode, *args, **kwargs)

        with ExitStack() as stack:
            for method in ("socket.socket", "socket.create_connection", "socket.getaddrinfo",
                           "subprocess.Popen", "subprocess.run", "os.system", "pathlib.Path.write_text",
                           "pathlib.Path.write_bytes"):
                stack.enter_context(patch(method, side_effect=AssertionError("Forbidden side effect")))
            stack.enter_context(patch("builtins.open", side_effect=read_only))
            result = self.normalize()
            self.output_validator.validate(result)


if __name__ == "__main__":
    unittest.main()
