from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PipelineRunRequest(BaseModel):
    """
    Payload for POST /pipeline/run.

    thesis_id is optional — if omitted, the pipeline uses the default
    specialty tax thesis (seeded at startup).
    """

    thesis_id: Optional[UUID] = None


class PipelineRunOut(BaseModel):
    """Full pipeline run record, used for status polling."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thesis_id: Optional[UUID] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str                         # "running" | "completed" | "failed"
    companies_added: int = 0
    duplicates_found: int = 0
    errors: list[Any] = []             # [{collector, error, at}]


class PipelineStartResponse(BaseModel):
    """
    Immediate response from POST /pipeline/run.

    Returns the run_id so the client can poll GET /pipeline/runs/{run_id}.
    HTTP 202 Accepted — the pipeline runs asynchronously after this response.
    """

    run_id: UUID
    status: str
    message: str
