import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class Contact(Base):
    """
    Key contact or owner associated with a company.

    One company can have multiple contacts (e.g., founding partner + COO).
    Contacts are extracted from company websites and Google Maps listings.
    All fields are optional — partial data is the norm for this source set.

    Cascade: deleted when parent company is deleted (ON DELETE CASCADE).
    """

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Parent FK ─────────────────────────────────────────────────────────────
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Contact fields ────────────────────────────────────────────────────────
    # All nullable — pipeline captures what's publicly available
    name: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text)

    # Which collector/enricher surfaced this contact
    source: Mapped[Optional[str]] = mapped_column(Text)

    # ── Relationships ─────────────────────────────────────────────────────────
    company: Mapped["Company"] = relationship(
        "Company", back_populates="contacts"
    )

    def __repr__(self) -> str:
        return (
            f"<Contact id={self.id} name={self.name!r} "
            f"company_id={self.company_id}>"
        )
