"""FastAPI Control API for Autonomous Cyber Range Control Center."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional
import uuid

import asyncio

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from dashboards.app.backend.event_sink import EventSink
from dashboards.app.backend.models import (
    AgentEvent,
    ControlResponse,
    DemoReadinessResponse,
    EvidenceDetailResponse,
    EvidenceListResponse,
    FindingsListResponse,
    PreflightResponse,
    ProposalActionRequest,
    RangeStatus,
    RunComparisonResponse,
    RunHistoryItem,
    RunHistoryResponse,
    RunSummaryResponse,
    RunTimelineResponse,
    StartRunRequest,
    SystemStatus,
)
from dashboards.app.backend.range_controller import RangeController
from dashboards.app.backend.run_history import RunIndex
from dashboards.app.backend.run_manager import RunManager
from dashboards.app.backend.model_profiles import ProfileStore, create_router


# Singletons
event_sink = EventSink()
range_controller = RangeController()
model_profiles = ProfileStore(env_path=ROOT / ".env")
run_manager = RunManager(model_profiles=model_profiles)
run_index = RunIndex(run_manager=run_manager)

app = FastAPI(
    title="Autonomous Cyber Range Control Center API",
    version="1.0.0",
    description="Control plane adapter connecting Dashboard UI to Cyber Range runtime and safety gate",
)
app.include_router(create_router(model_profiles))

# Strict development CORS setup (supporting Vite on 5173 / 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/research/overview")
def get_research_overview() -> Dict[str, Any]:
    """Read canonical task status and bounded offline artifact summaries only."""
    from dashboards.app.backend.research_overview import build_research_overview

    return build_research_overview(ROOT)


@app.get("/api/status", response_model=SystemStatus)
def get_system_status() -> SystemStatus:
    """Return unified operational status across Range, Run, Safety, and Evidence."""
    range_stat = range_controller.get_status()
    run_stat, agent_stat, safety_stat, evidence_stat, pipeline_stat = run_manager.get_snapshot()

    return SystemStatus(
        api="healthy",
        timestamp_utc=range_stat.checked_at_utc,
        range=range_stat,
        run=run_stat,
        agent=agent_stat,
        safety=safety_stat,
        evidence=evidence_stat,
        pipeline=pipeline_stat,
    )


@app.get("/api/range/status", response_model=RangeStatus)
def get_range_status() -> RangeStatus:
    """Return real Docker container and gateway health without faking."""
    return range_controller.get_status()


@app.post("/api/range/start", response_model=RangeStatus)
async def start_range() -> RangeStatus:
    """Start isolated ShopLab services (lab-ecommerce and gateway)."""
    return range_controller.start()


@app.post("/api/range/stop", response_model=RangeStatus)
async def stop_range() -> RangeStatus:
    """Stop owned lab services while preserving volume state."""
    return range_controller.stop_owned()


@app.post("/api/demo/preflight", response_model=PreflightResponse)
async def run_preflight() -> PreflightResponse:
    """Execute real preflight validation checks without bypass."""
    return run_manager.run_preflight()


@app.get("/api/demo/readiness", response_model=DemoReadinessResponse)
async def get_demo_readiness() -> DemoReadinessResponse:
    """Return unified system readiness assessment separating REQUIRED vs OPTIONAL capabilities."""
    return run_manager.get_demo_readiness(range_controller=range_controller)


@app.get("/api/runs/current")
async def get_current_run() -> Dict[str, Any]:
    """Return comprehensive snapshot of the active/latest execution run."""
    run_stat, agent_stat, safety_stat, evidence_stat, pipeline_stat = run_manager.get_snapshot()
    return {
        "run": run_stat.model_dump(),
        "agent": agent_stat.model_dump(),
        "safety": safety_stat.model_dump(),
        "evidence": evidence_stat.model_dump(),
        "pipeline": pipeline_stat.model_dump(),
    }


@app.post("/api/runs", response_model=ControlResponse)
async def start_new_run(request: StartRunRequest) -> ControlResponse:
    """Initiate a new closed-loop autonomous run or demo scenario."""
    res = run_manager.start_run(request, event_sink)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=res.message,
        )
    return res


@app.post("/api/runs/{run_id}/stop", response_model=ControlResponse)
async def stop_run(run_id: str) -> ControlResponse:
    """Gracefully stop an active execution run."""
    res = run_manager.stop_run(run_id, event_sink)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )
    return res


@app.post("/api/runs/{run_id}/pause", response_model=ControlResponse)
async def pause_run(run_id: str) -> ControlResponse:
    """Cooperatively request run pause before next safe boundary."""
    res = run_manager.pause_run(run_id, event_sink)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )
    return res


@app.post("/api/runs/{run_id}/resume", response_model=ControlResponse)
async def resume_run(run_id: str) -> ControlResponse:
    """Resume execution from paused state."""
    res = run_manager.resume_run(run_id, event_sink)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )
    return res


@app.post("/api/runs/{run_id}/proposals/{proposal_id}/approve", response_model=ControlResponse)
async def approve_proposal(run_id: str, proposal_id: str) -> ControlResponse:
    """Operator approves proposal; dispatches strictly through Safety Gate."""
    res = run_manager.approve_proposal(run_id, proposal_id, event_sink)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )
    return res


@app.post("/api/runs/{run_id}/proposals/{proposal_id}/reject", response_model=ControlResponse)
async def reject_proposal(
    run_id: str, proposal_id: str, body: Optional[ProposalActionRequest] = None
) -> ControlResponse:
    """Operator rejects proposal; runner ingests refusal observation and replans."""
    reason = body.reason if body else None
    res = run_manager.reject_proposal(run_id, proposal_id, reason=reason, event_sink=event_sink)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )
    return res


@app.post("/api/emergency-stop", response_model=ControlResponse)
async def emergency_stop() -> ControlResponse:
    """Trigger immediate emergency kill switch across runtime and safety gate."""
    return run_manager.emergency_stop(event_sink)


@app.get("/api/runs/history", response_model=RunHistoryResponse)
def get_runs_history(
    planner: Optional[str] = None,
    control_mode: Optional[str] = None,
    state: Optional[str] = None,
    scenario: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_test_runs: bool = True,
) -> RunHistoryResponse:
    """Read-only listing of all indexed execution runs across filesystem evidence."""
    return run_index.list_runs(
        planner=planner,
        control_mode=control_mode,
        state=state,
        scenario=scenario,
        search=search,
        limit=limit,
        offset=offset,
        include_test_runs=include_test_runs,
    )


@app.get("/api/runs/compare", response_model=RunComparisonResponse)
async def compare_runs(run_a: str, run_b: str) -> RunComparisonResponse:
    """Compare two execution runs side-by-side with metrics, action sequences, and safety diff."""
    try:
        run_index.validate_run_id(run_a)
        run_index.validate_run_id(run_b)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    res = run_index.compare_runs(run_a, run_b)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"One or both runs ({run_a}, {run_b}) not found for comparison",
        )
    return res


@app.get("/api/runs/compare/export")
async def export_run_comparison(run_a: str, run_b: str, format: str = "json") -> Response:
    """Export run comparison as downloadable JSON or CSV artifact."""
    try:
        run_index.validate_run_id(run_a)
        run_index.validate_run_id(run_b)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    try:
        content, media_type = run_index.export_comparison(run_a, run_b, format=format)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    ext = "csv" if format.lower() == "csv" else "json"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="comparison_{run_a}_{run_b}.{ext}"'},
    )


@app.get("/api/runs/{run_id}/evidence", response_model=EvidenceListResponse)
async def get_run_evidence(run_id: str) -> EvidenceListResponse:
    """Read-only listing of all recorded and cryptographic evidence for run_id."""
    try:
        res = run_manager.get_run_evidence(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
    return res


@app.get("/api/runs/{run_id}/evidence/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_run_evidence_detail(run_id: str, evidence_id: str) -> EvidenceDetailResponse:
    """Read-only detail and payload of an individual verified evidence artifact."""
    try:
        res = run_manager.get_run_evidence_detail(run_id, evidence_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evidence {evidence_id} not found for run {run_id}")
    return res


@app.get("/api/runs/{run_id}/findings", response_model=FindingsListResponse)
async def get_run_findings(run_id: str) -> FindingsListResponse:
    """Read-only list of structured findings and discovered attack surfaces for run_id."""
    try:
        res = run_manager.get_run_findings(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
    return res


@app.get("/api/runs/{run_id}/summary", response_model=RunSummaryResponse)
async def get_run_summary(run_id: str) -> RunSummaryResponse:
    """Read-only comprehensive summary report for run_id."""
    try:
        res = run_manager.get_run_summary(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
    return res


@app.get("/api/runs/{run_id}", response_model=RunHistoryItem)
async def get_run_detail(run_id: str) -> RunHistoryItem:
    """Return single execution run metadata and metrics."""
    try:
        run_index.validate_run_id(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    item = run_index.get_run(run_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
    return item


@app.get("/api/runs/{run_id}/timeline", response_model=RunTimelineResponse)
async def get_run_timeline(run_id: str) -> RunTimelineResponse:
    """Return chronologically sorted timeline steps for historical replay."""
    try:
        run_index.validate_run_id(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    res = run_index.get_run_timeline(run_id)
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found")
    return res




@app.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str) -> EventSourceResponse:
    """Server-Sent Events (SSE) realtime stream filtered by run_id."""
    async def event_generator():
        # First send existing history for this run
        for historical in event_sink.get_history(run_id=run_id):
            yield {
                "id": historical.get("event_id"),
                "event": historical.get("type", "message"),
                "data": json.dumps(historical),
            }
        # Then stream live events
        async for live_event in event_sink.subscribe(run_id=run_id):
            yield {
                "id": live_event.get("event_id"),
                "event": live_event.get("type", "message"),
                "data": json.dumps(live_event),
            }

    return EventSourceResponse(event_generator(), ping=15)


@app.get("/api/events")
async def stream_all_events() -> EventSourceResponse:
    """Server-Sent Events (SSE) realtime stream for all control center events."""
    async def event_generator():
        # First send recent history
        for historical in event_sink.get_history(limit=50):
            yield {
                "id": historical.get("event_id"),
                "event": historical.get("type", "message"),
                "data": json.dumps(historical),
            }
        # Then stream live events
        async for live_event in event_sink.subscribe():
            yield {
                "id": live_event.get("event_id"),
                "event": live_event.get("type", "message"),
                "data": json.dumps(live_event),
            }

    return EventSourceResponse(event_generator(), ping=15)
