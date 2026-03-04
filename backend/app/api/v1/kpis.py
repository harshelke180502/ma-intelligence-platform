"""
KPI aggregation route.

GET /kpis returns all dashboard KPI values in a single payload computed
with one SQL query (plus one GROUP BY query for state breakdown).

Design: PostgreSQL's FILTER clause allows conditional aggregation in a
single scan of the companies table.  This avoids 6+ round-trips for
individual counts and is the correct SQL approach for this pattern.

  SELECT
    COUNT(*) FILTER (WHERE is_excluded = FALSE)                      AS total,
    COUNT(*) FILTER (WHERE is_excluded = FALSE AND services @> ...) AS rd_credits,
    ...
    AVG(...) FILTER (WHERE is_excluded = FALSE AND revenue IS NOT NULL) AS avg_rev
  FROM companies;
"""

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import cast, desc, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.company import Company
from app.models.pipeline_run import PipelineRun
from app.schemas.kpi import KPIResponse, ServiceBreakdown, StateCount

router = APIRouter(prefix="/kpis", tags=["kpis"])


def _svc(key: str) -> Any:
    """
    Returns a JSONB containment condition: services @> CAST('["key"]' AS JSONB).

    Used inside FILTER clauses to count companies offering a specific service.
    The GIN index on companies.services makes each @> evaluation O(log n).
    """
    return Company.services.op("@>")(cast(json.dumps([key]), JSONB))


# ── GET /kpis ─────────────────────────────────────────────────────────────────

@router.get("", response_model=KPIResponse)
async def get_kpis(db: AsyncSession = Depends(get_db)) -> KPIResponse:
    """
    All dashboard KPI values in a single response.

    Two DB queries total:
      1. Aggregation query — total, per-service counts, ownership %, avg revenue
      2. State breakdown — GROUP BY state for the choropleth map

    The heavy aggregation uses PostgreSQL FILTER to compute all counters
    in one table scan rather than issuing a separate query per metric.
    """
    from sqlalchemy import and_

    active = Company.is_excluded.is_(False)

    # ── Query 1: all scalar KPIs in one table scan ────────────────────────────
    agg_stmt = select(
        # Total active companies
        func.count().filter(active).label("total"),

        # Per-service counts — NOT mutually exclusive; a company offering
        # both R&D Credits and WOTC increments both counters.
        func.count().filter(and_(active, _svc("rd_credits"))).label("rd_credits"),
        func.count().filter(and_(active, _svc("cost_seg"))).label("cost_seg"),
        func.count().filter(and_(active, _svc("wotc"))).label("wotc"),
        func.count().filter(and_(active, _svc("sales_use_tax"))).label("sales_use_tax"),

        # Excluded companies count (for the "companies excluded" KPI card)
        func.count().filter(Company.is_excluded.is_(True)).label("excluded"),

        # Ownership identified: not NULL and not 'unknown'
        func.count().filter(
            and_(
                active,
                Company.ownership_type.isnot(None),
                Company.ownership_type != "unknown",
            )
        ).label("ownership_known"),

        # Average revenue — midpoint of (min + max) range, in thousands USD.
        # Only computed for rows where both bounds are available.
        func.avg(
            (Company.revenue_est_min + Company.revenue_est_max) / 2.0
        ).filter(
            and_(
                active,
                Company.revenue_est_min.isnot(None),
                Company.revenue_est_max.isnot(None),
            )
        ).label("avg_revenue"),
    )

    agg_row = (await db.execute(agg_stmt)).one()

    # ── Query 2: state breakdown (requires GROUP BY) ──────────────────────────
    state_stmt = (
        select(Company.state, func.count().label("count"))
        .where(Company.is_excluded.is_(False), Company.state.isnot(None))
        .group_by(Company.state)
        .order_by(desc("count"))
    )
    state_rows = (await db.execute(state_stmt)).all()

    # ── Query 3: last completed pipeline run ──────────────────────────────────
    last_run_at: Optional[datetime] = await db.scalar(
        select(PipelineRun.completed_at)
        .where(PipelineRun.status == "completed")
        .order_by(desc(PipelineRun.completed_at))
        .limit(1)
    )

    # ── Compute derived metrics ───────────────────────────────────────────────
    total = agg_row.total or 0
    pct_ownership = (
        round((agg_row.ownership_known / total) * 100, 1) if total > 0 else 0.0
    )

    return KPIResponse(
        total_companies=total,
        by_service=ServiceBreakdown(
            rd_credits=agg_row.rd_credits or 0,
            cost_seg=agg_row.cost_seg or 0,
            wotc=agg_row.wotc or 0,
            sales_use_tax=agg_row.sales_use_tax or 0,
        ),
        by_state=[
            StateCount(state=row.state, count=row.count) for row in state_rows
        ],
        pct_ownership_identified=pct_ownership,
        avg_revenue_est=(
            float(agg_row.avg_revenue) if agg_row.avg_revenue is not None else None
        ),
        companies_excluded=agg_row.excluded or 0,
        last_pipeline_run=last_run_at,
    )
