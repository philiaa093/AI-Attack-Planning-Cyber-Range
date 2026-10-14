import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ControlCenter } from '../pages/ControlCenter';
import { apiClient } from '../api/client';
import type { SystemStatus, AgentEvent } from '../api/types';

// Mock mockSystemStatus
const mockSystemStatus: SystemStatus = {
  api: 'healthy',
  timestamp_utc: '2026-10-11T14:00:00Z',
  range: {
    status: 'UNAVAILABLE',
    target_id: 'lab-ecommerce',
    origin: 'http://127.0.0.1:18088',
    services: {},
    message: 'Docker runtime is unavailable. Start Docker Desktop before launching the cyber range.',
    checked_at_utc: '2026-10-11T14:00:00Z',
  },
  run: {
    run_id: 'RUN-TEST-1234',
    state: 'IDLE',
    mode: 'RULE',
    planner: 'rule',
    scenario: 'SCN-001',
    target: 'lab-ecommerce',
    started_at_utc: null,
    ended_at_utc: null,
    stop_reason: null,
    error: null,
    decisions_count: 0,
    network_dispatches: 0,
    evidence_count: 0,
  },
  agent: {
    state: 'IDLE',
    mode: 'RULE',
    planner: 'rule',
    requested_mode: 'RULE',
    actual_mode: 'NOT_RUN',
    fallback_reason: null,
    current_action: null,
    current_phase: 'RECON',
    budget_remaining: {},
    facts_count: 5,
    decisions_count: 0,
    last_decision: null,
  },
  safety: {
    target_allowlist: ['lab-ecommerce'],
    action_allowlist: ['DISCOVER_ROOT', 'DISCOVER_PAGE'],
    lab_mode: true,
    kill_switch_active: false,
    network_dispatches: 0,
    permits_count: 0,
    denials_count: 0,
  },
  evidence: {
    count: 2,
    verified_count: 2,
    pending_count: 0,
    last_evidence_id: 'EVD-TEST-001',
    integrity_status: 'VERIFIED',
  },
  pipeline: {
    current_step: null,
    steps: {
      PREFLIGHT: 'NOT_RUN',
      RANGE: 'NOT_RUN',
      OBSERVE: 'NOT_RUN',
      STATE: 'NOT_RUN',
      PLAN: 'NOT_RUN',
      SAFETY: 'NOT_RUN',
      EXECUTE: 'NOT_RUN',
      EVIDENCE: 'NOT_RUN',
      VERIFY: 'NOT_RUN',
      COMPLETE: 'NOT_RUN',
    },
  },
};

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;

  constructor(public url: string) {
    MockEventSource.instances.push(this);
    setTimeout(() => {
      if (this.onopen) this.onopen();
    }, 10);
  }

  addEventListener(event: string, cb: (e: MessageEvent) => void) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(cb);
  }

  removeEventListener(event: string, cb: (e: MessageEvent) => void) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((f) => f !== cb);
    }
  }

  emit(eventType: string, data: AgentEvent) {
    const event = { data: JSON.stringify(data) } as MessageEvent;
    if (this.listeners[eventType]) {
      this.listeners[eventType].forEach((fn) => fn(event));
    }
    if (this.onmessage) {
      this.onmessage(event);
    }
  }

  close() {
    this.readyState = 2;
  }
}

