import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class RawRecord(Base):
    """
    Immutable audit log of every raw payload received from a data source.

    Design intent:
    - Written immediately when a collector returns data, before normalization.
    - Never mutated after insert — only the `processed` flag and `company_id`
      FK are updated after normalization links the record to a Company.
    - Enables re-running the normalization/deduplication step without
      re-scraping data sources.
    - The JSONB `raw_payload` stores the source-native shape, which differs
      per collector (Google Places result ≠ state filing ≠ HTML scrape).
    - GIN index on `raw_payload` allows `@>` queries for debugging, e.g.
      finding all Google Maps records that mentioned a specific service term.

    Cascade: company_id is SET NULL (not CASCADE DELETE) so that deleting a
    duplicate company record does not destroy the source audit trail.
    """

    __tablename__ = "raw_records"

    __table_args__ = (
        # Partial index — the pipeline's main query: WHERE processed = FALSE
        Index(
            "idx_raw_records_unprocessed",
            "processed",
            postgresql_where=text("processed = FALSE"),
        ),
        # GIN index — supports containment queries on the raw payload for
        # debugging and reprocessing specific source shapes
        Index(
            "idx_raw_records_payload_gin",
            "raw_payload",
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which collector produced this record
    source_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Collector identifier: 'google_places' | 'state_filings' | "
            "'ascsp' | 'web_scraper' | 'manual_import'"
        ),
        index=True,
    )

    # The complete, unmodified response object from the source
    raw_payload: Mapped[Any] = mapped_column(JSONB, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Set to TRUE after the normalizer has processed this record
    processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # Set after deduplication links this record to a canonical company.
    # NULL means the record is either unprocessed or was rejected.
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    company: Mapped[Optional["Company"]] = relationship(
        "Company", back_populates="raw_records"
    )

    def __repr__(self) -> str:
        return (
            f"<RawRecord id={self.id} source={self.source_name!r} "
            f"processed={self.processed}>"
        )
