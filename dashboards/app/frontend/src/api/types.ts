export type RangeState =
  | 'STOPPED'
  | 'STARTING'
  | 'HEALTHY'
  | 'UNHEALTHY'
  | 'UNAVAILABLE'
  | 'UNKNOWN';

export type AgentState =
  | 'IDLE'
  | 'STARTING'
  | 'PREFLIGHT'
  | 'RUNNING'
  | 'WAITING_FOR_APPROVAL'
  | 'PAUSING'
  | 'PAUSED'
  | 'RESUMING'
  | 'STOPPING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BLOCKED';

export type ControlMode = 'AUTONOMOUS' | 'ASSISTED' | 'MANUAL';

export interface PendingProposal {
  plan_id: string;
  action_id: string;
  action_name?: string;
  action_class?: string;
  target_id: string;
  reason_code?: string;
  confidence?: number;
  resource_ref?: string;
  parameter_name?: string;
  safety_decision?: string;
  requested_mode?: string;
  actual_mode?: string;
  decision_origin?: string;
  provider?: string;
  model?: string;
  control_mode?: string;
}

export type StepState =
  | 'NOT_RUN'
  | 'PENDING'
  | 'RUNNING'
  | 'PASS'
  | 'DENIED'
  | 'BLOCKED'
  | 'FAILED'
  | 'COMPLETED';

export interface RangeStatus {
  status: RangeState;
  target_id: string;
  origin: string;
  services: Record<string, unknown>;
  message: string;
  checked_at_utc: string;
}

export interface AgentStatus {
  state: AgentState;
  mode: string;
  planner: string;
  control_mode?: string;
  requested_mode: string;
  actual_mode: string;
  provider?: string | null;
  model?: string | null;
  fallback_reason: string | null;
  current_action: string | null;
  current_phase: string | null;
  budget_remaining: Record<string, unknown>;
  facts_count: number;
  decisions_count: number;
  pause_count?: number;
  operator_approvals?: number;
  operator_rejections?: number;
  pending_proposal?: PendingProposal | null;
  last_decision: Record<string, unknown> | null;
}

export interface SafetyStatus {
  target_allowlist: string[];
  action_allowlist: string[];
  lab_mode: boolean;
  kill_switch_active: boolean;
  network_dispatches: number;
  permits_count: number;
  denials_count: number;
}

export interface EvidenceStatus {
  count: number;
  verified_count: number;
  pending_count: number;
  last_evidence_id: string | null;
  integrity_status: string;
}

export type PipelineStepKey =
  | 'PREFLIGHT'
  | 'RANGE'
  | 'OBSERVE'
  | 'STATE'
  | 'PLAN'
  | 'SAFETY'
  | 'EXECUTE'
  | 'EVIDENCE'
  | 'VERIFY'
  | 'COMPLETE';

export interface PipelineStatus {
  current_step: string | null;
  steps: Record<PipelineStepKey | string, StepState>;
}

export interface RunStatus {
  run_id: string | null;
  state: AgentState;
  mode: string;
  planner: string;
  control_mode?: string;
  scenario: string;
  target: string;
  started_at_utc: string | null;
  ended_at_utc: string | null;
  stop_reason: string | null;
  error: string | null;
  decisions_count: number;
  network_dispatches: number;
  evidence_count: number;
  pending_proposal?: PendingProposal | null;
}

export interface SystemStatus {
  api: string;
  timestamp_utc: string;
  range: RangeStatus;
  run: RunStatus;
  agent: AgentStatus;
  safety: SafetyStatus;
  evidence: EvidenceStatus;
  pipeline: PipelineStatus;
}

export interface ControlResponse {
  success: boolean;
  message: string;
  run_id?: string | null;
  timestamp_utc: string;
  data?: Record<string, unknown> | null;
}

export interface PreflightCheckItem {
  name: string;
  passed: boolean;
  detail: string;
}

export interface PreflightResponse {
  passed: boolean;
  outcome: string;
  checks: PreflightCheckItem[];
  blockers: string[];
  timestamp_utc: string;
}

export interface ReadinessCheckItem {
  name: string;
  category: 'REQUIRED' | 'OPTIONAL';
  passed: boolean;
  status: 'READY' | 'DEGRADED' | 'BLOCKED' | 'NOT_CONFIGURED' | 'CONFIGURED';
  detail: string;
  diagnostic?: string | null;
}

export interface DemoReadinessResponse {
  overall_status: 'READY' | 'DEGRADED' | 'BLOCKED';
  summary: string;
  timestamp_utc: string;
  checks: ReadinessCheckItem[];
  blockers: string[];
  warnings: string[];
  details: {
    llm_status: string;
    llm_provenance_disclosure: string;
    llm_fallback_ready: boolean;
    rule_baseline_ready: boolean;
    offline_replay_available: boolean;
    safe_targets: string[];
    target_count?: number;
    action_count?: number;
    ports?: {
      backend: number;
      frontend: number;
      gateway: number;
    };
  };
}

export interface StartRunRequest {
  mode: 'presentation' | 'deny-demo' | 'autonomous' | 'safe' | string;
  planner: 'rule' | 'llm-unavailable' | 'llm' | 'hybrid' | string;
  control_mode?: ControlMode | string;
  allow_fallback?: boolean;
  target?: string;
  max_decisions?: number;
  seed_path?: string;
  scenario?: string;
  approve_read_only?: boolean;
  preview_one_page?: boolean;
}

