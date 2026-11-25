"""Pydantic models and schemas for Autonomous Cyber Range Control Center."""
from __future__ import annotations

from enum import Enum
import ipaddress
from typing import Any, Dict, List, Literal, Optional
import urllib.parse
from pydantic import BaseModel, Field, model_validator


def validate_target_origin(origin_val: Optional[str]) -> str:
    if not origin_val:
        return "http://127.0.0.1:18088"
    norm = origin_val.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(norm)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("Target origin must use http or https scheme")
    if parsed.username or parsed.password:
        raise ValueError("Userinfo / credentials in target origin forbidden")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("Target origin hostname cannot be empty")
    is_loopback = host in ("127.0.0.1", "localhost", "::1")
    is_private_ip = False
    try:
        ip = ipaddress.ip_address(host)
        is_private_ip = ip.is_private or ip.is_loopback
    except ValueError:
        if host.endswith(".local") or host.endswith(".lab") or host == "host.docker.internal":
            is_private_ip = True
    if not (is_loopback or is_private_ip):
        raise ValueError(
            "Public or external hostnames are forbidden by Centralized Safety Gate policy. "
            "Only loopback or private lab network addresses (e.g. 10.x.x.x, 192.168.x.x) are allowed."
        )
    return norm


SCAN_LAB_ORIGINS = {
    "lab-webapp-a": "http://127.0.0.1:18085",
    "lab-webapp-b": "http://127.0.0.1:18086",
}


def validate_isolated_lab_target(target: str, origin: Optional[str], *, scan_only: bool = False) -> str:
    """Accept only exact target/provider pairs; volatile Web labs support scans only."""
    normalized = validate_target_origin(origin)
    if scan_only and target in SCAN_LAB_ORIGINS and normalized == SCAN_LAB_ORIGINS[target]:
        return normalized
    if target != "lab-ecommerce" or normalized not in (
        "http://127.0.0.1:18088", "http://10.0.0.2:8080",
    ):
        raise ValueError("ISOLATED_LAB_TARGET_UNSUPPORTED")
    return normalized


