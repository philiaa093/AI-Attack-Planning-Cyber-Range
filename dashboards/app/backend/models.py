"""Pydantic models and schemas for Autonomous Cyber Range Control Center."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


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
    scenario: str = "SCN-001"
    target: str = "lab-ecommerce"
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
    max_decisions: int = Field(default=30, ge=1, le=100, strict=True)
    max_requests: int = Field(default=120, ge=1, le=500, strict=True)
    max_pages: int = Field(default=30, ge=1, le=100, strict=True)
    seed_path: str = "/"
    scenario: str = "SCN-001"
    approve_read_only: bool = True
    approve_active_verification: bool = Field(default=False, strict=True)
    preview_one_page: bool = False
    external_scanners: List[Literal["zap-passive", "zap-active", "nuclei"]] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_scanner_scope(self):
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