export interface AgentEvent {
  event_id: string;
  run_id: string;
  type: string;
  timestamp_utc: string;
  phase?: string | null;
  iteration?: number | null;
  payload: Record<string, unknown>;
}

export type SseConnectionStatus =
  | 'CONNECTING'
  | 'CONNECTED'
  | 'DISCONNECTED'
  | 'RECONNECTING'
  | 'ERROR';

export interface EvidenceItem {
  evidence_id: string;
  run_id: string;
  artifact_type: string;
  path: string;
  sha256: string;
  size_bytes: number;
  verified: boolean;
  created_at_utc: string;
  observed_state: string;
  expected_state: string;
}

export interface EvidenceListResponse {
  run_id: string;
  evidence_count: number;
  verified_count: number;
  integrity_status: string;
  items: EvidenceItem[];
}

export interface EvidenceDetailResponse {
  evidence_id: string;
  run_id: string;
  artifact_type: string;
  path: string;
  sha256: string;
  verified: boolean;
  created_at_utc: string;
  size_bytes: number;
  record: Record<string, unknown>;
  content: unknown;
}

export interface FindingItem {
  finding_id: string;
  run_id: string;
  category: string;
  severity: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  title: string;
  detail: string;
  evidence_refs: string[];
  confidence: number;
  timestamp_utc: string;
}

export interface FindingsListResponse {
  run_id: string;
  findings_count: number;
  items: FindingItem[];
}

export interface RunSummaryResponse {
  run_id: string;
  status: string;
  mode: string;
  planner: string;
  target: string;
  scenario: string;
  started_at_utc: string | null;
  ended_at_utc: string | null;
  stop_reason: string | null;
  decisions_count: number | null;
  approved_actions: number | null;
  denied_actions: number | null;
  network_dispatches: number | null;
  evidence_count: number | null;
  verified_count: number | null;
  integrity_status: string;
  facts_count: number | null;
  findings_count: number | null;
}

export type PlannerVerificationStatus =
  | 'UNKNOWN'
  | 'LLM_PROVIDER_RECORDED'
  | 'RULE_EXECUTED'
  | 'LLM_PROVIDER_EXECUTED'
  | 'LLM_FALLBACK_TO_RULE'
  | 'LLM_PROVIDER_NOT_AVAILABLE'
  | 'HYBRID_NOT_IMPLEMENTED';

export interface RunHistoryItem {
  run_id: string;
  created_at_utc?: string | null;
  started_at_utc?: string | null;
  ended_at_utc?: string | null;
  duration_ms?: number | null;
  scenario: string;
  target_id: string;
  planner_requested: string;
  planner_actual: string;
  planner_verification: PlannerVerificationStatus | string;
  provider?: string | null;
  model?: string | null;
  control_mode: string;
  fallback_reason?: string | null;
  state: string;
  outcome: string;
  stop_reason?: string | null;
  iterations: number | null;
  proposals: number | null;
  permits: number | null;
  denials: number | null;
  network_dispatches: number | null;
  observations: number | null;
  evidence_count: number;
  verified_evidence_count: number | null;
  evidence_integrity?: string;
  integrity_scope?: string;
  findings_count: number | null;
  pause_count: number | null;
  operator_approvals: number | null;
  operator_rejections: number | null;
}

export interface RunHistoryResponse {
  runs: RunHistoryItem[];
  total_count: number;
}

export interface TimelineEventItem {
  step_index: number;
  event_id: string;
  run_id: string;
  type: string;
  timestamp_utc: string;
  phase?: string | null;
  iteration?: number | null;
  title: string;
  description: string;
  payload: Record<string, unknown>;
}

export interface RunTimelineResponse {
  run_id: string;
  events: TimelineEventItem[];
}

export interface ComparisonMetric {
  metric: string;
  label: string;
  run_a_value: unknown;
  run_b_value: unknown;
  delta?: unknown | null;
  unit?: string | null;
}

export interface ActionSequenceItem {
  iteration: number;
  action_id: string;
  target_id?: string | null;
  safety_decision: string;
  dispatched: boolean | null;
  outcome?: string | null;
  resource_ref?: string | null;
  parameter_name?: string | null;
  reason?: string | null;
}

export interface RunComparisonResponse {
  run_a: RunHistoryItem;
  run_b: RunHistoryItem;
  metrics: ComparisonMetric[];
  action_sequence_a: ActionSequenceItem[];
  action_sequence_b: ActionSequenceItem[];
  findings_overlap: {
    shared_count: number;
    unique_a_count: number;
    unique_b_count: number;
    shared_findings: string[];
    unique_a_findings: string[];
    unique_b_findings: string[];
  };
  safety_diff: {
    run_a_permits: number | null;
    run_b_permits: number | null;
    run_a_denials: number | null;
    run_b_denials: number | null;
    permits_delta: number | null;
    denials_delta: number | null;
    policy_adherence: string;
  };
  summary_verdict: string;
  comparison_kind?: string;
  comparability_reasons?: string[];
}
