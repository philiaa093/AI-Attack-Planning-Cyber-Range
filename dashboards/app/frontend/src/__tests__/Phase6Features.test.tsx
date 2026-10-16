import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { App } from '../App';
import { RunDetailPage } from '../pages/RunDetailPage';
import { RunComparisonPage } from '../pages/RunComparisonPage';
import { RunHistoryPage } from '../pages/RunHistoryPage';
import { EventFeed } from '../components/events/EventFeed';
import { PresentationHero } from '../components/presentation/PresentationHero';
import { PresentationTimeline, PresentationResults } from '../components/presentation/PresentationSummary';
import type { AgentEvent } from '../api/types';
import { apiClient } from '../api/client';
import type {
  RunComparisonResponse,
  RunHistoryItem,
  RunTimelineResponse,
  SystemStatus,
} from '../api/types';

const mockSystemStatus: SystemStatus = {
  api: 'healthy',
  timestamp_utc: '2026-10-11T14:00:00Z',
  range: {
    status: 'HEALTHY',
    target_id: 'lab-ecommerce',
    origin: 'http://127.0.0.1:18088',
    services: {},
    message: 'Range running',
    checked_at_utc: '2026-10-11T14:00:00Z',
  },
  run: {
    run_id: 'RUN-TEST-001',
    state: 'COMPLETED',
    mode: 'RULE',
    planner: 'rule',
    scenario: 'SCN-001',
    target: 'lab-ecommerce',
    started_at_utc: '2026-10-11T14:00:00Z',
    ended_at_utc: '2026-10-11T14:00:10Z',
    stop_reason: 'COMPLETED',
    error: null,
    decisions_count: 5,
    network_dispatches: 4,
    evidence_count: 6,
  },
  agent: {
    state: 'COMPLETED',
    mode: 'RULE',
    planner: 'rule',
    requested_mode: 'RULE',
    actual_mode: 'RULE',
    fallback_reason: null,
    current_action: null,
    current_phase: 'REPORTING',
    budget_remaining: {},
    facts_count: 8,
    decisions_count: 5,
    last_decision: null,
  },
  safety: {
    target_allowlist: ['lab-ecommerce'],
    action_allowlist: ['ACTION-RECON-002'],
    lab_mode: true,
    kill_switch_active: false,
    network_dispatches: 4,
    permits_count: 4,
    denials_count: 1,
  },
  evidence: {
    count: 6,
    verified_count: 6,
    pending_count: 0,
    last_evidence_id: 'EV-123',
    integrity_status: 'VERIFIED',
  },
  pipeline: {
    current_step: 'COMPLETE',
    steps: {},
  },
};

const mockRuns: RunHistoryItem[] = [
  {
    run_id: 'RUN-RULE-001',
    scenario: 'SCN-001',
    target_id: 'lab-ecommerce',
    planner_requested: 'RULE',
    planner_actual: 'RULE',
    planner_verification: 'RULE_EXECUTED',
    control_mode: 'AUTONOMOUS',
    state: 'COMPLETED',
    outcome: 'COMPLETED',
    iterations: 4,
    proposals: 4,
    permits: 4,
    denials: 0,
    network_dispatches: 4,
    observations: 10,
    evidence_count: 8,
    verified_evidence_count: 8,
    findings_count: 2,
    pause_count: 0,
    operator_approvals: 0,
    operator_rejections: 0,
  },
  {
    run_id: 'RUN-LLM-FALLBACK-002',
    scenario: 'SCN-001',
    target_id: 'lab-ecommerce',
    planner_requested: 'LLM',
    planner_actual: 'RULE',
    planner_verification: 'LLM_FALLBACK_TO_RULE',
    fallback_reason: 'Provider key unconfigured',
    control_mode: 'AUTONOMOUS',
    state: 'COMPLETED',
    outcome: 'COMPLETED',
    iterations: 4,
    proposals: 4,
    permits: 4,
    denials: 0,
    network_dispatches: 4,
    observations: 10,
    evidence_count: 8,
    verified_evidence_count: 8,
    findings_count: 2,
    pause_count: 0,
    operator_approvals: 0,
    operator_rejections: 0,
  },
];

