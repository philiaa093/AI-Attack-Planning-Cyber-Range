"""Shared base adapter with safety validation for all tool adapters.

Every adapter inherits from BaseAdapter to get:
- Target allowlist enforcement (lab-* only)
- Action allowlist enforcement (catalog IDs only)
- Rate limiting
- Observation and scanner-result builders conforming to contracts
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---------- config loaders ----------

def _load_json(rel_path):
    return json.loads((ROOT / rel_path).read_text(encoding="utf-8"))


def load_target_allowlist():
    return _load_json("configs/safety/target-allowlist.yaml")


def load_action_allowlist():
    return _load_json("configs/safety/action-allowlist.yaml")


def load_rate_limit():
    return _load_json("configs/safety/rate-limit.yaml")


def load_request_budget():
    return _load_json("configs/safety/request-budget.yaml")


# ---------- validators ----------

_TARGET_PATTERN = re.compile(r"^lab-[a-z0-9-]+$")
_ACTION_PATTERN = re.compile(r"^ACTION-[A-Z]+-[0-9]{3}$")


def validate_target(target_id):
    """Raise ValueError if target_id is not in the allowlist."""
    if not _TARGET_PATTERN.match(target_id):
        raise ValueError(f"target_id '{target_id}' does not match lab-* pattern")
    allowed = load_target_allowlist()["allowed_target_ids"]
    if target_id not in allowed:
        raise ValueError(f"target_id '{target_id}' not in target allowlist")


def validate_action(action_id, expected_class=None):
    """Raise ValueError if action_id is not in the catalog."""
    if not _ACTION_PATTERN.match(action_id):
        raise ValueError(f"action_id '{action_id}' does not match ACTION-*-NNN pattern")
    catalog = load_action_allowlist()
    if action_id not in catalog["allowed_action_ids"]:
        raise ValueError(f"action_id '{action_id}' not in action allowlist")
    if expected_class:
        actual = catalog["action_classes"].get(action_id)
        if actual != expected_class:
            raise ValueError(f"action_id '{action_id}' class is '{actual}', expected '{expected_class}'")


# ---------- rate limiter ----------

class RateLimiter:
    """Token-bucket rate limiter scoped per (run_id, target_id)."""

    def __init__(self):
        cfg = load_rate_limit()
        self._rps = cfg["requests_per_second"]
        self._burst = cfg["burst"]
        self._tokens = {}  # key -> (tokens, last_time)

    def acquire(self, run_id, target_id):
        """Acquire a rate-limit token. Raises RuntimeError if exceeded."""
        key = f"{run_id}:{target_id}"
        now = time.monotonic()
        tokens, last = self._tokens.get(key, (self._burst, now))
        elapsed = now - last
        tokens = min(self._burst, tokens + elapsed * self._rps)
        if tokens < 1:
            raise RuntimeError(f"rate limit exceeded for {key}")
        self._tokens[key] = (tokens - 1, now)


# ---------- output builders ----------

def build_observation(observation_id, run_id, action_id, outcome, new_facts=None, evidence_refs=None):
    """Build an observation conforming to observation.schema.json."""
    obs = {
        "observation_id": observation_id,
        "run_id": run_id,
        "action_id": action_id,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": outcome,
    }
    if new_facts is not None:
        obs["new_facts"] = new_facts
    if evidence_refs is not None:
        obs["evidence_refs"] = evidence_refs
    return obs


def build_scanner_result(source, target_id, finding_type, confidence, endpoint_id=None):
    """Build a scanner-result conforming to scanner-result.schema.json."""
    return {
        "source": source,
        "target_id": target_id,
        "endpoint_id": endpoint_id,
        "finding_type": finding_type,
        "confidence": confidence,
    }


# ---------- base adapter ----------

class BaseAdapter:
    """Base class for all tool adapters."""

    # Subclasses must set these
    ADAPTER_SOURCE = None    # "DISCOVERY", "ZAP", "NUCLEI"
    ALLOWED_ACTIONS = {}     # {action_id: action_class}

    def __init__(self):
        self._rate_limiter = RateLimiter()

    def validate_request(self, action_id, target_id, run_id):
        """Run all safety checks before execution. Raises on violation."""
        validate_target(target_id)
        if action_id not in self.ALLOWED_ACTIONS:
            raise ValueError(
                f"action '{action_id}' not handled by {self.__class__.__name__}; "
                f"allowed: {list(self.ALLOWED_ACTIONS.keys())}"
            )
        validate_action(action_id, expected_class=self.ALLOWED_ACTIONS[action_id])
        self._rate_limiter.acquire(run_id, target_id)

    def execute(self, action_id, target_id, run_id, parameters=None):
        """Validate and dispatch. Returns an observation dict."""
        self.validate_request(action_id, target_id, run_id)
        return self._run(action_id, target_id, run_id, parameters or {})

    def _run(self, action_id, target_id, run_id, parameters):
        """Subclasses implement tool-specific logic here."""
        raise NotImplementedError
