"""Canonical Action Registry and Contract Semantics for Bounded TTP Capabilities.

RT-03A — Generic TTP Action Contract.

Enforces:
  1. Action Catalog defines CAPABILITY, not concrete target instances.
  2. Target independence: action definitions contain zero hardcoded IPs, hostnames, lab targets, or vulnerability fixtures.
  3. Structured preconditions: typed, machine-validated, zero eval or arbitrary python strings.
  4. Active vs Historical Access: actions requiring execution capability demand require_active_session; closed sessions never satisfy execution.
  5. Hard Invariant: expected_effects NEVER directly mutates BeliefState or StateManager.
  6. Operational costs: step_cost and operational noise_cost are bounded non-negative numbers.
  7. Backward compatibility: legacy web actions are preserved and classified as LEGACY_WEB_COMPAT.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.validation.validate_scaffold import ROOT
from shared.schema_validation import validate_shape

ACTION_SCHEMA_PATH = ROOT / "agent/planner/contracts/action.schema.json"
CATALOG_PATH = ROOT / "actions/catalog/action-catalog.json"

TARGET_LEAKAGE_PATTERN = re.compile(
    r"\b(lab-[a-z0-9-]+|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}|victim|juice-shop|ecommerce|ground[_-]?truth|truth_records)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PreconditionContract:
    """Structured, machine-validated preconditions for action proposal eligibility."""
    target_visible: bool = False
    host_observed: bool = False
    service_observed: bool = False
    required_service_type: str | None = None
    finding_confirmed: bool = False
    min_access_level: str = "NONE"  # "NONE", "FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM"
    require_active_session: bool = False
    require_valid_credential: bool = False
    require_reachability: bool = False
    objective_not_achieved: bool = False
    allowed_phases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.min_access_level == "UNPRIVILEGED":
            object.__setattr__(self, "min_access_level", "USER")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PreconditionContract:
        if not data:
            return cls()
        min_access = data.get("min_access_level", "NONE")
        if min_access == "UNPRIVILEGED":
            min_access = "USER"
        return cls(
            target_visible=bool(data.get("target_visible", False)),
            host_observed=bool(data.get("host_observed", False)),
            service_observed=bool(data.get("service_observed", False)),
            required_service_type=data.get("required_service_type"),
            finding_confirmed=bool(data.get("finding_confirmed", False)),
            min_access_level=min_access,
            require_active_session=bool(data.get("require_active_session", False)),
            require_valid_credential=bool(data.get("require_valid_credential", False)),
            require_reachability=bool(data.get("require_reachability", False)),
            objective_not_achieved=bool(data.get("objective_not_achieved", False)),
            allowed_phases=tuple(data.get("allowed_phases", ())),
        )


@dataclass(frozen=True)
class EffectContract:
    """Expected/potential effects used strictly for documentation and heuristics.

    HARD INVARIANT:
      This object does NOT mutate BeliefState, StateManager, or KnowledgeStateStore.
      State transitions can only be triggered via canonical observations emitted by
      the executor and normalized by ObservationNormalizer.
    """
    potential_facts: tuple[str, ...] = ()
    potential_access_level: str | None = None
    potential_session_transition: str | None = None  # "NONE", "OPEN_SESSION", "CLOSE_SESSION"
    potential_credential_discovery: bool = False
    potential_lateral_reachability: bool = False
    potential_objective_completion: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if self.potential_access_level == "UNPRIVILEGED":
            object.__setattr__(self, "potential_access_level", "USER")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EffectContract:
        if not data:
            return cls()
        pot_access = data.get("potential_access_level")
        if pot_access == "UNPRIVILEGED":
            pot_access = "USER"
        return cls(
            potential_facts=tuple(data.get("potential_facts", ())),
            potential_access_level=pot_access,
            potential_session_transition=data.get("potential_session_transition"),
            potential_credential_discovery=bool(data.get("potential_credential_discovery", False)),
            potential_lateral_reachability=bool(data.get("potential_lateral_reachability", False)),
            potential_objective_completion=bool(data.get("potential_objective_completion", False)),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class MitreAttackMetadata:
    """Non-operational reference metadata mapping action capability to MITRE ATT&CK."""
    tactic: str
    technique_id: str
    technique_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MitreAttackMetadata | None:
        if not data:
            return None
        return cls(
            tactic=data["tactic"],
            technique_id=data["technique_id"],
            technique_name=data.get("technique_name", ""),
        )


@dataclass(frozen=True)
class ActionDefinition:
    """Canonical generic action capability definition adhering to RT-03A contract."""
    action_id: str
    action_class: str = "GENERIC"
    name: str = ""
    description: str = ""
    target_kind: str = "HOST"
    classification: str = "ENTERPRISE_TTP"
    preconditions: PreconditionContract = field(default_factory=PreconditionContract)
    expected_effects: EffectContract = field(default_factory=EffectContract)
    step_cost: int = 1
    noise_cost: float = 1.0
    required_capability: str = "NETWORK_CLIENT"
    argument_schema: dict[str, Any] = field(default_factory=dict)
    mitre_attack: MitreAttackMetadata | None = None
    target_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionDefinition:
        return cls(
            action_id=data["action_id"],
            action_class=data["action_class"],
            name=data.get("name", data["action_id"]),
            description=data.get("description", ""),
            target_kind=data.get("target_kind", "NONE"),
            classification=data.get("classification", "ENTERPRISE_TTP"),
            preconditions=PreconditionContract.from_dict(data.get("preconditions")),
            expected_effects=EffectContract.from_dict(data.get("expected_effects")),
            step_cost=int(data.get("step_cost", 1)),
            noise_cost=float(data.get("noise_cost", 1.0)),
            required_capability=data.get("required_capability", "NETWORK_CLIENT"),
            argument_schema=dict(data.get("argument_schema", data.get("parameters", {}))),
            mitre_attack=MitreAttackMetadata.from_dict(data.get("mitre_attack")),
            target_id=data.get("target_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary matching action.schema.json."""
        out: dict[str, Any] = {
            "action_id": self.action_id,
            "action_class": self.action_class,
            "name": self.name,
            "description": self.description,
            "target_kind": self.target_kind,
            "classification": self.classification,
            "step_cost": self.step_cost,
            "noise_cost": self.noise_cost,
            "required_capability": self.required_capability,
        }
        pre = {
            k: v for k, v in {
                "target_visible": self.preconditions.target_visible,
                "host_observed": self.preconditions.host_observed,
                "service_observed": self.preconditions.service_observed,
                "required_service_type": self.preconditions.required_service_type,
                "finding_confirmed": self.preconditions.finding_confirmed,
                "min_access_level": self.preconditions.min_access_level if self.preconditions.min_access_level != "NONE" else None,
                "require_active_session": self.preconditions.require_active_session,
                "require_valid_credential": self.preconditions.require_valid_credential,
                "require_reachability": self.preconditions.require_reachability,
                "objective_not_achieved": self.preconditions.objective_not_achieved,
                "allowed_phases": list(self.preconditions.allowed_phases) if self.preconditions.allowed_phases else None,
            }.items() if v is not None and v is not False
        }
        if pre:
            out["preconditions"] = pre
        effects = {
            k: v for k, v in {
                "potential_facts": list(self.expected_effects.potential_facts) if self.expected_effects.potential_facts else None,
                "potential_access_level": self.expected_effects.potential_access_level,
                "potential_session_transition": self.expected_effects.potential_session_transition,
                "potential_credential_discovery": self.expected_effects.potential_credential_discovery or None,
                "potential_lateral_reachability": self.expected_effects.potential_lateral_reachability or None,
                "potential_objective_completion": self.expected_effects.potential_objective_completion or None,
                "description": self.expected_effects.description or None,
            }.items() if v is not None
        }
        if effects:
            out["expected_effects"] = effects
        if self.mitre_attack:
            out["mitre_attack"] = {
                "tactic": self.mitre_attack.tactic,
                "technique_id": self.mitre_attack.technique_id,
            }
            if self.mitre_attack.technique_name:
                out["mitre_attack"]["technique_name"] = self.mitre_attack.technique_name
        if self.target_id:
            out["target_id"] = self.target_id
        if self.argument_schema:
            out["argument_schema"] = self.argument_schema
        return out


