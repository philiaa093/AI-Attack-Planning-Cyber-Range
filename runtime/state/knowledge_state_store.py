"""Offline SQLite journal and indexed projections over the existing StateManager.

No dispatch or policy authorization. Only normalized, already-redacted observations
belong here. One connection per thread; separate instances may share a local DB.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.memory.state.state_manager import StateManager
from runtime.evidence.discovery_recorder import redact_secrets
from scripts.validation.validate_scaffold import validate_shape


_ROOT = Path(__file__).resolve().parents[2]
_APP_ID = 0x4B535331
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_DDL = (
    """CREATE TABLE contexts (
        context_id TEXT PRIMARY KEY, definition TEXT NOT NULL, state TEXT NOT NULL)""",
    """CREATE TABLE observations (
        seq INTEGER PRIMARY KEY, context_id TEXT NOT NULL REFERENCES contexts(context_id),
        observation_id TEXT NOT NULL, envelope TEXT NOT NULL, sha256 TEXT NOT NULL,
        ingested_utc TEXT NOT NULL, UNIQUE(context_id, observation_id))""",
    """CREATE TABLE facts (
        context_id TEXT NOT NULL REFERENCES contexts(context_id), fact_id TEXT NOT NULL,
        subject TEXT NOT NULL, fact_type TEXT NOT NULL, confidence REAL NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(context_id, fact_id))""",
    "CREATE INDEX facts_subject ON facts(context_id, subject, fact_type, confidence)",
    "CREATE INDEX facts_type ON facts(context_id, fact_type, confidence)",
    """CREATE VIEW assets AS SELECT context_id, subject AS target_id, COUNT(*) AS fact_count
        FROM facts WHERE fact_type IN ('TARGET', 'SERVICE', 'ENDPOINT')
        GROUP BY context_id, subject""",
    """CREATE TRIGGER observations_no_update BEFORE UPDATE ON observations
        BEGIN SELECT RAISE(ABORT, 'append-only observations'); END""",
    """CREATE TRIGGER observations_no_delete BEFORE DELETE ON observations
        BEGIN SELECT RAISE(ABORT, 'append-only observations'); END""",
)


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("finite JSON data required") from exc


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _id(value):
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise ValueError("invalid identity; use 1-128 ASCII identifier characters")
    return value


@dataclass(frozen=True)
class StoreContext:
    run_id: str
    session_id: str
    episode_id: str

    def __post_init__(self):
        for value in (self.run_id, self.session_id, self.episode_id):
            _id(value)

    @property
    def key(self):
        return _json([self.run_id, self.session_id, self.episode_id])


class KnowledgeStateStore:
    """Transactional offline storage. get_state() retains the canonical state shape."""

    def __init__(self, database=":memory:"):
        self._observation_schema = json.loads(
            (_ROOT / "agent/planner/contracts/observation.schema.json").read_text("utf-8"))
        self._state_schema = json.loads(
            (_ROOT / "agent/planner/contracts/state.schema.json").read_text("utf-8"))
        self._db = sqlite3.connect(database, isolation_level=None, timeout=5.0)
        self._db.row_factory = sqlite3.Row
        try:
            # Validate existing schema BEFORE setting persistent options or writing.
            with self._transaction(write=True):
                objects = self._db.execute(
                    "SELECT sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
                version = self._db.execute("PRAGMA user_version").fetchone()[0]
                app_id = self._db.execute("PRAGMA application_id").fetchone()[0]
                if not objects and version == 0 and app_id == 0:
                    for statement in _DDL:
                        self._db.execute(statement)
                    self._db.execute(f"PRAGMA application_id = {_APP_ID}")
                    self._db.execute("PRAGMA user_version = 1")
                else:
                    canonical = lambda text: " ".join(text.split())
                    if (version != 1 or app_id != _APP_ID or
                            {canonical(row[0]) for row in objects} !=
                            {canonical(statement) for statement in _DDL}):
                        raise ValueError("unsupported knowledge-store schema; no migration")
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.execute("PRAGMA synchronous = FULL")
        except BaseException:
            self._db.close()
            raise

    @contextmanager
    def _transaction(self, *, write=False):
        self._db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _context(self, context):
        if not isinstance(context, StoreContext):
            raise ValueError("StoreContext required")
        row = self._db.execute("SELECT * FROM contexts WHERE context_id = ?",
                               (context.key,)).fetchone()
        if row is None:
            raise ValueError("unknown run/session/episode context")
        return row

    def create_context(self, context, *, scenario_id, objective_id, budget,
                       allowed_subjects, allowed_actions):
        """Register immutable scope narrowed by the caller's approved policy.

        These allowlists limit stored data; they do not authorize any action.
        Session IDs are opaque labels, never cookies or authentication tokens.
        """
        if not isinstance(context, StoreContext):
            raise ValueError("StoreContext required")
        _id(scenario_id)
        _id(objective_id)
        if not isinstance(allowed_subjects, (list, tuple, set, frozenset)):
            raise ValueError("subject allowlist required")
        if not isinstance(allowed_actions, (list, tuple, set, frozenset)):
            raise ValueError("action allowlist required")
        subjects = sorted({_id(item) for item in allowed_subjects})
        actions = sorted({_id(item) for item in allowed_actions})
        if not subjects or not actions or any(
                not re.fullmatch(r"ACTION-[A-Z]+-[0-9]{3}", item) for item in actions):
            raise ValueError("nonempty typed scope required")
        if not isinstance(budget, dict) or set(budget) != {"actions", "requests", "seconds"}:
            raise ValueError("explicit initial actions/requests/seconds budget required")
        sm = StateManager(context.run_id, scenario_id, objective_id, budget)
        errors = validate_shape(sm.get_state(), self._state_schema)
        if errors:
            raise ValueError("invalid initial state")
        definition = _json(dict(run_id=context.run_id, scenario_id=scenario_id,
                                objective_id=objective_id, budget=budget,
                                allowed_subjects=subjects, allowed_actions=actions))
        with self._transaction(write=True):
            existing = self._db.execute("SELECT definition FROM contexts WHERE context_id = ?",
                                        (context.key,)).fetchone()
            if existing:
                if existing[0] != definition:
                    raise ValueError("conflicting context definition")
                return False
            self._db.execute("INSERT INTO contexts VALUES (?, ?, ?)",
                             (context.key, definition, _json(sm.get_state())))
        return True

    def ingest(self, context, observation, *, source, source_sha256,
               requests=0, seconds=0.0, phase=None):
        """Atomically append one normalized observation and refresh projections.

        Costs are caller-recorded accounting data, not inferred from scan results.
        Equal observation IDs must match the whole canonical envelope, including
        provenance/costs/phase. Return False for an identical retry.
        """
        _id(source)
        if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source_sha256):
            raise ValueError("source SHA-256 required")
        if type(requests) is not int or requests < 0:
            raise ValueError("request cost must be a nonnegative integer")
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("time cost must be finite and nonnegative")
        if phase is not None and phase not in (
                "RECON", "DISCOVERY", "ANALYSIS", "TESTING", "REPLAN", "TERMINAL"):
            raise ValueError("invalid phase")
        canonical = _json(observation)
        if len(canonical.encode("utf-8")) > 1024 * 1024:
            raise ValueError("observation exceeds 1 MiB limit")
        observation = json.loads(canonical)  # own all mutable input
        if validate_shape(observation, self._observation_schema):
            raise ValueError("invalid normalized observation")
        _id(observation["observation_id"])
        if redact_secrets(observation) != observation:
            raise ValueError("observation must already be redacted by the normalizer")
        try:
            timestamp = datetime.fromisoformat(observation["timestamp_utc"].replace("Z", "+00:00"))
            if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
                raise ValueError("UTC required")
        except (ValueError, TypeError) as exc:
            raise ValueError("observation timestamp must be UTC") from exc
        observation["timestamp_utc"] = timestamp.isoformat().replace("+00:00", "Z")
        facts = observation.get("new_facts", [])
        if len({fact["fact_id"] for fact in facts}) != len(facts):
            raise ValueError("duplicate fact IDs within observation")
        envelope = dict(observation=observation, source=source,
                        source_sha256=source_sha256.lower(), redaction="NORMALIZER_REDACTED",
                        requests=requests, seconds=float(seconds), phase=phase)
        text = _json(envelope)
        with self._transaction(write=True):
            row = self._context(context)
            definition = json.loads(row["definition"])
            if (observation["run_id"] != context.run_id or
                    observation["action_id"] not in definition["allowed_actions"] or
                    any(f["subject"] not in definition["allowed_subjects"] for f in facts)):
                raise ValueError("observation outside context scope")
            existing = self._db.execute(
                "SELECT envelope FROM observations WHERE context_id = ? AND observation_id = ?",
                (context.key, observation["observation_id"])).fetchone()
            if existing:
                if existing[0] != text:
                    raise ValueError("conflicting observation identity")
                return False
            sm = self._rebuild(context, row)
            previous = {f["fact_id"]: f for f in sm.get_state()["observed_facts"]}
            for fact in facts:
                old = previous.get(fact["fact_id"])
                if old and any(old[key] != fact[key] for key in ("fact_type", "subject", "value")):
                    raise ValueError("conflicting fact identity; use a new fact ID for changed facts")
            self._apply(sm, envelope)
            state = sm.get_state()
            self._db.execute("INSERT INTO observations(context_id, observation_id, envelope, sha256, ingested_utc) VALUES (?, ?, ?, ?, ?)",
                             (context.key, observation["observation_id"], text, _hash(text),
                              datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")))
            for fact in state["observed_facts"]:
                self._db.execute("""INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(context_id, fact_id) DO UPDATE SET
                    subject=excluded.subject, fact_type=excluded.fact_type,
                    confidence=excluded.confidence, payload=excluded.payload""",
                    (context.key, fact["fact_id"], fact["subject"], fact["fact_type"],
                     fact["confidence"], _json(fact)))
            self._db.execute("UPDATE contexts SET state = ? WHERE context_id = ?",
                             (_json(state), context.key))
        return True

    @staticmethod
    def _apply(sm, envelope):
        sm.apply_observation(envelope["observation"])
        sm.decrement_requests(envelope["requests"])
        sm.decrement_seconds(envelope["seconds"])
        if envelope["phase"] is not None:
            sm.set_phase(envelope["phase"])

    def _rebuild(self, context, row):
        definition = json.loads(row["definition"])
        sm = StateManager(definition["run_id"], definition["scenario_id"],
                          definition["objective_id"], definition["budget"])
        for event in self._db.execute(
                "SELECT envelope, sha256 FROM observations WHERE context_id = ? ORDER BY seq",
                (context.key,)):
            if _hash(event["envelope"]) != event["sha256"]:
                raise ValueError("observation journal hash mismatch")
            self._apply(sm, json.loads(event["envelope"]))
        if _json(sm.get_state()) != row["state"]:
            raise ValueError("state snapshot differs from observation replay")
        return sm

    def reconstruct(self, context):
        """Verify journal hashes and snapshot, then return deterministic state."""
        with self._transaction():
            return self._rebuild(context, self._context(context)).get_state()

    def get_state(self, context):
        return json.loads(self._context(context)["state"])

    def query_facts(self, context, *, subject=None, fact_type=None,
                    min_confidence=0.0, limit=100, offset=0):
        self._context(context)
        if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
            raise ValueError("limit must be 1-1000 and offset nonnegative")
        if type(min_confidence) not in (int, float) or not 0 <= min_confidence <= 1:
            raise ValueError("confidence must be finite in [0, 1]")
        clauses, args = ["context_id = ?", "confidence >= ?"], [context.key, min_confidence]
        if subject is not None:
            clauses.append("subject = ?")
            args.append(_id(subject))
        if fact_type is not None:
            if fact_type not in self._observation_schema["$defs"]["fact"]["properties"]["fact_type"]["enum"]:
                raise ValueError("unknown fact type")
            clauses.append("fact_type = ?")
            args.append(fact_type)
        rows = self._db.execute("SELECT payload FROM facts WHERE " + " AND ".join(clauses) +
                                " ORDER BY fact_id LIMIT ? OFFSET ?", (*args, limit, offset))
        return [json.loads(row[0]) for row in rows]

    def list_assets(self, context):
        self._context(context)
        return [dict(row) for row in self._db.execute(
            "SELECT target_id, fact_count FROM assets WHERE context_id = ? ORDER BY target_id",
            (context.key,))]

    def observations(self, context, *, limit=100, offset=0):
        """Paginated append order, including provenance/hash/ingestion UTC."""
        self._context(context)
        if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
            raise ValueError("invalid observation page")
        return [dict(row) | {"envelope": json.loads(row["envelope"])} for row in self._db.execute(
            "SELECT seq, envelope, sha256, ingested_utc FROM observations WHERE context_id = ? ORDER BY seq LIMIT ? OFFSET ?",
            (context.key, limit, offset))]
