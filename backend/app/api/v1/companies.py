"""
Company routes.

GET /companies  — paginated, filterable, sortable company list
GET /companies/{id} — full company detail with contacts
PUT /companies/{id} — analyst correction (partial update)
"""

import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, cast, desc, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.company import Company
from app.schemas.company import (
    CompanyList,
    CompanyOut,
    CompanyUpdate,
    PaginatedCompanies,
)

router = APIRouter(prefix="/companies", tags=["companies"])

# ── Sort column allowlist ─────────────────────────────────────────────────────
# Maps URL param → ORM column.  Prevents SQL injection — no string is ever
# interpolated into a query; we always resolve to a known column object.
_SORTABLE: dict[str, Any] = {
    "name": Company.name,
    "state": Company.state,
    "revenue_est_min": Company.revenue_est_min,
    "employee_count": Company.employee_count,
    "thesis_fit_score": Company.thesis_fit_score,
    "created_at": Company.created_at,
    "ownership_type": Company.ownership_type,
}


def _jsonb_overlap(column: Any, values: list[str]) -> Any:
    """
    JSONB && operator — true if the column array overlaps with values.

    Used for OR-semantics service filtering:
      services && CAST('["rd_credits","wotc"]' AS JSONB)
    returns companies that offer rd_credits OR wotc (or both).

    The GIN index on companies.services makes this O(log n).
    """
    return column.op("&&")(cast(json.dumps(values), JSONB))


def _apply_filters(
    stmt: Any,
    state: Optional[list[str]],
    service: Optional[list[str]],
    ownership: Optional[str],
    revenue_min: Optional[int],
    employees_min: Optional[int],
    include_excluded: bool,
) -> Any:
    """
    Apply all active filters to a SQLAlchemy SELECT statement.

    Extracted as a helper so the same filters can be applied to both the
    COUNT query (for total) and the paginated data query without duplication.
    """
    if not include_excluded:
        stmt = stmt.where(Company.is_excluded.is_(False))

    if state:
        stmt = stmt.where(Company.state.in_(state))

    if service:
        # OR: company offers any of the requested service types
        stmt = stmt.where(_jsonb_overlap(Company.services, service))

    if ownership:
        stmt = stmt.where(Company.ownership_type == ownership)

    if revenue_min is not None:
        # Match companies whose minimum revenue estimate meets the threshold.
        # NULL revenue rows are excluded — incomplete data is not surfaced
        # as meeting the threshold.
        stmt = stmt.where(
            Company.revenue_est_min.isnot(None),
            Company.revenue_est_min >= revenue_min,
        )

    if employees_min is not None:
        stmt = stmt.where(
            Company.employee_count.isnot(None),
            Company.employee_count >= employees_min,
        )

    return stmt


# ── GET /companies ────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedCompanies)
async def list_companies(
    # ── Filters ──────────────────────────────────────────────────────────────
    # Repeat the param to pass multiple values: ?state=TX&state=FL
    state: Optional[list[str]] = Query(
        default=None,
        description="Filter by 2-char state code. Repeatable: ?state=TX&state=FL",
    ),
    service: Optional[list[str]] = Query(
        default=None,
        description=(
            "Filter by service type (OR logic). "
            "Valid: rd_credits, cost_seg, wotc, sales_use_tax"
        ),
    ),
    ownership: Optional[str] = Query(
        default=None,
        description="Filter by ownership type: private, pe_backed, public, franchise, unknown",
    ),
    revenue_min: Optional[int] = Query(
        default=None,
        ge=0,
        description="Minimum revenue_est_min in thousands USD",
    ),
    employees_min: Optional[int] = Query(
        default=None,
        ge=0,
        description="Minimum employee_count",
    ),
    include_excluded: bool = Query(
        default=False,
        description="If true, include companies flagged as excluded from the thesis",
    ),
    # ── Sort ─────────────────────────────────────────────────────────────────
    sort: str = Query(
        default="name",
        description=f"Sort column. Valid: {', '.join(_SORTABLE)}",
    ),
    order: str = Query(
        default="asc",
        pattern="^(asc|desc)$",
        description="Sort direction: asc or desc",
    ),
    # ── Pagination ────────────────────────────────────────────────────────────
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    # ── DB ────────────────────────────────────────────────────────────────────
    db: AsyncSession = Depends(get_db),
) -> PaginatedCompanies:
    """
    Paginated, filterable, sortable company list.

    All filters combine with AND logic; multi-value params (state, service)
    use OR within their group:
      ?state=TX&state=FL&service=rd_credits&service=wotc
      → (state IN ('TX','FL')) AND (services && '["rd_credits","wotc"]')
    """
    # Resolve sort column from allowlist — fall back to name if unknown
    sort_col = _SORTABLE.get(sort, Company.name)
    sort_expr = desc(sort_col) if order == "desc" else asc(sort_col)

    filter_kwargs = dict(
        state=state,
        service=service,
        ownership=ownership,
        revenue_min=revenue_min,
        employees_min=employees_min,
        include_excluded=include_excluded,
    )

    # Total count (same filters, no pagination)
    count_stmt = _apply_filters(
        select(func.count()).select_from(Company), **filter_kwargs
    )
    total: int = (await db.scalar(count_stmt)) or 0

    # Paginated data
    offset = (page - 1) * limit
    data_stmt = (
        _apply_filters(select(Company), **filter_kwargs)
        .order_by(sort_expr)
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(data_stmt)).scalars().all()

    return PaginatedCompanies.build(
        items=[CompanyList.model_validate(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
    )


# ── GET /companies/{id} ───────────────────────────────────────────────────────

@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyOut:
    """
    Full company detail including all contacts.

    selectinload is used explicitly (rather than relying on lazy="selectin"
    on the model) because async SQLAlchemy sessions do not support
    implicit lazy loading — the load must be requested at query time.
    """
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(selectinload(Company.contacts))
    )
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    return CompanyOut.model_validate(company)


# ── PUT /companies/{id} ───────────────────────────────────────────────────────

@router.put("/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyOut:
    """
    Analyst correction endpoint.

    Only fields included in the payload (non-None) are applied.
    This allows analysts to correct misclassified ownership types, update
    employee counts, or manually exclude/include a company without a full PUT.
    """
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(selectinload(Company.contacts))
    )
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # Apply only the fields the caller provided
    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(company, field, value)

    await db.commit()
    await db.refresh(company)

    return CompanyOut.model_validate(company)
