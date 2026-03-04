"""
Company schemas.

Three response shapes serve different consumers:
  - CompanyList  — lightweight, used in paginated table rows (no contacts)
  - CompanyOut   — full detail, used in the company drawer/detail page
  - CompanyUpdate — partial update payload for analyst corrections (PUT)
  - PaginatedCompanies — envelope for the GET /companies list response
"""

import math
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.contact import ContactOut


class CompanyList(BaseModel):
    """
    Lightweight projection used in the paginated company table.

    Excludes contacts to keep list responses small.  The frontend renders
    these as table rows; clicking a row triggers a separate GET /{id} call
    that returns the full CompanyOut with contacts.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    website: Optional[str] = None

    # JSONB array of service keys, e.g. ["rd_credits", "cost_seg"]
    services: list[str] = []

    # Revenue range in thousands USD — both may be None if unknown
    revenue_est_min: Optional[int] = None
    revenue_est_max: Optional[int] = None
    employee_count: Optional[int] = None

    ownership_type: Optional[str] = None
    is_excluded: bool = False
    exclusion_reason: Optional[str] = None
    thesis_fit_score: Optional[float] = None
    primary_source: str
    created_at: datetime


class CompanyOut(BaseModel):
    """
    Full company detail including contacts.

    Returned by GET /companies/{id}.  Contacts are loaded via selectinload
    in the route handler; with from_attributes=True Pydantic reads the
    already-loaded relationship list directly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    website: Optional[str] = None
    services: list[str] = []
    revenue_est_min: Optional[int] = None
    revenue_est_max: Optional[int] = None
    employee_count: Optional[int] = None
    ownership_type: Optional[str] = None
    union_affiliated: bool = False
    is_excluded: bool = False
    exclusion_reason: Optional[str] = None
    thesis_fit_score: Optional[float] = None
    primary_source: str
    created_at: datetime
    updated_at: datetime

    # Contacts loaded via selectinload in the detail route handler
    contacts: list[ContactOut] = []


class CompanyUpdate(BaseModel):
    """
    Partial update payload for analyst corrections.

    All fields are Optional — only provided fields are applied.
    Intentionally narrow: analysts can correct classification and size data
    but cannot rename companies or change primary_source (data integrity).
    """

    ownership_type: Optional[str] = None
    services: Optional[list[str]] = None
    revenue_est_min: Optional[int] = None
    revenue_est_max: Optional[int] = None
    employee_count: Optional[int] = None
    union_affiliated: Optional[bool] = None
    is_excluded: Optional[bool] = None
    exclusion_reason: Optional[str] = None

    @field_validator("ownership_type")
    @classmethod
    def validate_ownership(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"private", "pe_backed", "public", "franchise", "unknown"}
        if v is not None and v not in allowed:
            raise ValueError(f"ownership_type must be one of {allowed}")
        return v


class PaginatedCompanies(BaseModel):
    """Envelope returned by GET /companies."""

    items: list[CompanyList]
    total: int      # total matching records (before pagination)
    page: int       # current page (1-indexed)
    limit: int      # page size
    pages: int      # total pages = ceil(total / limit)

    @classmethod
    def build(
        cls,
        items: list[Any],
        total: int,
        page: int,
        limit: int,
    ) -> "PaginatedCompanies":
        pages = math.ceil(total / limit) if total > 0 else 0
        return cls(items=items, total=total, page=page, limit=limit, pages=pages)
