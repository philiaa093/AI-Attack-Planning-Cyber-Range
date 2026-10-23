"""Hidden Simulator Scenario Model (RT-04A).

Represents the complete ground-truth environment specification used exclusively by
the Enterprise Attack Simulator and Evaluation environment.

HARD INVARIANTS:
1. Ground Truth Isolation: This model and its instances are strictly forbidden from being
   imported, loaded, or inspected by any module in runtime/planners/** or agent/planner/**.
2. Zero-Knowledge Initial State: Only the entry seed node identity may be exposed to the
   planner at t=0. Hidden nodes, topology edges, vulnerabilities, credentials, and objective
   locations remain confidential inside this model.
3. Declarative Specification: No executable code, shell commands, or arbitrary Python expressions
   are permitted in scenario contracts.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.simulation.models.true_state import TrueState


NODE_KINDS = (
    "ENTRY",
    "INTERNAL_HOST",
    "DMZ_HOST",
    "DATABASE",
    "CRITICAL_ASSET",
    "DECOY",
    "WORKSTATION",
    "SERVER",
)

VULNERABILITY_FAMILIES = (
    "SQLI",
    "PATH_TRAVERSAL",
    "COMMAND_INJECTION",
    "WEAK_AUTH",
    "RCE",
    "DESERIALIZATION",
    "MISCONFIGURATION",
)

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

ACCESS_LEVELS = ("NONE", "FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM")

CREDENTIAL_KINDS = ("PASSWORD", "SSH_KEY", "API_TOKEN", "KERBEROS_TICKET", "JWT")

CREDENTIAL_VALIDITY_STATES = ("VALID", "INVALID", "REVOKED", "HONEY_TOKEN")

DETECTION_STATES = ("QUIET", "MONITORING", "ALERTED", "CONTAINED")

COMPLETION_CONDITIONS = ("ACCESS", "EXFILTRATE", "MODIFY")


@dataclass(frozen=True)
class ServiceDefinition:
    service_id: str
    port: int
    protocol: str
    service_type: str
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "port": self.port,
            "protocol": self.protocol,
            "service_type": self.service_type,
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ServiceDefinition:
        return cls(
            service_id=str(data["service_id"]),
            port=int(data["port"]),
            protocol=str(data["protocol"]),
            service_type=str(data["service_type"]),
            capabilities=tuple(str(c) for c in data.get("capabilities", ())),
        )


@dataclass(frozen=True)
class VulnerabilityPrerequisites:
    min_access_level: str = "NONE"
    require_valid_credential: bool = False
    required_credential_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {"min_access_level": self.min_access_level}
        if self.require_valid_credential:
            res["require_valid_credential"] = True
        if self.required_credential_id:
            res["required_credential_id"] = self.required_credential_id
        return res

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> VulnerabilityPrerequisites:
        if not data:
            return cls()
        return cls(
            min_access_level=str(data.get("min_access_level", "NONE")),
            require_valid_credential=bool(data.get("require_valid_credential", False)),
            required_credential_id=data.get("required_credential_id"),
        )


@dataclass(frozen=True)
class VulnerabilityDefinition:
    vulnerability_id: str
    vulnerability_family: str
    severity: str
    target_service_id: str | None = None
    prerequisites: VulnerabilityPrerequisites = field(default_factory=VulnerabilityPrerequisites)

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "vulnerability_id": self.vulnerability_id,
            "vulnerability_family": self.vulnerability_family,
            "severity": self.severity,
            "target_service_id": self.target_service_id,
        }
        prereq_dict = self.prerequisites.to_dict()
        if prereq_dict:
            res["prerequisites"] = prereq_dict
        return res

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VulnerabilityDefinition:
        return cls(
            vulnerability_id=str(data["vulnerability_id"]),
            vulnerability_family=str(data["vulnerability_family"]),
            severity=str(data["severity"]),
            target_service_id=data.get("target_service_id"),
            prerequisites=VulnerabilityPrerequisites.from_dict(data.get("prerequisites")),
        )


@dataclass(frozen=True)
class HiddenNode:
    node_id: str
    node_kind: str
    network_zone: str
    services: tuple[ServiceDefinition, ...] = ()
    vulnerabilities: tuple[VulnerabilityDefinition, ...] = ()
    initial_access_level: str = "NONE"
    ip: str | None = None
    hostname: str | None = None
    is_decoy: bool = False
    decoy_metadata: dict[str, Any] | None = None
    credentials_present: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "node_id": self.node_id,
            "node_kind": self.node_kind,
            "network_zone": self.network_zone,
            "ip": self.ip,
            "hostname": self.hostname,
            "is_decoy": self.is_decoy,
            "initial_access_level": self.initial_access_level,
            "services": [s.to_dict() for s in self.services],
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "credentials_present": list(self.credentials_present),
        }
        if self.decoy_metadata is not None:
            res["decoy_metadata"] = copy.deepcopy(self.decoy_metadata)
        return res

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HiddenNode:
        return cls(
            node_id=str(data["node_id"]),
            node_kind=str(data["node_kind"]),
            network_zone=str(data["network_zone"]),
            services=tuple(ServiceDefinition.from_dict(s) for s in data.get("services", ())),
            vulnerabilities=tuple(VulnerabilityDefinition.from_dict(v) for v in data.get("vulnerabilities", ())),
            initial_access_level=str(data.get("initial_access_level", "NONE")),
            ip=data.get("ip"),
            hostname=data.get("hostname"),
            is_decoy=bool(data.get("is_decoy", False)),
            decoy_metadata=copy.deepcopy(data.get("decoy_metadata")),
            credentials_present=tuple(str(c) for c in data.get("credentials_present", ())),
        )


@dataclass(frozen=True)
class TopologyEdge:
    edge_id: str
    source: str
    target: str
    protocol: str
    is_blocked: bool = False
    port: int | None = None
    bidirectional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source": self.source,
            "target": self.target,
            "protocol": self.protocol,
            "port": self.port,
            "bidirectional": self.bidirectional,
            "is_blocked": self.is_blocked,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TopologyEdge:
        return cls(
            edge_id=str(data["edge_id"]),
            source=str(data["source"]),
            target=str(data["target"]),
            protocol=str(data["protocol"]),
            port=int(data["port"]) if data.get("port") is not None else None,
            bidirectional=bool(data.get("bidirectional", False)),
            is_blocked=bool(data.get("is_blocked", False)),
        )


@dataclass(frozen=True)
class HiddenTopology:
    edges: tuple[TopologyEdge, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"edges": [e.to_dict() for e in self.edges]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HiddenTopology:
        return cls(edges=tuple(TopologyEdge.from_dict(e) for e in data.get("edges", ())))


@dataclass(frozen=True)
class HiddenCredential:
    credential_id: str
    principal: str
    credential_kind: str
    valid_nodes: tuple[str, ...] = ()
    granted_access_level: str = "USER"
    validity_state: str = "VALID"
    is_decoy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "principal": self.principal,
            "credential_kind": self.credential_kind,
            "valid_nodes": list(self.valid_nodes),
            "granted_access_level": self.granted_access_level,
            "validity_state": self.validity_state,
            "is_decoy": self.is_decoy,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HiddenCredential:
        return cls(
            credential_id=str(data["credential_id"]),
            principal=str(data["principal"]),
            credential_kind=str(data["credential_kind"]),
            valid_nodes=tuple(str(n) for n in data.get("valid_nodes", ())),
            granted_access_level=str(data.get("granted_access_level", "USER")),
            validity_state=str(data.get("validity_state", "VALID")),
            is_decoy=bool(data.get("is_decoy", False)),
        )


@dataclass(frozen=True)
class ObjectiveDefinition:
    objective_id: str
    target_node_id: str
    required_access_level: str
    completion_condition: str
    target_artifact: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "objective_id": self.objective_id,
            "target_node_id": self.target_node_id,
            "target_artifact": self.target_artifact,
            "required_access_level": self.required_access_level,
            "completion_condition": self.completion_condition,
        }
        if self.description:
            res["description"] = self.description
        return res

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ObjectiveDefinition:
        return cls(
            objective_id=str(data["objective_id"]),
            target_node_id=str(data["target_node_id"]),
            target_artifact=data.get("target_artifact"),
            required_access_level=str(data["required_access_level"]),
            completion_condition=str(data["completion_condition"]),
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True)
class DetectionModel:
    noise_threshold: float
    alert_threshold: float
    initial_detection_state: str = "QUIET"
    containment_threshold: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "noise_threshold": float(self.noise_threshold),
            "alert_threshold": float(self.alert_threshold),
            "initial_detection_state": self.initial_detection_state,
        }
        if self.containment_threshold > 0.0:
            res["containment_threshold"] = float(self.containment_threshold)
        return res

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DetectionModel:
        return cls(
            noise_threshold=float(data["noise_threshold"]),
            alert_threshold=float(data["alert_threshold"]),
            initial_detection_state=str(data.get("initial_detection_state", "QUIET")),
            containment_threshold=float(data.get("containment_threshold", 0.0)),
        )


@dataclass(frozen=True)
class ObservationTemplate:
    fact_type: str
    emit_on: str  # "SUCCESS", "FAILURE", "ALWAYS"
    probability: float
    confidence: float
    source_kind: str
    subject_template: str
    value_template: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_type": self.fact_type,
            "emit_on": self.emit_on,
            "probability": float(self.probability),
            "confidence": float(self.confidence),
            "source_kind": self.source_kind,
            "subject_template": self.subject_template,
            "value_template": copy.deepcopy(self.value_template),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ObservationTemplate:
        return cls(
            fact_type=str(data["fact_type"]),
            emit_on=str(data["emit_on"]),
            probability=float(data["probability"]),
            confidence=float(data["confidence"]),
            source_kind=str(data["source_kind"]),
            subject_template=str(data["subject_template"]),
            value_template=copy.deepcopy(data["value_template"]),
        )


@dataclass(frozen=True)
class StateMutations:
    grant_access_level: str | None = None
    create_session: bool = False
    close_session: bool = False
    reveal_credentials: tuple[str, ...] | None = None
    set_objective_achieved: bool = False
    block_edges: tuple[dict[str, str], ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {}
        if self.grant_access_level is not None:
            res["grant_access_level"] = self.grant_access_level
        if self.create_session:
            res["create_session"] = True
        if self.close_session:
            res["close_session"] = True
        if self.reveal_credentials is not None:
            res["reveal_credentials"] = list(self.reveal_credentials)
        if self.set_objective_achieved:
            res["set_objective_achieved"] = True
        if self.block_edges is not None:
            res["block_edges"] = [copy.deepcopy(e) for e in self.block_edges]
        return res

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> StateMutations:
        if not data:
            return cls()
        reveal = data.get("reveal_credentials")
        block = data.get("block_edges")
        return cls(
            grant_access_level=data.get("grant_access_level"),
            create_session=bool(data.get("create_session", False)),
            close_session=bool(data.get("close_session", False)),
            reveal_credentials=tuple(str(c) for c in reveal) if reveal is not None else None,
            set_objective_achieved=bool(data.get("set_objective_achieved", False)),
            block_edges=tuple(dict(e) for e in block) if block is not None else None,
        )


@dataclass(frozen=True)
class TransitionOutcome:
    mutations: StateMutations
    observations: tuple[ObservationTemplate, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutations": self.mutations.to_dict(),
            "observations": [o.to_dict() for o in self.observations],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TransitionOutcome:
        return cls(
            mutations=StateMutations.from_dict(data.get("mutations")),
            observations=tuple(ObservationTemplate.from_dict(o) for o in data.get("observations", ())),
        )


@dataclass(frozen=True)
class ScenarioTransition:
    transition_id: str
    action_id: str
    match_conditions: dict[str, Any]
    success_probability: float
    noise_delta: float
    success_outcome: TransitionOutcome
    failure_outcome: TransitionOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "action_id": self.action_id,
            "match_conditions": copy.deepcopy(self.match_conditions),
            "success_probability": float(self.success_probability),
            "noise_delta": float(self.noise_delta),
            "success_outcome": self.success_outcome.to_dict(),
            "failure_outcome": self.failure_outcome.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScenarioTransition:
        return cls(
            transition_id=str(data["transition_id"]),
            action_id=str(data["action_id"]),
            match_conditions=copy.deepcopy(dict(data.get("match_conditions", {}))),
            success_probability=float(data["success_probability"]),
            noise_delta=float(data.get("noise_delta", 0.0)),
            success_outcome=TransitionOutcome.from_dict(data["success_outcome"]),
            failure_outcome=TransitionOutcome.from_dict(data["failure_outcome"]),
        )


@dataclass(frozen=True)
class HiddenScenario:
    schema_version: str
    scenario_id: str
    name: str
    description: str
    entry_seed: str
    hidden_nodes: tuple[HiddenNode, ...]
    hidden_topology: HiddenTopology
    hidden_credentials: tuple[HiddenCredential, ...]
    objective: ObjectiveDefinition
    detection_model: DetectionModel
    transitions: tuple[ScenarioTransition, ...]
    random_seed: int | None = None

    def get_node(self, node_id: str) -> HiddenNode | None:
        for node in self.hidden_nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_entry_node(self) -> HiddenNode:
        entry = self.get_node(self.entry_seed)
        if entry is None:
            raise ValueError(f"Entry seed node {self.entry_seed!r} not found in scenario nodes")
        return entry

    def get_reachable_neighbors(self, node_id: str) -> list[str]:
        neighbors: list[str] = []
        for edge in self.hidden_topology.edges:
            if edge.is_blocked:
                continue
            if edge.source == node_id:
                neighbors.append(edge.target)
            elif edge.bidirectional and edge.target == node_id:
                neighbors.append(edge.source)
        return sorted(set(neighbors))

    def create_initial_true_state(self, run_id: str, seed: int | None = None) -> TrueState:
        """Create initial ground-truth state at t=0 for this scenario."""
        from runtime.simulation.models.true_state import (
            TrueState,
            NodeTrueState,
            SimulatedSession,
            CredentialTruth,
            ReachabilityEdge,
            ObjectiveTruth,
            DefenderState,
        )

        effective_seed = seed if seed is not None else (self.random_seed or 0)
        node_states: dict[str, NodeTrueState] = {}
        active_sessions: dict[str, SimulatedSession] = {}

        for node in self.hidden_nodes:
            is_entry = (node.node_id == self.entry_seed)
            initial_lvl = node.initial_access_level
            is_foothold = (initial_lvl in ("FOOTHOLD", "USER", "PRIVILEGED", "SYSTEM"))
            active_sess_ids: list[str] = []

            if is_entry and is_foothold:
                sess_id = f"sess-init-{node.node_id}"
                active_sessions[sess_id] = SimulatedSession(
                    session_id=sess_id,
                    node_id=node.node_id,
                    access_level=initial_lvl,
                    established_at_step=0,
                    session_state="ACTIVE",
                )
                active_sess_ids.append(sess_id)

            node_states[node.node_id] = NodeTrueState(
                node_id=node.node_id,
                access_level=initial_lvl,
                compromised=is_foothold,
                foothold_established=is_foothold,
                active_session_ids=tuple(active_sess_ids),
            )

        creds_truth: dict[str, CredentialTruth] = {}
        for cred in self.hidden_credentials:
            creds_truth[cred.credential_id] = CredentialTruth(
                credential_id=cred.credential_id,
                principal=cred.principal,
                validity_state=cred.validity_state,
                discovered=False,
                used_count=0,
            )

        reach_edges: list[ReachabilityEdge] = []
        for edge in self.hidden_topology.edges:
            reach_edges.append(ReachabilityEdge(
                source=edge.source,
                target=edge.target,
                protocol=edge.protocol,
                port=edge.port,
                is_blocked=edge.is_blocked,
            ))
            if edge.bidirectional:
                reach_edges.append(ReachabilityEdge(
                    source=edge.target,
                    target=edge.source,
                    protocol=edge.protocol,
                    port=edge.port,
                    is_blocked=edge.is_blocked,
                ))

        obj_truth = ObjectiveTruth(
            objective_id=self.objective.objective_id,
            target_node_id=self.objective.target_node_id,
            is_achieved=False,
            achieved_at_step=None,
        )

        defender = DefenderState(
            accumulated_noise=0.0,
            detection_state=self.detection_model.initial_detection_state,
            alerts_triggered=0,
            contained_nodes=(),
        )

        return TrueState(
            scenario_id=self.scenario_id,
            run_id=run_id,
            current_step=0,
            random_seed=effective_seed,
            node_states=node_states,
            active_sessions=active_sessions,
            credentials_truth=creds_truth,
            reachability_truth=tuple(reach_edges),
            objective_truth=obj_truth,
            defender_state=defender,
            action_history=(),
        )

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "entry_seed": self.entry_seed,
            "hidden_nodes": [n.to_dict() for n in self.hidden_nodes],
            "hidden_topology": self.hidden_topology.to_dict(),
            "hidden_credentials": [c.to_dict() for c in self.hidden_credentials],
            "objective": self.objective.to_dict(),
            "detection_model": self.detection_model.to_dict(),
            "transitions": [t.to_dict() for t in self.transitions],
        }
        if self.random_seed is not None:
            res["random_seed"] = self.random_seed
        return res

    def deterministic_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    def deterministic_hash(self) -> str:
        return hashlib.sha256(self.deterministic_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> HiddenScenario:
        return cls(
            schema_version=str(data["schema_version"]),
            scenario_id=str(data["scenario_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            entry_seed=str(data["entry_seed"]),
            hidden_nodes=tuple(HiddenNode.from_dict(n) for n in data.get("hidden_nodes", ())),
            hidden_topology=HiddenTopology.from_dict(data.get("hidden_topology", {})),
            hidden_credentials=tuple(HiddenCredential.from_dict(c) for c in data.get("hidden_credentials", ())),
            objective=ObjectiveDefinition.from_dict(data["objective"]),
            detection_model=DetectionModel.from_dict(data["detection_model"]),
            transitions=tuple(ScenarioTransition.from_dict(t) for t in data.get("transitions", ())),
            random_seed=int(data["random_seed"]) if data.get("random_seed") is not None else None,
        )
