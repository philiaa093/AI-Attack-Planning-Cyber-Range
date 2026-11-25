"""Acceptance test suite (E01-E09) for SL-11: Evidence packaging, integrity, reporting, and replay.

Tests:
  E01: Existing run/file collision -> Exclusive failure, original bytes/hash unchanged
  E02: Intent/result write/flush failure -> Fail closed, zero dispatch or no next dispatch
  E03: Truncated/tampered/missing reference -> Integrity failure, no verified report/replay
  E04: Secret/PII/session fixture across tree -> Redacted before persistence, zero raw secret occurrences
  E05: Expected differs observed -> Separate fields, no false confirmation
  E06: Retry/duplicate/conflicting observations -> Unique trace or explicit conflict, no overwrite
  E07: Deterministic offline replay -> Zero network/provider dispatch, matching reconstructed state
  E08: Lab report with blocked phases -> Honest provenance/limits, no full-goal claim
  E09: Restore/teardown and historical references -> Evidence retained, historical records read-only
"""
from __future__ import annotations

import copy
import hashlib
import http.server
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from runtime.safety.discovery_gate import (
    ApprovalToken,
    CentralizedSafetyGate,
    DiscoveryRequest,
)
from runtime.evidence.discovery_recorder import (
    DurableEvidenceRecorder,
    EvidenceFailure,
    redact_secrets,
)
from runtime.evidence.evidence_package import (
    EvidenceManifest,
    EvidencePackageError,
    EvidenceVerifier,
    IntegrityError,
    LabReportBuilder,
    NetworkDispatchBlockedError,
    OfflineEvidenceReplayer,
    ZeroNetworkGuard,
)
from runtime.orchestration.ptes_coordinator import (
    CoordinatorReport,
    PTESCoordinator,
    PhaseRecord,
)
from scripts.validation.validate_scaffold import ROOT


class EphemeralMockServer:
    """Loopback mock HTTP server tracking received requests."""

    def __init__(self) -> None:
        self.request_count = 0
        self.last_path = ""
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parent.request_count += 1
                parent.last_path = self.path
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>ShopLab</h1></body></html>")

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)


class EvidenceReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        os.environ["APPROVED_EVIDENCE_ROOT"] = str(self.base_dir.resolve())
        self.mock_server = EphemeralMockServer()

        self.target_id = "lab-ecommerce"
        self.action_id = "ACTION-RECON-002"
        self.run_id = "RUN-SL11-TEST-001"

        self.target_registry = {
            self.target_id: {"host": "127.0.0.1", "port": self.mock_server.port}
        }
        self.target_allowlist = {self.target_id}
        self.action_allowlist = {self.action_id}

        self.approval = ApprovalToken(
            approval_id="APP-SL11-001",
            run_id=self.run_id,
            target_id=self.target_id,
            action_id=self.action_id,
            not_before=time.time() - 10,
            expires_at=time.time() + 300,
        )

    def tearDown(self) -> None:
        os.environ.pop("APPROVED_EVIDENCE_ROOT", None)
        self.mock_server.close()
        self.temp_dir.cleanup()

    def _make_gate(self, recorder: DurableEvidenceRecorder) -> CentralizedSafetyGate:
        return CentralizedSafetyGate(
            base_origin=f"http://127.0.0.1:{self.mock_server.port}",
            target_registry=self.target_registry,
            target_allowlist=self.target_allowlist,
            action_allowlist=self.action_allowlist,
            recorder=recorder,
            lab_mode=True,
        )

    # -------------------------------------------------------------------------
    # E01: Existing run/file collision
    # -------------------------------------------------------------------------
    def test_e01_existing_run_collision(self) -> None:
        """Collision test: exclusive creation fails and original files remain 100% intact."""
        run_dir = self.base_dir / "colliding_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        sentinel_file = run_dir / "existing_artifact.txt"
        sentinel_content = b"ORIGINAL_IMMUTABLE_EVIDENCE_BYTES"
        sentinel_file.write_bytes(sentinel_content)
        original_sha = hashlib.sha256(sentinel_content).hexdigest()

        # Attempting exclusive creation on existing directory must raise EvidenceFailure
        with self.assertRaises(EvidenceFailure) as ctx:
            DurableEvidenceRecorder(
                run_id="colliding_run",
                base_dir=run_dir,
                exclusive_creation=True,
            )
        self.assertIn("already exists", str(ctx.exception).lower())

        # Verify original bytes and hash are completely unchanged
        self.assertTrue(sentinel_file.is_file())
        self.assertEqual(sentinel_file.read_bytes(), sentinel_content)
        current_sha = hashlib.sha256(sentinel_file.read_bytes()).hexdigest()
        self.assertEqual(current_sha, original_sha)

    # -------------------------------------------------------------------------
    # E02: Intent/result write/flush failure
    # -------------------------------------------------------------------------
    def test_e02_write_flush_fsync_failure(self) -> None:
        """Fail-closed test: flush or fsync failure stops dispatch immediately."""
        ev_dir = self.base_dir / "e02_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E02", base_dir=ev_dir)
        gate = self._make_gate(recorder)

        # Create matching approval token for RUN-E02
        e02_approval = ApprovalToken(
            approval_id="APP-E02",
            run_id="RUN-E02",
            target_id=self.target_id,
            action_id=self.action_id,
            not_before=time.time() - 10,
            expires_at=time.time() + 300,
        )

        req = DiscoveryRequest(
            run_id="RUN-E02",
            target_id=self.target_id,
            action_id=self.action_id,
            url=f"http://127.0.0.1:{self.mock_server.port}/",
            approval=e02_approval,
        )

        # Inject flush failure before intent write
        recorder.inject_flush_failure(True)

        resp = gate.dispatch(req)

        self.assertEqual(resp.outcome, "ERROR")
        self.assertEqual(resp.refusal_reason, "INTENT_EVIDENCE_WRITE_FAILED")
        self.assertEqual(self.mock_server.request_count, 0)  # ZERO network dispatch!
        self.assertTrue(gate.halted_due_to_evidence)

        # Subsequent request must be rejected because gate is halted
        resp2 = gate.dispatch(req)
        self.assertEqual(resp2.outcome, "ERROR")
        self.assertEqual(resp2.refusal_reason, "HALTED_DUE_TO_EVIDENCE_FAILURE")
        self.assertEqual(self.mock_server.request_count, 0)

    # -------------------------------------------------------------------------
    # E03: Truncated/tampered/missing reference
    # -------------------------------------------------------------------------
    def test_e03_truncated_tampered_missing_reference(self) -> None:
        """Integrity failure test: tampered, truncated, or missing reference fails verification."""
        ev_dir = self.base_dir / "e03_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E03", base_dir=ev_dir)

        # Persist valid intent and result
        art_intent = recorder.persist_intent({"action_id": "ACTION-RECON-001", "url": "http://127.0.0.1/"})
        art_result = recorder.persist_result(
            {"action_id": "ACTION-RECON-001", "status_code": 200},
            derived_from=[art_intent["evidence_id"]],
        )

        manifest = EvidenceManifest.build_manifest(ev_dir, run_id="RUN-E03")
        self.assertEqual(manifest["records_count"], 2)

        # Clean verification should pass
        v_res = EvidenceVerifier.verify_directory(ev_dir)
        self.assertTrue(v_res.passed)
        self.assertEqual(v_res.verified_records_count, 2)

        # Case A: Tamper 1 byte in result payload
        result_payload_path = Path(art_result["payload_path"])
        original_bytes = result_payload_path.read_bytes()
        tampered_bytes = original_bytes + b" "
        result_payload_path.write_bytes(tampered_bytes)

        v_tampered = EvidenceVerifier.verify_directory(ev_dir)
        self.assertFalse(v_tampered.passed)
        self.assertTrue(any("HASH_MISMATCH" in err for err in v_tampered.errors))

        # Replay must fail on tampered directory
        replay_res = OfflineEvidenceReplayer.replay_run(ev_dir)
        self.assertFalse(replay_res.success)
        self.assertIn("INTEGRITY_VERIFICATION_FAILED", str(replay_res.error))

        # Restore bytes
        result_payload_path.write_bytes(original_bytes)

        # Case B: Delete payload file
        intent_payload_path = Path(art_intent["payload_path"])
        backup_intent = intent_payload_path.read_bytes()
        intent_payload_path.unlink()

        v_deleted = EvidenceVerifier.verify_directory(ev_dir)
        self.assertFalse(v_deleted.passed)
        self.assertTrue(any("MISSING_PAYLOAD" in err for err in v_deleted.errors))

        # Restore payload
        intent_payload_path.write_bytes(backup_intent)

        # Case C: Inject broken reference
        record_files = list(ev_dir.glob("record-result-*.json"))
        self.assertTrue(len(record_files) > 0)
        rec_data = json.loads(record_files[0].read_text(encoding="utf-8"))
        rec_data["derived_from"] = ["EV-NONEXISTENT-REFERENCE-1234"]
        record_files[0].write_text(json.dumps(rec_data), encoding="utf-8")

        v_ref = EvidenceVerifier.verify_directory(ev_dir)
        self.assertFalse(v_ref.passed)
        self.assertFalse(v_ref.reference_graph_ok)
        self.assertTrue(any("MISSING_REFERENCE" in err for err in v_ref.errors))

    # -------------------------------------------------------------------------
    # E04: Secret/PII/session fixture across tree
    # -------------------------------------------------------------------------
    def test_e04_secret_redaction_across_tree(self) -> None:
        """Redaction test: zero unredacted raw secrets in payloads, records, manifests, or reports."""
        ev_dir = self.base_dir / "e04_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E04", base_dir=ev_dir)

        synthetic_password = "super_secret_password_12345"
        synthetic_session = "session_token_xyz_98765"
        synthetic_bearer = "Bearer secret_bearer_token_abc123"
        synthetic_email = "admin_synthetic@shoplab.local"
        synthetic_query = "?password=raw_secret_password_val"

        # Ingest payload with various secret forms
        secret_payload = {
            "password": synthetic_password,
            "session": synthetic_session,
            "authorization": synthetic_bearer,
            "user_email": synthetic_email,
            "request_url": f"http://127.0.0.1:18088/login{synthetic_query}",
            "nested_auth": {
                "api_key": "api_key_secret_fixture_value",
                "csrf_token": "csrf_token_fixture_value",
            },
        }

        art = recorder.persist_phase_artifact("phase2_intel", secret_payload)
        manifest = EvidenceManifest.build_manifest(ev_dir, run_id="RUN-E04")

        # Generate report
        coord_rep = {
            "run_id": "RUN-E04",
            "target_id": "lab-ecommerce",
            "phases": {"PHASE_1": {"outcome": "COMPLETED"}},
            "pipeline_control_completed": True,
            "full_ptes_assessment_completed": False,
            "evidence_refs": [art["evidence_id"]],
        }
        LabReportBuilder.build_report(coord_rep, ev_dir, manifest=manifest)

        # Scan 100% of files in evidence directory for any raw secret substring
        raw_secret_strings = [
            synthetic_password,
            synthetic_session,
            "secret_bearer_token_abc123",
            synthetic_email,
            "raw_secret_password_val",
            "api_key_secret_fixture_value",
            "csrf_token_fixture_value",
        ]

        for f_path in ev_dir.rglob("*"):
            if f_path.is_file():
                content = f_path.read_text(encoding="utf-8", errors="ignore")
                for s in raw_secret_strings:
                    self.assertNotIn(
                        s,
                        content,
                        f"Raw secret '{s}' found unredacted in file '{f_path.name}'",
                    )

        # Verification check should pass secrets_clean
        v_res = EvidenceVerifier.verify_directory(ev_dir)
        self.assertTrue(v_res.secrets_clean)

    def test_response_snippet_omitted_before_temporary_write_and_hash(self) -> None:
        """Do not persist response bodies, including malformed or truncated secret markup."""
        ev_dir = self.base_dir / "response_redaction_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-BODY-REDACTION", base_dir=ev_dir)
        secret = "syntheticCsrfSecret123456789"
        examples = (
            f"<input type='hidden' name='csrf_token' value='{secret}'>",
            f'<input value="{secret}" type="hidden" name="csrf_token">',
            f'<input value={secret} name=csrf_token>',
            json.dumps({"csrf_token": secret}),
            f"<input name='csrf_token' value='{secret}",
        )
        real_replace = os.replace
        temporary_writes = []
        def observe_temporary_file(src, dst):
            temporary_writes.append(Path(src).read_bytes())
            real_replace(src, dst)

        for index, body in enumerate(examples):
            with self.subTest(body_type=index):
                original = {"run_id": "RUN-BODY-REDACTION", "body_snippet": body,
                            "status_code": 200, "body_bytes": len(body), "truncated": True,
                            "headers": {"Set-Cookie": "session=" + secret, "Content-Type": "text/html"},
                            "nested": [{" BoDy_SnIpPeT ": {"value": secret}}]}
                with patch("runtime.evidence.discovery_recorder.os.replace", side_effect=observe_temporary_file):
                    artifact = recorder.persist_result(original)
                raw_payload = Path(artifact["payload_path"]).read_bytes()
                payload = json.loads(raw_payload)
                self.assertEqual(payload["body_snippet"], "[BODY_SNIPPET_OMITTED]")
                self.assertEqual(payload["nested"][0][" BoDy_SnIpPeT "], "[BODY_SNIPPET_OMITTED]")
                self.assertEqual(payload["status_code"], 200)
                self.assertEqual(payload["body_bytes"], len(body))
                self.assertTrue(payload["truncated"])
                self.assertEqual(payload["headers"]["Content-Type"], "text/html")
                self.assertEqual(payload["headers"]["Set-Cookie"], "[REDACTED]")
                self.assertEqual(hashlib.sha256(raw_payload).hexdigest(), artifact["sha256"])
                self.assertEqual(original["body_snippet"], body)

        self.assertEqual(len(temporary_writes), 2 * len(examples))
        for raw in temporary_writes:
            self.assertNotIn(secret.encode(), raw)
        for path in ev_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret.encode(), path.read_bytes())

    def test_failed_partial_response_write_leaves_no_raw_snippet(self) -> None:
        ev_dir = self.base_dir / "partial_response_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-BODY-PARTIAL", base_dir=ev_dir)
        recorder.inject_partial_write()
        secret = "syntheticPartialCsrf123456789"
        original_unlink = Path.unlink
        temporary_writes = []
        def observe_temporary_file(path, *args, **kwargs):
            if path.parent == ev_dir and path.suffix == ".tmp" and path.exists():
                temporary_writes.append(path.read_bytes())
            return original_unlink(path, *args, **kwargs)
        with patch("pathlib.Path.unlink", autospec=True, side_effect=observe_temporary_file):
            with self.assertRaises(EvidenceFailure):
                recorder.persist_result({"body_snippet": f"<input name='csrf_token' value='{secret}'>"})
        self.assertEqual(len(temporary_writes), 1)
        self.assertNotIn(b"<input", temporary_writes[0])
        self.assertNotIn(b"syntheticPartial", temporary_writes[0])
        for path in ev_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret.encode(), path.read_bytes())
        self.assertFalse(list(ev_dir.glob("*.tmp")))

    # -------------------------------------------------------------------------
    # E05: Expected differs observed
    # -------------------------------------------------------------------------
    def test_e05_expected_differs_observed(self) -> None:
        """Expected vs observed separation: differences are preserved as distinct fields without false confirmation."""
        ev_dir = self.base_dir / "e05_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E05", base_dir=ev_dir)

        # Record where expected != observed
        art = recorder._persist_file(
            prefix="probe",
            payload_data={"endpoint": "/admin", "status_code": 403},
            expected_state="STATUS_200_AUTHORIZED",
            observed_state="STATUS_403_FORBIDDEN",
        )

        record_file = Path(art["record_path"])
        rec_data = json.loads(record_file.read_text(encoding="utf-8"))

        self.assertEqual(rec_data["expected_state"], "STATUS_200_AUTHORIZED")
        self.assertEqual(rec_data["observed_state"], "STATUS_403_FORBIDDEN")
        self.assertNotEqual(rec_data["expected_state"], rec_data["observed_state"])

        v_res = EvidenceVerifier.verify_directory(ev_dir)
        self.assertTrue(v_res.passed)  # Schema valid
        self.assertEqual(len(v_res.discrepancies), 1)
        self.assertEqual(v_res.discrepancies[0]["expected_state"], "STATUS_200_AUTHORIZED")
        self.assertEqual(v_res.discrepancies[0]["observed_state"], "STATUS_403_FORBIDDEN")

    # -------------------------------------------------------------------------
    # E06: Retry/duplicate/conflicting observations
    # -------------------------------------------------------------------------
    def test_e06_retries_and_conflicting_observations(self) -> None:
        """Retries and duplicate handling: distinct retry identities and conflict detection."""
        ev_dir = self.base_dir / "e06_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E06", base_dir=ev_dir)

        # Retries with unique traceable identities
        art_attempt_1 = recorder.persist_result({
            "request_id": "REQ-001-TRY-1",
            "attempt": 1,
            "status_code": 504,
            "outcome": "TIMEOUT",
        })
        art_attempt_2 = recorder.persist_result({
            "request_id": "REQ-001-TRY-2",
            "attempt": 2,
            "status_code": 200,
            "outcome": "SUCCESS",
        })

        self.assertNotEqual(art_attempt_1["evidence_id"], art_attempt_2["evidence_id"])
        self.assertNotEqual(art_attempt_1["payload_path"], art_attempt_2["payload_path"])

        # Conflict test: duplicate evidence_id with conflicting data
        conflict_rec_path = ev_dir / "record-conflict-test.json"
        conflicting_record = {
            "evidence_id": art_attempt_1["evidence_id"],  # Duplicate ID
            "run_id": "RUN-E06",
            "path": art_attempt_2["payload_path"],  # Different payload!
            "sha256": art_attempt_2["sha256"],
            "created_at_utc": art_attempt_2["created_at_utc"],
            "source": "EXECUTOR",
            "redacted": True,
            "expected_state": "DISPATCH_CONFIRMED",
            "observed_state": "DISPATCH_CONFIRMED",
            "derived_from": [],
        }
        conflict_rec_path.write_text(json.dumps(conflicting_record), encoding="utf-8")

        v_res = EvidenceVerifier.verify_directory(ev_dir)
        self.assertFalse(v_res.passed)
        self.assertTrue(len(v_res.conflicts) > 0)
        self.assertTrue(any("CONFLICT_DETECTED" in err for err in v_res.errors))

    # -------------------------------------------------------------------------
    # E07: Deterministic offline replay
    # -------------------------------------------------------------------------
    def test_e07_deterministic_offline_replay_zero_network(self) -> None:
        """Offline replay test: deterministic reconstruction with guaranteed zero network calls."""
        ev_dir = self.base_dir / "e07_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E07", base_dir=ev_dir)

        # Record discovery results
        art_res1 = recorder.persist_result({
            "action_id": "ACTION-RECON-001",
            "url": "http://127.0.0.1:18088/",
            "status_code": 200,
        })
        art_res2 = recorder.persist_result({
            "action_id": "ACTION-RECON-002",
            "url": "http://127.0.0.1:18088/register",
            "status_code": 200,
        })

        manifest = EvidenceManifest.build_manifest(ev_dir, run_id="RUN-E07")

        # Execute offline replay
        replay_res = OfflineEvidenceReplayer.replay_run(ev_dir, expected_run_id="RUN-E07")

        self.assertTrue(replay_res.success)
        self.assertEqual(replay_res.network_dispatch_count, 0)
        self.assertEqual(replay_res.observations_replayed, 2)
        self.assertTrue(replay_res.reconstructed_facts_count >= 2)
        self.assertTrue(replay_res.proposal_matched)

        # Verify that ZeroNetworkGuard actually blocks network attempts
        with self.assertRaises(NetworkDispatchBlockedError):
            with ZeroNetworkGuard():
                import urllib.request
                urllib.request.urlopen("http://127.0.0.1:18088/")

    # -------------------------------------------------------------------------
    # E08: Lab report with blocked phases
    # -------------------------------------------------------------------------
    def test_e08_lab_report_honesty_and_blocked_phases(self) -> None:
        """Report honesty test: blocked phases, rule provenance, confirmed=0, bounded scope disclaimer."""
        ev_dir = self.base_dir / "e08_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E08", base_dir=ev_dir)

        # Simulate coordinator report where Phase 5 is BLOCKED
        p1 = PhaseRecord("RUN-E08", "PHASE-01", "PRE_ENGAGEMENT", "2026-10-11T00:00:00Z", outcome="COMPLETED")
        p5 = PhaseRecord(
            "RUN-E08",
            "PHASE-05",
            "EXPLOITATION",
            "2026-10-11T00:01:00Z",
            outcome="BLOCKED",
            transition_reason="NO_APPROVED_CAPABILITY",
            limitations=["Exploitation not authorized"],
        )
        p6 = PhaseRecord(
            "RUN-E08",
            "PHASE-06",
            "POST_EXPLOITATION",
            "2026-10-11T00:01:30Z",
            outcome="NOT_RUN",
            transition_reason="EXPLOITATION_NOT_PERFORMED",
        )

        coord_rep = CoordinatorReport(
            run_id="RUN-E08",
            target_id="lab-ecommerce",
            phases={
                "PHASE_1": asdict(p1),
                "PHASE_5": asdict(p5),
                "PHASE_6": asdict(p6),
            },
            pipeline_control_completed=True,
            full_ptes_assessment_completed=False,  # Transparent honest assessment
            budget_initial={"requests": 50, "pages": 20},
            budget_consumed={"requests": 8, "pages": 4},
            budget_remaining={"requests": 42, "pages": 16},
            observed_inventory_count=4,
            hypotheses_count=2,
            candidate_findings_count=2,
            negative_results_count=1,
            confirmed_findings_count=0,  # MUST be 0
            blocked_operations_count=1,
            network_dispatch_count=8,
            unsafe_dispatch_count=0,
            evidence_refs=["EV-P1-001", "EV-P5-001"],
            coverage_limitations=["Bounded safe non-destructive discovery only"],
            unresolved_items=["Exploitation verification unresolved"],
            planner_provenance={
                "requested_mode": "HYBRID",
                "actual_mode": "RULE",
                "provider": "rule_engine",
                "fallback_reason": "NO_LLM_KEY",
            },
        )

        md_path, json_path = LabReportBuilder.build_report(coord_rep, ev_dir)

        self.assertTrue(md_path.is_file())
        self.assertTrue(json_path.is_file())

        md_content = md_path.read_text(encoding="utf-8")
        json_data = json.loads(json_path.read_text(encoding="utf-8"))

        # Verify title & disclaimers
        self.assertTrue(md_content.startswith("# LAB RESEARCH REPORT"))
        self.assertIn("LAB RESEARCH REPORT ONLY", json_data["disclaimer"])
        self.assertIn("LAB RESEARCH EVALUATION ONLY", md_content)

        # Verify honest status claims
        self.assertFalse(json_data["full_ptes_assessment_completed"])
        self.assertTrue(json_data["pipeline_control_completed"])
        self.assertEqual(json_data["findings_summary"]["confirmed_vulnerabilities"], 0)

        # Verify Phase 5 BLOCKED and Phase 6 NOT_RUN
        self.assertIn("**BLOCKED**", md_content)
        self.assertIn("NO_APPROVED_CAPABILITY", md_content)
        self.assertIn("**NOT_RUN**", md_content)

        # Verify planner fallback provenance
        self.assertEqual(json_data["planner_provenance"]["actual_mode"], "RULE")
        self.assertEqual(json_data["planner_provenance"]["fallback_reason"], "NO_LLM_KEY")

    # -------------------------------------------------------------------------
    # E09: Restore/teardown evidence preservation
    # -------------------------------------------------------------------------
    def test_e09_restore_evidence_preservation(self) -> None:
        """Teardown/restore test: simulated range reset leaves evidence directory untouched."""
        ev_dir = self.base_dir / "e09_evidence"
        recorder = DurableEvidenceRecorder(run_id="RUN-E09", base_dir=ev_dir)

        art = recorder.persist_result({"action_id": "ACTION-RECON-001", "status_code": 200})
        payload_file = Path(art["payload_path"])
        original_hash = hashlib.sha256(payload_file.read_bytes()).hexdigest()

        # Simulate cyber-range container reset / volume cleanup outside evidence dir
        mock_runtime_volume = self.base_dir / "cyber_range_runtime"
        mock_runtime_volume.mkdir()
        (mock_runtime_volume / "app.db").write_text("MUTABLE_APP_DATA")

        # Range reset empties app runtime directory
        shutil.rmtree(mock_runtime_volume)

        # Verify evidence remains byte-for-byte identical
        self.assertTrue(payload_file.is_file())
        current_hash = hashlib.sha256(payload_file.read_bytes()).hexdigest()
        self.assertEqual(current_hash, original_hash)

    # -------------------------------------------------------------------------
    # B01: Absolute outside path escape
    # -------------------------------------------------------------------------
    def test_b01_absolute_outside_path_rejected(self) -> None:
        """B01: custom base_dir outside approved root fails with EvidenceFailure, no writes outside root."""
        app_root = self.base_dir / "approved_evidence"
        app_root.mkdir(parents=True, exist_ok=True)
        outside_dir = self.base_dir / "unauthorized_outside_dir"

        with self.assertRaises(EvidenceFailure) as ctx:
            DurableEvidenceRecorder(
                run_id="RUN-B01",
                base_dir=outside_dir,
                approved_root=app_root,
            )
        self.assertIn("escape rejected", str(ctx.exception).lower())
        self.assertFalse(outside_dir.exists())

    # -------------------------------------------------------------------------
    # B02: Parent traversal ('..') escape
    # -------------------------------------------------------------------------
    def test_b02_dotdot_escape_rejected(self) -> None:
        """B02: destination path whose normalized components leave approved root is rejected."""
        app_root = self.base_dir / "approved_evidence"
        app_root.mkdir(parents=True, exist_ok=True)
        dotdot_dir = app_root / "subdir" / ".." / ".." / "escaped_destination"

        with self.assertRaises(EvidenceFailure) as ctx:
            DurableEvidenceRecorder(
                run_id="RUN-B02",
                base_dir=dotdot_dir,
                approved_root=app_root,
            )
        self.assertIn("escape rejected", str(ctx.exception).lower())
        self.assertFalse(dotdot_dir.exists())

    # -------------------------------------------------------------------------
    # B03: Symlink escape
    # -------------------------------------------------------------------------
    def test_b03_symlink_escape_rejected(self) -> None:
        """B03: child symlink pointing outside approved root is rejected."""
        app_root = self.base_dir / "approved_evidence"
        app_root.mkdir(parents=True, exist_ok=True)
        outside_target = self.base_dir / "outside_symlink_target"
        outside_target.mkdir(parents=True, exist_ok=True)
        symlink_link = app_root / "symlink_child"

        try:
            os.symlink(outside_target, symlink_link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"UNVERIFIED_PLATFORM_LIMITATION: symlink creation not permitted ({exc})")

        with self.assertRaises(EvidenceFailure) as ctx:
            DurableEvidenceRecorder(
                run_id="RUN-B03",
                base_dir=symlink_link / "run_payloads",
                approved_root=app_root,
            )
        self.assertTrue(
            "escape rejected" in str(ctx.exception).lower() or "outside approved root" in str(ctx.exception).lower()
        )

    # -------------------------------------------------------------------------
    # B04: Valid child path
    # -------------------------------------------------------------------------
    def test_b04_valid_child_path_allowed(self) -> None:
        """B04: destination strictly inside approved root is allowed."""
        app_root = self.base_dir / "approved_evidence"
        app_root.mkdir(parents=True, exist_ok=True)
        valid_dest = app_root / "runtime" / "RUN-B04"

        recorder = DurableEvidenceRecorder(
            run_id="RUN-B04",
            base_dir=valid_dest,
            approved_root=app_root,
        )
        self.assertEqual(recorder.directory, valid_dest.resolve())
        self.assertTrue(recorder.directory.is_dir())

    # -------------------------------------------------------------------------
    # B05: Aborted run preservation and collision rejection (Recurrence Protection)
    # -------------------------------------------------------------------------
    def test_b05_aborted_run_preservation_and_collision_rejection(self) -> None:
        """B05: An aborted/failed run must be preserved intact; retrying with the same ID must fail collision."""
        app_root = self.base_dir / "approved_evidence"
        app_root.mkdir(parents=True, exist_ok=True)
        run_id = "RUN-FAIL-PRESERVE-001"
        dest_1 = app_root / "runtime" / run_id

        # 1. Initialize run under exclusive creation
        rec_1 = DurableEvidenceRecorder(
            run_id=run_id,
            base_dir=dest_1,
            approved_root=app_root,
            exclusive_creation=True,
        )

        # 2. Persist at least one valid artifact
        art = rec_1.persist_intent({
            "action_id": "ACTION-RECON-001",
            "url": "http://127.0.0.1:18088/",
        })
        written_file = Path(art["payload_path"])
        self.assertTrue(written_file.is_file())
        orig_bytes = written_file.read_bytes()
        orig_sha = hashlib.sha256(orig_bytes).hexdigest()

        # 3. Simulate subsequent workflow / coordinator failure
        try:
            raise RuntimeError("SIMULATED_PIPELINE_OR_PHASE_FAILURE")
        except RuntimeError:
            pass  # Pipeline aborted

        # 4. Invariant: run directory and written artifact MUST NOT be deleted
        self.assertTrue(dest_1.is_dir())
        self.assertTrue(written_file.is_file())
        self.assertEqual(hashlib.sha256(written_file.read_bytes()).hexdigest(), orig_sha)

        # 5. Second attempt with the SAME run ID must fail collision under exclusive creation
        with self.assertRaises(EvidenceFailure) as ctx:
            DurableEvidenceRecorder(
                run_id=run_id,
                base_dir=dest_1,
                approved_root=app_root,
                exclusive_creation=True,
            )
        self.assertIn("already exists", str(ctx.exception).lower())

        # 6. Artifact bytes in aborted run remain completely unchanged after rejected retry
        self.assertEqual(hashlib.sha256(written_file.read_bytes()).hexdigest(), orig_sha)

        # 7. Recovery requires a distinct, brand-new run ID
        recovery_run_id = "RUN-FAIL-PRESERVE-002"
        recovery_dest = app_root / "runtime" / recovery_run_id
        rec_2 = DurableEvidenceRecorder(
            run_id=recovery_run_id,
            base_dir=recovery_dest,
            approved_root=app_root,
            exclusive_creation=True,
        )
        self.assertTrue(rec_2.directory.is_dir())
        self.assertNotEqual(rec_1.directory, rec_2.directory)


