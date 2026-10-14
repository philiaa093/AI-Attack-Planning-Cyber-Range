import type {
  ControlResponse,
  DemoReadinessResponse,
  EvidenceDetailResponse,
  EvidenceListResponse,
  FindingsListResponse,
  PreflightResponse,
  RangeStatus,
  RunComparisonResponse,
  RunHistoryItem,
  RunHistoryResponse,
  RunSummaryResponse,
  RunTimelineResponse,
  StartRunRequest,
  SystemStatus,
} from './types';
import type { ModelProfile, ModelProfileInput } from './modelProfiles';

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}: ${res.statusText}`;
    let data: unknown;
    try {
      data = await res.json();
      if (data && typeof data === 'object' && 'detail' in data) {
        errorDetail = String((data as { detail: unknown }).detail);
      } else if (data && typeof data === 'object' && 'message' in data) {
        errorDetail = String((data as { message: unknown }).message);
      }
    } catch {
      // response body was not JSON
    }
    throw new ApiError(res.status, errorDetail, data);
  }
  return res.json() as Promise<T>;
}

export const apiClient = {
  async getModelProfiles(): Promise<{ profiles: ModelProfile[] }> {
    return handleResponse(await fetch(`${API_BASE_URL}/api/model-profiles`, { cache: 'no-store' }));
  },

  async saveModelProfile(input: ModelProfileInput, id?: string): Promise<ModelProfile> {
    return handleResponse(await fetch(`${API_BASE_URL}/api/model-profiles${id ? `/${encodeURIComponent(id)}` : ''}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    }));
  },

  async removeModelProfile(id: string): Promise<{ removed: boolean }> {
    return handleResponse(await fetch(`${API_BASE_URL}/api/model-profiles/${encodeURIComponent(id)}/remove`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
    }));
  },

  async getSystemStatus(): Promise<SystemStatus> {
    const res = await fetch(`${API_BASE_URL}/api/status`);
    return handleResponse<SystemStatus>(res);
  },

  async getRangeStatus(): Promise<RangeStatus> {
    const res = await fetch(`${API_BASE_URL}/api/range/status`);
    return handleResponse<RangeStatus>(res);
  },

  async startRange(): Promise<RangeStatus> {
    const res = await fetch(`${API_BASE_URL}/api/range/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<RangeStatus>(res);
  },

  async stopRange(): Promise<RangeStatus> {
    const res = await fetch(`${API_BASE_URL}/api/range/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<RangeStatus>(res);
  },

  async runPreflight(): Promise<PreflightResponse> {
    const res = await fetch(`${API_BASE_URL}/api/demo/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<PreflightResponse>(res);
  },

  async getDemoReadiness(): Promise<DemoReadinessResponse> {
    const res = await fetch(`${API_BASE_URL}/api/demo/readiness`);
    return handleResponse<DemoReadinessResponse>(res);
  },

  async getCurrentRun(): Promise<Record<string, unknown>> {
    const res = await fetch(`${API_BASE_URL}/api/runs/current`);
    return handleResponse<Record<string, unknown>>(res);
  },

  async startRun(req: StartRunRequest): Promise<ControlResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<ControlResponse>(res);
  },

  async stopRun(runId: string): Promise<ControlResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<ControlResponse>(res);
  },

  async pauseRun(runId: string): Promise<ControlResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/pause`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<ControlResponse>(res);
  },

  async resumeRun(runId: string): Promise<ControlResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<ControlResponse>(res);
  },

  async approveProposal(runId: string, proposalId: string): Promise<ControlResponse> {
    const res = await fetch(
      `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/proposals/${encodeURIComponent(proposalId)}/approve`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }
    );
    return handleResponse<ControlResponse>(res);
  },

  async rejectProposal(runId: string, proposalId: string, reason = 'Operator rejected proposal'): Promise<ControlResponse> {
    const res = await fetch(
      `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/proposals/${encodeURIComponent(proposalId)}/reject`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      }
    );
    return handleResponse<ControlResponse>(res);
  },

  async emergencyStop(): Promise<ControlResponse> {
    const res = await fetch(`${API_BASE_URL}/api/emergency-stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<ControlResponse>(res);
  },

  getEventsUrl(runId?: string): string {
    if (runId) {
      return `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/events`;
    }
    return `${API_BASE_URL}/api/events`;
  },

  async getRunEvidence(runId: string): Promise<EvidenceListResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/evidence`);
    return handleResponse<EvidenceListResponse>(res);
  },

  async getRunEvidenceDetail(runId: string, evidenceId: string): Promise<EvidenceDetailResponse> {
    const res = await fetch(
      `${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/evidence/${encodeURIComponent(evidenceId)}`
    );
    return handleResponse<EvidenceDetailResponse>(res);
  },

  async getRunFindings(runId: string): Promise<FindingsListResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/findings`);
    return handleResponse<FindingsListResponse>(res);
  },

  async getRunSummary(runId: string): Promise<RunSummaryResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/summary`);
    return handleResponse<RunSummaryResponse>(res);
  },

  async getRunHistory(params?: {
    planner?: string;
    control_mode?: string;
    state?: string;
    scenario?: string;
    search?: string;
  }): Promise<RunHistoryResponse> {
    const query = new URLSearchParams();
    if (params?.planner) query.set('planner', params.planner);
    if (params?.control_mode) query.set('control_mode', params.control_mode);
    if (params?.state) query.set('state', params.state);
    if (params?.scenario) query.set('scenario', params.scenario);
    if (params?.search) query.set('search', params.search);

    const url = `${API_BASE_URL}/api/runs/history${query.toString() ? `?${query.toString()}` : ''}`;
    const res = await fetch(url);
    return handleResponse<RunHistoryResponse>(res);
  },

  async getRunDetail(runId: string): Promise<RunHistoryItem> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}`);
    return handleResponse<RunHistoryItem>(res);
  },

  async getRunTimeline(runId: string): Promise<RunTimelineResponse> {
    const res = await fetch(`${API_BASE_URL}/api/runs/${encodeURIComponent(runId)}/timeline`);
    return handleResponse<RunTimelineResponse>(res);
  },

  async compareRuns(runA: string, runB: string): Promise<RunComparisonResponse> {
    const query = new URLSearchParams({ run_a: runA, run_b: runB });
    const res = await fetch(`${API_BASE_URL}/api/runs/compare?${query.toString()}`);
    return handleResponse<RunComparisonResponse>(res);
  },

  getComparisonExportUrl(runA: string, runB: string, format = 'json'): string {
    const query = new URLSearchParams({ run_a: runA, run_b: runB, format });
    return `${API_BASE_URL}/api/runs/compare/export?${query.toString()}`;
  },
};
