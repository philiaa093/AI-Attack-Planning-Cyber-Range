"""TASK-023: bounded, offline Gymnasium replay of observed report metadata.

No scanner, executor, provider or transport integration. Replay indices are not
canonical action IDs. Caller-supplied replay approval never authorizes dispatch.
Audit is volatile and separate from agent info; durable evidence is UNRESOLVED.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from runtime.planners.planner_interface import StateSnapshot


OPERATIONS = ("READ_INVENTORY", "REVIEW_REPORT", "FINISH")
_TARGET = re.compile(r"lab-[a-z0-9-]{1,64}")


def _target(value):
    if type(value) is not str or not _TARGET.fullmatch(value):
        raise ValueError("bounded lab target identifier required")
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("integer outside supported bounds")
    return value


@dataclass(frozen=True)
class ReplayAsset:
    """Minimized observed metadata; None means no available report conclusion."""

    target_id: str
    inventory_items: int = 0
    candidate_reported: bool | None = None

    def __post_init__(self):
        _target(self.target_id)
        _integer(self.inventory_items, 0, 10_000)
        if self.candidate_reported is not None and type(self.candidate_reported) is not bool:
            raise ValueError("candidate_reported must be bool or None")


class ReplayAssessmentEnv(gym.Env):
    """Read fixed fixtures with explicit simulation approval and step-based rate.

