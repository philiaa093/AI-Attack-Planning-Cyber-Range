import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import type { AgentEvent, SystemStatus } from '../api/types';

interface UseSystemStatusOptions {
  pollingIntervalMs?: number;
}

export function useSystemStatus({ pollingIntervalMs = 8000 }: UseSystemStatusOptions = {}) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const mounted = useRef(false);
  const isFetching = useRef(false);
  const refreshPending = useRef(false);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentRunId = useRef<string | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!mounted.current) return;
    if (isFetching.current) {
      refreshPending.current = true;
      return;
    }
    isFetching.current = true;
    try {
      do {
        refreshPending.current = false;
        try {
          const data = await apiClient.getSystemStatus();
          if (!mounted.current) return;
          currentRunId.current = data.run.run_id;
          setStatus(data);
          setError(null);
        } catch (err) {
          if (!mounted.current) return;
          setError(err instanceof Error ? err : new Error(String(err)));
        }
      } while (refreshPending.current && mounted.current);
    } finally {
      isFetching.current = false;
      if (mounted.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void fetchStatus();
    return () => {
      mounted.current = false;
      refreshPending.current = false;
      if (refreshTimer.current !== null) clearTimeout(refreshTimer.current);
      refreshTimer.current = null;
    };
  }, [fetchStatus]);

  useEffect(() => {
    if (pollingIntervalMs <= 0) return;
    const interval = setInterval(() => { void fetchStatus(); }, pollingIntervalMs);
    return () => clearInterval(interval);
  }, [fetchStatus, pollingIntervalMs]);

  const updateFromEvent = useCallback((event: AgentEvent) => {
    if (!mounted.current || !event ||
        typeof event.event_id !== 'string' || !event.event_id.trim() ||
        typeof event.run_id !== 'string' || !event.run_id.trim() ||
        typeof event.type !== 'string' || !event.type.trim() ||
        typeof event.timestamp_utc !== 'string' || !Number.isFinite(Date.parse(event.timestamp_utc))) return;
    if (currentRunId.current && event.run_id !== currentRunId.current && event.type !== 'RUN_STARTED') return;

    // ponytail: REST owns status until the backend offers an atomic event cursor.
    // Coalesce SSE bursts without postponing refresh indefinitely on a busy stream.
    if (refreshTimer.current !== null) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      void fetchStatus();
    }, 250);
  }, [fetchStatus]);

  return { status, isLoading, error, refetch: fetchStatus, updateFromEvent };
}
