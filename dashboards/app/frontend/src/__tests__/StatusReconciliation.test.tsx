import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { apiClient } from '../api/client';
import { useSystemStatus } from '../hooks/useSystemStatus';
import type { AgentEvent, SystemStatus } from '../api/types';

const snapshot = {
  timestamp_utc: '2026-10-13T10:00:00Z',
  run: { run_id: 'RUN-UI', state: 'RUNNING', decisions_count: 1, network_dispatches: 2 },
  evidence: { count: 3 }, agent: {},
  safety: { permits_count: 2, denials_count: 1, network_dispatches: 2 },
  range: {}, pipeline: { steps: {} },
} as SystemStatus;

// Counted after the range check began, before REST read the snapshot.
const event = {
  event_id: 'IN-SNAPSHOT', run_id: 'RUN-UI', type: 'EVIDENCE_RECORDED',
  timestamp_utc: '2026-10-13T10:00:01Z', payload: {},
} as AgentEvent;

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function mount() {
  const hook = renderHook(() => useSystemStatus({ pollingIntervalMs: 0 }));
  await act(async () => {});
  return hook;
}

async function flushRefresh() {
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
}

it('does not recount backlog newer than the range-check timestamp', async () => {
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(snapshot);
  const { result } = await mount();
  act(() => {
    for (const type of ['EVIDENCE_RECORDED', 'SAFETY_PERMITTED', 'SAFETY_DENIED', 'ACTION_DISPATCHED', 'ACTION_COMPLETED']) {
      result.current.updateFromEvent({ ...event, event_id: type, type } as AgentEvent);
    }
  });
  expect(result.current.status).toEqual(snapshot);
  await flushRefresh();
  expect(result.current.status).toEqual(snapshot);
  expect(getStatus).toHaveBeenCalledTimes(2);
});

it('coalesces replay bursts and reads new counts from REST', async () => {
  const next = { ...snapshot, evidence: { ...snapshot.evidence, count: 4 } };
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus')
    .mockResolvedValueOnce(snapshot).mockResolvedValue(next);
  const { result } = await mount();
  act(() => {
    for (let i = 0; i < 100; i++) result.current.updateFromEvent(event);
  });
  expect(result.current.status?.evidence.count).toBe(3);
  await flushRefresh();
  expect(result.current.status?.evidence.count).toBe(4);
  expect(getStatus).toHaveBeenCalledTimes(2);
});

it('reads again when events arrive during an in-flight snapshot request', async () => {
  let resolveSnapshot!: (value: SystemStatus) => void;
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus')
    .mockReturnValueOnce(new Promise(resolve => { resolveSnapshot = resolve; }))
    .mockResolvedValue({ ...snapshot, evidence: { ...snapshot.evidence, count: 4 } });
  const { result } = await mount();
  act(() => result.current.updateFromEvent(event));
  await flushRefresh();
  expect(getStatus).toHaveBeenCalledTimes(1);
  await act(async () => resolveSnapshot(snapshot));
  expect(getStatus).toHaveBeenCalledTimes(2);
  expect(result.current.status?.evidence.count).toBe(4);
});

it('ignores malformed events and other-run counters, but refreshes for a new run', async () => {
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(snapshot);
  const { result } = await mount();
  act(() => {
    result.current.updateFromEvent({ ...event, run_id: 'RUN-OTHER' });
    result.current.updateFromEvent({ ...event, timestamp_utc: 'invalid' });
    result.current.updateFromEvent({ ...event, event_id: '' });
  });
  await flushRefresh();
  expect(getStatus).toHaveBeenCalledTimes(1);
  const next = { ...snapshot, run: { ...snapshot.run, run_id: 'RUN-NEXT' } };
  getStatus.mockResolvedValue(next);
  act(() => result.current.updateFromEvent({ ...event, run_id: 'RUN-NEXT', type: 'RUN_STARTED' }));
  await flushRefresh();
  expect(result.current.status?.run.run_id).toBe('RUN-NEXT');
});

it('keeps the last snapshot on failure and permits retry from a replayed event', async () => {
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValueOnce(snapshot)
    .mockRejectedValueOnce(new Error('offline')).mockResolvedValue(snapshot);
  const { result } = await mount();
  act(() => result.current.updateFromEvent(event));
  await flushRefresh();
  expect(result.current.status).toEqual(snapshot);
  expect(result.current.error?.message).toBe('offline');
  act(() => result.current.updateFromEvent(event));
  await flushRefresh();
  expect(getStatus).toHaveBeenCalledTimes(3);
  expect(result.current.error).toBeNull();
});

it('cancels queued refreshes on unmount', async () => {
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus').mockResolvedValue(snapshot);
  const { result, unmount } = await mount();
  act(() => result.current.updateFromEvent(event));
  unmount();
  await flushRefresh();
  expect(getStatus).toHaveBeenCalledTimes(1);
});

it('does not follow up an in-flight request after unmount', async () => {
  let resolveSnapshot!: (value: SystemStatus) => void;
  const getStatus = vi.spyOn(apiClient, 'getSystemStatus')
    .mockReturnValue(new Promise(resolve => { resolveSnapshot = resolve; }));
  const { result, unmount } = await mount();
  act(() => result.current.updateFromEvent(event));
  await flushRefresh();
  unmount();
  await act(async () => resolveSnapshot(snapshot));
  expect(getStatus).toHaveBeenCalledTimes(1);
});
