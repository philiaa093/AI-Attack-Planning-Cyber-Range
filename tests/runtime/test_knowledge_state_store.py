"""Offline TASK-019 SQLite compatibility, isolation and durability tests."""
import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from runtime.state.knowledge_state_store import KnowledgeStateStore, StoreContext
from scripts.validation.validate_scaffold import validate_shape


SOURCE_HASH = hashlib.sha256(b"synthetic-normalized-fixture").hexdigest()


def observation(number=1, *, run_id="RUN-019", confidence=0.8):
    return dict(observation_id=f"OBS-{number}", run_id=run_id,
                action_id="ACTION-RECON-001", timestamp_utc="2026-10-11T00:00:00Z",
                outcome="SUCCESS", evidence_refs=[], new_facts=[
                    dict(fact_id=f"F-{number}", fact_type="ENDPOINT", subject="lab-fixture",
                         value=f"/page-{number}", confidence=confidence)])


def register(store, context):
    return store.create_context(context, scenario_id="SCN-001", objective_id="OBJ-019",
                                budget=dict(actions=10, requests=20, seconds=60.0),
                                allowed_subjects={"lab-fixture"},
                                allowed_actions={"ACTION-RECON-001"})


def ingest(store, context, obs=None, **kwargs):
    return store.ingest(context, obs or observation(), source="NORMALIZED-FIXTURE",
                        source_sha256=SOURCE_HASH, **kwargs)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = KnowledgeStateStore()
        self.context = StoreContext("RUN-019", "SESSION-1", "EPISODE-1")
        register(self.store, self.context)
        self.addCleanup(self.store.close)

    def test_state_and_indexed_assets(self):
        ingest(self.store, self.context, requests=2, seconds=1.5, phase="DISCOVERY")
        state = self.store.get_state(self.context)
        self.assertFalse(validate_shape(state, self.store._state_schema))
        self.assertEqual(state["remaining_budget"], dict(actions=9, requests=18, seconds=58.5))
        self.assertEqual(state["phase"], "DISCOVERY")
        self.assertEqual(self.store.list_assets(self.context),
                         [dict(target_id="lab-fixture", fact_count=1)])
        facts = self.store.query_facts(self.context, subject="lab-fixture", fact_type="ENDPOINT")
        self.assertEqual(facts[0]["source_observation_id"], "OBS-1")
        self.assertEqual(self.store.reconstruct(self.context), state)

    def test_duplicate_does_not_charge_budget(self):
        ingest(self.store, self.context, requests=2, seconds=1)
        before = self.store.get_state(self.context)
        self.assertFalse(ingest(self.store, self.context, requests=2, seconds=1.0))
        self.assertEqual(self.store.get_state(self.context), before)
        self.assertEqual(len(self.store.observations(self.context)), 1)

    def test_conflicting_payload_and_accounting_are_atomic(self):
        ingest(self.store, self.context)
        before = self.store.get_state(self.context)
        conflicting = observation()
        conflicting["outcome"] = "ERROR"
        for obs, cost in [(conflicting, 0), (observation(), 1)]:
            with self.assertRaisesRegex(ValueError, "conflicting observation"):
                ingest(self.store, self.context, obs, requests=cost)
        self.assertEqual(before, self.store.get_state(self.context))

    def test_fact_conflict_preserves_journal(self):
        ingest(self.store, self.context)
        obs = observation(2)
        obs["new_facts"][0]["fact_id"] = "F-1"
        with self.assertRaisesRegex(ValueError, "conflicting fact"):
            ingest(self.store, self.context, obs)
        self.assertEqual(len(self.store.observations(self.context)), 1)

    def test_same_fact_semantics_keep_highest_confidence_and_provenance(self):
        ingest(self.store, self.context)
        for number, confidence in [(2, 0.9), (3, 0.7)]:
            obs = observation()
            obs["observation_id"] = f"OBS-{number}"
            obs["new_facts"][0]["confidence"] = confidence
            ingest(self.store, self.context, obs)
        fact = self.store.query_facts(self.context)[0]
        self.assertEqual(fact["confidence"], 0.9)
        self.assertEqual(fact["source_observation_id"], "OBS-2")
        self.assertEqual(len(self.store.observations(self.context)), 3)

    def test_run_session_episode_isolation(self):
        ingest(self.store, self.context)
        for ctx in [StoreContext("RUN-019", "SESSION-2", "EPISODE-1"),
                    StoreContext("RUN-019", "SESSION-1", "EPISODE-2"),
                    StoreContext("RUN-020", "SESSION-1", "EPISODE-1")]:
            register(self.store, ctx)
            self.assertEqual(self.store.list_assets(ctx), [])
            ingest(self.store, ctx, observation(run_id=ctx.run_id))
            self.assertEqual(self.store.get_state(ctx)["remaining_budget"]["actions"], 9)
        self.assertEqual(self.store.get_state(self.context)["remaining_budget"]["actions"], 9)

    def test_scope_and_schema_rejections_leave_state_unchanged(self):
        original = self.store.get_state(self.context)
        invalid = []
        for key, value in [("run_id", "RUN-OTHER"), ("action_id", "ACTION-RECON-999"),
                           ("expected_state", {}), ("timestamp_utc", "2026-10-11T07:00:00+07:00")]:
            obs = observation()
            obs[key] = value
            invalid.append(obs)
        for key, value in [("subject", "outside-scope"), ("confidence", float("nan")),
                           ("value", "password=syntheticsecret"), ("confidence", True)]:
            obs = observation()
            obs["new_facts"][0][key] = value
            invalid.append(obs)
        obs = observation()
        obs["new_facts"] *= 2
        invalid.append(obs)
        invalid.extend([None, [], {"observation_id": "OBS-1"}])
        for obs in invalid:
            with self.subTest(obs=obs):
                with self.assertRaises(ValueError):
                    self.store.ingest(self.context, obs, source="FIXTURE", source_sha256=SOURCE_HASH)
        self.assertEqual(original, self.store.get_state(self.context))
        self.assertEqual(self.store.observations(self.context), [])

    def test_invalid_costs_phase_and_provenance(self):
        for kwargs in [dict(requests=-1), dict(requests=True), dict(seconds=-1),
                       dict(seconds=float("inf")), dict(seconds=True), dict(phase="UNKNOWN")]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ingest(self.store, self.context, **kwargs)
        with self.assertRaises(ValueError):
            self.store.ingest(self.context, observation(), source="FIXTURE", source_sha256="invalid")

    def test_timestamp_and_hash_case_canonicalization(self):
        ingest(self.store, self.context)
        obs = observation()
        obs["timestamp_utc"] = "2026-10-11T00:00:00+00:00"
        self.assertFalse(self.store.ingest(self.context, obs, source="NORMALIZED-FIXTURE",
                                          source_sha256=SOURCE_HASH.upper()))

    def test_input_and_output_cannot_mutate_storage(self):
        obs = observation()
        ingest(self.store, self.context, obs)
        obs["new_facts"][0]["value"] = "changed"
        self.store.get_state(self.context)["observed_facts"].clear()
        self.store.query_facts(self.context)[0]["value"] = "changed"
        self.store.observations(self.context)[0]["envelope"].clear()
        self.assertEqual(self.store.query_facts(self.context)[0]["value"], "/page-1")

    def test_filtered_pagination_and_parameterized_queries(self):
        for number in range(1, 4):
            ingest(self.store, self.context, observation(number, confidence=number / 4))
        self.assertEqual(len(self.store.query_facts(self.context, min_confidence=0.5)), 2)
        self.assertEqual(self.store.query_facts(self.context, limit=1, offset=1)[0]["fact_id"], "F-2")
        self.assertEqual(len(self.store.observations(self.context, limit=1, offset=2)), 1)
        with self.assertRaises(ValueError):
            self.store.query_facts(self.context, subject="' OR 1=1 --")
        for kwargs in [dict(limit=0), dict(limit=1001), dict(offset=-1),
                       dict(fact_type="UNKNOWN"), dict(min_confidence=float("nan"))]:
            with self.assertRaises(ValueError):
                self.store.query_facts(self.context, **kwargs)

    def test_journal_sql_update_and_delete_rejected(self):
        ingest(self.store, self.context)
        for sql in ["UPDATE observations SET sha256 = 'changed'", "DELETE FROM observations"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.store._db.execute(sql)
        self.assertEqual(self.store.reconstruct(self.context), self.store.get_state(self.context))

    def test_write_failure_rolls_back_all_projections(self):
        before = self.store.get_state(self.context)
        self.store._db.execute("""CREATE TEMP TRIGGER fail_facts BEFORE INSERT ON facts
            BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            ingest(self.store, self.context)
        self.assertEqual(self.store.observations(self.context), [])
        self.assertEqual(self.store.list_assets(self.context), [])
        self.assertEqual(self.store.get_state(self.context), before)

    def test_snapshot_mismatch_blocks_reconstruction_and_new_ingestion(self):
        self.store._db.execute("UPDATE contexts SET state = '{}' WHERE context_id = ?", (self.context.key,))
        for call in [lambda: self.store.reconstruct(self.context),
                     lambda: ingest(self.store, self.context)]:
            with self.assertRaisesRegex(ValueError, "snapshot differs"):
                call()
        self.assertEqual(self.store.observations(self.context), [])

    def test_journal_hash_mismatch_blocks_replay_and_new_ingestion(self):
        ingest(self.store, self.context)
        # Simulate corruption by a privileged DB writer outside the store API.
        self.store._db.execute("DROP TRIGGER observations_no_update")
        self.store._db.execute("UPDATE observations SET sha256 = 'corrupt'")
        for call in [lambda: self.store.reconstruct(self.context),
                     lambda: ingest(self.store, self.context, observation(2))]:
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                call()
        self.assertEqual(len(self.store.observations(self.context)), 1)

    def test_store_operations_do_not_dispatch(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            ingest(self.store, self.context)
            self.store.query_facts(self.context)
            self.store.reconstruct(self.context)

    def test_context_registration_is_idempotent_and_explicit(self):
        self.assertFalse(register(self.store, self.context))
        with self.assertRaises(ValueError):
            self.store.create_context(self.context, scenario_id="SCN-001", objective_id="OTHER",
                budget=dict(actions=10, requests=20, seconds=60),
                allowed_subjects=["lab-fixture"], allowed_actions=["ACTION-RECON-001"])
        with self.assertRaises(ValueError):
            StoreContext("RUN-019", "", "EPISODE-1")
        with self.assertRaises(ValueError):
            self.store.get_state(StoreContext("UNKNOWN", "SESSION", "EPISODE"))


class FileStoreTests(unittest.TestCase):
    def test_reopen_persistence_and_duplicate_accounting(self):
        ctx = StoreContext("RUN-019", "SESSION", "EPISODE")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            with KnowledgeStateStore(path) as store:
                register(store, ctx)
                ingest(store, ctx, requests=3, seconds=4, phase="ANALYSIS")
                before = store.get_state(ctx)
            with KnowledgeStateStore(path) as store:
                self.assertEqual(store.reconstruct(ctx), before)
                self.assertFalse(ingest(store, ctx, requests=3, seconds=4, phase="ANALYSIS"))
                self.assertEqual(store.get_state(ctx), before)

    def test_two_writers_deduplicate_and_serialize(self):
        ctx = StoreContext("RUN-019", "SESSION", "EPISODE")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "knowledge.sqlite"
            with KnowledgeStateStore(path) as store:
                register(store, ctx)
            def writer(number):
                with KnowledgeStateStore(path) as store:
                    return ingest(store, ctx, observation(number), requests=1)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(writer, [1, 1, 2, 3]))
            self.assertEqual(sum(results), 3)
            with KnowledgeStateStore(path) as store:
                self.assertEqual(store.reconstruct(ctx)["remaining_budget"],
                                 dict(actions=7, requests=17, seconds=60.0))

    def test_unknown_database_is_rejected_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unrelated.sqlite"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE unrelated (value TEXT)")
                db.execute("INSERT INTO unrelated VALUES ('preserve')")
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "unsupported"):
                KnowledgeStateStore(path)
            self.assertEqual(before, path.read_bytes())

    def test_future_version_is_rejected_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "future.sqlite"
            with KnowledgeStateStore(path):
                pass
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("PRAGMA user_version = 2")
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                KnowledgeStateStore(path)
            self.assertEqual(before, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
