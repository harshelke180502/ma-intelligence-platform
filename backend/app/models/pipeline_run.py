import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.thesis import Thesis


class PipelineRun(Base):
    """
    Audit record for a single execution of the data pipeline.

    Created when POST /api/v1/pipeline/run is called.
    Updated throughout the run: status transitions running → completed | failed.
    Used by the dashboard header to show "last updated" and pipeline health.

    The `errors` JSONB array captures per-collector failures without halting
    the overall run — a partial result is better than no result.  Structure:
        [{"collector": "google_places", "error": "rate limited", "at": "..."}]
    """

    __tablename__ = "pipeline_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_pipeline_run_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # NULL thesis_id is allowed so runs can be recorded even if the thesis
    # record is later deleted (SET NULL on the FK).
    thesis_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thesis.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status lifecycle: running → completed | failed
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="'running'"
    )

    companies_added: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    duplicates_found: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # Per-collector error log — populated even on partial success so that
    # analysts can see which sources were unavailable during a given run.
    errors: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    thesis: Mapped[Optional["Thesis"]] = relationship(
        "Thesis", back_populates="pipeline_runs"
    )

    def __repr__(self) -> str:
        return (
            f"<PipelineRun id={self.id} status={self.status!r} "
            f"companies_added={self.companies_added}>"
        )
