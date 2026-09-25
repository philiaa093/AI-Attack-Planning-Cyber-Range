"""Unit tests for TASK-019: Knowledge-state store.

Covers:
- StateManager: apply observations, build state, phase transitions, budget tracking
- ActionLog: immutable append-only log, replay, serialization
- KnowledgeRepository: indexed fact access
- Deterministic reconstruction from history
- No ground-truth tokens present
"""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.memory.state.state_manager import StateManager
from agent.memory.history.action_log import ActionLog
from agent.memory.knowledge_base.knowledge_repo import KnowledgeRepository


# ===================== StateManager Tests =====================

class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.sm = StateManager(
            run_id="RUN-001",
            scenario_id="SCN-001",
            objective_id="OBJ-001",
        )

    def test_initial_state(self):
        state = self.sm.get_state()
        self.assertEqual(state["schema_version"], "1.0")
        self.assertEqual(state["run_id"], "RUN-001")
        self.assertEqual(state["scenario_id"], "SCN-001")
        self.assertEqual(state["phase"], "RECON")
        self.assertEqual(state["observed_facts"], [])
        self.assertEqual(state["previous_actions"], [])

    def test_apply_observation_adds_facts(self):
        obs = {
            "observation_id": "OBS-001",
            "action_id": "ACTION-RECON-001",
            "new_facts": [
                {
                    "fact_id": "F1",
                    "fact_type": "SERVICE",
                    "subject": "lab-sqli-001",
                    "value": "http/80",
                    "confidence": 0.95,
                }
            ],
        }
        self.sm.apply_observation(obs)
        state = self.sm.get_state()
        self.assertEqual(len(state["observed_facts"]), 1)
        self.assertEqual(state["observed_facts"][0]["source_observation_id"], "OBS-001")
        self.assertIn("ACTION-RECON-001", state["previous_actions"])

    def test_budget_decrements(self):
        initial = self.sm.get_state()["remaining_budget"]["actions"]
        obs = {"observation_id": "OBS-002", "action_id": "ACTION-RECON-001", "new_facts": []}
        self.sm.apply_observation(obs)
        state = self.sm.get_state()
        self.assertEqual(state["remaining_budget"]["actions"], initial - 1)

    def test_phase_transition(self):
        self.sm.set_phase("DISCOVERY")
        self.assertEqual(self.sm.phase, "DISCOVERY")
        self.assertEqual(self.sm.get_state()["phase"], "DISCOVERY")

    def test_invalid_phase_rejected(self):
        with self.assertRaises(ValueError):
            self.sm.set_phase("INVALID")

    def test_dedup_keeps_highest_confidence(self):
        obs1 = {
            "observation_id": "OBS-003",
            "action_id": "ACTION-SCAN-001",
            "new_facts": [{
                "fact_id": "F1",
                "fact_type": "CANDIDATE_FINDING",
                "subject": "lab-sqli-001",
                "value": "sqli",
                "confidence": 0.5,
            }],
        }
        obs2 = {
            "observation_id": "OBS-004",
            "action_id": "ACTION-SCAN-002",
            "new_facts": [{
                "fact_id": "F1",
                "fact_type": "CANDIDATE_FINDING",
                "subject": "lab-sqli-001",
                "value": "sqli",
                "confidence": 0.9,
            }],
        }
        self.sm.apply_observation(obs1)
        self.sm.apply_observation(obs2)
        state = self.sm.get_state()
        self.assertEqual(len(state["observed_facts"]), 1)
        self.assertEqual(state["observed_facts"][0]["confidence"], 0.9)

    def test_action_dedup(self):
        obs = {"observation_id": "OBS-005", "action_id": "ACTION-RECON-001", "new_facts": []}
        self.sm.apply_observation(obs)
        self.sm.apply_observation(obs)
        state = self.sm.get_state()
        self.assertEqual(state["previous_actions"].count("ACTION-RECON-001"), 1)

    def test_decrement_requests(self):
        self.sm.decrement_requests(5)
        state = self.sm.get_state()
        self.assertEqual(state["remaining_budget"]["requests"], 495)

    def test_decrement_seconds(self):
        self.sm.decrement_seconds(100.0)
        state = self.sm.get_state()
        self.assertEqual(state["remaining_budget"]["seconds"], 3500.0)

    def test_custom_budget(self):
        sm = StateManager("R", "SCN-001", "O", budget={"actions": 10, "requests": 20, "seconds": 60.0})
        state = sm.get_state()
        self.assertEqual(state["remaining_budget"]["actions"], 10)

    def test_fact_count(self):
        obs = {
            "observation_id": "OBS-006",
            "action_id": "ACTION-RECON-001",
            "new_facts": [
                {"fact_id": "F1", "fact_type": "SERVICE", "subject": "t", "value": "v", "confidence": 0.5},
                {"fact_id": "F2", "fact_type": "ENDPOINT", "subject": "t", "value": "v2", "confidence": 0.5},
            ],
        }
        self.sm.apply_observation(obs)
        self.assertEqual(self.sm.get_fact_count(), 2)

    def test_state_schema_required_fields(self):
        state = self.sm.get_state()
        for field in ["schema_version", "run_id", "scenario_id", "objective_id",
                       "phase", "remaining_budget", "observed_facts"]:
            self.assertIn(field, state)


