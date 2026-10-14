"""Offline Nuclei boundary tests using metadata fixtures, without payloads."""

import builtins
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.validate_scaffold import validate_shape
from tools.adapters.nuclei.adapter import NucleiAdapter
from tools.parsers import nuclei_parser as parser

ROOT = Path(__file__).resolve().parents[2]
TARGET = "lab-sqli-001"
MANIFEST = {"fixture-sqli": "sqli", "fixture-xss": "xss", "fixture-path": "path-traversal"}


def record(**fields):
    item = {
        "template-id": "fixture-sqli",
        "type": "http",
        "host": f"http://{TARGET}",
        "matched-at": f"http://{TARGET}/observed",
        "matcher-status": True,
        "info": {"severity": "high", "tags": ["sqli"]},
    }
    item.update(fields)
    return item


class NucleiOfflineTests(unittest.TestCase):
    def parse(self, data, **kwargs):
        return parser.parse_nuclei_results(data, TARGET, allowed_templates=MANIFEST, **kwargs)

    def jsonl(self, text):
        return parser.parse_nuclei_jsonl(text, TARGET, allowed_templates=MANIFEST)

    def test_contract_minimization_and_input_preservation(self):
        data = [record(**{
            "matched-at": f"http://{TARGET}/PRIVATE_SENTINEL?token=PRIVATE_SENTINEL#PRIVATE_SENTINEL",
            "request": "PRIVATE_SENTINEL", "response": "PRIVATE_SENTINEL",
            "extracted-results": ["PRIVATE_SENTINEL"],
            "info": {"severity": "high", "tags": ["sqli"], "name": "PRIVATE_SENTINEL"},
        })]
        before = copy.deepcopy(data)
        results = self.parse(data)
        schema = json.loads((ROOT / "agent/planner/contracts/scanner-result.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_shape(results[0], schema), [])
        self.assertEqual(set(results[0]), set(schema["required"]))
        self.assertIsNone(results[0]["endpoint_id"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(results))
        self.assertEqual(before, data)

    def test_all_families_are_manifest_classified(self):
        for template_id, family in MANIFEST.items():
            with self.subTest(family=family):
                result = self.parse([record(**{"template-id": template_id})])[0]
                self.assertEqual(result["finding_type"], family)

    def test_severity_and_tags_never_supply_confidence(self):
        for severity in ("info", "low", "medium", "high", "critical", "unknown"):
            result = self.parse([record(info={"severity": severity, "tags": ["rce", "xss"]})])[0]
            self.assertEqual(result["confidence"], 0.0)
            self.assertEqual(result["finding_type"], "sqli")

    def test_empty_and_failed_match_are_not_findings(self):
        self.assertEqual(self.parse([]), [])
        self.assertEqual(self.jsonl(" \n\r\n"), [])
        self.assertEqual(self.parse([record(**{"matcher-status": False})]), [])
        self.assertEqual(parser.parse_nuclei_results([], TARGET), [])

    def test_default_deny_and_exact_template_ids(self):
        with self.assertRaises(ValueError):
            parser.parse_nuclei_results([record()], TARGET)
        for template_id in ("sqli", "fixture-sqli-new", "fixture-*", None, [], "PRIVATE_SENTINEL"):
            with self.subTest(template_id=template_id), self.assertRaises(ValueError) as error:
                self.parse([record(**{"template-id": template_id})])
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))

    def test_template_manifest_validation(self):
        for manifest in ([], {"a": "rce"}, {"a": None}, {"../a": "sqli"},
                         {"a\n": "sqli"}, {1: "sqli"}, {"": "xss"}, {"a" * 129: "xss"}):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                parser.parse_nuclei_results([], TARGET, allowed_templates=manifest)
        with patch.object(parser, "MAX_TEMPLATES", 1):
            parser.validate_template_manifest({"a": "sqli"})
            with self.assertRaises(ValueError):
                parser.validate_template_manifest({"a": "sqli", "b": "xss"})

    def test_adapter_copies_manifest(self):
        manifest = {"fixture-sqli": "sqli"}
        adapter = NucleiAdapter(allowed_templates=manifest)
        manifest["fixture-sqli"] = "xss"
        result = adapter.import_report([record()], target_id=TARGET)[0]
        self.assertEqual(result["finding_type"], "sqli")

    def test_target_validation(self):
        for target in (None, [], "outside.invalid", "lab-unknown-999", TARGET + "\n"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                parser.parse_nuclei_results([], target, allowed_templates=MANIFEST)

    def test_uri_rejections_do_not_echo_input(self):
        uris = ["relative", "http://[broken", "http://outside.invalid/PRIVATE_SENTINEL",
                f"http://user:PRIVATE_SENTINEL@{TARGET}/", f"http://{TARGET}./",
                f"http://{TARGET}.outside.invalid/", f"http://%6cab-sqli-001/",
                f"ftp://{TARGET}/", f"//{TARGET}/", f"http://{TARGET}:0/",
                f"http://{TARGET}:080/", f"http://{TARGET}:65536/",
                f"http://{TARGET}\\other/", f"http://{TARGET}/\nsecret"]
        for uri in uris:
            for field in ("host", "matched-at", "url"):
                with self.subTest(field=field, uri=uri), self.assertRaises(ValueError) as error:
                    self.parse([record(**{field: uri})])
                self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))

    def test_origin_consistency_and_canonicalization(self):
        self.parse([record(host=f"HTTP://{TARGET.upper()}:80", **{"matched-at": f"http://{TARGET}/a"})])
        for uri in (f"https://{TARGET}/a", f"http://{TARGET}:8080/a", "http://lab-xss-001/a"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                self.parse([record(**{"matched-at": uri})])
        other = record(host=f"http://{TARGET}:8080", **{"matched-at": f"http://{TARGET}:8080/a"})
        with self.assertRaises(ValueError):
            self.parse([record(), other])

    def test_malformed_shapes_and_legacy_metadata(self):
        for data in (None, {}, "[]", [None], [{}]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.parse(data)
        for fields in ({"type": "dns"}, {"matcher-status": 1}, {"matcher-status": None},
                       {"info": None}, {"info": {"severity": []}},
                       {"info": {"severity": "high", "tags": "sqli"}},
                       {"info": {"severity": "high", "tags": [1]}},
                       {"severity": "high"}, {"tags": ["sqli"]}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.parse([record(**fields)])
        data = record()
        del data["matcher-status"]
        with self.assertRaises(ValueError):
            self.parse([data])

    def test_all_or_nothing_even_for_failed_matchers(self):
        bad = record(**{"matcher-status": False, "matched-at": "http://outside.invalid/PRIVATE_SENTINEL"})
        data = [record(), bad]
        before = copy.deepcopy(data)
        for parse in (lambda: self.parse(data), lambda: self.jsonl("\n".join(map(json.dumps, data)))):
            with self.assertRaises(ValueError) as error:
                parse()
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))
        self.assertEqual(data, before)

    def test_duplicates_do_not_inflate_confidence(self):
        results = self.parse([record(), record()])
        self.assertEqual(len(results), 2)  # Preserve multiplicity; endpoint provenance is unresolved.
        self.assertTrue(all(item["confidence"] == 0.0 for item in results))

    def test_jsonl_matches_decoded_output(self):
        data = [record(), record(**{"template-id": "fixture-xss"})]
        text = "\r\n".join(json.dumps(item) for item in data) + "\r\n"
        self.assertEqual(self.jsonl(text), self.parse(data))

    def test_jsonl_unicode_line_separator_is_data(self):
        data = [record(extra="metadata\u2028still-metadata")]
        self.assertEqual(self.jsonl(json.dumps(data[0], ensure_ascii=False)), self.parse(data))

    def test_tool_error_rejects_entire_report_without_leaking_message(self):
        for value in ("PRIVATE_SENTINEL", None, False, 1):
            with self.subTest(value=value), self.assertRaises(ValueError) as error:
                self.parse([record(), record(error=value)])
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))
        self.assertEqual(len(self.parse([record(error="")])), 1)

    def test_jsonl_rejects_duplicates_truncation_and_nonfinite_numbers(self):
        good = json.dumps(record())
        for text in ('{"template-id":"a","template-id":"b"}',
                     good[:-1], good + '\nPRIVATE_SENTINEL', '[{}]',
                     '{"extra":NaN}', '{"extra":Infinity}',
                     good.replace('"high"', '"high", "severity":"low"')):
            with self.subTest(text=text), self.assertRaises(ValueError) as error:
                self.jsonl(text)
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))

    def test_jsonl_no_file_paths_or_bytes(self):
        for text in (b"[]", Path("report.jsonl"), "E:/PRIVATE_SENTINEL.jsonl", "\ud800"):
            with self.subTest(kind=type(text)), self.assertRaises(ValueError) as error:
                self.jsonl(text)
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))

    def test_record_and_uri_limits(self):
        with patch.object(parser, "MAX_RECORDS", 1):
            self.parse([record()])
            self.jsonl(json.dumps(record()))
            for call in (lambda: self.parse([record(), record()]),
                         lambda: self.jsonl(json.dumps(record()) + "\n" + json.dumps(record()))):
                with self.assertRaises(ValueError):
                    call()
        uri = f"http://{TARGET}/a"
        with patch.object(parser, "MAX_URI_CHARS", len(uri)):
            self.parse([record(**{"matched-at": uri})])
            with self.assertRaises(ValueError):
                self.parse([record(**{"matched-at": uri + "b"})])

    def test_exact_json_byte_and_depth_limits(self):
        for text in ("a", '"\\\n', "tiếng Việt"):
            data = [record(extra=text)]
            size = len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode("utf-8"))
            with patch.object(parser, "MAX_JSON_BYTES", size):
                self.parse(data)
            with patch.object(parser, "MAX_JSON_BYTES", size - 1), self.assertRaises(ValueError):
                self.parse(data)
        with patch.object(parser, "MAX_DEPTH", 4):
            self.parse([record()])
            with self.assertRaises(ValueError):
                self.parse([record(extra=[[[[1]]]])])

    def test_exact_jsonl_utf8_byte_limit(self):
        text = json.dumps(record(extra="tiếng Việt"), ensure_ascii=False)
        size = len(text.encode("utf-8"))
        with patch.object(parser, "MAX_JSON_BYTES", size + 2):
            self.jsonl(text)
        with patch.object(parser, "MAX_JSON_BYTES", size - 1), self.assertRaises(ValueError):
            self.jsonl(text)

    def test_non_json_cycles_and_huge_numbers(self):
        for extra in (float("nan"), float("inf"), (), {1: "x"}, "\ud800", object(), 1 << 4097):
            with self.subTest(kind=type(extra)), self.assertRaises(ValueError):
                self.parse([record(extra=extra)])
        data = [record()]
        data[0]["cycle"] = data
        with self.assertRaises(ValueError):
            self.parse(data)

    def test_execute_denied_with_unique_schema_valid_observations(self):
        schema = json.loads((ROOT / "agent/planner/contracts/observation.schema.json").read_text(encoding="utf-8"))
        adapter = NucleiAdapter()
        ids = set()
        with patch.object(adapter._rate_limiter, "acquire"):
            for parameters in (None, {}):
                obs, results = adapter.execute("ACTION-SCAN-002", TARGET, "RUN-017", parameters)
                self.assertEqual(validate_shape(obs, schema), [])
                self.assertEqual(obs["outcome"], "DENIED")
                self.assertEqual(obs["new_facts"], [])
                self.assertEqual(obs["evidence_refs"], [])
                self.assertEqual(results, [])
                ids.add(obs["observation_id"])
        self.assertEqual(len(ids), 2)

    def test_execute_invalid_inputs_and_fake_approval(self):
        for action, target, run, params in ((None, TARGET, "RUN-017", None),
                ("ACTION-SCAN-001", TARGET, "RUN-017", None),
                ("ACTION-SCAN-002", None, "RUN-017", None),
                ("ACTION-SCAN-002", TARGET, None, None),
                ("ACTION-SCAN-002", TARGET, "RUN-017\n", None),
                ("ACTION-SCAN-002", TARGET, "RUN-017", []),
                ("ACTION-SCAN-002", TARGET, "RUN-017", {"approval": True}),
                ("ACTION-SCAN-002", TARGET, "RUN-017", {"command": "PRIVATE_SENTINEL"})):
            with self.subTest(action=action, run=run), self.assertRaises(ValueError) as error:
                NucleiAdapter().execute(action, target, run, params)
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))

    def test_import_attempt_quota_and_invalid_config(self):
        adapter = NucleiAdapter(allowed_templates=MANIFEST)
        adapter._max_imports = 1
        with patch.object(adapter._rate_limiter, "acquire"):
            with self.assertRaises(ValueError):
                adapter.import_report([{}], target_id=TARGET)
            with self.assertRaises(RuntimeError):
                adapter.import_report([record()], target_id=TARGET)
        for ceiling in (False, 0, 101, None, 1.0):
            with patch("tools.adapters.nuclei.adapter.load_request_budget", return_value={"max_actions": ceiling}), self.assertRaises(ValueError):
                NucleiAdapter()

    def test_rate_limit_and_jsonl_wrapper(self):
        adapter = NucleiAdapter(allowed_templates=MANIFEST)
        with patch("tools.adapters.base.time.monotonic", return_value=1):
            self.assertEqual(len(adapter.import_report(json.dumps(record()), target_id=TARGET)), 1)
            with self.assertRaises(RuntimeError):
                adapter.import_report([record()], target_id=TARGET)

    def test_concurrent_import_quota_is_atomic(self):
        adapter = NucleiAdapter(allowed_templates=MANIFEST)
        adapter._max_imports = 1

        def attempt(_):
            try:
                return adapter.import_report([record()], target_id=TARGET)
            except RuntimeError:
                return None

        with patch.object(adapter._rate_limiter, "acquire"), ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_zero_network_process_and_filesystem_writes(self):
        adapter = NucleiAdapter(allowed_templates=MANIFEST)
        original_open = builtins.open

        def read_only_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError("Unexpected filesystem write")
            return original_open(file, mode, *args, **kwargs)

        with ExitStack() as stack:
            for name in ("socket.socket", "socket.getaddrinfo", "subprocess.Popen", "os.system", "os.open",
                         "pathlib.Path.write_text", "pathlib.Path.write_bytes"):
                stack.enter_context(patch(name, side_effect=AssertionError("Unexpected external side effect")))
            stack.enter_context(patch("builtins.open", side_effect=read_only_open))
            stack.enter_context(patch("io.open", side_effect=read_only_open))
            self.assertEqual(len(adapter.import_report([record()], target_id=TARGET)), 1)
            obs, results = adapter.execute("ACTION-SCAN-002", TARGET, "RUN-017")
            self.assertEqual(obs["outcome"], "DENIED")
            self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
