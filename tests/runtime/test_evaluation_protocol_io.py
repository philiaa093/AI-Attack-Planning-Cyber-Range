"""Pinned protocol loading and existing runner integration; all data is synthetic."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from runtime.evaluation.evaluate_all import demo_protocol, evaluate_all
from runtime.evaluation.evaluation_protocol_io import load_protocol, protocol_document
from runtime.evaluation.evaluation_package import verify_evaluation_package


class ProtocolInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / "protocol.json"
        self.document = protocol_document(demo_protocol())

    def load(self, data=None):
        self.input.write_text(json.dumps(self.document if data is None else data), encoding="utf-8")
        sha = hashlib.sha256(self.input.read_bytes()).hexdigest()
        return load_protocol(self.input, sha, input_root=self.root)

    def test_pinned_protocol_roundtrip_and_zero_network_evaluation(self):
        pinned = self.load()
        self.assertEqual(pinned.protocol.fingerprint(), demo_protocol().fingerprint())
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network")) as net:
            run = evaluate_all(pinned.protocol, self.root / "new-runs",
                               protocol_input_sha256=pinned.input_sha256)
        net.assert_not_called()
        configuration = json.loads((run / "configuration.json").read_text())["observed_state"]
        self.assertEqual(configuration["protocol_input_sha256"], pinned.input_sha256)
        self.assertEqual(configuration["protocol_sha256"], pinned.protocol.fingerprint())
        manifest_sha = hashlib.sha256((run / "manifest.json").read_bytes()).hexdigest()
        verification = verify_evaluation_package(run, manifest_sha)
        self.assertEqual(verification["verified_artifacts"], 11)
        self.assertEqual(verification["experimental_claims"], "UNRESOLVED")
        before = (run / "report.md").read_bytes()
        (run / "report.md").write_bytes(before + b"changed")
        with self.assertRaises(ValueError):
            verify_evaluation_package(run, manifest_sha)
        self.assertEqual((run / "report.md").read_bytes(), before + b"changed")

    def test_wrong_hash_rejected(self):
        self.load()
        with self.assertRaises(ValueError):
            load_protocol(self.input, "0" * 64, input_root=self.root)

    def test_duplicate_and_nonfinite_fields_rejected(self):
        for value in ('{"source":"x","source":"y"}', '{"source":NaN}'):
            self.input.write_text(value, encoding="utf-8")
            sha = hashlib.sha256(self.input.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                load_protocol(self.input, sha, input_root=self.root)

    def test_unknown_fields_or_unmatched_budgets_rejected(self):
        extra = dict(self.document, executor="untrusted")
        budget = copy.deepcopy(self.document)
        budget["splits"]["test"][0]["max_steps"] += 1
        for value in (extra, budget):
            with self.assertRaises(ValueError):
                self.load(value)

    def test_renaming_fixture_does_not_hide_split_contamination(self):
        value = copy.deepcopy(self.document)
        value["splits"]["test"][0]["assets"] = value["splits"]["train"][0]["assets"]
        with self.assertRaises(ValueError):
            self.load(value)

    def test_wrong_root_and_malformed_asset_rejected(self):
        pinned = self.load()
        with self.assertRaises(ValueError):
            load_protocol(self.input, pinned.input_sha256, input_root=self.root / "other")
        value = copy.deepcopy(self.document)
        value["splits"]["test"][0]["assets"] = [["lab-fixture", 1]]
        with self.assertRaises(ValueError):
            self.load(value)

    def test_resource_bounds_and_seed_types_rejected(self):
        for seeds in ([], [True], [1, 1], list(range(101))):
            with self.assertRaises(ValueError):
                self.load(dict(self.document, seeds=seeds))
