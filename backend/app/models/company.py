import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.raw_record import RawRecord


class Company(Base):
    """
    Canonical, deduplicated company record.

    One row per real-world company after normalization and deduplication.
    Raw scrape payloads live in raw_records; this table holds only the
    cleansed, analyst-ready data.

    Deduplication anchor: UNIQUE (name, state).  The pipeline uses
    INSERT ... ON CONFLICT (name, state) DO UPDATE to merge data from
    multiple sources into a single row, preferring non-NULL values.

    Revenue fields are stored in thousands of USD as INTEGER to avoid
    floating-point representation drift.  A range (min/max) communicates
    that revenue estimates are inherently imprecise.
    """

    __tablename__ = "companies"

    __table_args__ = (
        # ── Deduplication anchor ──────────────────────────────────────────────
        UniqueConstraint("name", "state", name="uq_company_name_state"),
        # ── Business-rule constraint ──────────────────────────────────────────
        CheckConstraint(
            "ownership_type IN "
            "('private', 'pe_backed', 'public', 'franchise', 'unknown')",
            name="ck_company_ownership_type",
        ),
        # ── Indexes ───────────────────────────────────────────────────────────
        # Standard B-tree index — most dashboard filters are state-scoped
        Index("idx_companies_state", "state"),
        # Partial index — pipeline queries only unexcluded companies
        Index(
            "idx_companies_active",
            "is_excluded",
            postgresql_where=text("is_excluded = FALSE"),
        ),
        # GIN index — enables efficient @> containment queries on the services
        # JSONB array, e.g. services @> '["rd_credits"]'
        Index("idx_companies_services_gin", "services", postgresql_using="gin"),
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[Optional[str]] = mapped_column(
        String(2), comment="2-char USPS state code"
    )
    website: Mapped[Optional[str]] = mapped_column(
        Text, comment="Canonical root domain, e.g. acmetax.com"
    )

    # ── Thesis-relevant fields ────────────────────────────────────────────────
    # String array of qualifying service keys, e.g. ["rd_credits", "wotc"]
    services: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Revenue stored as a range in thousands USD — estimates are imprecise
    revenue_est_min: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Lower bound of revenue estimate in thousands USD"
    )
    revenue_est_max: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Upper bound of revenue estimate in thousands USD"
    )
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)

    # ── Classification ────────────────────────────────────────────────────────
    ownership_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="One of: private, pe_backed, public, franchise, unknown",
    )
    union_affiliated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # ── Exclusion tracking ────────────────────────────────────────────────────
    # Excluded companies are stored (not deleted) so the pipeline can report
    # them and analysts can audit the exclusion decision.
    is_excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    exclusion_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="'erc_primary' | 'property_tax_only' | 'union' | 'out_of_geo'",
    )

    # ── Scoring ───────────────────────────────────────────────────────────────
    # 0.00–1.00 composite fit score computed at normalization time.
    # Factors: service match count, size threshold met, private ownership.
    thesis_fit_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))

    # ── Provenance ────────────────────────────────────────────────────────────
    # The first/primary source that surfaced this company.  Additional sources
    # are tracked via raw_records FK.
    primary_source: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # onupdate fires when the ORM issues an UPDATE.  For server-side triggers
    # (bulk SQL updates), add a PostgreSQL function + trigger in the migration.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    contacts: Mapped[list["Contact"]] = relationship(
        "Contact",
        back_populates="company",
        cascade="all, delete-orphan",
        # Load contacts in the same query as the company for detail view
        lazy="selectin",
    )
    raw_records: Mapped[list["RawRecord"]] = relationship(
        "RawRecord",
        back_populates="company",
        # Don't cascade deletes — raw_records is an audit log
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r} state={self.state!r}>"
