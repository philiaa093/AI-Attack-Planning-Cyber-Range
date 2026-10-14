# Autonomous Cyber Range Control Center

## 1. Overview

The **Autonomous Cyber Range Control Center** provides an operator dashboard and control plane for observing and governing AI Agent attack planning inside an isolated Web Cyber Range (ShopLab).

The system enforces a strict closed control loop:
```text
OBSERVE
  ↓
PLAN (ObservedStatePlanner: RULE / LLM)
  ↓
SAFETY GATE (CentralizedSafetyGate: 10 policy checks)
  ↓
EXECUTE (Controlled Executor / Gate Dispatch)
  ↓
COLLECT EVIDENCE (DurableEvidenceRecorder)
  ↓
VERIFY (EvidenceVerifier)
  ↓
UPDATE STATE (StateManager / PlannerStateAdapter)
  ↓
REPLAN
```

AI planning operates **strictly within the bounded cyber-range**, allowlisted target registry, and canonical action catalog. Arbitrary shell access or unapproved live network dispatch is categorically rejected.

---

## 2. Architecture

```text
Browser (React + Vite Dashboard - Phase 3)
         │ HTTP / Server-Sent Events (SSE)
         ▼
Control Plane (FastAPI @ 127.0.0.1:8000 - Phase 1 & 2)
   ├── RangeController      → Docker Compose isolation, ownership tracking, health probes
   ├── RunManager           → Background execution thread, state mutex, emergency kill switch
   ├── EventSink            → Thread-safe event bus, bounded ring buffer, multi-subscriber SSE
   ├── AutonomousRunner     → Fail-safe event_hook emitting 20+ typed runtime events
   └── CentralizedSafetyGate → Authority on network dispatch, policy enforcement & budget
         │
         ▼
Cyber Range Runtime (ShopLab)
   ├── Reverse Proxy Gateway (127.0.0.1:18088 loopback ingress)
   └── Isolated Web Target (lab-ecommerce on internal cyber-range_lab network)
```

---

## 3. Directory Structure

```text
dashboards/app/
├── README.md               # Main application overview and architecture
├── __init__.py
├── backend/                # Python FastAPI Control Plane (Phase 1 & 2 Completed)
│   ├── README.md           # Detailed backend architecture, event catalog, API specs, and tests
│   ├── __init__.py
│   ├── control_api.py      # FastAPI application, route handlers, CORS, and SSE streams
│   ├── models.py           # Typed Pydantic schemas (RangeStatus, RunStatus, AgentStatus, AgentEvent, etc.)
│   ├── event_sink.py       # Thread-safe event bus, ring buffer, and async SSE generator
│   ├── range_controller.py # Docker lifecycle wrapper reusing canonical demo runner
│   ├── run_manager.py      # Background worker management, thread synchronization, kill switch, event bridge
│   └── requirements.txt    # Backend dependencies (fastapi, uvicorn, pydantic, sse-starlette)
└── frontend/               # React + TypeScript + Vite Dashboard (Phase 3)
```

---

## 4. Implementation Status

- **Phase 0 — Repository Analysis & Architecture Blueprint**: `COMPLETED`
  - Reused existing canonical components (`AutonomousRunner`, `CentralizedSafetyGate`, `StateManager`, `DurableEvidenceRecorder`, `EvidenceVerifier`).
- **Phase 1 — Backend Control Plane**: `COMPLETED`
  - FastAPI endpoints for Range control, preflight validation, run management, and emergency stop.
  - Fail-closed Docker handling and thread-safe snapshots.
- **Phase 2 — Structured Runtime Events & SSE**: `COMPLETED`
  - Decoupled `event_hook` in `AutonomousRunner` emitting 20+ structured lifecycle events.
  - Fail-safe error isolation (`_emit_event` catches telemetry exceptions without impacting safety or execution).
  - Safety denial invariant preserved (0 dispatches on `SAFETY_DENIED`).
  - Real-time synchronization between runner events and `RunManager` state snapshots.
  - Live SSE streaming via `/api/events` and `/api/runs/{run_id}/events` with `: ping\n\n` keepalive.
- **Phase 3 — Frontend MVP**: `COMPLETED`
  - React 18 + TypeScript + Vite + TailwindCSS + Lucide Icons operator dashboard.
  - Real-time named Server-Sent Events (SSE) stream listener and local optimistic state reconciliation.
  - 5 Operational Cards: Cyber Range, Autonomous Agent, Safety Gate, Executor, Evidence Vault.
  - 10-node Closed-Loop Pipeline with real-time step state tracking.
  - Dual telemetry view: Current Agent Activity + Chronological Live Event Stream.
  - Preflight Modal with granular check outcomes and blocker reporting.
  - Autonomous Run Launcher supporting Safety Deny Demo, Autonomous Run, and Presentation Demo.
  - Emergency Kill Switch integration with prompt confirmation.
  - Fail-safe handling for Docker unavailable and Control API disconnected states without crashing.

