# Dashboard Control Plane Backend

## 1. Scope & Responsibility

The backend located in `dashboards/app/backend/` serves as the **Control Plane Adapter** bridging the Operator Dashboard to the Cyber Range runtime, Autonomous Agent loop, Centralized Safety Gate, and Evidence Verification engine.

### Core Architectural Principles:
- **No Arbitrary Shell**: Zero arbitrary command execution endpoints. All agent actions are strictly typed actions from `ACTION_CATALOG` (13 canonical actions). Operator controls are strictly typed operations (`START_RANGE`, `STOP_RANGE`, `PREFLIGHT`, `START_RUN`, `STOP_RUN`, `EMERGENCY_STOP`).
- **No Fabricated State**: All dashboard metrics (request counts, container status, evidence IDs, safety gate decisions, findings, remaining budget) originate directly from live runtime components (`service_snapshot()`, `CentralizedSafetyGate`, `DurableEvidenceRecorder`, `StateManager`, `AutonomousRunner`).
- **Fail-Closed Safety**: When Docker is unavailable, the backend reports `status: UNAVAILABLE` with diagnostic details instead of crashing or fabricating a false `HEALTHY` state.
- **Fail-Safe Telemetry**: Runtime telemetry hooks never hold execution or safety authority. Exceptions within telemetry callbacks are safely caught and logged; they cannot bypass the Safety Gate or cause arbitrary network dispatches.
- **Thread Safety**: All state reads during active agent execution use mutex locks (`threading.Lock`) and return deep copies.

---

## 2. Core Modules

### 2.1 `models.py`
Defines typed Pydantic models for REST APIs, state snapshots, and SSE streaming:
- `RangeStatus`: Docker service state (`STOPPED`, `STARTING`, `HEALTHY`, `UNHEALTHY`, `UNAVAILABLE`), container IDs, loopback Gateway status (`127.0.0.1:18088/health`), and port bindings.
- `AgentStatus`: Agent execution state (`IDLE`, `STARTING`, `RUNNING`, `PAUSED`, `STOPPING`, `COMPLETED`, `FAILED`, `BLOCKED`), active planner mode (`RULE`, `LLM`, `MOCK`), current action proposal, remaining request budget, observed facts, and findings count.
- `SafetyStatus`: Target and action allowlists, lab mode verification, kill switch status, dispatch counts, permits vs denials.
- `EvidenceStatus`: Artifact count, verification status, latest evidence ID, and integrity hashes.
- `PipelineStatus`: Visual pipeline stage tracking (`PREFLIGHT`, `RANGE`, `OBSERVE`, `STATE`, `PLAN`, `SAFETY`, `EXECUTE`, `EVIDENCE`, `VERIFY`, `COMPLETE`, `BLOCKED`).
- `AgentEvent`: Structured runtime event envelope with sequential integer `id`, ISO 8601 UTC `timestamp`, `event_type`, `run_id`, `iteration`, and structured `data`.
- `SystemStatus`: Unified snapshot aggregating all cards.
- `PreflightResponse`: Preflight validation covering Docker daemon, image availability, policy contracts, storage write access, and service health.

### 2.2 `event_sink.py`
Thread-safe event bus and SSE broadcasting engine:
- `publish(event)`: Non-blocking append to a bounded ring buffer (`deque(maxlen=1000)`) and broadcast to all active subscriber `asyncio.Queue` instances.
- `subscribe(run_id=None)`: Asynchronous generator feeding Server-Sent Events (SSE) to connected clients. Manages subscriber lifecycle with cleanup on disconnect.
- `get_history(run_id=None, limit=100)`: Snapshot retrieval for newly connected clients, enabling instant replay of run history.

### 2.3 `range_controller.py`
Encapsulates Docker Compose operations by reusing verified logic from `scripts/demo/run_professor_demo.py`:
- Enforces network isolation (`cyber-range_lab` internal network, no target host port publishing).
- Tracks owned container IDs (`_owned`) to ensure only invocation-owned containers are stopped on teardown.
- Preserves named volumes (`cyber-range_ecommerce-data`).
- Probes Gateway loopback HTTP health (`GET http://127.0.0.1:18088/health`).

### 2.4 `run_manager.py`
Coordinates the execution lifecycle and bridges the autonomous runtime to the dashboard:
- Spawns background worker threads (`threading.Thread`) for non-blocking execution.
- Prevents concurrent runs by rejecting new run requests with `409 Conflict` while a run is active.
- Wires `AutonomousRunner(event_hook=self._on_runtime_event)` so that runtime events automatically update `AgentStatus` snapshots and advance `PipelineStatus` stages.
- Executes `emergency_stop()`: immediately engages `KillSwitch`, halts network dispatches, publishes `EMERGENCY_STOP_ACTIVATED`, transitions pipeline stage to `BLOCKED`, and preserves evidence.