Observation asset columns: inventory reviewed, report reviewed, report available,
candidate observed. Candidate metadata is revealed only when a report is reviewed.
The per-episode budget belongs to this simulator, never to the source state store.
"""

    metadata = {"render_modes": []}

    def __init__(self, assets, *, approved_targets=(), approved_operations=(),
                 lab_mode=True, max_steps=20, min_interval_ticks=1):
        super().__init__()
        if type(assets) not in (list, tuple) or not 1 <= len(assets) <= 64:
            raise ValueError("1-64 fixed ReplayAsset rows required")
        if any(type(asset) is not ReplayAsset for asset in assets):
            raise ValueError("ReplayAsset required")
        self._fixtures = tuple(assets)
        self._targets = tuple(asset.target_id for asset in self._fixtures)
        if len(set(self._targets)) != len(self._targets):
            raise ValueError("duplicate target")
        if type(approved_targets) not in (list, tuple, set, frozenset):
            raise ValueError("explicit replay target approval collection required")
        self._approved_targets = frozenset(_target(t) for t in approved_targets)
        if not self._approved_targets <= set(self._targets):
            raise ValueError("approval cannot extend fixture target allowlist")
        if type(approved_operations) not in (list, tuple, set, frozenset):
            raise ValueError("explicit replay operation approval collection required")
        if any(type(op) is not str or op not in OPERATIONS for op in approved_operations):
            raise ValueError("unknown replay operation")
        self._approved_operations = frozenset(approved_operations)
        if type(lab_mode) is not bool:
            raise ValueError("lab_mode must be boolean")
        self._lab_mode = lab_mode
        self._max_steps = _integer(max_steps, 1, 10_000)
        self._interval = _integer(min_interval_ticks, 1, 10_000)
        n = len(self._fixtures)
        self.finish_action = 2 * n
        self.action_space = spaces.Discrete(self.finish_action + 1)
        self.observation_space = spaces.Dict({
            "assets": spaces.MultiBinary((n, 4)),
            "inventory_counts": spaces.Box(0, 10_000, (n,), dtype=np.int32),
            "remaining_budget": spaces.Box(0.0, 1.0, (1,), dtype=np.float32),
        })
        self._run_id = "RUN-023-" + uuid.uuid4().hex
        self._source = "SIMULATED_FIXTURE"
        self._source_hash = hashlib.sha256(json.dumps([
            [a.target_id, a.inventory_items, a.candidate_reported] for a in assets
        ], separators=(",", ":")).encode()).hexdigest()
        self._audit = []
        self._episode = 0
        self._done = True
        self._closed = False

    @classmethod
    def from_snapshot(cls, snapshot, *, targets, **kwargs):
        """Read TASK-019/020 snapshot; do not copy raw fact values or mutate store.

        Absence of a CANDIDATE_FINDING is unknown, never a clean scan result.
        The source hash binds to snapshot JSON, not to verified external evidence.
        """
        if type(snapshot) is not StateSnapshot:
            raise ValueError("validated StateSnapshot required")
        if type(targets) not in (list, tuple) or not 1 <= len(targets) <= 64:
            raise ValueError("explicit bounded target list required")
        for target in targets:
            _target(target)
        facts = snapshot.to_dict()["observed_facts"]
        rows = []
        for target in targets:
            scoped = [fact for fact in facts if fact["subject"] == target]
            count = sum(f["fact_type"] in ("TARGET", "SERVICE", "ENDPOINT") for f in scoped)
            has_candidate = any(f["fact_type"] == "CANDIDATE_FINDING" for f in scoped)
            rows.append(ReplayAsset(target, count, True if has_candidate else None))
        env = cls(rows, **kwargs)
        env._source = "OFFLINE_STATE_SNAPSHOT"
        env._source_hash = snapshot.revision
        return env

    @property
    def target_ids(self):
        return self._targets

    def audit_records(self):
        """Detached volatile records across resets; not immutable disk evidence."""
        return tuple(json.loads(record) for record in self._audit)

    def _record(self, operation, target, outcome, expected, observed, *, episode=None):
        record = dict(
            timestamp_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            run_id=self._run_id, episode_id=f"EPISODE-{self._episode if episode is None else episode}",
            sequence=len(self._audit) + 1, source=self._source,
            source_sha256=self._source_hash, redaction="METADATA_ONLY",
            operation=operation, target_id=target, outcome=outcome,
            expected_state=expected, observed_state=observed,
        )
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        record["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        self._audit.append(json.dumps(record, sort_keys=True, separators=(",", ":")))

    def _observation(self):
        return dict(
            assets=self._assets.copy(), inventory_counts=self._counts.copy(),
            remaining_budget=np.array(
                [(self._max_steps - self._steps) / self._max_steps], dtype=np.float32),
        )

    def _decode(self, action):
        n = len(self._fixtures)
        if action == self.finish_action:
            return "FINISH", None
        return ("READ_INVENTORY", action) if action < n else ("REVIEW_REPORT", action - n)

    def _denial(self, operation, asset, tick):
        if not self._lab_mode:
            return "DENIED_LAB_MODE"
        if operation not in self._approved_operations:
            return "DENIED_APPROVAL"
        if asset is None:
            return None
        if self._targets[asset] not in self._approved_targets:
            return "DENIED_TARGET"
        if tick - self._last_read < self._interval:
            return "DENIED_RATE"
        if operation == "REVIEW_REPORT" and not self._assets[asset, 0]:
            return "DENIED_ORDER"
        return None

    def _info(self, outcome):
        mask = np.zeros(self.action_space.n, dtype=np.int8)
        if not self._done:
            for action in range(self.action_space.n):
                op, asset = self._decode(action)
                if self._denial(op, asset, self._steps + 1) is None:
                    mask[action] = 1
        # No hidden report metadata, snapshot hash, audit IDs, or ground truth.
        return dict(action_mask=mask, outcome=outcome, provenance=self._source,
                    network_dispatches=0)

    def reset(self, *, seed=None, options=None):
        if self._closed:
            raise RuntimeError("environment closed")
        if options is not None and (type(options) is not dict or options):
            raise ValueError("reset options unsupported")
        if seed is not None and (isinstance(seed, (bool, np.bool_)) or
                                 not isinstance(seed, (int, np.integer)) or seed < 0):
            raise ValueError("nonnegative integer seed required")
        super().reset(seed=seed)
        self._done = True
        next_episode = self._episode + 1
        # Record intent before restoring simulator state; no store/evidence deletion.
        self._record("RESET", None, "RESTORE", {"next_episode": next_episode},
                     {"scope": "SIMULATOR_MEMORY_ONLY"}, episode=next_episode)
        self._episode = next_episode
        self._assets = np.zeros((len(self._fixtures), 4), dtype=np.int8)
        self._counts = np.zeros(len(self._fixtures), dtype=np.int32)
        self._steps = 0
        self._last_read = -self._interval
        self._done = False
        return self._observation(), self._info("RESET")

    def step(self, action):
        if self._done or self._closed:
            raise RuntimeError("reset required before step")
        if (isinstance(action, (bool, np.bool_)) or
                not isinstance(action, (int, np.integer)) or
                not self.action_space.contains(action)):
            self._done = True
            self._record("REFUSE_INPUT", None, "DENIED_MALFORMED", {}, {"state_changed": False})
            raise ValueError("scalar discrete action required; episode stopped")
        action = int(action)
        operation, asset = self._decode(action)
        tick = self._steps + 1
        denial = self._denial(operation, asset, tick)
        reward, outcome, terminated = -0.01, "NO_PROGRESS", False
        next_assets, next_counts = self._assets.copy(), self._counts.copy()
        next_last_read = self._last_read
        if denial:
            reward -= 0.5
            outcome = denial
        elif operation == "FINISH":
            complete = bool(self._assets[:, 1].all())
            reward += 1.0 if complete else -0.5
            outcome = "REVIEW_COMPLETE" if complete else "STOPPED_EARLY"
            terminated = True
        else:
            next_last_read = tick
            fixture = self._fixtures[asset]
            column = 0 if operation == "READ_INVENTORY" else 1
            if not self._assets[asset, column]:
                next_assets[asset, column] = 1
                if column == 0:
                    next_counts[asset] = fixture.inventory_items
                    reward += 0.1
                    outcome = "INVENTORY_OBSERVED"
                else:
                    available = fixture.candidate_reported is not None
                    next_assets[asset, 2] = int(available)
                    next_assets[asset, 3] = int(fixture.candidate_reported is True)
                    reward += 0.2
                    outcome = "REPORT_REVIEWED" if available else "REPORT_UNAVAILABLE"
        truncated = tick >= self._max_steps and not terminated
        target = None if asset is None else self._targets[asset]
        try:
            self._record(operation, target, outcome,
                         {"replay_only": True, "network_dispatches": 0},
                         {"tick": tick, "assets": next_assets.tolist(),
                          "inventory_counts": next_counts.tolist(),
                          "terminated": terminated, "truncated": truncated})
        except Exception:
            self._done = True
            raise
        self._assets, self._counts = next_assets, next_counts
        self._steps, self._last_read = tick, next_last_read
        self._done = terminated or truncated
        return self._observation(), float(reward), terminated, bool(truncated), self._info(outcome)

    def close(self):
        self._closed = self._done = True