- **Phase 6 — Run History, Timeline Replay & Planner Comparison**: `COMPLETED`
  - Canonical Filesystem-Backed Run Index scanning `evidence/runtime/`, `scripts/demo/demo-output/`, `reports/`, and active runs.
  - Read-only historical timeline replay engine with playback controls (Scrubber, Play/Pause, 1x/2x/4x speed) and guaranteed zero network dispatch (`HISTORICAL REPLAY — NO LIVE EXECUTION`).
  - Side-by-side experiment comparison with metric diffs, step-by-step action sequence alignment, safety invariant checks, and findings overlap.
  - Honest LLM provenance tracking (`RULE_EXECUTED`, `LLM_FALLBACK_TO_RULE`, `LLM_PROVIDER_NOT_AVAILABLE`, `HYBRID_NOT_IMPLEMENTED`). In unconfigured API key environments, fallback runs are transparently audited as `LLM_FALLBACK_TO_RULE`.
  - Neutral academic language enforcement across comparative verdicts ("Observed", "Measured", "Recorded").
  - Exportable research deliverables via JSON and CSV (`/api/runs/compare/export`).
  - High-resolution visual captures: `run-history.png`, `run-replay.png`, `planner-comparison.png`.

---

## 5. Operational Modes

1. **MANUAL**:
   - AI Planner proposes next typed action.
   - Operator reviews and explicitly approves execution.
2. **ASSISTED**:
   - Safe read-only actions (RECON / PASSIVE SCAN) execute automatically within budget.
   - Sensitive or active verifications require operator token approval.
3. **AUTONOMOUS LAB**:
   - Autonomous closed loop runs unassisted until goal completion, budget exhaustion, or terminal state.
   - All network dispatches remain bounded by `CentralizedSafetyGate`.

---

## 6. Supported Demo Scenarios

- **Presentation Demo**: Bounded multi-page discovery, HTML form/link metadata extraction, normalization into StateManager, and RULE plan proposal.
- **Autonomous Demo**: Closed-loop observation -> state -> plan -> gate -> execute -> evidence -> replan.
- **Safety Deny Demo**: Synthetic unallowlisted target proposal (`lab-not-approved`) rejected by Safety Gate with **zero network dispatch** (`dispatch_count = 0`).
- **LLM Fallback Demo**: Injected LLM provider outage demonstrating automatic, audited fallback to RULE baseline with preserved provenance.
- **One-page Preview**: Single-page bounded preview for rapid pre-presentation verification.

---

## 7. REST API Endpoints (Phase 6)

| Endpoint | Method | Description |
|---|---|---|
| `/api/runs/history` | GET | Returns filtered list of past and active runs with provenance metadata |
| `/api/runs/{run_id}` | GET | Returns detailed summary, execution metrics, and safety tallies for a single run |
| `/api/runs/{run_id}/timeline` | GET | Returns chronologically ordered event ledger for deterministic timeline replay |
| `/api/runs/compare?run_a={id}&run_b={id}` | GET | Returns side-by-side metrics diff, action sequence diff, and overlap analysis |
| `/api/runs/compare/export?run_a={id}&run_b={id}&format={json\|csv}` | GET | Exports comparison analysis as downloadable JSON or CSV file |

---

## 8. How to Run & Verify

### Prerequisites
- Node.js >= 18 (Tested on Node.js v24.19.0, npm 11.17.0)
- Python >= 3.10
- Docker Desktop (Required for live ShopLab container execution; Safety Deny Demo can run without Docker)

### 1. Start the Backend Control Plane
```powershell
python -B -m uvicorn dashboards.app.backend.control_api:app --host 127.0.0.1 --port 8000
```

### 2. Start the Frontend Dashboard
```powershell
cd dashboards/app/frontend
npm install
npm run dev
```
Open browser at: `http://127.0.0.1:5173`

### 3. Run Safety Deny Demo from Dashboard
1. Click **Start Autonomous Run** in the bottom control bar.
2. Select **Safety Deny Demo** (Zero Dispatch Proof).
3. Click **Launch Execution**.
4. Observe real-time state:
   - Safety Gate: `DENIED` (`Last Denial Reason: DEMO_DENIAL_PROPOSAL`)
   - Executor: `NOT CALLED` (`Zero network dispatch`)
   - Network Dispatches: `0`
   - Evidence Vault: `SHA-256 VALID`
   - Pipeline: `SAFETY` = `DENIED`, `EXECUTE` = `BLOCKED`, `COMPLETE` = `COMPLETED`.

### 4. Run Frontend Tests & Typecheck
```powershell
cd dashboards/app/frontend
npm run typecheck
npm run test
npm run build
```

### 5. Run Backend Regression Tests
```powershell
python -B -m unittest discover -s tests/backend -p "test_*.py" -v
```
