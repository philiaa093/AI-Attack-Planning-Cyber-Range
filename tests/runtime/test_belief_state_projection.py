"""Tests for RT-02B Belief State Projection and query interface.

Validates:
A. HOST observation -> known_hosts
B. SERVICE observation -> known_services
C. ACCESS observation -> access_state projection
D. CREDENTIAL observation -> known_credentials (opaque handle, no plaintext secrets)
E. SESSION observation -> sessions (active/closed, no shell/subprocess)
F. REACHABILITY observation -> observed_reachability (directed edges from probe facts)
G. DETECTION_SIGNAL observation -> detection_signals (attacker-visible signals)
H. OBJECTIVE observation -> objective_status (trusted evidence-backed objectives)
I. PLANNER_INFERENCE host hypothesis does NOT become known host
J. PLANNER_INFERENCE credential does NOT become usable credential
K. PLANNER_INFERENCE access does NOT elevate privilege
L. Hypothesis does NOT open visible_target_ids
M. Hidden target allowlist does NOT appear in projection
N. Ground Truth does NOT appear in projection
O. Same observation replay is idempotent and deterministic
P. Projection from same observation sequence is bit-for-bit identical
Q. Provenance trace is complete
R. Integration with StateManager, KnowledgeStateStore, and PlannerStateAdapter
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from agent.memory.state.belief_state import BeliefState, project_belief_state
from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.enterprise_normalizer import EnterpriseObservationNormalizer
from runtime.planners.planner_adapter import PlannerStateAdapter
from runtime.planners.planner_interface import project_visible_targets
from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from scripts.validation.validate_scaffold import ROOT, validate_shape

STATE_SCHEMA = json.loads(
    (ROOT / "agent" / "planner" / "contracts" / "state.schema.json").read_text(encoding="utf-8")
)


class TestBeliefStateProjection(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer = EnterpriseObservationNormalizer()
        self.run_id = "RUN-TEST-001"
        self.action_id = "ACTION-SCAN-001"

    def test_01_host_discovery_populates_known_hosts(self) -> None:
        """Requirement A: HOST observation projects to known_hosts."""
        obs = self.normalizer.normalize_host_discovery(
            [{"host": "host-alpha", "ip": "10.0.1.5", "confidence": 0.95}],
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-HOST-001"],
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        self.assertTrue(belief.is_host_known("host-alpha"))
        host_info = belief.known_hosts["host-alpha"]
        self.assertEqual(host_info["host"], "host-alpha")
        self.assertEqual(host_info["ip"], "10.0.1.5")
        self.assertEqual(host_info["access_level"], "NONE")
        self.assertEqual(host_info["confidence"], 0.95)
        self.assertTrue(len(host_info["provenance"]) > 0)

    def test_02_service_discovery_populates_known_services(self) -> None:
        """Requirement B: SERVICE observation projects to known_services."""
        obs = self.normalizer.normalize_service_discovery(
            [{"host": "host-alpha", "port": 443, "protocol": "https", "confidence": 0.9}],
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-SVC-001"],
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        services = belief.known_services
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["host"], "host-alpha")
        self.assertEqual(services[0]["port"], 443)
        self.assertEqual(services[0]["protocol"], "https")

    def test_03_endpoint_discovery_populates_known_endpoints(self) -> None:
        """Requirement B2: ENDPOINT fact projects to known_endpoints."""
        facts = [{
            "fact_id": "FACT-ENDP-001",
            "fact_type": "ENDPOINT",
            "subject": "host-alpha",
            "value": "/api/v1/auth",
            "confidence": 0.85,
            "source_observation_id": "OBS-001",
        }]
        belief = BeliefState.from_facts(facts)
        self.assertEqual(len(belief.known_endpoints), 1)
        self.assertEqual(belief.known_endpoints[0]["host"], "host-alpha")
        self.assertEqual(belief.known_endpoints[0]["path"], "/api/v1/auth")

    def test_04_access_observation_updates_access_state_monotonically(self) -> None:
        """Requirement C: ACCESS observation updates access_state and known_hosts monotonically."""
        # 1. Discover host first
        obs_host = self.normalizer.normalize_host_discovery(
            ["host-target-01"],
            run_id=self.run_id,
            action_id=self.action_id,
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs_host)
        self.assertEqual(sm.get_belief_state().get_host_access("host-target-01"), "NONE")

        # 2. Gain FOOTHOLD
        obs_foothold = {
            "observation_id": "OBS-ACCE-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-ACCE-001",
                "fact_type": "ACCESS",
                "subject": "host-target-01",
                "value": "FOOTHOLD",
                "confidence": 0.9,
            }],
        }
        sm.apply_observation(obs_foothold)
        self.assertEqual(sm.get_belief_state().get_host_access("host-target-01"), "FOOTHOLD")
        self.assertEqual(sm.get_belief_state().known_hosts["host-target-01"]["access_level"], "FOOTHOLD")

        # 3. Elevate to PRIVILEGED
        obs_priv = {
            "observation_id": "OBS-ACCE-002",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:01:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-ACCE-002",
                "fact_type": "ACCESS",
                "subject": "host-target-01",
                "value": "PRIVILEGED",
                "confidence": 0.95,
            }],
        }
        sm.apply_observation(obs_priv)
        self.assertEqual(sm.get_belief_state().get_host_access("host-target-01"), "PRIVILEGED")

        # 4. Invariant: lower access fact does NOT regress higher confirmed access
        obs_lower = {
            "observation_id": "OBS-ACCE-003",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:02:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-ACCE-003",
                "fact_type": "ACCESS",
                "subject": "host-target-01",
                "value": "USER",
                "confidence": 0.9,
            }],
        }
        sm.apply_observation(obs_lower)
        self.assertEqual(sm.get_belief_state().get_host_access("host-target-01"), "PRIVILEGED")

    def test_05_credential_observation_redacts_secrets_and_transitions_validity(self) -> None:
        """Requirement D: CREDENTIAL observation contains opaque metadata only and transitions state."""
        obs = self.normalizer.normalize_credentials(
            [{
                "principal": "domain_admin",
                "password": "CleartextPassword123!",
                "scope": "CORP.LOCAL",
                "kind": "NTLM_HASH",
                "validity": "VALID",
            }],
            run_id=self.run_id,
            action_id=self.action_id,
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        creds = belief.known_credentials
        self.assertEqual(len(creds), 1)
        cred = creds[0]
        self.assertTrue(cred["credential_id"].startswith("CRED-OPAQ-"))
        self.assertEqual(cred["principal"], "domain_admin")
        self.assertEqual(cred["validity_state"], "VALID")

        # Invariant: Plaintext password never appears in belief state
        belief_json = json.dumps(belief.to_dict())
        self.assertNotIn("CleartextPassword123!", belief_json)

        # Validity transition: mark credential REVOKED
        obs_revoked = {
            "observation_id": "OBS-CRED-REV",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:05:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-CRED-REV",
                "fact_type": "CREDENTIAL",
                "subject": "CORP.LOCAL",
                "value": {
                    "credential_id": cred["credential_id"],
                    "principal": "domain_admin",
                    "credential_kind": "NTLM_HASH",
                    "observed_scope": "CORP.LOCAL",
                    "validity_state": "REVOKED",
                },
                "confidence": 1.0,
            }],
        }
        sm.apply_observation(obs_revoked)
        updated_creds = sm.get_belief_state().known_credentials
        self.assertEqual(updated_creds[0]["validity_state"], "REVOKED")
        self.assertEqual(len(sm.get_belief_state().get_valid_credentials()), 0)

    def test_06_session_observation_sanitizes_handles_and_tracks_state(self) -> None:
        """Requirement E: SESSION observation sanitizes handles and transitions ACTIVE -> CLOSED."""
        obs = self.normalizer.normalize_session(
            [{
                "target_id": "host-alpha",
                "access_level": "USER",
                "state": "ACTIVE",
                "raw_shell": "/bin/bash",
                "subprocess_handle": 12345,
            }],
            run_id=self.run_id,
            action_id=self.action_id,
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        sessions = belief.sessions
        self.assertEqual(len(sessions), 1)
        sess = sessions[0]
        self.assertTrue(sess["session_id"].startswith("SESS-OPAQ-"))
        self.assertEqual(sess["target_id"], "host-alpha")
        self.assertEqual(sess["state"], "ACTIVE")
        self.assertEqual(len(belief.active_sessions), 1)

        # Invariant: Raw shell / process handle must NOT leak into belief state
        belief_json = json.dumps(belief.to_dict())
        self.assertNotIn("/bin/bash", belief_json)
        self.assertNotIn("subprocess_handle", belief_json)

        # Transition: Session closed
        obs_closed = {
            "observation_id": "OBS-SESS-CLOSE",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "timestamp_utc": "2026-10-17T12:10:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-SESS-CLOSE",
                "fact_type": "SESSION",
                "subject": "host-alpha",
                "value": {
                    "session_id": sess["session_id"],
                    "target_id": "host-alpha",
                    "access_level": "USER",
                    "state": "CLOSED",
                },
                "confidence": 1.0,
            }],
        }
        sm.apply_observation(obs_closed)
        self.assertEqual(sm.get_belief_state().sessions[0]["state"], "CLOSED")
        self.assertEqual(len(sm.get_belief_state().active_sessions), 0)

    def test_07_reachability_observation_builds_directed_edge(self) -> None:
        """Requirement F: REACHABILITY observation builds directed edge strictly from probe facts."""
        obs = self.normalizer.normalize_reachability(
            [{"from_host": "host-dmz", "to_host": "host-internal", "protocol": "smb", "confidence": 0.9}],
            run_id=self.run_id,
            action_id=self.action_id,
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        edges = belief.observed_reachability
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["from_host"], "host-dmz")
        self.assertEqual(edges[0]["to_host"], "host-internal")
        self.assertEqual(edges[0]["protocol"], "smb")
        self.assertEqual(belief.get_reachable_from("host-dmz"), ["host-internal"])
        self.assertEqual(belief.get_reachable_from("host-internal"), [])

    def test_08_detection_signal_records_attacker_observable_events(self) -> None:
        """Requirement G: DETECTION_SIGNAL records attacker-observable signals only."""
        obs = self.normalizer.normalize_detection_signal(
            [{"source_target": "host-target", "signal_type": "WAF_REJECTION", "observable_event": "HTTP 403 Forbidden"}],
            run_id=self.run_id,
            action_id=self.action_id,
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        sigs = belief.detection_signals
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["signal_type"], "WAF_REJECTION")
        self.assertEqual(sigs[0]["source_target"], "host-target")

    def test_09_objective_observation_tracks_trusted_progress(self) -> None:
        """Requirement H: OBJECTIVE observation tracks trusted progress with evidence."""
        obs = self.normalizer.normalize_objective(
            [{"objective_id": "OBJ-FLAG-01", "status": "ACHIEVED"}],
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-FLAG-PROOVED-01"],
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        objs = belief.objective_status
        self.assertIn("OBJ-FLAG-01", objs)
        self.assertEqual(objs["OBJ-FLAG-01"]["status"], "ACHIEVED")
        self.assertIn("EV-FLAG-PROOVED-01", objs["OBJ-FLAG-01"]["evidence_refs"])

    def test_10_hypotheses_hard_boundary_planner_inference(self) -> None:
        """Requirements I, J, K: PLANNER_INFERENCE is isolated into hypotheses ONLY.

        Tests that planner inferences cannot self-confirm into:
        - known_hosts
        - known_credentials
        - access_state elevation
        - active sessions
        - observed reachability
        - confirmed findings
        - objective achievement
        """
        inference_obs = {
            "observation_id": "OBS-INFER-001",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "source_kind": "PLANNER_INFERENCE",
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {
                    "fact_id": "FACT-INFER-HOST",
                    "fact_type": "HOST",
                    "subject": "ghost-host-99",
                    "value": "10.99.99.99",
                    "confidence": 0.8,
                },
                {
                    "fact_id": "FACT-INFER-CRED",
                    "fact_type": "CREDENTIAL",
                    "subject": "DOMAIN.FAKE",
                    "value": {
                        "credential_id": "CRED-OPAQ-FAKE",
                        "principal": "fake_admin",
                        "credential_kind": "NTLM_HASH",
                        "observed_scope": "DOMAIN.FAKE",
                        "validity_state": "VALID",
                    },
                    "confidence": 0.8,
                },
                {
                    "fact_id": "FACT-INFER-ACCE",
                    "fact_type": "ACCESS",
                    "subject": "host-alpha",
                    "value": "SYSTEM",
                    "confidence": 0.99,
                },
                {
                    "fact_id": "FACT-INFER-SESS",
                    "fact_type": "SESSION",
                    "subject": "ghost-host-99",
                    "value": {
                        "session_id": "SESS-OPAQ-FAKE",
                        "target_id": "ghost-host-99",
                        "access_level": "SYSTEM",
                        "state": "ACTIVE",
                    },
                    "confidence": 0.9,
                },
                {
                    "fact_id": "FACT-INFER-REACH",
                    "fact_type": "REACHABILITY",
                    "subject": "host-alpha -> ghost-host-99",
                    "value": {"from_host": "host-alpha", "to_host": "ghost-host-99", "protocol": "ssh"},
                    "confidence": 0.9,
                },
                {
                    "fact_id": "FACT-INFER-FIND",
                    "fact_type": "CONFIRMED_FINDING",
                    "subject": "ghost-host-99",
                    "value": {"vuln": "CVE-2024-FAKE"},
                    "confidence": 1.0,
                },
                {
                    "fact_id": "FACT-INFER-OBJ",
                    "fact_type": "OBJECTIVE",
                    "subject": "OBJ-FLAG-FAKE",
                    "value": "ACHIEVED",
                    "confidence": 1.0,
                },
            ],
        }

        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(inference_obs)

        belief = sm.get_belief_state()

        # Invariant I: Host hypothesis is NOT in known_hosts
        self.assertFalse(belief.is_host_known("ghost-host-99"))
        self.assertNotIn("ghost-host-99", belief.known_hosts)

        # Invariant J: Credential hypothesis is NOT in known_credentials
        self.assertEqual(len(belief.known_credentials), 0)

        # Invariant K: Access hypothesis does NOT elevate access
        self.assertEqual(belief.get_host_access("host-alpha"), "NONE")

        # Session hypothesis is NOT in sessions
        self.assertEqual(len(belief.sessions), 0)

        # Reachability hypothesis is NOT in observed_reachability
        self.assertEqual(len(belief.observed_reachability), 0)

        # Finding hypothesis is NOT in confirmed_findings
        self.assertEqual(len(belief.confirmed_findings), 0)

        # Objective hypothesis is NOT in objective_status
        self.assertNotIn("OBJ-FLAG-FAKE", belief.objective_status)

        # ALL 7 facts must reside strictly in hypotheses
        self.assertEqual(len(belief.hypotheses), 7)
        hyp_types = {h["fact_type"] for h in belief.hypotheses}
        self.assertEqual(
            hyp_types,
            {"HOST", "CREDENTIAL", "ACCESS", "SESSION", "REACHABILITY", "CONFIRMED_FINDING", "OBJECTIVE"},
        )

    def test_11_hypotheses_do_not_open_planner_visibility(self) -> None:
        """Requirement L: Hypothesis observations never open visible_target_ids."""
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        # Ingest an inferred target
        sm.apply_observation({
            "observation_id": "OBS-INFER-TGT",
            "run_id": self.run_id,
            "action_id": self.action_id,
            "source_kind": "PLANNER_INFERENCE",
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [{
                "fact_id": "FACT-INFER-TGT",
                "fact_type": "TARGET",
                "subject": "lab-inferred-secret",
                "value": "discovered",
                "confidence": 0.9,
            }],
        })

        visible = project_visible_targets(sm.get_state(), initial_seed="lab-seed-host")
        self.assertIn("lab-seed-host", visible)
        self.assertNotIn("lab-inferred-secret", visible)

    def test_12_isolation_invariants_no_ground_truth(self) -> None:
        """Requirements M, N: Ground Truth keys and hidden allowlists never enter Belief State."""
        facts = [{
            "fact_id": "FACT-CORRUPT-001",
            "fact_type": "HOST",
            "subject": "lab-corrupt",
            "value": {
                "ip": "10.0.0.1",
                "ground_truth": "FLAG{forbidden_truth}",
                "siem_score": 99.9,
            },
            "confidence": 1.0,
            "source_observation_id": "OBS-001",
        }]
        belief_dict = project_belief_state(facts)
        serialized = json.dumps(belief_dict)
        self.assertNotIn("ground_truth", serialized)
        self.assertNotIn("FLAG{forbidden_truth}", serialized)
        self.assertNotIn("siem_score", serialized)

    def test_13_determinism_and_idempotence(self) -> None:
        """Requirements O, P: Replay produces bit-for-bit identical Belief State projection."""
        obs1 = self.normalizer.normalize_host_discovery(
            ["host-b", "host-a"],
            run_id=self.run_id,
            action_id=self.action_id,
        )
        obs2 = self.normalizer.normalize_service_discovery(
            [
                {"host": "host-b", "port": 80, "protocol": "http"},
                {"host": "host-a", "port": 22, "protocol": "ssh"},
            ],
            run_id=self.run_id,
            action_id=self.action_id,
        )

        sm1 = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm1.apply_observation(obs1)
        sm1.apply_observation(obs2)

        sm2 = StateManager.reconstruct_from_observations([obs1, obs2], self.run_id, "SCN-001", "OBJ-001")

        b1 = sm1.get_belief_state()
        b2 = sm2.get_belief_state()

        # Must be bit-for-bit identical
        self.assertEqual(json.dumps(b1.to_dict(), sort_keys=True), json.dumps(b2.to_dict(), sort_keys=True))
        self.assertEqual(b1, b2)

        # PlannerStateAdapter idempotent duplicate replay
        adapter = PlannerStateAdapter(sm1)
        applied = adapter.ingest_observation(obs1)
        self.assertFalse(applied)  # duplicate replay rejected idempotently
        self.assertEqual(adapter.get_belief_state(), b1)

    def test_14_provenance_trace_completeness(self) -> None:
        """Requirement Q: Provenance trace is complete across all belief facts."""
        obs = self.normalizer.normalize_host_discovery(
            ["host-provenance"],
            run_id=self.run_id,
            action_id=self.action_id,
            evidence_refs=["EV-PROV-001"],
        )
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        sm.apply_observation(obs)

        belief = sm.get_belief_state()
        self.assertIn(obs["observation_id"], belief.provenance_refs)
        host_prov = belief.known_hosts["host-provenance"]["provenance"]
        self.assertIn(obs["observation_id"], host_prov)

    def test_15_state_manager_state_schema_conformance(self) -> None:
        """State produced by StateManager validates against state.schema.json."""
        sm = StateManager(self.run_id, "SCN-001", "OBJ-001")
        obs = self.normalizer.normalize_host_discovery(["host-schema"], run_id=self.run_id, action_id=self.action_id)
        sm.apply_observation(obs)

        state = sm.get_state()
        errors = validate_shape(state, STATE_SCHEMA)
        self.assertEqual(errors, [])

    def test_16_knowledge_state_store_belief_state_reconstruction(self) -> None:
        """KnowledgeStateStore get_belief_state integration."""
        ctx = StoreContext("RUN-KSS-001", "SESS-01", "EP-01")
        budget = {"actions": 10, "requests": 50, "seconds": 3600.0}

        obs = self.normalizer.normalize_host_discovery(
            ["host-store"],
            run_id=ctx.run_id,
            action_id=self.action_id,
        )

        with KnowledgeStateStore(":memory:") as store:
            store.create_context(
                ctx,
                scenario_id="SCN-001",
                objective_id="OBJ-001",
                budget=budget,
                allowed_subjects=["host-store"],
                allowed_actions=[self.action_id],
            )
            store.ingest(ctx, obs, source="test", source_sha256="0" * 64)

            belief = store.get_belief_state(ctx)
            self.assertTrue(belief.is_host_known("host-store"))
            self.assertEqual(belief.known_hosts["host-store"]["host"], "host-store")


if __name__ == "__main__":
    unittest.main()
