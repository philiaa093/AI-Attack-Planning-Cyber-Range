"""Planner state adapter connecting SL-08 observations to the planner.

Enforces:
  - Observation idempotency: identical replay does not duplicate facts or budget decrement
  - Explicit conflict detection: conflicting observation with same ID raises ValueError
  - Single source of truth for budget: StateManager owns action/time budgets; no double decrement
  - State minimization and redaction: planner receives only observed facts, endpoints, and capabilities
  - Zero target route assumptions in state transformation
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from agent.memory.state.state_manager import StateManager
from agent.perception.normalizers.observation_normalizer import ObservationNormalizer
from runtime.evidence.discovery_recorder import redact_secrets
from scripts.validation.validate_scaffold import ROOT, validate_shape


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_observation(observation: dict[str, Any]) -> str:
    canonical = _canonical_json(observation)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PlannerStateAdapter:
    """Adapts raw/normalized SL-08 observations into clean, idempotent StateManager planner state."""

    def __init__(
        self,
        state_manager: StateManager,
        normalizer: ObservationNormalizer | None = None,
    ) -> None:
        self.state_manager = state_manager
        self.normalizer = normalizer or ObservationNormalizer()
        self.seen_observations: dict[str, str] = {}  # obs_id -> sha256 fingerprint

        # Load observation schema for validation
        obs_schema_path = ROOT / "agent" / "planner" / "contracts" / "observation.schema.json"
        self._obs_schema = json.loads(obs_schema_path.read_text(encoding="utf-8"))

    def ingest_observation(self, observation: dict[str, Any]) -> bool:
        """Ingest one observation dict into StateManager with idempotency and conflict checks.

        Returns:
            True if observation was newly applied.
            False if observation was an identical duplicate (ignored idempotently).
        Raises:
            ValueError if observation violates schema or conflicts with an existing observation ID.
        """
        if not isinstance(observation, dict):
            raise ValueError("observation must be a dictionary")

        errors = validate_shape(observation, self._obs_schema)
        if errors:
            raise ValueError(f"observation schema violation: {errors}")

        obs_id = observation.get("observation_id", "")
        if not obs_id:
            raise ValueError("missing observation_id")

        digest = _hash_observation(observation)
        previous_digest = self.seen_observations.get(obs_id)

        if previous_digest is not None:
            if previous_digest == digest:
                # Identical duplicate replay: do NOT re-apply, do NOT double-decrement budget
                return False
            else:
                # Conflicting observation with same identity: reject explicitly
                raise ValueError(
                    f"conflicting observation identity '{obs_id}': "
                    f"previous hash {previous_digest[:12]} != new hash {digest[:12]}"
                )

        # Apply newly seen observation to StateManager
        self.seen_observations[obs_id] = digest
        self.state_manager.apply_observation(observation)
        return True

    def get_minimized_planner_state(self) -> dict[str, Any]:
        """Return a minimized, redacted planner state containing only necessary context."""
        raw_state = self.state_manager.get_state()
        redacted_state = redact_secrets(raw_state)

        observed_facts = redacted_state.get("observed_facts", [])
        endpoints = []
        services = []

        for f in observed_facts:
            ft = f.get("fact_type")
            val = f.get("value")
            if ft == "ENDPOINT" and val and val not in endpoints:
                endpoints.append(val)
            elif ft == "SERVICE" and val and val not in services:
                services.append(val)

        return {
            "run_id": redacted_state.get("run_id"),
            "scenario_id": redacted_state.get("scenario_id"),
            "objective_id": redacted_state.get("objective_id"),
            "phase": redacted_state.get("phase"),
            "remaining_budget": copy.deepcopy(redacted_state.get("remaining_budget", {})),
            "previous_actions": list(redacted_state.get("previous_actions", [])),
            "fact_count": len(observed_facts),
            "observed_facts": observed_facts,
            "discovered_endpoints": endpoints,
            "discovered_services": services,
        }
