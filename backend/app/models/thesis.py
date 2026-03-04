import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.pipeline_run import PipelineRun


class Thesis(Base):
    """
    Represents a single investment thesis configuration.

    The default thesis (specialty tax advisory) is seeded at startup.
    Additional theses can be created via POST /api/v1/thesis to support
    the bonus feature: running the pipeline against a different mandate.

    Services and exclusions are stored as JSONB string arrays using the
    same service-key vocabulary used across the entire system:
        "rd_credits"    — R&D Tax Credits
        "cost_seg"      — Cost Segregation
        "wotc"          — Work Opportunity Tax Credits
        "sales_use_tax" — Sales & Use Tax consulting
        "erc"           — Employee Retention Credit (exclusion marker)
        "property_tax"  — Property Tax consulting (exclusion marker)
    """

    __tablename__ = "thesis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # List of qualifying service keys, e.g. ["rd_credits", "cost_seg", "wotc"]
    services: Mapped[Any] = mapped_column(JSONB, nullable=False)

    # Size thresholds — NULL means "no minimum"
    revenue_min: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Minimum revenue in thousands USD"
    )
    employee_min: Mapped[Optional[int]] = mapped_column(Integer)

    # NULL states = all continental US states in scope
    states: Mapped[Optional[Any]] = mapped_column(
        JSONB, comment="List of 2-char state codes; NULL = all continental US"
    )

    # Service keys that disqualify a company, e.g. ["erc", "property_tax"]
    exclusions: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Ownership types that qualify, e.g. ["private", "franchise"]
    # NULL = any non-public ownership
    ownership: Mapped[Optional[Any]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="thesis", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Thesis id={self.id} name={self.name!r}>"