class DispatchEvidenceLinkTests(unittest.TestCase):
    """Offline contract checks with mocked HTTP and an isolated evidence directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.recorder = DurableEvidenceRecorder(
            "RUN-LINK-TEST", base_dir=self.directory, approved_root=self.directory, source="OPERATOR"
        )
        target, action = "lab-ecommerce", "ACTION-RECON-002"
        self.approval = ApprovalToken("APP-LINK", "RUN-LINK-TEST", target, action,
                                      time.time() - 1, time.time() + 300)
        self.gate = CentralizedSafetyGate(
            base_origin="http://127.0.0.1:18088",
            target_registry={target: {"host": "127.0.0.1", "port": 18088}},
            target_allowlist={target}, canonical_target_allowlist={target},
            action_allowlist={action}, canonical_action_allowlist={action},
            recorder=self.recorder,
        )
        self.req = DiscoveryRequest("RUN-LINK-TEST", target, action,
                                    "http://127.0.0.1:18088/", approval=self.approval)

    def test_each_result_links_its_own_intent_and_redacts(self):
        secret = "syntheticSessionValue123456789"
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.getheaders.return_value = [("Set-Cookie", "session=" + secret)]
            response.read.return_value = b"fixture response"
            first = self.gate.dispatch(self.req)
            second = self.gate.dispatch(self.req)
        self.assertTrue(first.durable_confirmed)
        self.assertTrue(second.durable_confirmed)
        artifacts = self.recorder.artifacts
        self.assertEqual(len(artifacts), 4)
        records = [json.loads(Path(a["record_path"]).read_text(encoding="utf-8")) for a in artifacts]
        self.assertEqual([r["source"] for r in records], ["VALIDATOR", "EXECUTOR"] * 2)
        self.assertEqual(records[1]["derived_from"], [records[0]["evidence_id"]])
        self.assertEqual(records[3]["derived_from"], [records[2]["evidence_id"]])
        self.assertNotEqual(records[0]["evidence_id"], records[2]["evidence_id"])
        self.assertTrue(EvidenceVerifier.verify_directory(self.directory).passed)
        for path in self.directory.iterdir():
            self.assertNotIn(secret.encode(), path.read_bytes())

    def test_missing_intent_id_stops_before_dispatch(self):
        with patch.object(self.recorder, "persist_intent", return_value={}), \
                patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            result = self.gate.dispatch(self.req)
            again = self.gate.dispatch(self.req)
        self.assertEqual(result.refusal_reason, "INTENT_EVIDENCE_WRITE_FAILED")
        self.assertEqual(again.refusal_reason, "HALTED_DUE_TO_EVIDENCE_FAILURE")
        self.assertEqual(self.gate.network_dispatch_count, 0)
        connection.assert_not_called()

    def test_unconfirmed_or_reused_intent_and_unexpected_exception_fail_closed(self):
        existing = self.recorder.persist_intent({"action_id": "ACTION-RECON-002"})
        for bad_result in ({"evidence_id": "EV-INTENT-not-recorded"}, existing,
                           TypeError("legacy recorder has no source argument")):
            with self.subTest(case=type(bad_result).__name__):
                self.gate.halted_due_to_evidence = False
                kwargs = {"side_effect": bad_result} if isinstance(bad_result, Exception) else {"return_value": bad_result}
                with patch.object(self.recorder, "persist_intent", **kwargs), \
                        patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
                    result = self.gate.dispatch(self.req)
                self.assertEqual(result.refusal_reason, "INTENT_EVIDENCE_WRITE_FAILED")
                self.assertTrue(self.gate.halted_due_to_evidence)
                connection.assert_not_called()
        self.assertEqual(self.gate.network_dispatch_count, 0)

    def test_result_failure_stops_later_dispatch(self):
        self.recorder.inject_result_failure()
        with patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.getheaders.return_value = []
            response.read.return_value = b"fixture"
            result = self.gate.dispatch(self.req)
            again = self.gate.dispatch(self.req)
        self.assertEqual(result.refusal_reason, "RESULT_EVIDENCE_WRITE_FAILED")
        self.assertEqual(again.refusal_reason, "HALTED_DUE_TO_EVIDENCE_FAILURE")
        self.assertEqual(self.gate.network_dispatch_count, 1)
        connection.assert_called_once()

    def test_unexpected_result_exception_stops_later_dispatch(self):
        with patch.object(self.recorder, "persist_result", side_effect=TypeError("unexpected recorder error")), \
                patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.getheaders.return_value = []
            response.read.return_value = b"fixture"
            result = self.gate.dispatch(self.req)
            again = self.gate.dispatch(self.req)
        self.assertEqual(result.refusal_reason, "RESULT_EVIDENCE_WRITE_FAILED")
        self.assertEqual(again.refusal_reason, "HALTED_DUE_TO_EVIDENCE_FAILURE")
        self.assertEqual(self.gate.network_dispatch_count, 1)
        connection.assert_called_once()

    def test_unconfirmed_result_stops_later_dispatch(self):
        with patch.object(self.recorder, "persist_result", return_value={}), \
                patch("runtime.safety.discovery_gate.http.client.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.getheaders.return_value = []
            response.read.return_value = b"fixture"
            result = self.gate.dispatch(self.req)
            again = self.gate.dispatch(self.req)
        self.assertEqual(result.refusal_reason, "RESULT_EVIDENCE_WRITE_FAILED")
        self.assertEqual(again.refusal_reason, "HALTED_DUE_TO_EVIDENCE_FAILURE")
        self.assertEqual(self.gate.network_dispatch_count, 1)

    def test_source_override_validated_before_any_write(self):
        art = self.recorder.persist_phase_artifact("fixture", {"x": 1}, source="PLANNER")
        record = json.loads(Path(art["record_path"]).read_text(encoding="utf-8"))
        self.assertEqual(record["source"], "PLANNER")
        self.assertEqual(self.recorder.source, "OPERATOR")
        before = {p.name for p in self.directory.iterdir()}
        for invalid in ("invalid", "", [], 1):
            with self.subTest(invalid=invalid), self.assertRaises(EvidenceFailure):
                self.recorder.persist_result({"x": 1}, source=invalid)
        self.assertEqual({p.name for p in self.directory.iterdir()}, before)
        default = self.recorder.persist_result({"x": 2})
        self.assertEqual(json.loads(Path(default["record_path"]).read_text(encoding="utf-8"))["source"], "OPERATOR")


if __name__ == "__main__":
    unittest.main()
