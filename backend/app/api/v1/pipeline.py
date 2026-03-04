"""
Pipeline routes.

POST /pipeline/run        — trigger a pipeline run (stub; logic added next increment)
GET  /pipeline/runs       — list all pipeline runs
GET  /pipeline/runs/{id}  — status of a specific run (for polling)

The POST endpoint returns HTTP 202 Accepted immediately and creates a
PipelineRun record.  The actual collector/normalizer/deduplicator logic
will be wired in the next increment; for now the run is created with
status='running' and immediately marked 'failed' with a "not yet implemented"
error so the stub is honest about its state.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.pipeline_run import PipelineRun
from app.models.thesis import Thesis
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
    Trigger a pipeline run.

    HTTP 202 Accepted — the pipeline executes asynchronously.
    Poll GET /pipeline/runs/{run_id} to track progress.

    STUB: Pipeline execution is not yet implemented.  The run record is
    created and immediately finalized as 'failed' with a clear error message
    so the endpoint is honest.  The orchestrator will be wired here in the
    next implementation increment.
    """
    # Validate thesis if explicitly provided
    if request.thesis_id is not None:
        thesis = await db.get(Thesis, request.thesis_id)
        if thesis is None:
            raise HTTPException(
                status_code=404,
                detail=f"Thesis {request.thesis_id} not found",
            )

    # Create pipeline run record
    run = PipelineRun(
        thesis_id=request.thesis_id,
        status="running",
    )
    db.add(run)
    await db.flush()  # populate run.id before the commit

    # ── STUB: mark immediately failed with a clear placeholder error ──────────
    # Remove this block and replace with:
    #   asyncio.create_task(orchestrator.run(run.id, db))
    # once the orchestrator is implemented.
    run.status = "failed"
    run.completed_at = datetime.now(timezone.utc)
    run.errors = [
        {
            "collector": "orchestrator",
            "error": "Pipeline not yet implemented — stub endpoint",
            "at": datetime.now(timezone.utc).isoformat(),
        }
    ]
    # ── END STUB ─────────────────────────────────────────────────────────────

    await db.commit()
    await db.refresh(run)

    return PipelineStartResponse(
        run_id=run.id,
        status=run.status,
        message=(
            "Pipeline run created. "
            "Poll GET /api/v1/pipeline/runs/{run_id} for status. "
            "[STUB: pipeline logic not yet implemented]"
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