# ===================== Deterministic Reconstruction =====================

class TestDeterministicReconstruction(unittest.TestCase):
    def test_reconstruct_matches_sequential(self):
        observations = [
            {
                "observation_id": "OBS-001",
                "action_id": "ACTION-RECON-001",
                "new_facts": [
                    {"fact_id": "F1", "fact_type": "SERVICE", "subject": "lab-sqli-001",
                     "value": "http/80", "confidence": 0.95},
                ],
            },
            {
                "observation_id": "OBS-002",
                "action_id": "ACTION-SCAN-001",
                "new_facts": [
                    {"fact_id": "F2", "fact_type": "CANDIDATE_FINDING", "subject": "lab-sqli-001",
                     "value": "sqli", "confidence": 0.9},
                ],
            },
        ]

        # Sequential
        sm1 = StateManager("RUN-001", "SCN-001", "OBJ-001")
        for obs in observations:
            sm1.apply_observation(obs)

        # Reconstructed
        sm2 = StateManager.reconstruct_from_observations(
            observations, "RUN-001", "SCN-001", "OBJ-001"
        )

        self.assertEqual(sm1.get_state(), sm2.get_state())

    def test_reconstruct_from_action_log(self):
        log = ActionLog()
        obs1 = {
            "observation_id": "OBS-001",
            "run_id": "RUN-001",
            "action_id": "ACTION-RECON-001",
            "timestamp_utc": "2025-01-01T00:00:00Z",
            "outcome": "SUCCESS",
            "new_facts": [
                {"fact_id": "F1", "fact_type": "SERVICE", "subject": "lab-sqli-001",
                 "value": "http/80", "confidence": 0.95},
            ],
        }
        log.record_action("RUN-001", "ACTION-RECON-001")
        log.record_observation(obs1)

        # Reconstruct from log replay
        sm = StateManager.reconstruct_from_observations(
            log.replay_observations(), "RUN-001", "SCN-001", "OBJ-001"
        )
        state = sm.get_state()
        self.assertEqual(len(state["observed_facts"]), 1)
        self.assertIn("ACTION-RECON-001", state["previous_actions"])


# ===================== ActionLog Tests =====================

class TestActionLog(unittest.TestCase):
    def setUp(self):
        self.log = ActionLog()

    def test_record_action(self):
        entry = self.log.record_action("RUN-001", "ACTION-RECON-001")
        self.assertEqual(entry["type"], "action")
        self.assertEqual(entry["seq"], 0)

    def test_record_observation(self):
        obs = {"observation_id": "OBS-001", "outcome": "SUCCESS"}
        entry = self.log.record_observation(obs)
        self.assertEqual(entry["type"], "observation")

    def test_sequence_numbers(self):
        self.log.record_action("RUN-001", "ACTION-RECON-001")
        self.log.record_observation({"observation_id": "OBS-001"})
        self.log.record_action("RUN-001", "ACTION-SCAN-001")
        entries = self.log.entries
        self.assertEqual([e["seq"] for e in entries], [0, 1, 2])

    def test_immutability(self):
        self.log.record_action("RUN-001", "ACTION-RECON-001")
        entries = self.log.entries
        entries.clear()  # mutate the copy
        self.assertEqual(len(self.log), 1)  # original unchanged

    def test_observation_deep_copy(self):
        obs = {"observation_id": "OBS-001", "data": [1, 2, 3]}
        self.log.record_observation(obs)
        obs["data"].append(4)  # mutate original
        recorded = self.log.get_observations()[0]["observation"]
        self.assertEqual(recorded["data"], [1, 2, 3])  # not affected

    def test_get_action_ids(self):
        self.log.record_action("RUN-001", "ACTION-RECON-001")
        self.log.record_observation({"observation_id": "OBS-001"})
        self.log.record_action("RUN-001", "ACTION-SCAN-001")
        self.assertEqual(self.log.get_action_ids(), ["ACTION-RECON-001", "ACTION-SCAN-001"])

    def test_json_roundtrip(self):
        self.log.record_action("RUN-001", "ACTION-RECON-001")
        self.log.record_observation({"observation_id": "OBS-001", "outcome": "SUCCESS"})
        json_str = self.log.to_json()
        restored = ActionLog.from_json(json_str)
        self.assertEqual(len(restored), 2)
        self.assertEqual(restored.entries[0]["action_id"], "ACTION-RECON-001")

    def test_replay_observations(self):
        self.log.record_action("RUN-001", "ACTION-RECON-001")
        self.log.record_observation({"observation_id": "OBS-001"})
        self.log.record_action("RUN-001", "ACTION-SCAN-001")
        self.log.record_observation({"observation_id": "OBS-002"})
        replayed = list(self.log.replay_observations())
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[0]["observation_id"], "OBS-001")

    def test_empty_log(self):
        self.assertEqual(len(self.log), 0)
        self.assertEqual(self.log.entries, [])
        self.assertEqual(list(self.log.replay_observations()), [])


