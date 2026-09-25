"""Immutable action/observation history log.

Append-only. Supports deterministic replay and state reconstruction.
Isolation: no expected-data references.
"""

import copy
import json
from datetime import datetime, timezone


class ActionLog:
    """Immutable append-only log of actions and observations.

    Each entry is timestamped and sequenced. Log can be replayed
    to reconstruct state deterministically.
    """

    def __init__(self):
        self._entries = []
        self._seq = 0

    @property
    def entries(self):
        """Return shallow copy of entries (immutability guard)."""
        return list(self._entries)

    def __len__(self):
        return len(self._entries)

    def record_action(self, run_id, action_id, parameters=None):
        """Record an action dispatch."""
        entry = {
            "seq": self._seq,
            "type": "action",
            "run_id": run_id,
            "action_id": action_id,
            "parameters": parameters or {},
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._entries.append(entry)
        self._seq += 1
        return entry

    def record_observation(self, observation):
        """Record an observation result. Deep-copies to preserve immutability."""
        entry = {
            "seq": self._seq,
            "type": "observation",
            "observation": copy.deepcopy(observation),
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._entries.append(entry)
        self._seq += 1
        return entry

    def get_actions(self):
        """Return all action entries."""
        return [e for e in self._entries if e["type"] == "action"]

    def get_observations(self):
        """Return all observation entries."""
        return [e for e in self._entries if e["type"] == "observation"]

    def get_action_ids(self):
        """Return ordered list of action_ids dispatched."""
        return [e["action_id"] for e in self._entries if e["type"] == "action"]

    def to_json(self):
        """Serialize log to JSON string for persistence."""
        return json.dumps(self._entries, indent=2)

    @classmethod
    def from_json(cls, json_str):
        """Reconstruct log from JSON string."""
        log = cls()
        entries = json.loads(json_str)
        log._entries = entries
        log._seq = max((e["seq"] for e in entries), default=-1) + 1
        return log

    def replay_observations(self):
        """Yield observations in sequence order for state reconstruction."""
        for entry in self._entries:
            if entry["type"] == "observation":
                yield entry["observation"]
