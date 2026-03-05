"""
Pipeline routes.

POST /pipeline/run        — trigger a full pipeline run (blocking, ~minutes)
GET  /pipeline/runs       — list all pipeline runs, most recent first
GET  /pipeline/runs/{id}  — status / result of a specific run
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.pipeline_run import PipelineRun
from app.models.thesis import Thesis
from app.pipeline.orchestrator import run_pipeline
from app.schemas.pipeline_run import (
    PipelineRunOut,
    PipelineRunRequest,
    PipelineStartResponse,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── POST /pipeline/run ────────────────────────────────────────────────────────

@router.post("/run", response_model=PipelineStartResponse, status_code=202)
async def trigger_pipeline_run(
    request: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
) -> PipelineStartResponse:
    """
    Trigger a full pipeline run.

    Runs synchronously in the request — the response is returned only after
    all collectors, normalization, and upserts complete (~minutes for a full
    49-state run).  A production deployment would move this to a task queue
    and return immediately with a run_id for polling.

    thesis_id is validated if provided; the orchestrator currently uses the
    hardcoded default thesis parameters regardless.
    """
    if request.thesis_id is not None:
        thesis = await db.get(Thesis, request.thesis_id)
        if thesis is None:
            raise HTTPException(
                status_code=404,
                detail=f"Thesis {request.thesis_id} not found",
            )

    run = await run_pipeline(db)

    return PipelineStartResponse(
        run_id=run.id,
        status=run.status,
        message=(
            f"Pipeline {run.status}. "
            f"companies_added={run.companies_added}  "
            f"duplicates_found={run.duplicates_found}  "
            f"errors={len(run.errors)}"
        ),
    )


# ── GET /pipeline/runs ────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[PipelineRunOut])
async def list_pipeline_runs(
    db: AsyncSession = Depends(get_db),
) -> list[PipelineRunOut]:
    """List all pipeline runs, most recent first."""
    rows = (
        await db.execute(
            select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(50)
        )
    ).scalars().all()

    return [PipelineRunOut.model_validate(r) for r in rows]


# ── GET /pipeline/runs/{run_id} ───────────────────────────────────────────────

@router.get("/runs/{run_id}", response_model=PipelineRunOut)
async def get_pipeline_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunOut:
    """
    Status of a specific pipeline run.

    Poll this endpoint after POST /pipeline/run to track progress.
    A run moves from status='running' → 'completed' | 'failed'.
    """
    run = await db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    return PipelineRunOut.model_validate(run)
