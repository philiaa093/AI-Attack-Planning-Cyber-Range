"""Simulator True State Model (RT-04A).

Represents runtime simulator ground truth. Strictly confined to the evaluation and
simulation domain.

HARD INVARIANTS:
1. Physical Isolation: This model and its instances are strictly forbidden from being imported,
   read, or subclassed by any module in runtime/planners/** or agent/planner/**.
2. Distinct Model Architecture: TrueState is an independent ground-truth model and does NOT
   inherit from, subclass, or share state representations with BeliefState.
3. Determinism: Same scenario seed and action sequence serializes bit-for-bit deterministically.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence


ACCESS_LEVELS = ("NONE", "FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM")
SESSION_STATES = ("ACTIVE", "CLOSED", "TERMINATED")
CREDENTIAL_VALIDITY_STATES = ("VALID", "INVALID", "REVOKED", "HONEY_TOKEN")
DETECTION_STATES = ("QUIET", "MONITORING", "ALERTED", "CONTAINED")


@dataclass(frozen=True)
class NodeTrueState:
    node_id: str
    access_level: str
    compromised: bool
    foothold_established: bool
    active_session_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.access_level not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access_level: {self.access_level!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "access_level": self.access_level,
            "compromised": self.compromised,
            "foothold_established": self.foothold_established,
            "active_session_ids": list(self.active_session_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NodeTrueState:
        return cls(
            node_id=str(data["node_id"]),
            access_level=str(data["access_level"]),
            compromised=bool(data["compromised"]),
            foothold_established=bool(data["foothold_established"]),
            active_session_ids=tuple(str(s) for s in data.get("active_session_ids", ())),
        )


@dataclass(frozen=True)
class SimulatedSession:
    session_id: str
    node_id: str
    access_level: str
    established_at_step: int
    session_state: str = "ACTIVE"

    def __post_init__(self) -> None:
        if self.session_state not in SESSION_STATES:
            raise ValueError(f"Invalid session_state: {self.session_state!r}")
        if self.access_level not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access_level: {self.access_level!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "node_id": self.node_id,
            "access_level": self.access_level,
            "established_at_step": self.established_at_step,
            "session_state": self.session_state,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SimulatedSession:
        return cls(
            session_id=str(data["session_id"]),
            node_id=str(data["node_id"]),
            access_level=str(data["access_level"]),
            established_at_step=int(data["established_at_step"]),
            session_state=str(data.get("session_state", "ACTIVE")),
        )


@dataclass(frozen=True)
class CredentialTruth:
    credential_id: str
    principal: str
    validity_state: str
    discovered: bool = False
    used_count: int = 0

    def __post_init__(self) -> None:
        if self.validity_state not in CREDENTIAL_VALIDITY_STATES:
            raise ValueError(f"Invalid validity_state: {self.validity_state!r}")
        if self.used_count < 0:
            raise ValueError(f"used_count must be non-negative: {self.used_count}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "principal": self.principal,
            "validity_state": self.validity_state,
            "discovered": self.discovered,
            "used_count": self.used_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CredentialTruth:
        return cls(
            credential_id=str(data["credential_id"]),
            principal=str(data["principal"]),
            validity_state=str(data["validity_state"]),
            discovered=bool(data.get("discovered", False)),
            used_count=int(data.get("used_count", 0)),
        )


@dataclass(frozen=True)
class ReachabilityEdge:
    source: str
    target: str
    protocol: str
    port: int | None = None
    is_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "protocol": self.protocol,
            "port": self.port,
            "is_blocked": self.is_blocked,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReachabilityEdge:
        return cls(
            source=str(data["source"]),
            target=str(data["target"]),
            protocol=str(data["protocol"]),
            port=int(data["port"]) if data.get("port") is not None else None,
            is_blocked=bool(data.get("is_blocked", False)),
        )


@dataclass(frozen=True)
class ObjectiveTruth:
    objective_id: str
    target_node_id: str
    is_achieved: bool = False
    achieved_at_step: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "target_node_id": self.target_node_id,
            "is_achieved": self.is_achieved,
            "achieved_at_step": self.achieved_at_step,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ObjectiveTruth:
        return cls(
            objective_id=str(data["objective_id"]),
            target_node_id=str(data["target_node_id"]),
            is_achieved=bool(data.get("is_achieved", False)),
            achieved_at_step=int(data["achieved_at_step"]) if data.get("achieved_at_step") is not None else None,
        )


@dataclass(frozen=True)
class DefenderState:
    accumulated_noise: float = 0.0
    detection_state: str = "QUIET"
    alerts_triggered: int = 0
    contained_nodes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.detection_state not in DETECTION_STATES:
            raise ValueError(f"Invalid detection_state: {self.detection_state!r}")
        if self.accumulated_noise < 0.0:
            raise ValueError(f"accumulated_noise must be non-negative: {self.accumulated_noise}")
        if self.alerts_triggered < 0:
            raise ValueError(f"alerts_triggered must be non-negative: {self.alerts_triggered}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "accumulated_noise": float(self.accumulated_noise),
            "detection_state": self.detection_state,
            "alerts_triggered": self.alerts_triggered,
            "contained_nodes": list(self.contained_nodes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DefenderState:
        return cls(
            accumulated_noise=float(data.get("accumulated_noise", 0.0)),
            detection_state=str(data.get("detection_state", "QUIET")),
            alerts_triggered=int(data.get("alerts_triggered", 0)),
            contained_nodes=tuple(str(n) for n in data.get("contained_nodes", ())),
        )


@dataclass(frozen=True)
class SimulatorActionRecord:
    step: int
    action_id: str
    success: bool
    noise_delta: float
    timestamp_utc: str
    target_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action_id": self.action_id,
            "target_node_id": self.target_node_id,
            "success": self.success,
            "noise_delta": float(self.noise_delta),
            "timestamp_utc": self.timestamp_utc,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SimulatorActionRecord:
        return cls(
            step=int(data["step"]),
            action_id=str(data["action_id"]),
            target_node_id=data.get("target_node_id"),
            success=bool(data["success"]),
            noise_delta=float(data.get("noise_delta", 0.0)),
            timestamp_utc=str(data["timestamp_utc"]),
        )


@dataclass(frozen=True)
class TrueState:
    scenario_id: str
    run_id: str
    current_step: int
    random_seed: int
    node_states: dict[str, NodeTrueState]
    active_sessions: dict[str, SimulatedSession]
    credentials_truth: dict[str, CredentialTruth]
    reachability_truth: tuple[ReachabilityEdge, ...]
    objective_truth: ObjectiveTruth
    defender_state: DefenderState
    action_history: tuple[SimulatorActionRecord, ...] = ()

    def get_node_access_level(self, node_id: str) -> str:
        state = self.node_states.get(node_id)
        return state.access_level if state else "NONE"

    def has_active_session(self, node_id: str) -> bool:
        for sess in self.active_sessions.values():
            if sess.node_id == node_id and sess.session_state == "ACTIVE":
                return True
        return False

    def is_objective_achieved(self) -> bool:
        return self.objective_truth.is_achieved

    def get_compromised_nodes(self) -> list[str]:
        return sorted([nid for nid, ns in self.node_states.items() if ns.compromised])

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "current_step": self.current_step,
            "random_seed": self.random_seed,
            "node_states": {k: v.to_dict() for k, v in sorted(self.node_states.items())},
            "active_sessions": {k: v.to_dict() for k, v in sorted(self.active_sessions.items())},
            "credentials_truth": {k: v.to_dict() for k, v in sorted(self.credentials_truth.items())},
            "reachability_truth": [e.to_dict() for e in self.reachability_truth],
            "objective_truth": self.objective_truth.to_dict(),
            "defender_state": self.defender_state.to_dict(),
            "action_history": [a.to_dict() for a in self.action_history],
        }

    def deterministic_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    def deterministic_hash(self) -> str:
        return hashlib.sha256(self.deterministic_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrueState:
        node_states = {
            k: NodeTrueState.from_dict(v) for k, v in data.get("node_states", {}).items()
        }
        active_sessions = {
            k: SimulatedSession.from_dict(v) for k, v in data.get("active_sessions", {}).items()
        }
        credentials_truth = {
            k: CredentialTruth.from_dict(v) for k, v in data.get("credentials_truth", {}).items()
        }
        reachability_truth = tuple(
            ReachabilityEdge.from_dict(e) for e in data.get("reachability_truth", ())
        )
        objective_truth = ObjectiveTruth.from_dict(data["objective_truth"])
        defender_state = DefenderState.from_dict(data["defender_state"])
        action_history = tuple(
            SimulatorActionRecord.from_dict(a) for a in data.get("action_history", ())
        )
        return cls(
            scenario_id=str(data["scenario_id"]),
            run_id=str(data["run_id"]),
            current_step=int(data["current_step"]),
            random_seed=int(data["random_seed"]),
            node_states=node_states,
            active_sessions=active_sessions,
            credentials_truth=credentials_truth,
            reachability_truth=reachability_truth,
            objective_truth=objective_truth,
            defender_state=defender_state,
            action_history=action_history,
        )
