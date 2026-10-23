"""Bootstrap observation generator for Enterprise Attack Planning simulation.

Initializes Planner-safe initial visibility at t=0 conforming strictly to Fog-of-War:
- Emits canonical observation containing ONLY the scenario entry_seed.
- Does NOT expose hidden topology, non-entry nodes, vulnerabilities, credentials, or objective locations.
- Produces valid Draft 2020-12 closed canonical observation envelope.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.perception.normalizers.enterprise_normalizer import (
    make_enterprise_fact_id,
    validate_canonical_observation,
)
from runtime.simulation.models.scenario import HiddenScenario


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BootstrapObservationGenerator:
    """Generates canonical initial observation at t=0 exposing only the entry seed."""

    def __init__(self) -> None:
        pass

    def generate_bootstrap_observation(
        self,
        scenario: HiddenScenario,
        run_id: str,
        timestamp_utc: str | None = None,
    ) -> dict[str, Any]:
        """Generate canonical bootstrap observation envelope for the scenario entry seed.

        Args:
            scenario: The validated HiddenScenario.
            run_id: Unique execution identifier.
            timestamp_utc: Optional ISO-8601 UTC timestamp.

        Returns:
            Canonical observation dict validating against observation.schema.json.
        """
        eff_ts = timestamp_utc or _now_utc()
        entry_node_id = scenario.entry_seed

        fact_value = {
            "target_id": entry_node_id,
            "status": "REACHABLE",
        }
        fact_id = make_enterprise_fact_id("TARGET", entry_node_id, fact_value)

        target_fact = {
            "fact_id": fact_id,
            "fact_type": "TARGET",
            "subject": entry_node_id,
            "value": fact_value,
            "confidence": 1.0,
        }

        obs: dict[str, Any] = {
            "observation_id": f"OBS-BOOTSTRAP-{run_id[:8]}",
            "run_id": run_id,
            "action_id": "ACTION-DISCOVERY-001",
            "timestamp_utc": eff_ts,
            "outcome": "SUCCESS",
            "new_facts": [target_fact],
            "evidence_refs": [f"sim-bootstrap://{scenario.scenario_id}"],
            "source_kind": "SIMULATED",
            "confidence": 1.0,
            "sequence_num": 0,
            "source_target": entry_node_id,
        }

        errors = validate_canonical_observation(obs)
        if errors:
            raise ValueError(
                f"BootstrapObservationGenerator generated invalid canonical observation: {errors}"
            )

        return obs
