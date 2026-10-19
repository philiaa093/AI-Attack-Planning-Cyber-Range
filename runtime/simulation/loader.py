"""Canonical Scenario Loader and Validator (RT-04A).

Loads declarative scenario specifications, enforces Draft 2020-12 closed-schema validation,
and validates cross-entity semantic integrity.

Invariants:
- Planner domain has NO access to this loader.
- Malformed or schema-violating scenarios fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from scripts.validation.validate_scaffold import load_json
from shared.schema_validation import validate_shape
from runtime.simulation.models.scenario import HiddenScenario


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "scenario.schema.json"


class ScenarioLoader:
    """Loads and validates hidden scenario manifests against canonical closed schema."""

    def __init__(self, schema_path: Path | str | None = None) -> None:
        self.schema_path = Path(schema_path) if schema_path else SCENARIO_SCHEMA_PATH
        self._schema = self._load_schema()

    def _load_schema(self) -> dict[str, Any]:
        if not self.schema_path.is_file():
            raise FileNotFoundError(f"Scenario schema not found at {self.schema_path}")
        errors: list[str] = []
        schema_data = load_json(self.schema_path, errors)
        if errors or not isinstance(schema_data, dict):
            raise ValueError(f"Failed to load scenario schema: {errors}")
        return schema_data

    def validate_scenario_data(self, data: Mapping[str, Any]) -> list[str]:
        """Validate scenario dictionary against closed schema and semantic integrity rules."""
        errors: list[str] = []

        # 1. Structural schema validation (Draft 2020-12 closed object)
        shape_errors = validate_shape(data, self._schema)
        errors.extend(shape_errors)
        if shape_errors:
            # If shape itself is invalid, return early
            return errors

        # 2. Semantic reference integrity checks
        nodes = data.get("hidden_nodes", [])
        node_ids = {node.get("node_id") for node in nodes if isinstance(node, dict)}

        # Check unique node IDs
        if len(node_ids) != len(nodes):
            errors.append("Duplicate node_id found in hidden_nodes")

        # Check entry seed exists
        entry_seed = data.get("entry_seed")
        if entry_seed not in node_ids:
            errors.append(f"entry_seed {entry_seed!r} does not exist in hidden_nodes")

        # Check objective target node exists
        objective = data.get("objective", {})
        if isinstance(objective, dict):
            obj_target = objective.get("target_node_id")
            if obj_target not in node_ids:
                errors.append(f"objective target_node_id {obj_target!r} does not exist in hidden_nodes")

        # Check topology edges reference existing nodes
        topology = data.get("hidden_topology", {})
        if isinstance(topology, dict):
            edges = topology.get("edges", [])
            for idx, edge in enumerate(edges):
                if isinstance(edge, dict):
                    src = edge.get("source")
                    dst = edge.get("target")
                    if src not in node_ids:
                        errors.append(f"topology edge [{idx}] source {src!r} not in hidden_nodes")
                    if dst not in node_ids:
                        errors.append(f"topology edge [{idx}] target {dst!r} not in hidden_nodes")

        # Check credentials valid_nodes reference existing nodes
        credentials = data.get("hidden_credentials", [])
        for idx, cred in enumerate(credentials):
            if isinstance(cred, dict):
                for target_node in cred.get("valid_nodes", []):
                    if target_node not in node_ids:
                        errors.append(f"credential [{idx}] valid_node {target_node!r} not in hidden_nodes")

        # Check transitions target nodes reference existing nodes if set
        transitions = data.get("transitions", [])
        for idx, trans in enumerate(transitions):
            if isinstance(trans, dict):
                match_cond = trans.get("match_conditions", {})
                if isinstance(match_cond, dict):
                    target_nid = match_cond.get("target_node_id")
                    if target_nid and target_nid != "ANY" and target_nid not in node_ids:
                        errors.append(f"transition [{idx}] match target_node_id {target_nid!r} not in hidden_nodes")

        return errors

    def load_from_dict(self, data: Mapping[str, Any]) -> HiddenScenario:
        """Validate and construct HiddenScenario from dictionary."""
        errors = self.validate_scenario_data(data)
        if errors:
            raise ValueError(f"Scenario validation failed with {len(errors)} error(s): {errors}")
        return HiddenScenario.from_dict(data)

    def load_from_file(self, path: Path | str) -> HiddenScenario:
        """Read, validate, and construct HiddenScenario from JSON file."""
        file_path = Path(path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Scenario file not found: {file_path}")
        errors: list[str] = []
        data = load_json(file_path, errors)
        if errors or not isinstance(data, dict):
            raise ValueError(f"Failed to parse scenario JSON file {file_path}: {errors}")
        return self.load_from_dict(data)