describe('Autonomous Cyber Range Control Center Frontend MVP', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', MockEventSource);
    MockEventSource.instances = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders backend offline state when API connection fails', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockRejectedValue(new Error('Connection refused'));

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByText(/Control API Offline/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Retry Connection/i)).toBeInTheDocument();
  });

  it('renders system status, cards, and Docker unavailable blocker clearly', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Research Control Center' })).toBeInTheDocument();
    });

    // Check Run ID
    expect(screen.getByText('RUN-TEST-1234')).toBeInTheDocument();

    const technical = screen.getByText('Technical details').closest('details')!;
    expect(technical.open).toBe(false);
    expect(screen.getByRole('button', { name: /Emergency Stop and Activate Kill Switch/i })).toBeVisible();
    fireEvent.click(screen.getByText('Technical details'));
    expect(technical.open).toBe(true);

    // Check Cyber Range Card & Docker Unavailable alert
    expect(screen.getByText(/Docker Unavailable/i)).toBeInTheDocument();

    // Check Evidence card verified count
    expect(screen.getByText(/SHA-256 VALID/i)).toBeInTheDocument();

    // Check Research Boundary
    expect(screen.getByText(/RESEARCH & SAFETY BOUNDARY INVARIANTS/i)).toBeInTheDocument();
    const isolatedBadges = screen.getAllByText(/ISOLATED LAB/i);
    expect(isolatedBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders pipeline states accurately', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByText('PREFLIGHT')).toBeInTheDocument();
      const safetyNodes = screen.getAllByText('SAFETY');
      expect(safetyNodes.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('EXECUTE')).toBeInTheDocument();
      expect(screen.getByText('COMPLETE')).toBeInTheDocument();
    });
  });

  it('keeps pending approval visible while technical details are collapsed', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue({
      ...mockSystemStatus,
      run: { ...mockSystemStatus.run, state: 'WAITING_FOR_APPROVAL' },
      agent: { ...mockSystemStatus.agent, pending_proposal: { plan_id: 'PLAN-UI-REVIEW', action_id: 'ACTION-PLAN-003', target_id: 'lab-ecommerce' } },
    });
    render(<ControlCenter />);
    await waitFor(() => expect(screen.getByRole('region', { name: 'Proposal Approval Review' })).toBeVisible());
    expect(screen.getByText('Technical details').closest('details')!.open).toBe(false);
    expect(screen.getByRole('heading', { name: 'A proposal awaits your review' })).toBeVisible();
  });

  it('handles named SSE event and appends live event feed', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByText('RUN-TEST-1234')).toBeInTheDocument();
    });

    const esInstance = MockEventSource.instances[0];
    expect(esInstance).toBeDefined();

    // Emit custom named SSE event wrapped in act
    const sampleEvent: AgentEvent = {
      event_id: 'EVT-001',
      run_id: 'RUN-TEST-1234',
      type: 'PLANNER_PROPOSED',
      timestamp_utc: '2026-10-11T14:15:00Z',
      phase: 'RECON',
      iteration: 1,
      payload: {
        action_id: 'DISCOVER_PAGE',
        intent: 'DISCOVER_ROUTES',
      },
    };

    act(() => {
      esInstance.emit('PLANNER_PROPOSED', sampleEvent);
    });

    await waitFor(() => {
      expect(screen.getAllByText('PLANNER_PROPOSED').length).toBeGreaterThan(0);
    });
  });

  it('SAFETY_DENIED event renders denied state with zero network dispatch in executor', async () => {
    const getStatus = vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByText('RUN-TEST-1234')).toBeInTheDocument();
    });

    const esInstance = MockEventSource.instances[0];
    expect(esInstance).toBeDefined();

    // SSE invalidates status; the updated REST snapshot confirms the refusal.
    getStatus.mockResolvedValue({
      ...mockSystemStatus,
      safety: { ...mockSystemStatus.safety, denials_count: 1 },
      pipeline: {
        ...mockSystemStatus.pipeline,
        steps: { ...mockSystemStatus.pipeline.steps, SAFETY: 'DENIED', EXECUTE: 'BLOCKED' },
      },
    });
    const denyEvent: AgentEvent = {
      event_id: 'EVT-DENY-01',
      run_id: 'RUN-TEST-1234',
      type: 'SAFETY_DENIED',
      timestamp_utc: '2026-10-11T14:15:05Z',
      phase: 'RECON',
      iteration: 1,
      payload: {
        target_id: 'lab-not-approved',
        reason: 'TARGET_NOT_ALLOWLISTED',
        dispatched: false,
      },
    };

    act(() => {
      esInstance.emit('SAFETY_DENIED', denyEvent);
    });

    await waitFor(() => {
      expect(screen.getByText(/Zero network dispatch/i)).toBeInTheDocument();
    });
    expect(getStatus).toHaveBeenCalledTimes(2);
  });

  it('Emergency Stop button opens confirmation and calls API endpoint', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);
    const emergencySpy = vi.spyOn(apiClient, 'emergencyStop').mockResolvedValue({
      success: true,
      message: 'Emergency kill switch activated. Dispatches halted.',
      run_id: 'RUN-TEST-1234',
      timestamp_utc: '2026-10-11T14:16:00Z',
    });

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Emergency Stop and Activate Kill Switch/i })).toBeInTheDocument();
    });

    // Click Emergency Stop to show modal
    const emergencyBtn = screen.getByRole('button', { name: /Emergency Stop and Activate Kill Switch/i });
    fireEvent.click(emergencyBtn);

    // Confirm button in modal
    const confirmBtn = screen.getByRole('button', { name: /Confirm Emergency Stop/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(emergencySpy).toHaveBeenCalledTimes(1);
    });
  });

  it('preflight modal displays checks and blockers clearly', async () => {
    vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(mockSystemStatus);
    vi.spyOn(apiClient, 'runPreflight').mockResolvedValue({
      passed: false,
      outcome: 'PREFLIGHT_BLOCKED',
      checks: [
        { name: 'DOCKER_AVAILABLE', passed: false, detail: 'docker binary not responding' },
        { name: 'CANONICAL_POLICY', passed: true, detail: 'Allowlist verified' },
      ],
      blockers: ['DOCKER_UNAVAILABLE'],
      timestamp_utc: '2026-10-11T14:10:00Z',
    });

    render(<ControlCenter />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Run Preflight Validation/i })).toBeInTheDocument();
    });

    const preflightBtn = screen.getByRole('button', { name: /Run Preflight Validation/i });
    fireEvent.click(preflightBtn);

    await waitFor(() => {
      expect(screen.getByText(/Cyber Range Preflight Validation/i)).toBeInTheDocument();
      expect(screen.getByText('PREFLIGHT_BLOCKED')).toBeInTheDocument();
      expect(screen.getByText('DOCKER_UNAVAILABLE')).toBeInTheDocument();
      expect(screen.getByText('docker binary not responding')).toBeInTheDocument();
    });
  });
});
