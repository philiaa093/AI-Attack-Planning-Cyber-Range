"""Kiểm thử importer offline; chỉ dùng fixtures và evidence trong tempfile."""
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.safety.discovery_gate import ApprovalToken, KillSwitch
from runtime.evidence.discovery_recorder import DurableEvidenceRecorder, EvidenceFailure
from runtime.discovery import discovery_report_importer as importer
from scripts.validation.validate_scaffold import ROOT
from shared.schema_validation import validate_shape


class DiscoveryReportImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.report = self.inputs / "report.json"
        self.recorder = DurableEvidenceRecorder(
            "RUN-IMPORT-TEST", base_dir=self.root / "evidence" / "run",
            approved_root=self.root / "evidence", source="TOOL_ADAPTER", exclusive_creation=True,
        )
        self.approval = ApprovalToken("APPROVAL-TEST", "RUN-IMPORT-TEST", "lab-ecommerce",
                                      importer.POLICY_ACTION, time.time() - 10, time.time() + 300)
        self.kill = KillSwitch()
        self.args = dict(report_format="httpx-jsonl", approved_input_root=self.inputs,
                         run_id="RUN-IMPORT-TEST", target_id="lab-ecommerce", approval=self.approval,
                         run_approved_targets={"lab-ecommerce"}, run_approved_actions={importer.POLICY_ACTION},
                         recorder=self.recorder, kill_switch=self.kill, lab_mode=True)
        # Không thay canonical config; đây là dữ liệu lab đã đăng ký trong repository.
        self.url = "http://127.0.0.1:18088/catalog"
        self.record = {"url": self.url, "status_code": 200, "tech": ["Python", "Django"]}

    def write(self, record=None, raw=None):
        self.report.write_bytes(raw if raw is not None else json.dumps(
            self.record if record is None else record, ensure_ascii=False).encode("utf-8"))

    def run_import(self, **overrides):
        return importer.import_discovery_report(self.report, **(self.args | overrides))

    def evidence(self):
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.recorder.directory.glob("*.json")]

    def test_httpx_metadata_hash_and_phase_evidence(self):
        self.write()
        raw = self.report.read_bytes()
        result = self.run_import()
        self.assertEqual(result["metadata"], [{"endpoint": self.url, "http_status": 200,
                         "declared_technologies": ["Django", "Python"], "verified": False}])
        self.assertEqual(result["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertFalse(result["action_executed"])
        self.assertEqual(result["external_execution"], "UNRESOLVED")
        self.assertEqual(result["provenance"], "IMPORTED_OFFLINE")
        self.assertNotIn("action_id", result)
        self.assertNotIn("new_facts", result)
        self.assertEqual(len(result["evidence_refs"]), 2)
        schema = json.loads((ROOT / "agent/planner/contracts/evidence.schema.json").read_text(encoding="utf-8"))
        records = [item for item in self.evidence() if "evidence_id" in item]
        self.assertEqual(len(records), 2)
        for item in records:
            self.assertEqual(validate_shape(item, schema), [])
            self.assertNotIn("DISPATCH", item["expected_state"])
            self.assertNotIn("DISPATCH", item["observed_state"])
            self.assertEqual(item["source"], "TOOL_ADAPTER")
            self.assertEqual(hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest(), item["sha256"])
        result_record = next(item for item in records if item["observed_state"] == "OFFLINE_METADATA_RECORDED")
        self.assertEqual(result_record["derived_from"], [result["evidence_refs"][0]])

    def test_whatweb_ignores_plugin_values_and_pseudo_plugins(self):
        self.write(raw=json.dumps([{"target": self.url, "http_status": 200, "plugins": {
            "Django": {"version": ["private-secret"]}, "IP": {"string": ["private-ip"]},
            "Cookies": {"string": ["session=private-cookie"]}, "Title": {"string": ["private-title"]},
            "HTTPServer": {"string": ["private-header"]}, "Python": {},
        }}]).encode())
        result = self.run_import(report_format="whatweb-json")
        self.assertEqual(result["metadata"][0]["declared_technologies"], ["Django", "Python"])
        self.assertNotIn("private-", json.dumps(result) + json.dumps(self.evidence()))

    def test_no_network_process_or_gate_dispatch(self):
        self.write()
        with patch("socket.socket", side_effect=AssertionError("Không có socket")) as network, \
             patch("http.client.HTTPConnection", side_effect=AssertionError("Không có HTTP")) as http, \
             patch("subprocess.Popen", side_effect=AssertionError("Không có subprocess")) as process, \
             patch("runtime.safety.discovery_gate.CentralizedSafetyGate.dispatch", side_effect=AssertionError("Không dispatch")) as dispatch:
            result = self.run_import()
        self.assertEqual(result["network_dispatch_count"], 0)
        for spy in (network, http, process, dispatch):
            spy.assert_not_called()

    def test_redaction_drops_query_fragment_body_and_headers(self):
        record = self.record | {"url": self.url + "?token=private-token&search=private-query#private-fragment",
                               "body": "private-body", "title": "private-title", "header": {"Authorization": "private-auth"}}
        self.write(record)
        result = self.run_import()
        text = json.dumps(result) + json.dumps(self.evidence())
        self.assertNotIn("private-", text)
        self.assertEqual(result["metadata"][0]["endpoint"], self.url)
        self.assertNotIn(str(self.inputs), text)

    def test_repeated_imports_preserve_evidence_and_have_new_ids(self):
        self.write()
        first = self.run_import()
        before = {path: path.read_bytes() for path in self.recorder.directory.glob("*.json")}
        second = self.run_import()
        self.assertNotEqual(first["import_id"], second["import_id"])
        self.assertTrue(set(first["evidence_refs"]).isdisjoint(second["evidence_refs"]))
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(len(list(self.recorder.directory.glob("*.json"))), 8)

    def test_duplicate_records_merge_deterministically(self):
        self.write(raw=(json.dumps(self.record) + "\n" + json.dumps(self.record | {"tech": ["Django", "Flask"]})).encode())
        result = self.run_import()
        self.assertEqual(len(result["metadata"]), 1)
        self.assertEqual(result["metadata"][0]["declared_technologies"], ["Django", "Flask", "Python"])

    def test_empty_and_failed_reports_are_partial(self):
        for raw in (b"", json.dumps(self.record | {"failed": True}).encode(),
                    json.dumps(self.record | {"status_code": 500}).encode(),
                    json.dumps(self.record | {"status_code": 0}).encode()):
            with self.subTest(raw=raw):
                self.write(raw=raw)
                result = self.run_import()
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(result["metadata"], [])

    def test_invalid_json_encoding_duplicate_nonfinite_depth_and_shape(self):
        cases = (b"{", b"\xff", b'{"url":"x","url":"y"}', b'{"value":NaN}',
                 b'{"value":1e999}', b'[' * 17 + b'0' + b']' * 17, b"null", b"[]")
        for raw in cases:
            with self.subTest(raw=raw):
                self.write(raw=raw)
                with self.assertRaises(ValueError):
                    self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_format_and_record_shape_validation(self):
        self.write()
        with self.assertRaises(ValueError):
            self.run_import(report_format="auto")
        with self.assertRaises(ValueError):
            self.run_import(report_format="whatweb-json")
        for record in (self.record | {"tech": "Django"}, self.record | {"status_code": True},
                       self.record | {"failed": "false"}, self.record | {"status_code": 99},
                       self.record | {"status_code": 600}, self.record | {"tech": ["secret=private"]}):
            self.write(record)
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_report_record_url_and_technology_bounds(self):
        raws = (b" " * (importer.MAX_BYTES + 1),
                (json.dumps(self.record) + "\n").encode() * (importer.MAX_RECORDS + 1),
                json.dumps(self.record | {"url": self.url + "a" * importer.MAX_URL_CHARS}).encode(),
                json.dumps(self.record | {"tech": ["a" * 129]}).encode(),
                json.dumps(self.record | {"tech": [f"Tech{i}" for i in range(33)]}).encode())
        for raw in raws:
            self.write(raw=raw)
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_metadata_total_limit(self):
        records = [self.record | {"url": self.url + str(i), "tech": [f"Tech{n}" for n in range(32)]} for i in range(32)]
        self.write(raw="\n".join(json.dumps(record) for record in records).encode())
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_urls_rejected_without_echoing_input(self):
        urls = ("https://127.0.0.1:18088/catalog", "http://example.org/private",
                "http://127.0.0.1:18089/catalog", "http://user:private@127.0.0.1:18088/catalog",
                "/catalog", self.url + "\nprivate", "http://127.0.0.1:bad/private",
                "http://127.0.0.1:18088/token/private", "http://127.0.0.1:18088/private@example.org")
        for url in urls:
            self.write(self.record | {"url": url})
            with self.assertRaises(ValueError) as caught:
                self.run_import()
            self.assertNotIn("private", str(caught.exception))
        self.assertEqual(self.evidence(), [])

    def test_missing_mismatched_expired_revoked_and_nonfinite_approval(self):
        self.write()
        now = time.time()
        bad = (None,
               ApprovalToken("A", "RUN-OTHER", "lab-ecommerce", importer.POLICY_ACTION, now-10, now+10),
               ApprovalToken("A", self.args["run_id"], "lab-ecommerce", "*", now-10, now+10),
               ApprovalToken("A", self.args["run_id"], "lab-ecommerce", importer.POLICY_ACTION, now-20, now-10),
               ApprovalToken("A", self.args["run_id"], "lab-ecommerce", importer.POLICY_ACTION, now+10, now+20),
               ApprovalToken("A", self.args["run_id"], "lab-ecommerce", importer.POLICY_ACTION, float("nan"), now+10))
        for approval in bad:
            with self.assertRaises(ValueError):
                self.run_import(approval=approval)
        self.approval.revoke()
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_caller_cannot_widen_canonical_policy(self):
        self.write()
        for kwargs in ({"run_approved_targets": set()}, {"run_approved_actions": set()}, {"lab_mode": False}):
            with self.assertRaises(ValueError):
                self.run_import(**kwargs)
        with patch.object(importer, "load_canonical_target_allowlist", return_value=set()):
            with self.assertRaises(ValueError):
                self.run_import()
        with patch.object(importer, "load_canonical_action_allowlist", return_value=set()):
            with self.assertRaises(ValueError):
                self.run_import()
        self.kill.activate()
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_malformed_caller_inputs_fail_closed(self):
        self.write()
        for kwargs in ({"report_format": []}, {"run_approved_targets": "lab-ecommerce"},
                       {"run_approved_actions": None}, {"run_approved_targets": {1}}):
            with self.assertRaises(ValueError):
                self.run_import(**kwargs)
        self.approval.approval_id = "../private"
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_invalid_run_and_recorder_identity(self):
        self.write()
        with self.assertRaises(ValueError):
            self.run_import(run_id="../private")
        self.recorder.source = "EXECUTOR"
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_input_outside_root_or_directory(self):
        self.write()
        for root in (self.root / "evidence", self.report):
            with self.assertRaises(ValueError):
                self.run_import(approved_input_root=root)
        with self.assertRaises(ValueError):
            importer.import_discovery_report(self.inputs, **self.args)
        self.assertEqual(self.evidence(), [])

    def test_symlink_rejected(self):
        self.write()
        linked = self.inputs / "linked.json"
        try:
            linked.symlink_to(self.report)
        except OSError:
            self.skipTest("OS không cấp quyền tạo symlink; reparse được kiểm bằng test mô phỏng riêng")
        with self.assertRaises(ValueError):
            importer.import_discovery_report(linked, **self.args)
        self.assertEqual(self.evidence(), [])

    def test_reparse_point_rejected(self):
        self.write()
        original = Path.lstat
        def reparse(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path == self.report:
                class Reparse:
                    st_mode = value.st_mode
                    st_file_attributes = 0x400
                return Reparse()
            return value
        with patch.object(Path, "lstat", reparse):
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_input_identity_change_rejected(self):
        self.write()
        original = os.fstat
        def changed(fd):
            value = original(fd)
            class Changed:
                st_mode = value.st_mode
                st_dev = value.st_dev
                st_ino = value.st_ino + 1
                st_size = value.st_size
                st_mtime_ns = value.st_mtime_ns
                st_ctime_ns = value.st_ctime_ns
            return Changed()
        with patch.object(importer.os, "fstat", changed):
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_evidence_failures_do_not_return_metadata(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        for fail_on in ("IMPORT_INTENT", "IMPORT_RESULT"):
            def failing(phase, *args, **kwargs):
                if phase == fail_on:
                    raise EvidenceFailure("Lỗi ghi được tiêm trong test")
                return original(phase, *args, **kwargs)
            with patch.object(self.recorder, "persist_phase_artifact", side_effect=failing):
                with self.assertRaises(EvidenceFailure):
                    self.run_import()
        self.assertEqual(len(self.recorder.artifacts), 1)

    def test_revocation_during_persistence_halts_before_result(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        def revoke(phase, *args, **kwargs):
            artifact = original(phase, *args, **kwargs)
            self.approval.revoke()
            return artifact
        with patch.object(self.recorder, "persist_phase_artifact", side_effect=revoke):
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(len(self.recorder.artifacts), 1)

    def test_kill_switch_after_result_prevents_output(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        def kill_after_result(phase, *args, **kwargs):
            artifact = original(phase, *args, **kwargs)
            if phase == "IMPORT_RESULT":
                self.kill.activate()
            return artifact
        with patch.object(self.recorder, "persist_phase_artifact", side_effect=kill_after_result):
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(len(self.recorder.artifacts), 2)

    def test_malformed_percent_paths_rejected(self):
        for suffix in ("/%ZZ", "/%", "/%FF", "/%0a"):
            self.write(self.record | {"url": self.url + suffix})
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(self.evidence(), [])

    def test_evidence_destination_change_stops_publication(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        outside = self.root / "outside"
        outside.mkdir()
        def change_destination(phase, *args, **kwargs):
            artifact = original(phase, *args, **kwargs)
            self.recorder.directory = outside
            return artifact
        with patch.object(self.recorder, "persist_phase_artifact", side_effect=change_destination):
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(len(self.recorder.artifacts), 1)

    def test_recorder_context_change_stops_before_result(self):
        original = self.recorder.persist_phase_artifact
        outside = self.root / "outside"
        outside.mkdir()
        changes = ({"approved_root": outside, "directory": outside},
                   {"run_id": "RUN-OTHER"}, {"source": "EXECUTOR"})
        for change in changes:
            with self.subTest(fields=tuple(change)):
                self.write()
                before = {path: path.read_bytes() for path in self.recorder.directory.glob("*.json")}
                saved = {key: getattr(self.recorder, key) for key in change}
                count = len(self.recorder.artifacts)
                def mutate(phase, *args, **kwargs):
                    artifact = original(phase, *args, **kwargs)
                    for key, value in change.items():
                        setattr(self.recorder, key, value)
                    return artifact
                try:
                    with patch.object(self.recorder, "persist_phase_artifact", side_effect=mutate):
                        with self.assertRaises(ValueError):
                            self.run_import()
                finally:
                    for key, value in saved.items():
                        setattr(self.recorder, key, value)
                self.assertEqual(len(self.recorder.artifacts), count + 1)
                self.assertEqual(list(outside.iterdir()), [])
                for path, raw in before.items():
                    self.assertEqual(path.read_bytes(), raw)

    def test_policy_revocation_stops_before_result(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        def revoke_policy(phase, *args, **kwargs):
            artifact = original(phase, *args, **kwargs)
            self.args["run_approved_targets"].clear()
            return artifact
        with patch.object(self.recorder, "persist_phase_artifact", side_effect=revoke_policy):
            with self.assertRaises(ValueError):
                self.run_import()
        self.assertEqual(len(self.recorder.artifacts), 1)

    def observation_args(self):
        return {"observation_approval": ApprovalToken("APPROVAL-REVIEW", self.args["run_id"],
                self.args["target_id"], importer.OBSERVATION_ACTION, time.time() - 10, time.time() + 300),
                "run_approved_actions": {importer.POLICY_ACTION, importer.OBSERVATION_ACTION}}

    def test_offline_observations_for_both_formats(self):
        schema = json.loads((ROOT / "agent/planner/contracts/observation.schema.json").read_text(encoding="utf-8"))
        for report_format in ("httpx-jsonl", "whatweb-json"):
            with self.subTest(format=report_format):
                if report_format == "httpx-jsonl":
                    self.write()
                else:
                    self.write(raw=json.dumps([{"target": self.url, "http_status": 200,
                                                "plugins": {"Django": {}, "Python": {}}}]).encode())
                result = self.run_import(report_format=report_format, **self.observation_args())
                obs = result["observation"]
                self.assertEqual(validate_shape(obs, schema), [])
                self.assertEqual(obs["action_id"], "ACTION-PLAN-003")
                self.assertEqual(obs["outcome"], "PARTIAL")
                self.assertEqual(obs["evidence_refs"], result["evidence_refs"])
                target_facts = [f for f in obs["new_facts"] if f["fact_type"] != "CONTROL"]
                self.assertEqual([f["value"] for f in target_facts], [self.url, "Django", "Python"])
                self.assertTrue(all(f["confidence"] == 0 for f in target_facts))
                self.assertEqual({f["value"] for f in obs["new_facts"] if f["fact_type"] == "CONTROL"},
                                 {"IMPORTED_OFFLINE", "EXTERNAL_EXECUTION_UNRESOLVED", "DECLARED_METADATA_UNVERIFIED"})
                records = [r for r in self.evidence() if r.get("evidence_id") == result["observation_evidence_ref"]]
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record["derived_from"], [result["evidence_refs"][1]])
                self.assertEqual(record["observed_state"], "OFFLINE_DECLARATIONS_RECORDED")
                self.assertEqual(json.loads(Path(record["path"]).read_text(encoding="utf-8")), obs)
                self.assertEqual(hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest(), record["sha256"])

    def test_observations_require_separate_valid_approval(self):
        self.write()
        self.assertNotIn("observation", self.run_import())
        before = len(self.recorder.artifacts)
        options = self.observation_args()
        for token in (False, self.approval,
                      ApprovalToken("A", "RUN-OTHER", "lab-ecommerce", importer.OBSERVATION_ACTION, 0, time.time() + 10),
                      ApprovalToken("A", self.args["run_id"], "lab-ecommerce", importer.OBSERVATION_ACTION, 0, 1)):
            with self.assertRaises(ValueError):
                self.run_import(**(options | {"observation_approval": token}))
        with self.assertRaises(ValueError):
            self.run_import(**(options | {"run_approved_actions": {importer.POLICY_ACTION}}))
        with patch.object(importer, "load_canonical_action_allowlist", return_value={importer.POLICY_ACTION}):
            with self.assertRaises(ValueError):
                self.run_import(**options)
        self.assertEqual(len(self.recorder.artifacts), before)

    def test_observation_revocation_before_each_publication(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        for phase, expected_count in (("IMPORT_INTENT", 1), ("IMPORT_RESULT", 2), ("IMPORT_OBSERVATION", 3)):
            with self.subTest(phase=phase):
                options = self.observation_args()
                before = len(self.recorder.artifacts)
                def revoke(name, *args, **kwargs):
                    artifact = original(name, *args, **kwargs)
                    if name == phase:
                        options["observation_approval"].revoke()
                    return artifact
                with patch.object(self.recorder, "persist_phase_artifact", side_effect=revoke):
                    with self.assertRaises(ValueError):
                        self.run_import(**options)
                self.assertEqual(len(self.recorder.artifacts), before + expected_count)

    def test_observation_write_failure_preserves_import_evidence(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        def failing(phase, *args, **kwargs):
            if phase == "IMPORT_OBSERVATION":
                raise EvidenceFailure("Lỗi ghi observation được tiêm")
            return original(phase, *args, **kwargs)
        with patch.object(self.recorder, "persist_phase_artifact", side_effect=failing):
            with self.assertRaises(EvidenceFailure):
                self.run_import(**self.observation_args())
        self.assertEqual(len(self.recorder.artifacts), 2)

    def test_empty_failed_observations_have_no_target_facts(self):
        for raw in (b"", json.dumps(self.record | {"failed": True}).encode()):
            self.write(raw=raw)
            obs = self.run_import(**self.observation_args())["observation"]
            self.assertEqual(obs["outcome"], "PARTIAL")
            self.assertEqual({f["fact_type"] for f in obs["new_facts"]}, {"CONTROL"})

    def test_observations_have_no_dispatch_and_preserve_old_evidence(self):
        self.write()
        options = self.observation_args()
        with patch("socket.socket", side_effect=AssertionError("Không network")), \
             patch("subprocess.Popen", side_effect=AssertionError("Không process")), \
             patch("runtime.safety.discovery_gate.CentralizedSafetyGate.dispatch", side_effect=AssertionError("Không dispatch")):
            first = self.run_import(**options)
            before = {p: p.read_bytes() for p in self.recorder.directory.glob("*.json")}
            second = self.run_import(**options)
        self.assertNotEqual(first["observation"]["observation_id"], second["observation"]["observation_id"])
        self.assertEqual([f["fact_id"] for f in first["observation"]["new_facts"] if f["fact_type"] != "CONTROL"],
                         [f["fact_id"] for f in second["observation"]["new_facts"] if f["fact_type"] != "CONTROL"])
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_observation_facts_deduplicate_across_status_codes(self):
        self.write(raw=(json.dumps(self.record) + "\n" + json.dumps(self.record | {"status_code": 201})).encode())
        obs = self.run_import(**self.observation_args())["observation"]
        self.assertEqual(len(obs["new_facts"]), 6)
        self.assertEqual(len({f["fact_id"] for f in obs["new_facts"]}), 6)

    def test_observation_schema_rejection_before_writes(self):
        self.write()
        with patch.object(importer, "validate_shape", return_value=["lỗi schema"]):
            with self.assertRaises(ValueError):
                self.run_import(**self.observation_args())
        self.assertEqual(self.evidence(), [])

    def simulation_args(self, rule="CLEAR", audit="CLEAR", control="CLEAR"):
        fixture = {key: {"expected": "CLEAR", "observed": value}
                   for key, value in (("rule", rule), ("audit", audit), ("control", control))}
        path = self.inputs / "simulation.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        return self.observation_args() | {"simulation_fixture_path": path}

    def test_simulation_replan_and_stop_matrix(self):
        self.write()
        cases = (("CLEAR", "CLEAR", "CLEAR", ["RULE", "CONTROL"], "COMPLETED_SIMULATION"),
                 ("BLOCKED", "CLEAR", "CLEAR", ["RULE", "AUDIT", "CONTROL"], "COMPLETED_SIMULATION"),
                 ("BLOCKED", "BLOCKED", "CLEAR", ["RULE", "AUDIT"], "NO_PROGRESS"),
                 ("MISSING", "CLEAR", "CLEAR", ["RULE"], "UNRESOLVED"),
                 ("BLOCKED", "MISSING", "CLEAR", ["RULE", "AUDIT"], "UNRESOLVED"),
                 ("CLEAR", "CLEAR", "MISSING", ["RULE", "CONTROL"], "UNRESOLVED"),
                 ("CLEAR", "CLEAR", "BLOCKED", ["RULE", "CONTROL"], "CONTROL_BLOCKED"))
        for rule, audit, control, steps, reason in cases:
            with self.subTest(rule=rule, audit=audit, control=control):
                result = self.run_import(**self.simulation_args(rule, audit, control))
                sim = result["simulation"]
                self.assertEqual([e["review_step"] for e in sim["transcript"]], ["REVIEW_" + s for s in steps])
                self.assertEqual(sim["stop_reason"], reason)
                self.assertEqual(sim["provenance"], "SIMULATED_FIXTURE")
                self.assertEqual(result["external_execution"], "UNRESOLVED")
                self.assertFalse(result["action_executed"])
                self.assertEqual(result["network_dispatch_count"], 0)
                for entry in sim["transcript"]:
                    self.assertEqual(entry["expected"], "CLEAR")
                    self.assertEqual(entry["mismatch"], entry["observed"] != "CLEAR")

    def test_simulation_both_formats_hash_and_evidence_chain(self):
        for report_format in ("httpx-jsonl", "whatweb-json"):
            with self.subTest(format=report_format):
                if report_format == "httpx-jsonl":
                    self.write()
                else:
                    self.write(raw=json.dumps([{"target": self.url, "http_status": 200}]).encode())
                options = self.simulation_args("BLOCKED")
                result = self.run_import(report_format=report_format, **options)
                sim = result["simulation"]
                self.assertEqual(sim["fixture_sha256"], hashlib.sha256(options["simulation_fixture_path"].read_bytes()).hexdigest())
                records = {r["evidence_id"]: r for r in self.evidence() if "evidence_id" in r}
                parent = result["observation_evidence_ref"]
                self.assertEqual(len(sim["evidence_refs"]), 7)
                for evidence_id in sim["evidence_refs"]:
                    record = records[evidence_id]
                    self.assertEqual(record["derived_from"], [parent])
                    self.assertNotIn("DISPATCH", record["observed_state"])
                    self.assertEqual(hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest(), record["sha256"])
                    parent = evidence_id
                summary = json.loads(Path(records[parent]["path"]).read_text(encoding="utf-8"))
                self.assertEqual(summary["transcript"], sim["transcript"])
                self.assertEqual(summary["stop_reason"], sim["stop_reason"])
                self.assertEqual(summary["evidence_refs"], sim["evidence_refs"][:-1])

    def test_simulation_fixture_strict_validation_before_evidence(self):
        self.write()
        options = self.simulation_args()
        path = options["simulation_fixture_path"]
        valid = json.loads(path.read_text())
        invalid = ([], valid | {"command": "ignored"}, {"rule": valid["rule"]},
                   valid | {"rule": {"expected": "CLEAR", "observed": "CLEAR", "action_id": "unknown"}},
                   valid | {"rule": {"expected": "CLEAR", "observed": []}},
                   valid | {"rule": {"expected": "CLEAR", "observed": "BYPASS"}})
        for value in invalid:
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.run_import(**options)
        for raw in (b"\xff", b'{"rule":0,"rule":1}', b" " * 16385):
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.run_import(**options)
        self.assertEqual(self.evidence(), [])

    def test_simulation_requires_review_scope_and_valid_budget(self):
        self.write()
        options = self.simulation_args()
        for changes in ({"observation_approval": None}, {"observation_approval": self.approval},
                        {"run_approved_actions": {importer.POLICY_ACTION}},
                        *({"simulation_max_steps": value} for value in (True, 0, 4, 1.5, "3")),
                        {"simulation_fixture_path": self.root / "outside.json"}):
            with self.assertRaises(ValueError):
                self.run_import(**(options | changes))
        self.assertEqual(self.evidence(), [])
        for budget in (1, 2):
            sim = self.run_import(**(options | {"simulation_max_steps": budget}))["simulation"]
            self.assertEqual(len(sim["transcript"]), budget)
            self.assertEqual(sim["stop_reason"], "BUDGET_EXHAUSTED" if budget == 1 else "COMPLETED_SIMULATION")

    def test_simulation_time_budget_stops_and_links_pending_intent(self):
        self.write()
        for ticks, count in (([0, 6, 6], 0), ([0, 0, 6, 6], 0),
                             ([0, 0, 0, 6, 6], 1)):
            options = self.simulation_args()
            with patch.object(importer.time, "monotonic", side_effect=ticks):
                result = self.run_import(**options)
            sim = result["simulation"]
            self.assertEqual(sim["stop_reason"], "TIME_BUDGET_EXHAUSTED")
            self.assertEqual(len(sim["transcript"]), count)
            records = {r["evidence_id"]: r for r in self.evidence() if "evidence_id" in r}
            parent = result["observation_evidence_ref"]
            for evidence_id in sim["evidence_refs"]:
                self.assertEqual(records[evidence_id]["derived_from"], [parent])
                parent = evidence_id
        with patch.object(importer.time, "monotonic", side_effect=[0, 0, 0, 0, 0, 0, 6]):
            with self.assertRaisesRegex(ValueError, "SIMULATION_TIME_BUDGET_EXHAUSTED"):
                self.run_import(**self.simulation_args())

    def test_simulation_rechecks_after_every_publication(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        for phase, occurrence in (("SIMULATION_INTENT", 1), ("SIMULATION_RESULT", 1),
                                  ("SIMULATION_INTENT", 2), ("SIMULATION_RESULT", 2),
                                  ("SIMULATION_SUMMARY", 1)):
            for mutation in ("approval", "kill", "policy", "destination"):
                with self.subTest(phase=phase, occurrence=occurrence, mutation=mutation):
                    options = self.simulation_args()
                    self.args["kill_switch"] = KillSwitch()
                    self.args["run_approved_targets"] = {"lab-ecommerce"}
                    saved_directory = self.recorder.directory
                    count = 0
                    def mutate(name, *args, **kwargs):
                        nonlocal count
                        artifact = original(name, *args, **kwargs)
                        if name == phase:
                            count += 1
                            if count == occurrence:
                                if mutation == "approval":
                                    options["observation_approval"].revoke()
                                elif mutation == "kill":
                                    self.args["kill_switch"].activate()
                                elif mutation == "policy":
                                    self.args["run_approved_targets"].clear()
                                else:
                                    self.recorder.directory = self.root
                        return artifact
                    try:
                        with patch.object(self.recorder, "persist_phase_artifact", side_effect=mutate):
                            with self.assertRaises(ValueError):
                                self.run_import(**options)
                    finally:
                        self.recorder.directory = saved_directory
                    self.assertEqual(count, occurrence)

    def test_simulation_write_failure_preserves_prior_evidence(self):
        self.write()
        original = self.recorder.persist_phase_artifact
        for phase in ("SIMULATION_INTENT", "SIMULATION_RESULT", "SIMULATION_SUMMARY"):
            before = {p: p.read_bytes() for p in self.recorder.directory.glob("*.json")}
            def failing(name, *args, **kwargs):
                if name == phase:
                    raise EvidenceFailure("Lỗi ghi simulation được tiêm")
                return original(name, *args, **kwargs)
            with patch.object(self.recorder, "persist_phase_artifact", side_effect=failing):
                with self.assertRaises(EvidenceFailure):
                    self.run_import(**self.simulation_args())
            for path, raw in before.items():
                self.assertEqual(path.read_bytes(), raw)

    def test_simulation_no_dispatch_replay_and_preservation(self):
        self.write()
        options = self.simulation_args("BLOCKED")
        with patch("socket.socket", side_effect=AssertionError("Không socket")) as network, \
             patch("http.client.HTTPConnection", side_effect=AssertionError("Không HTTP")) as http, \
             patch("subprocess.Popen", side_effect=AssertionError("Không subprocess")) as process, \
             patch("runtime.safety.discovery_gate.CentralizedSafetyGate.dispatch", side_effect=AssertionError("Không dispatch")) as dispatch:
            first = self.run_import(**options)
            before = {p: p.read_bytes() for p in self.recorder.directory.glob("*.json")}
            second = self.run_import(**options)
        for spy in (network, http, process, dispatch):
            spy.assert_not_called()
        self.assertNotEqual(first["simulation"]["simulation_id"], second["simulation"]["simulation_id"])
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        fields = ("review_step", "expected", "observed", "mismatch")
        self.assertEqual([{k: e[k] for k in fields} for e in first["simulation"]["transcript"]],
                         [{k: e[k] for k in fields} for e in second["simulation"]["transcript"]])
        self.assertEqual(first["simulation"]["stop_reason"], second["simulation"]["stop_reason"])
        self.assertNotIn("simulation", self.run_import(**self.observation_args()))

    def test_simulation_has_no_runner_planner_or_provider_imports(self):
        import ast
        tree = ast.parse(Path(importer.__file__).read_text(encoding="utf-8"))
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        modules.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
        self.assertEqual(modules, {"__future__", "hashlib", "json", "math", "os", "re", "stat", "time",
                                 "urllib.parse", "uuid", "datetime", "pathlib", "runtime.safety.discovery_gate",
                                 "runtime.evidence.discovery_recorder", "scripts.validation.validate_scaffold",
                                 "shared.schema_validation"})

    def test_fsync_failure_preserves_existing_records(self):
        self.write()
        self.run_import()
        before = {path: path.read_bytes() for path in self.recorder.directory.glob("*.json")}
        self.recorder.inject_fsync_failure()
        with self.assertRaises(EvidenceFailure):
            self.run_import()
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
