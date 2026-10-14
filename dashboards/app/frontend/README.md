# Autonomous Cyber Range Control Center — Frontend MVP

Frontend user interface and real-time observability console for the Autonomous Cyber Range Control Center.

## Technology Stack
- **Framework**: React 18
- **Language**: TypeScript 5.5
- **Build Tool**: Vite 5.4
- **Styling**: TailwindCSS 3.4 (Dark engineering dashboard aesthetic)
- **Icons**: Lucide React
- **Testing**: Vitest + React Testing Library + jsdom

## Getting Started

### Prerequisites
- Node.js >= 18 (`v24.19.0` verified)
- npm >= 9 (`11.17.0` verified)
- Python Control API backend running on `http://127.0.0.1:8000`

### Installation
```powershell
npm install
```

### Development Server
```powershell
npm run dev
```
Accessible at `http://127.0.0.1:5173`.

### Production Build & Typecheck
```powershell
npm run typecheck
npm run test
npm run build
```

## Architecture & Realtime Event Synchronization

1. **Authoritative REST Snapshots**: Initial hydration and periodic reconciliation occur via `GET /api/status`.
2. **Server-Sent Events (SSE)**: `useEventStream` registers listeners for custom named SSE events emitted by the backend runtime (`RUN_STARTED`, `PLANNER_STARTED`, `PLANNER_PROPOSED`, `SAFETY_PERMITTED`, `SAFETY_DENIED`, `ACTION_DISPATCHED`, `EVIDENCE_RECORDED`, `EVIDENCE_VERIFIED`, `RUN_COMPLETED`, etc.).
3. **Safety Gate Invariant Visualized**: In `deny-demo` scenario, the Safety Gate reflects `DENIED`, the Executor reflects `NOT CALLED`, and network dispatches are strictly `0`.
4. **Resilience**: If the Control API is offline or Docker is unavailable, the UI gracefully renders informative status cards without crashing.