# ===================== KnowledgeRepository Tests =====================

class TestKnowledgeRepository(unittest.TestCase):
    def setUp(self):
        self.facts = [
            {"fact_id": "F1", "fact_type": "SERVICE", "subject": "lab-sqli-001",
             "value": "http/80", "confidence": 0.95, "source_observation_id": "OBS-001"},
            {"fact_id": "F2", "fact_type": "ENDPOINT", "subject": "lab-sqli-001",
             "value": "/login", "confidence": 1.0, "source_observation_id": "OBS-001"},
            {"fact_id": "F3", "fact_type": "CANDIDATE_FINDING", "subject": "lab-sqli-001",
             "value": "sqli@/login", "confidence": 0.9, "source_observation_id": "OBS-002"},
            {"fact_id": "F4", "fact_type": "CANDIDATE_FINDING", "subject": "lab-xss-001",
             "value": "xss@/search", "confidence": 0.3, "source_observation_id": "OBS-003"},
            {"fact_id": "F5", "fact_type": "CONFIRMED_FINDING", "subject": "lab-sqli-001",
             "value": "sqli@/admin", "confidence": 0.99, "source_observation_id": "OBS-004"},
        ]
        self.repo = KnowledgeRepository(self.facts)

    def test_all_facts(self):
        self.assertEqual(len(self.repo.all_facts), 5)

    def test_by_type(self):
        services = self.repo.by_type("SERVICE")
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["value"], "http/80")

    def test_by_subject(self):
        sqli_facts = self.repo.by_subject("lab-sqli-001")
        self.assertEqual(len(sqli_facts), 4)

    def test_findings_all(self):
        findings = self.repo.findings()
        self.assertEqual(len(findings), 3)

    def test_findings_with_threshold(self):
        findings = self.repo.findings(min_confidence=0.5)
        self.assertEqual(len(findings), 2)  # F3 (0.9) and F5 (0.99)

    def test_findings_by_type(self):
        sqli = self.repo.findings_by_type("sqli")
        self.assertEqual(len(sqli), 2)  # F3 and F5

    def test_findings_by_type_with_threshold(self):
        sqli = self.repo.findings_by_type("sqli", min_confidence=0.95)
        self.assertEqual(len(sqli), 1)  # Only F5

    def test_services(self):
        self.assertEqual(len(self.repo.services()), 1)

    def test_endpoints(self):
        self.assertEqual(len(self.repo.endpoints()), 1)

    def test_fact_types(self):
        types = self.repo.fact_types()
        self.assertEqual(types, {"SERVICE", "ENDPOINT", "CANDIDATE_FINDING", "CONFIRMED_FINDING"})

    def test_subjects(self):
        subjects = self.repo.subjects()
        self.assertEqual(subjects, {"lab-sqli-001", "lab-xss-001"})

    def test_update(self):
        self.repo.update([{"fact_id": "F99", "fact_type": "SERVICE",
                          "subject": "lab-new", "value": "v", "confidence": 0.5}])
        self.assertEqual(len(self.repo.all_facts), 1)

    def test_empty_repo(self):
        repo = KnowledgeRepository()
        self.assertEqual(repo.all_facts, [])
        self.assertEqual(repo.findings(), [])


# ===================== Ground-Truth Isolation Check =====================

class TestNoGroundTruthInMemory(unittest.TestCase):
    """Verify no forbidden tokens in memory code."""

    FORBIDDEN = re.compile(r"ground[_-]?truth|truth_records|expected_detection", re.IGNORECASE)

    def _check_file(self, path):
        if path.exists():
            content = path.read_text(encoding="utf-8")
            matches = self.FORBIDDEN.findall(content)
            self.assertEqual(matches, [], f"forbidden token in {path}: {matches}")

    def test_state_manager_no_forbidden(self):
        root = Path(__file__).resolve().parents[2]
        self._check_file(root / "agent" / "memory" / "state" / "state_manager.py")

    def test_action_log_no_forbidden(self):
        root = Path(__file__).resolve().parents[2]
        self._check_file(root / "agent" / "memory" / "history" / "action_log.py")

    def test_knowledge_repo_no_forbidden(self):
        root = Path(__file__).resolve().parents[2]
        self._check_file(root / "agent" / "memory" / "knowledge_base" / "knowledge_repo.py")


if __name__ == "__main__":
    unittest.main()
