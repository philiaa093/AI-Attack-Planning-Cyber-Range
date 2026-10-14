"""Kiểm tra parser và wrapper ZAP ngoại tuyến bằng fixture không có payload."""

import builtins
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.validate_scaffold import validate_shape
from tools.adapters.zap.adapter import ZapAdapter
from tools.parsers import zap_parser

TARGET = "lab-sqli-001"
ROOT = Path(__file__).resolve().parents[2]


def report(**alert_fields):
    alert = {"alert": "SQL Injection", "confidence": "2", "uri": f"http://{TARGET}/login"}
    alert.update(alert_fields)
    return {"site": [{"host": TARGET, "alerts": [alert]}]}


class ZapOfflineTests(unittest.TestCase):
    def parse(self, data):
        return zap_parser.parse_zap_results(data, TARGET)

    def test_schema_and_no_secrets(self):
        data = report(uri=f"http://{TARGET}/PRIVATE_SENTINEL?token=PRIVATE_SENTINEL#PRIVATE_SENTINEL")
        before = copy.deepcopy(data)
        results = self.parse(data)
        schema = json.loads((ROOT / "agent/planner/contracts/scanner-result.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(len(results), 1)
        self.assertEqual(validate_shape(results[0], schema), [])
        self.assertEqual(results[0]["endpoint_id"], None)
        self.assertEqual(results[0]["finding_type"], "sqli")
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(results))
        self.assertEqual(data, before)

    def test_empty_and_instances(self):
        self.assertEqual(self.parse({"site": []}), [])
        data = report(instances=[{"uri": f"http://{TARGET}/a"}, {"uri": f"http://{TARGET}/b"}])
        self.assertEqual(len(self.parse(data)), 2)
        site = data["site"][0]
        site["@host"] = site.pop("host")
        self.assertEqual(len(self.parse(data)), 2)

    def test_confidence_not_severity(self):
        for code in range(5):
            for value in (code, str(code)):
                with self.subTest(value=value):
                    results = self.parse(report(confidence=value, riskcode="3"))
                    self.assertEqual(len(results), int(code > 0))
                    if results:
                        self.assertEqual(results[0]["confidence"], code / 4)
        data = report(riskcode="3")
        del data["site"][0]["alerts"][0]["confidence"]
        self.assertEqual(self.parse(data), [])
        for code in (True, False, 2.0, None, "5", "02", float("nan")):
            with self.subTest(code=code), self.assertRaises(ValueError):
                self.parse(report(confidence=code))

    def test_only_supported_candidates(self):
        for name in ("Directory Browsing", "Remote File Inclusion", "PRIVATE_SENTINEL"):
            self.assertEqual(self.parse(report(alert=name)), [])
        for name, family in (("Cross Site Scripting (Reflected)", "xss"), ("Path Traversal", "path-traversal")):
            self.assertEqual(self.parse(report(alert=name))[0]["finding_type"], family)

    def test_malformed_shapes(self):
        bad = [None, [], {}, {"site": None}, {"site": [None]}, {"site": [{"host": TARGET}]},
               {"site": [{"host": TARGET, "alerts": {}}]}, report(alert=None), report(instances=[]),
               report(instances=None), report(instances=[{}]), report(uri=None)]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.parse(data)

    def test_all_or_nothing_and_ignored_alert_scope(self):
        for fields in ({"alert": "Unknown"}, {"confidence": "0"}):
            data = report()
            bad = report(uri="http://outside.invalid/PRIVATE_SENTINEL", **fields)["site"][0]["alerts"][0]
            data["site"][0]["alerts"].append(bad)
            before = copy.deepcopy(data)
            with self.assertRaises(ValueError) as error:
                self.parse(data)
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))
            self.assertEqual(data, before)

    def test_target_scope(self):
        for target in (None, [], "lab-unknown-999", "outside.invalid", TARGET + "\n"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                zap_parser.parse_zap_results(report(), target)
        for host in ("lab-xss-001", TARGET + ".", None):
            data = report()
            data["site"][0]["host"] = host
            with self.assertRaises(ValueError):
                self.parse(data)
        data = report()
        data["site"][0]["@host"] = "lab-xss-001"
        with self.assertRaises(ValueError):
            self.parse(data)

    def test_uri_rejections_and_generic_errors(self):
        uris = [f"http://user:PRIVATE_SENTINEL@{TARGET}/", f"http://%6cab-sqli-001/",
                f"http://{TARGET}.outside.invalid/", f"http://{TARGET}./", f"ftp://{TARGET}/",
                f"//{TARGET}/", f"http://{TARGET}:0/", f"http://{TARGET}:65536/",
                f"http://{TARGET}:080/", f"http://{TARGET}\\other/", f"http://{TARGET}/\nsecret",
                "http://[broken", "relative", f"http://{TARGET} /", f"http://{TARGET}:443:80/"]
        for uri in uris:
            with self.subTest(uri=uri), self.assertRaises(ValueError) as error:
                self.parse(report(uri=uri))
            self.assertNotIn("PRIVATE_SENTINEL", str(error.exception))

    def test_origin_metadata(self):
        data = report(uri=f"https://{TARGET}:8443/a")
        site = data["site"][0]
        site.update({"@name": f"https://{TARGET}:8443", "@port": "8443", "@ssl": "true"})
        self.assertEqual(len(self.parse(data)), 1)
        for fields in ({"@port": "8444"}, {"scheme": "http"}, {"@name": f"https://{TARGET}:8444"}):
            bad = copy.deepcopy(data)
            bad["site"][0].update(fields)
            with self.assertRaises(ValueError):
                self.parse(bad)
        for uri in (f"http://{TARGET}/a", f"https://{TARGET}/a"):
            bad = copy.deepcopy(data)
            bad["site"][0]["alerts"][0]["uri"] = uri
            with self.assertRaises(ValueError):
                self.parse(bad)

    def test_limits_n_and_n_plus_one(self):
        uri = f"http://{TARGET}/a"
        with patch.object(zap_parser, "MAX_URI_CHARS", len(uri)):
            self.parse(report(uri=uri))
            with self.assertRaises(ValueError):
                self.parse(report(uri=uri + "b"))
        data = report()
        with patch.object(zap_parser, "MAX_SITES", 1):
            self.parse(data)
            data["site"].append(copy.deepcopy(data["site"][0]))
            with self.assertRaises(ValueError):
                self.parse(data)
        data = report()
        with patch.object(zap_parser, "MAX_ALERTS", 1):
            self.parse(data)
            data["site"][0]["alerts"].append(copy.deepcopy(data["site"][0]["alerts"][0]))
            with self.assertRaises(ValueError):
                self.parse(data)
        data = report(instances=[{"uri": uri}, {"uri": uri}])
        with patch.object(zap_parser, "MAX_INSTANCES", 2):
            self.assertEqual(len(self.parse(data)), 2)
            data["site"][0]["alerts"][0]["instances"].append({"uri": uri})
            with self.assertRaises(ValueError):
                self.parse(data)

    def test_json_byte_and_depth_boundaries(self):
        for text in ("a", '"\\\n', "tiếng Việt"):
            data = {"site": [], "note": text}
            size = len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode("utf-8"))
            with patch.object(zap_parser, "MAX_JSON_BYTES", size):
                self.parse(data)
            with patch.object(zap_parser, "MAX_JSON_BYTES", size - 1), self.assertRaises(ValueError):
                self.parse(data)
        data = {"site": []}
        with patch.object(zap_parser, "MAX_DEPTH", 1):
            self.parse(data)
            data["extra"] = [[]]
            with self.assertRaises(ValueError):
                self.parse(data)
        data = {"site": [], "note": "a" * 100}
        with patch.object(zap_parser, "MAX_JSON_BYTES", 20), patch.object(zap_parser.json.JSONEncoder, "iterencode", side_effect=AssertionError("Encoder không được chạy")):
            with self.assertRaises(ValueError):
                self.parse(data)

    def test_non_json_and_cycles(self):
        for value in (float("nan"), float("inf"), (), {1: "x"}, "\ud800", object()):
            with self.subTest(kind=type(value)), self.assertRaises(ValueError):
                self.parse({"site": [], "extra": value})
        data = {"site": []}
        data["cycle"] = data
        with self.assertRaises(ValueError):
            self.parse(data)

    def test_execute_denied_and_schema(self):
        schema = json.loads((ROOT / "agent/planner/contracts/observation.schema.json").read_text(encoding="utf-8"))
        for parameters in (None, {}, {"approval": True, "report": report()}):
            obs, results = ZapAdapter().execute("ACTION-SCAN-001", TARGET, "RUN-016", parameters)
            self.assertEqual(validate_shape(obs, schema), [])
            self.assertEqual(obs["outcome"], "DENIED")
            self.assertEqual(obs["new_facts"], [])
            self.assertEqual(results, [])

    def test_execute_invalid_input(self):
        for action, target, run, parameters in ((None, TARGET, "RUN-016", None),
                ("ACTION-RECON-001", TARGET, "RUN-016", None), ("ACTION-SCAN-001", None, "RUN-016", None),
                ("ACTION-SCAN-001", TARGET, None, None), ("ACTION-SCAN-001", TARGET, "RUN-016\n", None),
                ("ACTION-SCAN-001", TARGET, "RUN-016", [])):
            with self.subTest(action=action, run=run), self.assertRaises(ValueError):
                ZapAdapter().execute(action, target, run, parameters)

    def test_import_budget_and_rate(self):
        adapter = ZapAdapter()
        with patch.object(adapter._rate_limiter, "acquire"):
            adapter._max_imports = 1
            self.assertEqual(len(adapter.import_report(report(), target_id=TARGET)), 1)
            with self.assertRaises(RuntimeError):
                adapter.import_report(report(), target_id=TARGET)
        adapter = ZapAdapter()
        with patch("tools.adapters.base.time.monotonic", return_value=1):
            adapter.import_report(report(), target_id=TARGET)
            with self.assertRaises(RuntimeError):
                adapter.import_report(report(), target_id=TARGET)
        for ceiling in (False, 0, 101, None):
            with patch("tools.adapters.zap.adapter.load_request_budget", return_value={"max_actions": ceiling}), self.assertRaises(ValueError):
                ZapAdapter()

    def test_zero_dispatch_and_writes(self):
        adapter = ZapAdapter()
        original_open = builtins.open

        def read_only_open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError("Không write")
            return original_open(file, mode, *args, **kwargs)

        guards = [patch("socket.socket", side_effect=AssertionError("Không network")),
                  patch("subprocess.Popen", side_effect=AssertionError("Không process")),
                  patch("pathlib.Path.write_text", side_effect=AssertionError("Không write")),
                  patch("pathlib.Path.write_bytes", side_effect=AssertionError("Không write")),
                  patch("builtins.open", side_effect=read_only_open),
                  patch("io.open", side_effect=read_only_open),
                  patch("os.open", side_effect=AssertionError("Không ghi filesystem"))]
        with guards[0], guards[1], guards[2], guards[3], guards[4], guards[5], guards[6]:
            results = adapter.import_report(report(), target_id=TARGET)
            obs, scans = adapter.execute("ACTION-SCAN-001", TARGET, "RUN-016")
        self.assertEqual(len(results), 1)
        self.assertEqual(obs["outcome"], "DENIED")
        self.assertEqual(scans, [])


if __name__ == "__main__":
    unittest.main()
