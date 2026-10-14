"""Thread-safe event sink supporting synchronous publishing and asynchronous SSE streaming."""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import threading
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple
import uuid

from dashboards.app.backend.models import AgentEvent


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventSink:
    """Thread-safe, non-blocking event bus connecting runtime agents to SSE consumers."""

    def __init__(self, max_history: int = 2000) -> None:
        self._lock = threading.Lock()
        self._history: deque[Dict[str, Any]] = deque(maxlen=max_history)
        self._subscribers: Set[Tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()

    def publish(self, event: AgentEvent | Dict[str, Any]) -> Dict[str, Any]:
        """Publish an event thread-safely from any worker thread."""
        if isinstance(event, AgentEvent):
            event_dict = event.model_dump()
        elif isinstance(event, dict):
            event_dict = dict(event)
        else:
            raise ValueError("Event must be an AgentEvent or a dictionary")

        if not event_dict.get("event_id"):
            event_dict["event_id"] = f"EVT-{uuid.uuid4().hex[:12]}"
        if not event_dict.get("timestamp_utc"):
            event_dict["timestamp_utc"] = _utc_now_iso()

        with self._lock:
            self._history.append(event_dict)
            subscribers_snapshot = list(self._subscribers)

        for loop, q in subscribers_snapshot:
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self._safe_queue_put, q, event_dict)
                except RuntimeError:
                    # Loop might have shut down concurrently
                    pass

        return event_dict

    @staticmethod
    def _safe_queue_put(q: asyncio.Queue, item: Dict[str, Any]) -> None:
        try:
            if q.full():
                # Discard oldest to keep queue bounded and prevent backpressure deadlocks
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(item)
        except Exception:
            pass

    async def subscribe(self, run_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """Async generator yielding events for SSE streaming."""
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        sub_tuple = (loop, q)

        with self._lock:
            self._subscribers.add(sub_tuple)

        try:
            while True:
                event = await q.get()
                if run_id is None or event.get("run_id") == run_id:
                    yield event
        finally:
            with self._lock:
                self._subscribers.discard(sub_tuple)

    def get_history(self, run_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Return a snapshot list of recent events under lock."""
        with self._lock:
            if run_id is None:
                items = list(self._history)[-limit:]
            else:
                items = [e for e in self._history if e.get("run_id") == run_id][-limit:]
            return [dict(e) for e in items]

    def clear(self) -> None:
        """Clear event history (mainly for test cleanup)."""
        with self._lock:
            self._history.clear()
