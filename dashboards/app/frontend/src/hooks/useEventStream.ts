import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/client';
import type { AgentEvent, SseConnectionStatus } from '../api/types';

export const KNOWN_SSE_EVENTS = [
  'RUN_STARTED',
  'RUN_STOP_REQUESTED',
  'RUN_STOPPING',
  'RUN_STOPPED',
  'RUN_COMPLETED',
  'RUN_FAILED',
  'EMERGENCY_STOP_ACTIVATED',
  'KILL_SWITCH_ACTIVATED',
  'AGENT_ITERATION_STARTED',
  'AGENT_REPLANNING',
  'STOP_CONDITION_REACHED',
  'PLANNER_STARTED',
  'PLANNER_PROPOSED',
  'PLANNER_FALLBACK',
  'SAFETY_EVALUATION_STARTED',
  'SAFETY_PERMITTED',
  'SAFETY_DENIED',
  'ACTION_DISPATCH_STARTED',
  'ACTION_DISPATCHED',
  'ACTION_COMPLETED',
  'ACTION_FAILED',
  'OBSERVATION_RECEIVED',
  'STATE_UPDATED',
  'BUDGET_UPDATED',
  'EVIDENCE_RECORDED',
  'EVIDENCE_VERIFIED',
  'FINDING_CREATED',
  'message',
] as const;

interface UseEventStreamOptions {
  runId?: string | null;
  maxEvents?: number;
  onEvent?: (event: AgentEvent) => void;
  enabled?: boolean;
}

export function useEventStream({
  runId,
  maxEvents = 400,
  onEvent,
  enabled = true,
}: UseEventStreamOptions = {}) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [latestEvent, setLatestEvent] = useState<AgentEvent | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<SseConnectionStatus>('DISCONNECTED');
  const [errorCount, setErrorCount] = useState<number>(0);

  const eventSourceRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const handleIncomingMessage = useCallback(
    (e: MessageEvent) => {
      try {
        const raw = e.data;
        if (!raw) return;
        const parsed = (typeof raw === 'string' ? JSON.parse(raw) : raw) as AgentEvent;
        if (!parsed.event_id || !parsed.type) return;

        setLatestEvent(parsed);
        setEvents((prev) => {
          // Avoid duplicate event_id
          if (prev.some((item) => item.event_id === parsed.event_id)) {
            return prev;
          }
          const next = [...prev, parsed];
          if (next.length > maxEvents) {
            return next.slice(next.length - maxEvents);
          }
          return next;
        });

        if (onEventRef.current) {
          onEventRef.current(parsed);
        }
      } catch (err) {
        console.warn('Failed to parse incoming SSE event payload:', err, e.data);
      }
    },
    [maxEvents]
  );

  const connect = useCallback(() => {
    if (!enabled) return;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const url = apiClient.getEventsUrl(runId ?? undefined);
    setConnectionStatus('CONNECTING');

    try {
      const es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setConnectionStatus('CONNECTED');
        setErrorCount(0);
      };

      es.onerror = () => {
        // EventSource will automatically attempt to reconnect
        if (es.readyState === EventSource.CONNECTING) {
          setConnectionStatus('RECONNECTING');
        } else if (es.readyState === EventSource.CLOSED) {
          setConnectionStatus('DISCONNECTED');
        } else {
          setConnectionStatus('ERROR');
        }
        setErrorCount((c) => c + 1);
      };

      // Crucial: Register named event handlers since backend emits "event: <TYPE>"
      for (const eventName of KNOWN_SSE_EVENTS) {
        es.addEventListener(eventName, handleIncomingMessage as EventListener);
      }
      es.onmessage = handleIncomingMessage;
    } catch (err) {
      console.error('Failed to construct EventSource:', err);
      setConnectionStatus('ERROR');
    }
  }, [enabled, runId, handleIncomingMessage]);

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setConnectionStatus('DISCONNECTED');
    };
  }, [connect]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLatestEvent(null);
  }, []);

  return {
    events,
    latestEvent,
    connectionStatus,
    errorCount,
    reconnect: connect,
    clearEvents,
  };
}