const mockTimeline: RunTimelineResponse = {
  run_id: 'RUN-RULE-001',
  events: [
    {
      step_index: 1,
      event_id: 'EVT-1',
      run_id: 'RUN-RULE-001',
      type: 'RUN_STARTED',
      timestamp_utc: '2026-10-11T14:00:00Z',
      phase: 'PRE_ENGAGEMENT',
      iteration: 0,
      title: 'Run Started',
      description: 'Bounded autonomous run initialized',
      payload: {},
    },
    {
      step_index: 2,
      event_id: 'EVT-2',
      run_id: 'RUN-RULE-001',
      type: 'PLANNER_PROPOSED',
      timestamp_utc: '2026-10-11T14:00:01Z',
      phase: 'RECON',
      iteration: 1,
      title: 'Planner Proposed',
      description: 'Proposed ACTION-RECON-002',
      payload: { action_id: 'ACTION-RECON-002' },
    },
    {
      step_index: 3,
      event_id: 'EVT-3',
      run_id: 'RUN-RULE-001',
      type: 'SAFETY_PERMITTED',
      timestamp_utc: '2026-10-11T14:00:02Z',
      phase: 'RECON',
      iteration: 1,
      title: 'Safety Evaluated',
      description: 'Safety Gate permitted execution',
      payload: {},
    },
  ],
};

const mockComparison: RunComparisonResponse = {
  run_a: mockRuns[0],
  run_b: mockRuns[1],
  metrics: [
    {
      metric: 'planner_actual',
      label: 'Planner Actual',
      run_a_value: 'RULE',
      run_b_value: 'RULE',
      delta: null,
    },
    {
      metric: 'network_dispatches',
      label: 'Network Dispatches',
      run_a_value: 4,
      run_b_value: 4,
      delta: 0,
    },
  ],
  action_sequence_a: [
    {
      iteration: 1,
      action_id: 'ACTION-RECON-001',
      safety_decision: 'APPROVED',
      dispatched: true,
    },
  ],
  action_sequence_b: [
    {
      iteration: 1,
      action_id: 'ACTION-RECON-001',
      safety_decision: 'APPROVED',
      dispatched: true,
    },
  ],
  findings_overlap: {
    shared_count: 2,
    unique_a_count: 0,
    unique_b_count: 0,
    shared_findings: ['FIND-SURF-01', 'FIND-SURF-02'],
    unique_a_findings: [],
    unique_b_findings: [],
  },
  safety_diff: {
    run_a_permits: 4,
    run_b_permits: 4,
    run_a_denials: 0,
    run_b_denials: 0,
    permits_delta: 0,
    denials_delta: 0,
    policy_adherence: 'UNRESOLVED: counters do not prove policy adherence.',
  },
  summary_verdict: 'Observed identical dispatch metrics across RULE and LLM-fallback runs.',
};