class RangeState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class AgentState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    PREFLIGHT = "PREFLIGHT"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    RESUMING = "RESUMING"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ControlMode(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    ASSISTED = "ASSISTED"
    MANUAL = "MANUAL"


class StepState(str, Enum):
    NOT_RUN = "NOT_RUN"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASS = "PASS"
    DENIED = "DENIED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class RangeStatus(BaseModel):
    status: RangeState
    target_id: str = "lab-ecommerce"
    origin: str = "http://127.0.0.1:18088"
    services: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    checked_at_utc: str = ""


class AgentStatus(BaseModel):
    state: AgentState = AgentState.IDLE
    mode: str = "RULE"
    planner: str = "rule"
    control_mode: str = "AUTONOMOUS"
    requested_mode: str = "RULE"
    actual_mode: str = "NOT_RUN"
    provider: Optional[str] = "rule_engine"
    model: Optional[str] = "none"
    fallback_reason: Optional[str] = None
    current_action: Optional[str] = None
    current_phase: Optional[str] = "RECON"
    budget_remaining: Dict[str, Any] = Field(default_factory=dict)
    facts_count: int = 0
    decisions_count: int = 0
    pause_count: int = 0
    operator_approvals: int = 0
    operator_rejections: int = 0
    pending_proposal: Optional[Dict[str, Any]] = None
    last_decision: Optional[Dict[str, Any]] = None
    current_execution: Optional[Dict[str, Any]] = None
    last_verification: Optional[Dict[str, Any]] = None
    scanner_status: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class SafetyStatus(BaseModel):
    target_allowlist: List[str] = Field(default_factory=list)
    action_allowlist: List[str] = Field(default_factory=list)
    lab_mode: bool = True
    kill_switch_active: bool = False
    network_dispatches: int = 0
    permits_count: int = 0
    denials_count: int = 0


class EvidenceStatus(BaseModel):
    count: int = 0
    verified_count: int = 0
    pending_count: int = 0
    last_evidence_id: Optional[str] = None
    integrity_status: str = "NOT_STARTED"  # NOT_STARTED, VERIFIED, FAILED


class PipelineStatus(BaseModel):
    current_step: Optional[str] = None
    steps: Dict[str, StepState] = Field(default_factory=dict)


class RunStatus(BaseModel):
    run_id: Optional[str] = None
    state: AgentState = AgentState.IDLE
    mode: str = "presentation"
    planner: str = "rule"
    control_mode: str = "AUTONOMOUS"
    execution_scope: str = "combined"
    scenario: str = "SCN-001"
    target: str = "lab-ecommerce"
    target_origin: Optional[str] = "http://127.0.0.1:18088"
    started_at_utc: Optional[str] = None
    ended_at_utc: Optional[str] = None
    stop_reason: Optional[str] = None
    error: Optional[str] = None
    decisions_count: int = 0
    pause_count: int = 0
    operator_approvals: int = 0
    operator_rejections: int = 0
    network_dispatches: int = 0
    evidence_count: int = 0


class ControlResponse(BaseModel):
    success: bool
    message: str
    run_id: Optional[str] = None
    timestamp_utc: str = ""
    data: Optional[Dict[str, Any]] = None


class PreflightCheckItem(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class PreflightResponse(BaseModel):
    passed: bool
    outcome: str
    checks: List[PreflightCheckItem] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    timestamp_utc: str = ""


class ReadinessCheckItem(BaseModel):
    name: str
    category: str = "REQUIRED"  # "REQUIRED" | "OPTIONAL"
    passed: bool
    status: str                 # "READY" | "DEGRADED" | "BLOCKED" | "NOT_CONFIGURED"
    detail: str = ""
    diagnostic: Optional[str] = None


class DemoReadinessResponse(BaseModel):
    overall_status: str         # "READY" | "DEGRADED" | "BLOCKED"
    summary: str
    timestamp_utc: str = ""
    checks: List[ReadinessCheckItem] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class StartRunRequest(BaseModel):
    mode: str = "presentation"  # presentation, safe, deny-demo, autonomous
    planner: str = "rule"       # rule, llm-unavailable, llm, hybrid
    control_mode: str = "AUTONOMOUS"  # AUTONOMOUS, ASSISTED, MANUAL
    allow_fallback: bool = True
    target: str = "lab-ecommerce"
    target_origin: Optional[str] = "http://127.0.0.1:18088"
    max_decisions: int = Field(default=30, ge=1, le=100, strict=True)
    max_requests: int = Field(default=120, ge=1, le=500, strict=True)
    max_pages: int = Field(default=30, ge=1, le=100, strict=True)
    seed_path: str = "/"
    scenario: str = "SCN-001"
    approve_read_only: bool = True
    approve_active_verification: bool = Field(default=False, strict=True)
    preview_one_page: bool = False
    external_scanners: List[Literal["zap-passive", "zap-active", "nuclei"]] = Field(default_factory=list, max_length=2)
    approve_authenticated_workflow: bool = Field(default=False, strict=True)
    # Existing clients keep their original combined behavior unless they opt
    # into one of the independently runnable scopes.
    execution_scope: Literal["combined", "scan", "workflow"] = "combined"

    @model_validator(mode="after")
    def validate_scanner_scope(self):
        if self.mode != "deny-demo":
            self.target_origin = validate_isolated_lab_target(
                self.target, self.target_origin, scan_only=self.execution_scope == "scan")
        elif self.target_origin:
            self.target_origin = validate_target_origin(self.target_origin)
        if self.execution_scope == "scan" and self.approve_authenticated_workflow:
            raise ValueError("Scan-only runs cannot execute the authenticated workflow")
        if self.execution_scope == "workflow" and (not self.approve_authenticated_workflow
                or self.approve_active_verification or self.external_scanners):
            raise ValueError("Workflow-only runs require workflow approval and cannot enable scanning")
        if self.approve_authenticated_workflow and ((self.execution_scope != "workflow" and not self.approve_active_verification) or self.preview_one_page
                or self.mode != "autonomous" or self.control_mode != "AUTONOMOUS"
                or self.max_requests < 200):
            raise ValueError("Authenticated workflow requires autonomous lab-ecommerce, its scope-specific approval and at least 200 requests")
        selected = set(self.external_scanners)
        if len(selected) != len(self.external_scanners) or {"zap-passive", "zap-active"} <= selected:
            raise ValueError("Choose one ZAP mode and/or Nuclei")
        if selected and (not self.approve_active_verification or self.preview_one_page or self.mode == "deny-demo"):
            raise ValueError("External scanners require explicit lab approval and a non-preview run")
        return self


class ProposalActionRequest(BaseModel):
    reason: Optional[str] = None


class AgentEvent(BaseModel):
    event_id: str
    run_id: str
    type: str
    timestamp_utc: str
    phase: Optional[str] = None
    iteration: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class SystemStatus(BaseModel):
    api: str = "healthy"
    timestamp_utc: str = ""
    range: RangeStatus
    run: RunStatus
    agent: AgentStatus
    safety: SafetyStatus
    evidence: EvidenceStatus
    pipeline: PipelineStatus


class EvidenceItem(BaseModel):
    evidence_id: str
    run_id: str
    artifact_type: str
    path: str
    sha256: str
    size_bytes: int = 0
    verified: bool = False
    created_at_utc: str = ""
    observed_state: str = ""
    expected_state: str = ""


class EvidenceListResponse(BaseModel):
    run_id: str
    evidence_count: int
    verified_count: int
    integrity_status: str
    items: List[EvidenceItem] = Field(default_factory=list)


class EvidenceDetailResponse(BaseModel):
    evidence_id: str
    run_id: str
    artifact_type: str
    path: str
    sha256: str
    verified: bool
    created_at_utc: str
    size_bytes: int
    record: Dict[str, Any] = Field(default_factory=dict)
    content: Any = None


class FindingItem(BaseModel):
    finding_id: str
    run_id: str
    category: str
    severity: str  # INFO, LOW, MEDIUM, HIGH, CRITICAL
    title: str
    detail: str
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    timestamp_utc: str = ""
    classification: str = "OBSERVATION"
    verification_action: str = ""
    tool: str = ""
    resource_ref: str = ""
    input_ref: str = ""
    limitations: List[str] = Field(default_factory=list)


SECURITY_FINDING_CLASSES = frozenset({"CANDIDATE", "SIGNAL", "VERIFIED_IN_LAB"})


class FindingsListResponse(BaseModel):
    run_id: str
    findings_count: int
    items: List[FindingItem] = Field(default_factory=list)


class RunSummaryResponse(BaseModel):
    run_id: str
    status: str
    mode: str
    planner: str
    target: str
    scenario: str
    started_at_utc: Optional[str] = None
    ended_at_utc: Optional[str] = None
    stop_reason: Optional[str] = None
    decisions_count: Optional[int] = None
    approved_actions: Optional[int] = None
    denied_actions: Optional[int] = None
    network_dispatches: Optional[int] = None
    evidence_count: Optional[int] = None
    verified_count: Optional[int] = None
    integrity_status: str = "NOT_STARTED"
    facts_count: Optional[int] = None
    findings_count: Optional[int] = None


class PlannerVerificationStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    LLM_PROVIDER_RECORDED = "LLM_PROVIDER_RECORDED"
    RULE_EXECUTED = "RULE_EXECUTED"
    LLM_PROVIDER_EXECUTED = "LLM_PROVIDER_EXECUTED"
    LLM_FALLBACK_TO_RULE = "LLM_FALLBACK_TO_RULE"
    LLM_PROVIDER_NOT_AVAILABLE = "LLM_PROVIDER_NOT_AVAILABLE"
    HYBRID_NOT_IMPLEMENTED = "HYBRID_NOT_IMPLEMENTED"


class RunHistoryItem(BaseModel):
    run_id: str
    created_at_utc: Optional[str] = None
    started_at_utc: Optional[str] = None
    ended_at_utc: Optional[str] = None
    duration_ms: Optional[int] = None
    scenario: str = "UNKNOWN"
    target_id: str = "UNKNOWN"
    planner_requested: str = "UNKNOWN"
    planner_actual: str = "UNKNOWN"
    planner_verification: str = "UNKNOWN"
    provider: Optional[str] = None
    model: Optional[str] = None
    control_mode: str = "UNKNOWN"
    fallback_reason: Optional[str] = None
    state: str = "INCOMPLETE"
    outcome: str = "INCOMPLETE"
    stop_reason: Optional[str] = None
    iterations: Optional[int] = None
    proposals: Optional[int] = None
    permits: Optional[int] = None
    denials: Optional[int] = None
    network_dispatches: Optional[int] = None
    observations: Optional[int] = None
    evidence_count: int = 0
    verified_evidence_count: Optional[int] = None
    evidence_integrity: str = "NOT_VERIFIED"
    integrity_scope: str = "RECORD_HASHES_AND_REFERENCES"
    findings_count: Optional[int] = None
    pause_count: Optional[int] = None
    operator_approvals: Optional[int] = None
    operator_rejections: Optional[int] = None


class RunHistoryResponse(BaseModel):
    runs: List[RunHistoryItem] = Field(default_factory=list)
    total_count: int = 0


class TimelineEventItem(BaseModel):
    step_index: int
    event_id: str
    run_id: str
    type: str
    timestamp_utc: str
    phase: Optional[str] = None
    iteration: Optional[int] = None
    title: str = ""
    description: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class RunTimelineResponse(BaseModel):
    run_id: str
    events: List[TimelineEventItem] = Field(default_factory=list)


class ComparisonMetric(BaseModel):
    metric: str
    label: str
    run_a_value: Any
    run_b_value: Any
    delta: Optional[Any] = None
    unit: Optional[str] = None


class ActionSequenceItem(BaseModel):
    iteration: int
    action_id: str
    target_id: Optional[str] = None
    safety_decision: str
    dispatched: Optional[bool] = None
    outcome: Optional[str] = None
    resource_ref: Optional[str] = None
    parameter_name: Optional[str] = None
    reason: Optional[str] = None


class RunComparisonResponse(BaseModel):
    run_a: RunHistoryItem
    run_b: RunHistoryItem
    metrics: List[ComparisonMetric] = Field(default_factory=list)
    action_sequence_a: List[ActionSequenceItem] = Field(default_factory=list)
    action_sequence_b: List[ActionSequenceItem] = Field(default_factory=list)
    findings_overlap: Dict[str, Any] = Field(default_factory=dict)
    safety_diff: Dict[str, Any] = Field(default_factory=dict)
    summary_verdict: str = ""
    comparison_kind: str = "DESCRIPTIVE_ONLY"
    comparability_reasons: List[str] = Field(default_factory=list)


class TargetConfigRequest(BaseModel):
    target_id: str = "lab-ecommerce"
    origin: str = "http://127.0.0.1:18088"