class ActionRegistry:
    """Thread-safe, read-only canonical registry of bounded action definitions."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        self._path = catalog_path or CATALOG_PATH
        self._schema = json.loads(ACTION_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._actions: dict[str, ActionDefinition] = {}
        self._enterprise_actions: dict[str, ActionDefinition] = {}
        self._legacy_actions: dict[str, ActionDefinition] = {}
        self._load()

    def _load(self) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        # Load canonical actions list
        for item in data.get("actions", []):
            action = ActionDefinition.from_dict(item)
            self._actions[action.action_id] = action
            if action.classification == "LEGACY_WEB_COMPAT":
                self._legacy_actions[action.action_id] = action
            else:
                self._enterprise_actions[action.action_id] = action

        # Load enterprise actions list
        for item in data.get("enterprise_actions", []):
            action = ActionDefinition.from_dict(item)
            self._enterprise_actions[action.action_id] = action
            if action.action_id not in self._actions:
                self._actions[action.action_id] = action

    def get_action(self, action_id: str) -> ActionDefinition | None:
        return self._actions.get(action_id)

    def get_all_actions(self) -> list[ActionDefinition]:
        return list(self._actions.values())

    def get_enterprise_actions(self) -> list[ActionDefinition]:
        return list(self._enterprise_actions.values())

    def get_legacy_actions(self) -> list[ActionDefinition]:
        return list(self._legacy_actions.values())

    def validate_action(self, action: ActionDefinition) -> list[str]:
        """Validate an ActionDefinition against canonical Draft 2020-12 action.schema.json."""
        return validate_shape(action.to_dict(), self._schema)


_DEFAULT_REGISTRY: ActionRegistry | None = None


def get_action_registry(catalog_path: Path | None = None) -> ActionRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None or catalog_path is not None:
        reg = ActionRegistry(catalog_path)
        if catalog_path is None:
            _DEFAULT_REGISTRY = reg
        return reg
    return _DEFAULT_REGISTRY


def scan_action_for_target_leakage(action: ActionDefinition | dict[str, Any]) -> list[str]:
    """Automated scan verifying an action definition contains zero target-bound leakage."""
    raw = action.to_dict() if isinstance(action, ActionDefinition) else action
    text = json.dumps(raw)
    errors: list[str] = []

    # Target ID should not be present in generic enterprise TTP actions
    if raw.get("classification") == "ENTERPRISE_TTP" and "target_id" in raw:
        errors.append(f"{raw.get('action_id')}: generic enterprise action must not specify target_id")

    # Check for hardcoded target instances in text, descriptions, names
    for key in ("name", "description"):
        val = raw.get(key, "")
        if TARGET_LEAKAGE_PATTERN.search(val):
            errors.append(f"{raw.get('action_id')}.{key}: contains target leakage or ground truth pattern: {val!r}")

    return errors


def evaluate_precondition_contract(
    action: ActionDefinition,
    belief_state: Any,
    target_id: str | None = None,
) -> tuple[bool, list[str]]:
    """Contract-level precondition evaluation delegating to canonical ActionConstraintEvaluator.

    Canonical evaluator resides at runtime.evaluators.action_evaluator.ActionConstraintEvaluator.
    This helper is retained as a thin wrapper for backward compatibility.
    """
    from runtime.evaluators.action_evaluator import ActionConstraintEvaluator

    evaluator = ActionConstraintEvaluator()
    result = evaluator.evaluate(action=action, target_id=target_id, belief_state=belief_state)
    return result.eligible, list(result.reasons)


# Canonical 9 benchmark actions for planner-facing candidate space (RT-05A1)
CANONICAL_BENCHMARK_ACTION_IDS: tuple[str, ...] = (
    "ACTION-DISCOVERY-001",
    "ACTION-SCAN-001",
    "ACTION-FOOTHOLD-001",
    "ACTION-HOSTRECON-001",
    "ACTION-CREDS-001",
    "ACTION-PIVOT-001",
    "ACTION-PRIVESC-001",
    "ACTION-OBJECTIVE-001",
    "ACTION-STOP-001",
)

# Semantic capability family mapping for deduplication and equivalence (RT-05A1)
ACTION_FAMILY_MAP: dict[str, str] = {
    # Network Discovery / Recon
    "ACTION-RECON-001": "NETWORK_DISCOVERY",
    "ACTION-DISCOVERY-001": "NETWORK_DISCOVERY",
    # Service / Web Scan
    "ACTION-SCAN-001": "SERVICE_SCAN",
    "ACTION-SCAN-002": "ACTIVE_SCAN",
    "ACTION-RECON-002": "WEB_SURFACE_DISCOVERY",
    # Initial Access / Foothold
    "ACTION-WEB-001": "INITIAL_FOOTHOLD",
    "ACTION-WEB-002": "INITIAL_FOOTHOLD",
    "ACTION-WEB-003": "INITIAL_FOOTHOLD",
    "ACTION-FOOTHOLD-001": "INITIAL_FOOTHOLD",
    # Host Recon
    "ACTION-HOSTRECON-001": "HOST_RECON",
    # Credential Discovery
    "ACTION-AUTH-001": "CREDENTIAL_DISCOVERY",
    "ACTION-CREDS-001": "CREDENTIAL_DISCOVERY",
    # Lateral Movement / Pivot
    "ACTION-FLOW-001": "LATERAL_PIVOT",
    "ACTION-PIVOT-001": "LATERAL_PIVOT",
    # Privilege Escalation
    "ACTION-PRIVESC-001": "PRIVILEGE_ESCALATION",
    # Objective Access
    "ACTION-FLOW-002": "OBJECTIVE_ACCESS",
    "ACTION-OBJECTIVE-001": "OBJECTIVE_ACCESS",
    # Termination / Stop
    "ACTION-END-001": "STOP",
    "ACTION-END-002": "STOP",
    "ACTION-END-003": "STOP",
    "ACTION-STOP-001": "STOP",
    # Planning / Meta
    "ACTION-PLAN-001": "PLANNING",
    "ACTION-PLAN-002": "PLANNING",
    "ACTION-PLAN-003": "PLANNING",
}

# Mapping from legacy action IDs to canonical generic benchmark action IDs (RT-05A1)
CANONICAL_ACTION_MAP: dict[str, str] = {
    "ACTION-RECON-001": "ACTION-DISCOVERY-001",
    "ACTION-DISCOVERY-001": "ACTION-DISCOVERY-001",
    "ACTION-SCAN-001": "ACTION-SCAN-001",
    "ACTION-WEB-001": "ACTION-FOOTHOLD-001",
    "ACTION-FOOTHOLD-001": "ACTION-FOOTHOLD-001",
    "ACTION-HOSTRECON-001": "ACTION-HOSTRECON-001",
    "ACTION-AUTH-001": "ACTION-CREDS-001",
    "ACTION-CREDS-001": "ACTION-CREDS-001",
    "ACTION-FLOW-001": "ACTION-PIVOT-001",
    "ACTION-PIVOT-001": "ACTION-PIVOT-001",
    "ACTION-PRIVESC-001": "ACTION-PRIVESC-001",
    "ACTION-FLOW-002": "ACTION-OBJECTIVE-001",
    "ACTION-OBJECTIVE-001": "ACTION-OBJECTIVE-001",
    "ACTION-END-001": "ACTION-STOP-001",
    "ACTION-END-002": "ACTION-STOP-001",
    "ACTION-END-003": "ACTION-STOP-001",
    "ACTION-STOP-001": "ACTION-STOP-001",
}

# Mapping from canonical generic benchmark action IDs to legacy execution aliases
LEGACY_EXECUTION_MAP: dict[str, str] = {
    "ACTION-DISCOVERY-001": "ACTION-RECON-001",
    "ACTION-SCAN-001": "ACTION-SCAN-001",
    "ACTION-FOOTHOLD-001": "ACTION-WEB-001",
    "ACTION-CREDS-001": "ACTION-AUTH-001",
    "ACTION-PIVOT-001": "ACTION-FLOW-001",
    "ACTION-OBJECTIVE-001": "ACTION-FLOW-002",
    "ACTION-STOP-001": "ACTION-END-001",
}


def get_action_family(action_id: str) -> str | None:
    """Return the semantic capability family for an action ID."""
    return ACTION_FAMILY_MAP.get(action_id)


def get_canonical_action_id(action_id: str) -> str:
    """Return the canonical generic benchmark action ID for an action ID."""
    return CANONICAL_ACTION_MAP.get(action_id, action_id)


def get_legacy_action_id(action_id: str) -> str | None:
    """Return the legacy execution alias for an action ID if one exists."""
    return LEGACY_EXECUTION_MAP.get(action_id)


def are_actions_equivalent(action_a: str, action_b: str) -> bool:
    """Check if two action IDs represent the same underlying capability."""
    if action_a == action_b:
        return True
    can_a = CANONICAL_ACTION_MAP.get(action_a, action_a)
    can_b = CANONICAL_ACTION_MAP.get(action_b, action_b)
    if can_a == can_b:
        return True
    fam_a = ACTION_FAMILY_MAP.get(action_a)
    fam_b = ACTION_FAMILY_MAP.get(action_b)
    return fam_a is not None and fam_a == fam_b