describe('Phase 6: Research Experiment Dashboard & Run Replay', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('EventSource', class {
      addEventListener() {}
      removeEventListener() {}
      close() {}
    });
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);
    vi.spyOn(apiClient, 'getRunHistory').mockResolvedValue({
      runs: mockRuns,
      total_count: 2,
    });
    vi.spyOn(apiClient, 'getRunDetail').mockResolvedValue(mockRuns[0]);
    vi.spyOn(apiClient, 'getRunTimeline').mockResolvedValue(mockTimeline);
    vi.spyOn(apiClient, 'compareRuns').mockResolvedValue(mockComparison);
  });

  it('renders top navigation tabs and navigates between Overview, Runs, and Compare', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Research Control Center' })).toBeInTheDocument();
    });

    // Check top navigation tabs
    const overviewTab = screen.getByRole('button', { name: /overview/i });
    const runsTab = screen.getByRole('button', { name: /runs/i });
    const compareTab = screen.getByRole('button', { name: /compare/i });

    expect(overviewTab).toBeInTheDocument();
    expect(runsTab).toBeInTheDocument();
    expect(compareTab).toBeInTheDocument();

    // Click Runs tab
    fireEvent.click(runsTab);
    await waitFor(() => {
      expect(screen.getByText('Execution Run History')).toBeInTheDocument();
      expect(screen.getByText('RUN-RULE-001')).toBeInTheDocument();
      expect(screen.getByText('RUN-LLM-FALLBACK-002')).toBeInTheDocument();
    });

    // Check LLM fallback badge
    expect(screen.getByText('LLM → RULE FALLBACK')).toBeInTheDocument();
  });

  it('RunDetailPage displays HISTORICAL REPLAY banner and controls', async () => {
    render(
      <RunDetailPage
        runId="RUN-RULE-001"
        onBack={vi.fn()}
      />
    );

    await waitFor(() => {
      // Replay warning banner MUST be present
      expect(screen.getByText(/HISTORICAL REPLAY — NO LIVE EXECUTION/i)).toBeInTheDocument();
      expect(screen.getByText(/READ-ONLY/i)).toBeInTheDocument();
      // Player controls
      expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
    });
  });

  it('RunComparisonPage renders side-by-side comparative table and academic verdict', async () => {
    render(
      <RunComparisonPage
        initialRunA="RUN-RULE-001"
        initialRunB="RUN-LLM-FALLBACK-002"
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Planner & Run Experiment Comparison')).toBeInTheDocument();
      expect(screen.getByText('Comparative Execution Metrics')).toBeInTheDocument();
      expect(screen.getByText('Action Sequence Trajectory Diff')).toBeInTheDocument();
      expect(screen.getByText(/Observed identical dispatch metrics/i)).toBeInTheDocument();
    });
  });

  it('requests history pages from the server instead of slicing all runs locally', async () => {
    vi.mocked(apiClient.getRunHistory).mockResolvedValue({ runs: mockRuns, total_count: 30 });
    render(<RunHistoryPage onSelectRun={vi.fn()} onCompareRuns={vi.fn()} />);
    await waitFor(() => expect(apiClient.getRunHistory).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 25, offset: 0, include_test_runs: false }),
    ));
    fireEvent.click(await screen.findByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(apiClient.getRunHistory).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 25, offset: 25 }),
    ));
    expect(await screen.findByText(mockRuns[0].run_id)).toBeInTheDocument();
  });

  it('keeps unknown comparison measurements distinct from a measured zero', async () => {
    vi.mocked(apiClient.compareRuns).mockResolvedValue({
      ...mockComparison,
      metrics: [{ metric: 'duration_ms', label: 'Execution Duration', run_a_value: null, run_b_value: 0, delta: null, unit: 'ms' }],
      comparison_kind: 'DESCRIPTIVE_ONLY',
      comparability_reasons: ['Protocol equivalence has not been verified.'],
    });
    render(<RunComparisonPage initialRunA="RUN-RULE-001" initialRunB="RUN-LLM-FALLBACK-002" />);
    await waitFor(() => expect(screen.getByText('0 ms')).toBeInTheDocument());
    expect(screen.getByText(/Descriptive comparison/i)).toBeInTheDocument();
    expect(screen.getByText('Protocol equivalence has not been verified.')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText('null')).not.toBeInTheDocument();
  });

  it('hides test runs by default and restores them through the explicit filter', async () => {
    vi.mocked(apiClient.getRunHistory).mockResolvedValue({ runs: [...mockRuns, { ...mockRuns[0], run_id: 'TEST-HIDDEN-001' }], total_count: 3 });
    render(<RunHistoryPage onSelectRun={vi.fn()} onCompareRuns={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('RUN-RULE-001')).toBeInTheDocument());
    expect(screen.queryByText('TEST-HIDDEN-001')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include test runs' }));
    await waitFor(() => expect(screen.getByText('TEST-HIDDEN-001')).toBeInTheDocument());
  });

  it('keeps telemetry available while showing only milestones by default', () => {
    render(<EventFeed connectionStatus="CONNECTED" onClear={vi.fn()} onReconnect={vi.fn()} events={[
      { event_id: 'EVT-META', run_id: 'RUN-1', type: 'BUDGET_UPDATED', timestamp_utc: '', payload: {} },
      { event_id: 'EVT-PLAN', run_id: 'RUN-1', type: 'PLANNER_PROPOSED', timestamp_utc: '', payload: { action_id: 'ACTION-PLAN-003' } },
    ]} />);
    expect(screen.queryByText('BUDGET_UPDATED')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Detailed Telemetry' }));
    expect(screen.getByText('BUDGET_UPDATED')).toBeInTheDocument();
  });
});