### 2.5 `control_api.py`
FastAPI application exposing REST management endpoints, CORS middleware (allowing local origins `127.0.0.1:5173` and `localhost:5173`), and SSE event streams with periodic `: ping\n\n` keepalive frames.

---

## 3. Structured Runtime Events (Phase 2)

### 3.1 Event Architecture & Data Flow

```text
AutonomousRunner (runtime/autonomous_runner.py)
   │ (emits generic dict via _emit_event())
   ▼
event_hook callback
   │
   ▼
RunManager._on_runtime_event (dashboards/app/backend/run_manager.py)
   ├── Updates AgentStatus snapshot (thread-safe)
   ├── Transitions PipelineStatus stages (OBSERVE → PLAN → SAFETY → EXECUTE → EVIDENCE → VERIFY)
   │
   ▼
EventSink.publish (dashboards/app/backend/event_sink.py)
   ├── Appends to bounded history buffer (ring buffer: 1000 items)
   └── Broadcasts to all active subscriber asyncio.Queues
         │
         ▼
SSE Endpoint /api/events & /api/runs/{run_id}/events (dashboards/app/backend/control_api.py)
   │ (text/event-stream with id, event, data, and ping:15s keepalive)
   ▼
Frontend Browser Dashboard
```

### 3.2 Event Catalog

| Event Type | Trigger Point | Key Payload Fields | Pipeline Stage |
|---|---|---|---|
| `RUN_STARTED` | `AutonomousRunner.run()` begins | `run_id`, `max_iterations`, `target_allowlist` | `PREFLIGHT` |
| `AGENT_ITERATION_STARTED` | Loop iteration starts | `iteration`, `max_iterations`, `budget_remaining` | `OBSERVE` |
| `PLANNER_STARTED` | Planner invocation begins | `iteration`, `planner_type` | `PLAN` |
| `PLANNER_PROPOSED` | Action proposal returned | `action_id`, `action_type`, `target`, `parameters` | `PLAN` |
| `PLANNER_FALLBACK` | Primary planner failed, fell back to RULE | `primary_mode`, `fallback_mode`, `reason` | `PLAN` |
| `SAFETY_EVALUATION_STARTED`| Gate receives proposal | `action_id`, `action_type`, `target` | `SAFETY` |
| `SAFETY_PERMITTED` | Gate approved proposal | `action_id`, `action_type`, `target`, `decision: PERMIT` | `SAFETY` |
| `SAFETY_DENIED` | Gate rejected proposal | `action_id`, `action_type`, `target`, `decision: DENY`, `reason` | `SAFETY` |
| `ACTION_DISPATCH_STARTED` | Approved dispatch begins | `action_id`, `action_type`, `target` | `EXECUTE` |
| `ACTION_DISPATCHED` | Execution completed | `action_id`, `action_type`, `status_code`, `latency_ms` | `EXECUTE` |
| `ACTION_COMPLETED` | Result verified | `action_id`, `action_type`, `success`, `observation_count` | `EXECUTE` |
| `ACTION_FAILED` | Execution encountered error | `action_id`, `error_type`, `message` | `EXECUTE` |
| `OBSERVATION_RECEIVED` | New facts ingested | `observation_id`, `source`, `facts_count` | `OBSERVE` |
| `STATE_UPDATED` | StateManager updated | `state_version`, `endpoints_count`, `params_count` | `STATE` |
| `BUDGET_UPDATED` | Action budget consumed | `budget_remaining`, `budget_consumed`, `max_budget` | - |
| `EVIDENCE_RECORDED` | Evidence file committed | `evidence_id`, `artifact_path`, `sha256` | `EVIDENCE` |
| `EVIDENCE_VERIFIED` | Offline hash verified | `evidence_id`, `verified: true/false`, `rule_id` | `VERIFY` |
| `FINDING_CREATED` | Vulnerability fact logged | `finding_id`, `finding_type`, `severity`, `target` | `VERIFY` |
| `STOP_CONDITION_REACHED` | Exit condition triggered | `condition`, `iteration`, `total_actions` | `COMPLETE` |
| `AGENT_REPLANNING` | Planning next step | `iteration`, `replan_reason` | `PLAN` |
| `EMERGENCY_STOP_ACTIVATED`| Kill switch triggered | `reason`, `kill_switch_active: true` | `BLOCKED` |
| `RUN_STOPPED` | Graceful stop completed | `run_id`, `total_iterations`, `reason` | `COMPLETE` |
| `RUN_COMPLETED` | Normal completion | `run_id`, `total_iterations`, `findings_count` | `COMPLETE` |

### 3.3 Safety Invariants & Telemetry Fail-Safe Guarantees

