"""Real normalizer/store/interface integration on pinned synthetic local reports."""
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime.evidence.discovery_recorder import DurableEvidenceRecorder, EvidenceFailure
from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from runtime.evaluation.offline_review_pipeline import OfflineReviewPipeline


class OfflineReviewPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = StoreContext("RUN-OFFLINE-REVIEW-001", "SESSION-1", "EPISODE-1")
        self.target = "lab-sqli-001"
        self.store = KnowledgeStateStore()
        self.addCleanup(self.store.close)
        self.store.create_context(self.context, scenario_id="SCN-001", objective_id="OBJ-REVIEW",
                                  budget=dict(actions=10, requests=20, seconds=60.0),
                                  allowed_subjects={self.target},
                                  allowed_actions={"ACTION-SCAN-002", "ACTION-PLAN-003"})
        self.recorder = DurableEvidenceRecorder(self.context.run_id, base_dir=self.root / "evidence",
                                               approved_root=self.root, source="UNIT_TEST",
                                               exclusive_creation=True)
        self.input = self.root / "report.json"
        self.write_report()
        self.pipeline = self.consumer()

    def consumer(self):
        return OfflineReviewPipeline(self.store, self.context, self.recorder,
                                     input_root=self.root, allowed_targets=frozenset({self.target}),
                                     target_origin=f"http://{self.target}",
                                     template_families={"fixture-sqli": "sqli"})

    def write_report(self, **changes):
        envelope = dict(schema_version="1.0", source="NUCLEI", report_id="REPORT-FIXTURE-1",
                        run_id=self.context.run_id, action_id="ACTION-SCAN-002", target_id=self.target,
                        timestamp_utc="2026-10-13T00:00:00Z", status="SUCCESS", evidence_refs=[],
                        raw_output=[{"template-id": "fixture-sqli", "type": "http",
                                     "host": f"http://{self.target}", "matched-at": f"http://{self.target}/observed",
                                     "matcher-status": True, "info": {"severity": "high", "tags": ["sqli"]}}])
        envelope.update(changes)
        self.input.write_text(json.dumps(envelope), encoding="utf-8")
        self.sha = hashlib.sha256(self.input.read_bytes()).hexdigest()

    def ingest(self):
        return self.pipeline.ingest_report(self.input, self.sha, source="SIMULATED_FIXTURE")

    def test_evidence_before_state_and_schema_bound_proposal_with_zero_transport(self):
        original = self.store.ingest
        def check_persistence(*args, **kwargs):
            self.assertEqual(len(list(self.recorder.directory.glob("record-*.json"))), 1)
            return original(*args, **kwargs)
        budget = self.store.get_state(self.context)["remaining_budget"]
        with patch.object(self.store, "ingest", side_effect=check_persistence), \
                patch.object(socket.socket, "connect", side_effect=AssertionError("network")) as net, \
                patch.object(subprocess, "Popen", side_effect=AssertionError("process")) as process:
            self.assertTrue(self.ingest())
            after_ingest = self.store.get_state(self.context)["remaining_budget"]
            decision = self.pipeline.propose_review()
        net.assert_not_called(); process.assert_not_called()
        self.assertEqual(decision.actual_mode, "RULE")
        self.assertEqual(decision.proposal.to_dict()["action_id"], "ACTION-PLAN-003")
        self.assertEqual(len(decision.proposal.to_dict()["evidence_refs"]), 1)
        self.assertEqual(after_ingest, dict(budget, actions=budget["actions"] - 1))
        self.assertEqual(self.store.get_state(self.context)["remaining_budget"], after_ingest)
        facts = self.store.get_state(self.context)["observed_facts"]
        self.assertEqual(facts[0]["fact_type"], "CANDIDATE_FINDING")
        self.assertEqual(facts[0]["confidence"], 0.0)

    def test_retry_and_consumer_restart_preserve_receipt_and_state(self):
        self.ingest()
        before = self.store.reconstruct(self.context)
        records = {p.name:p.read_bytes() for p in self.recorder.directory.iterdir()}
        self.assertFalse(self.ingest())
        self.assertFalse(self.consumer().ingest_report(self.input, self.sha, source="SIMULATED_FIXTURE"))
        self.assertEqual(self.store.reconstruct(self.context), before)
        self.assertEqual({p.name:p.read_bytes() for p in self.recorder.directory.iterdir()}, records)

    def test_persistence_failure_never_ingests_and_stays_halted(self):
        before = self.store.get_state(self.context)
        with patch.object(self.recorder, "persist_phase_artifact", side_effect=EvidenceFailure("fixture failure")):
            with self.assertRaises(EvidenceFailure):
                self.ingest()
        self.assertEqual(self.store.get_state(self.context), before)
        with self.assertRaises(EvidenceFailure):
            self.pipeline.propose_review()

    def test_hash_mismatch_and_cross_run_rejected_before_state(self):
        for change in ("hash", "run"):
            consumer = self.consumer()
            if change == "hash":
                self.input.write_text("{}", encoding="utf-8")
            else:
                self.write_report(run_id="RUN-OTHER")
            with self.assertRaises(ValueError):
                consumer.ingest_report(self.input, self.sha, source="SIMULATED_FIXTURE")
            self.assertEqual(self.store.observations(self.context), [])

    def test_tampered_normalization_evidence_blocks_proposal_and_keeps_bytes(self):
        self.ingest()
        payload = next(self.recorder.directory.glob("offline_normalization-*.json"))
        payload.write_text("changed", encoding="utf-8")
        with self.assertRaises(EvidenceFailure):
            self.pipeline.propose_review()
        self.assertEqual(payload.read_text("utf-8"), "changed")

    def test_replay_provenance_cannot_change(self):
        self.ingest()
        with self.assertRaises(ValueError):
            self.consumer().ingest_report(self.input, self.sha, source="IMPORTED_OFFLINE")

    def test_unverified_input_references_rejected(self):
        self.write_report(evidence_refs=["EV-UNVERIFIED"])
        with self.assertRaises(ValueError):
            self.ingest()
        self.assertEqual(self.store.observations(self.context), [])