describe('Reviewed decision provenance', () => {
  const event = (type: string, runId = 'RUN-TEST-001'): AgentEvent => ({
    event_id: 'EVT-DECISION', run_id: runId, type, timestamp_utc: '2026-10-13T00:00:00Z',
    payload: { action_id: 'ACTION-PLAN-003', reason: 'RECORDED_REFUSAL' },
  });

  it('shows the recorded latest permission despite earlier denials', () => {
    render(<PresentationHero system={mockSystemStatus} latestEvent={event('SAFETY_PERMITTED')} />);
    expect(screen.getByText('PERMITTED')).toBeInTheDocument();
    expect(screen.queryByText('DENIED')).not.toBeInTheDocument();
    expect(screen.getByText('Recorded run dispatches:')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('never calls a run with prior dispatches guaranteed zero after a refusal', () => {
    render(<PresentationHero system={mockSystemStatus} latestEvent={event('SAFETY_DENIED')} />);
    expect(screen.getByText('DENIED')).toBeInTheDocument();
    expect(screen.getByText('Recorded refusal for this action')).toBeInTheDocument();
    expect(screen.queryByText(/guaranteed|zero dispatch/i)).not.toBeInTheDocument();
  });

  it('keeps another run event and absent decisions unknown', () => {
    const { rerender } = render(<PresentationHero system={mockSystemStatus}
      latestEvent={event('SAFETY_DENIED', 'RUN-OTHER')} />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.queryByText('ACTION-PLAN-003')).not.toBeInTheDocument();
    rerender(<PresentationHero system={null} latestEvent={null} />);
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.queryByText(/Decision #0/)).not.toBeInTheDocument();
  });
});

describe('Presentation overview', () => {
  it('guides an idle session to saved history without launching a run', () => {
    const onViewHistory = vi.fn();
    render(<PresentationHero system={{ ...mockSystemStatus, run: { ...mockSystemStatus.run, run_id: null, state: 'IDLE' } }} latestEvent={null} onViewHistory={onViewHistory} />);
    expect(screen.getByRole('heading', { name: 'No run in progress' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'View run history' }));
    expect(onViewHistory).toHaveBeenCalledOnce();
  });

  it('keeps a terminal lifecycle above a delayed activity event and discloses fallback', () => {
    render(<PresentationHero system={{ ...mockSystemStatus, agent: { ...mockSystemStatus.agent, requested_mode: 'LLM', actual_mode: 'RULE', fallback_reason: 'Provider unavailable' } }}
      latestEvent={{ event_id: 'LATE', run_id: mockSystemStatus.run.run_id!, type: 'PLANNER_PROPOSED', timestamp_utc: '', payload: {} }} />);
    expect(screen.getByRole('heading', { name: 'The run has completed' })).toBeInTheDocument();
    expect(screen.getByText('Provider unavailable')).toBeInTheDocument();
    expect(screen.getByText('LLM')).toBeInTheDocument();
    expect(screen.getByText('RULE')).toBeInTheDocument();
  });

  it('shows only current-run milestones and leaves event payloads expandable', () => {
    render(<PresentationTimeline runId="CURRENT" connectionStatus="CONNECTED" onReconnect={vi.fn()} events={[
      { event_id: 'FOREIGN', run_id: 'OTHER', type: 'SAFETY_DENIED', timestamp_utc: '', payload: {} },
      { event_id: 'CURRENT-PLAN', run_id: 'CURRENT', type: 'PLANNER_PROPOSED', timestamp_utc: '2026-10-13T07:00:00Z', payload: { action_id: 'ACTION-PLAN-003' } },
    ]} />);
    expect(screen.queryByText('Refusal recorded')).not.toBeInTheDocument();
    const summary = screen.getByText('Planner proposed an action');
    const disclosure = summary.closest('details')!;
    expect(disclosure.open).toBe(false);
    fireEvent.click(summary);
    expect(disclosure.open).toBe(true);
    expect(screen.getByText('07:00:00 UTC')).toBeInTheDocument();
    expect(screen.getByText(/ACTION-PLAN-003/)).toBeVisible();
  });

  it('distinguishes idle missing values from recorded zero and disables evidence without a run', () => {
    const system = { ...mockSystemStatus, agent: { ...mockSystemStatus.agent, facts_count: 0 } };
    const { rerender } = render(<PresentationResults system={system} onInspect={vi.fn()} />);
    const results = screen.getByRole('region', { name: 'Recorded results' });
    expect(within(results).getByText('0')).toBeInTheDocument();
    rerender(<PresentationResults system={{ ...system, run: { ...system.run, state: 'IDLE', run_id: null } }} onInspect={vi.fn()} />);
    expect(within(results).queryByText('0')).not.toBeInTheDocument();
    expect(within(results).getByRole('button', { name: 'View evidence' })).toBeDisabled();
  });
});
