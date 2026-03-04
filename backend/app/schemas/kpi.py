"""
KPI response schemas.

GET /kpis returns a single KPIResponse object computed in one SQL round-trip
using PostgreSQL FILTER aggregation.  The frontend renders this as the KPI
card row and as chart data.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ServiceBreakdown(BaseModel):
    """
    Company count per qualifying service type.

    A company with both R&D Credits and WOTC increments both counters —
    counts are not mutually exclusive.
    """

    rd_credits: int = 0
    cost_seg: int = 0
    wotc: int = 0
    sales_use_tax: int = 0


class StateCount(BaseModel):
    """Company count for a single US state."""

    state: str
    count: int


class KPIResponse(BaseModel):
    """
    All dashboard KPI values in a single payload.

    Designed for one API call on page load — the frontend renders
    all six KPI cards and the chart data from this single response.

    Revenue values are in thousands USD to match the database storage format.
    The frontend is responsible for formatting (e.g., $8,400K → $8.4M).
    """

    total_companies: int
    by_service: ServiceBreakdown
    by_state: list[StateCount]          # ordered by count desc
    pct_ownership_identified: float     # 0.0–100.0, % where ownership != unknown/null
    avg_revenue_est: Optional[float]    # midpoint average in thousands USD; null if no data
    companies_excluded: int             # count of is_excluded=TRUE rows
    last_pipeline_run: Optional[datetime]  # completed_at of most recent successful run