1. **Zero-Dispatch on Denial**:
   When the Safety Gate issues `SAFETY_DENIED`, the runtime emits `SAFETY_DENIED` and immediately skips execution. Zero `ACTION_DISPATCH_STARTED` or `ACTION_DISPATCHED` events are emitted.
2. **Telemetry Failure Non-Interference**:
   If `event_hook` raises any unhandled exception (e.g. queue overflow, socket error, serialization bug), `_emit_event()` catches and logs the failure (`Telemetry hook error: ...`). Execution continues safely; the Safety Gate is never bypassed, and safety authority remains absolute.
3. **Emergency Stop Preemption**:
   When `/api/emergency-stop` is called, `KillSwitch` activates immediately, pending network calls are dropped, `EMERGENCY_STOP_ACTIVATED` is broadcast, and the visual pipeline state is set to `BLOCKED`.

---

## 4. API Reference

| Endpoint | Method | Description | Response / Stream Format |
|---|---|---|---|
| `/api/status` | `GET` | Unified status across Range, Run, Agent, Safety, Evidence, Pipeline | `SystemStatus` (JSON) |
| `/api/range/status` | `GET` | Detailed Docker container and Gateway probe health | `RangeStatus` (JSON) |
| `/api/range/start` | `POST` | Starts project containers with ownership tracking | `RangeStatus` (JSON) |
| `/api/range/stop` | `POST` | Stops only invocation-owned containers, preserves volumes | `RangeStatus` (JSON) |
| `/api/demo/preflight` | `POST` | Executes real preflight validation checks | `PreflightResponse` (JSON) |
| `/api/runs/current` | `GET` | Snapshot of current or most recent execution run | `RunStatus` & card states (JSON) |
| `/api/runs` | `POST` | Initiates an execution run (`presentation`, `deny-demo`, `autonomous`) | `ControlResponse` (JSON) |
| `/api/runs/{run_id}/stop` | `POST` | Graceful stop request for active run | `ControlResponse` (JSON) |
| `/api/emergency-stop` | `POST` | Triggers immediate kill switch across gate and worker | `ControlResponse` (JSON) |
| `/api/events` | `GET` | SSE stream of all system and runtime events | `text/event-stream` |
| `/api/runs/{run_id}/events` | `GET` | SSE stream filtered by specific `run_id` | `text/event-stream` |

### SSE Wire Format

Every event delivered over `/api/events` conforms to the standard SSE wire format:
```text
id: 42
event: SAFETY_PERMITTED
data: {"id": 42, "event_type": "SAFETY_PERMITTED", "timestamp": "2026-10-11T14:05:00Z", "run_id": "RUN-001", "iteration": 1, "data": {"action_id": "act-1", "target": "http://gateway:8080/shop", "decision": "PERMIT"}}

: ping
```
- **`id`**: Incremental integer for reconnection tracking.
- **`event`**: Event type string for frontend event dispatching.
- **`data`**: Serialized JSON payload matching the `AgentEvent` schema.
- **Keepalive**: `: ping\n\n` comments transmitted every 15 seconds to prevent intermediate proxy timeout.

---

## 5. Testing & Verification

### 5.1 Test Suites

| Test Suite | File | Tests | Coverage Scope |
|---|---|---|---|
| **Backend API** | `tests/backend/test_control_api.py` | 8 PASS | REST endpoints, status aggregation, error handling, CORS |
| **Runtime Events & SSE** | `tests/backend/test_runtime_events.py` | 7 PASS | Event hook lifecycle, telemetry fail-safe, denial invariant, kill switch, SSE streaming |
| **Professor Demo** | `scripts/demo/test_professor_demo.py` | 21 PASS | Demo workflows, fallback, deny-demo, state extraction |
| **Safety Contracts** | `tests/safety/test_safety.py` | 17 PASS | CentralizedSafetyGate policy, allowlists, rate checks, budget limits |
| **Scaffold Gate** | `scripts/validation/validate_scaffold.py` | 0 errors | Canonical schema validation, cache cleanliness, contract integrity |

### 5.2 Running the Tests

```powershell
# Run backend API and runtime event tests
python -B -m unittest discover -s tests/backend -p test_control_api.py -v
python -B -m unittest discover -s tests/backend -p test_runtime_events.py -v

# Run safety regression suite
python -B -m unittest discover -s tests/safety -p test_safety.py -v

# Run scaffold validator
python -B scripts/validation/validate_scaffold.py
```

### 5.3 Live Verification of Backend & SSE

1. **Start the Backend Server**:
   ```powershell
   python -B -m uvicorn dashboards.app.backend.control_api:app --host 127.0.0.1 --port 8000
   ```

2. **Verify REST Status**:
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/status" | ConvertTo-Json -Depth 5
   ```

3. **Verify SSE Live Stream**:
   ```powershell
   curl.exe -N http://127.0.0.1:8000/api/events
   ```
