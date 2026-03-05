"""
Deduplicator: NormalizedCompanyInput → companies table (upsert).

upsert_company() uses a single PostgreSQL INSERT ... ON CONFLICT DO UPDATE
to atomically insert or merge a company record.  No SELECT-then-INSERT
pattern — the entire operation is one SQL statement, safe under concurrency.

Deduplication anchor: UNIQUE (name, state)
  Two records with the same company name in the same state are treated as
  the same entity and merged, regardless of which collector surfaced them.

Conflict resolution:
  ┌─────────────────┬──────────────────────────────────────────────────────┐
  │ Field           │ Strategy                                             │
  ├─────────────────┼──────────────────────────────────────────────────────┤
  │ city            │ COALESCE(existing, incoming) — non-null wins         │
  │ website         │ COALESCE(existing, incoming)                         │
  │ services        │ JSONB array union — deduplicated via array_agg       │
  │ ownership_type  │ COALESCE(existing, incoming) — real data over default│
  │ revenue_est_min │ COALESCE(existing, incoming) — real data over default│
  │ revenue_est_max │ COALESCE(existing, incoming) — real data over default│
  │ primary_source  │ NOT updated — first-seen source wins                 │
  │ updated_at      │ Always refreshed to NOW()                            │
  └─────────────────┴──────────────────────────────────────────────────────┘

Does NOT commit.  The orchestrator owns the transaction and calls
db.commit() after all records for a pipeline run have been flushed.
"""

import logging
import uuid

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.pipeline.schemas import NormalizedCompanyInput

logger = logging.getLogger(__name__)

# ── JSONB array union SQL fragment ────────────────────────────────────────────
#
# Merges two JSONB string arrays and deduplicates the result.
#
#   jsonb_array_elements_text() — unnests both arrays into individual text rows
#   array_agg(DISTINCT val)     — collects unique values (order is non-deterministic
#                                 but stable across upserts)
#   to_jsonb(...)               — converts the text[] back to a JSONB array
#   outer COALESCE              — guards against the NULL returned by array_agg
#                                 on an empty input (both arrays were [])
#
# The table name "companies" and pseudo-table "excluded" are PostgreSQL
# keywords within the ON CONFLICT DO UPDATE context — not hardcoded strings.
_SERVICES_UNION_SQL = text(
    "COALESCE("
    "  (SELECT to_jsonb(array_agg(DISTINCT val))"
    "   FROM jsonb_array_elements_text("
    "     COALESCE(companies.services, '[]'::jsonb) ||"
    "     COALESCE(excluded.services,  '[]'::jsonb)"
    "   ) AS t(val)),"
    "  '[]'::jsonb"
    ")"
)


async def upsert_company(
    db: AsyncSession,
    normalized: NormalizedCompanyInput,
) -> None:
    """
    Persist a normalized company record via INSERT ... ON CONFLICT DO UPDATE.

    Args:
        db:         AsyncSession owned by the orchestrator.  Only flush()
                    is called here; commit() is the caller's responsibility.
        normalized: A NormalizedCompanyInput with services already populated
                    by classify_services().

    The generated SQL is equivalent to:

        INSERT INTO companies (id, name, city, state, website, services, primary_source)
        VALUES (:id, :name, :city, :state, :website, :services, :primary_source)
        ON CONFLICT (name, state)
        DO UPDATE SET
            city       = COALESCE(excluded.city,    companies.city),
            website    = COALESCE(excluded.website, companies.website),
            services   = <JSONB union subquery>,
            updated_at = NOW();
    """
    values = {
        "id": uuid.uuid4(),
        "name": normalized.name,
        "city": normalized.city,
        "state": normalized.state,
        "website": normalized.website,
        "services": normalized.services,
        "primary_source": normalized.primary_source,
        "ownership_type": normalized.ownership_type,
        "revenue_est_min": normalized.revenue_est_min,
        "revenue_est_max": normalized.revenue_est_max,
    }

    stmt = pg_insert(Company).values(**values)

    # tbl — shorthand reference to existing table columns inside set_
    tbl = Company.__table__.c

    stmt = stmt.on_conflict_do_update(
        index_elements=["name", "state"],
        set_={
            # Scalar fields: prefer incoming non-null; keep existing if null
            "city":     func.coalesce(stmt.excluded.city,    tbl.city),
            "website":  func.coalesce(stmt.excluded.website, tbl.website),
            # JSONB union: accumulate service tags from all collectors
            "services": _SERVICES_UNION_SQL,
            # Prefer existing real data over incoming default ("private").
            # If an analyst has already set a known ownership type, keep it.
            "ownership_type":  func.coalesce(tbl.ownership_type,  stmt.excluded.ownership_type),
            # Prefer existing revenue estimates; fall back to thesis defaults.
            "revenue_est_min": func.coalesce(tbl.revenue_est_min, stmt.excluded.revenue_est_min),
            "revenue_est_max": func.coalesce(tbl.revenue_est_max, stmt.excluded.revenue_est_max),
            # Always reflect when this company record was last touched
            "updated_at": func.now(),
            # primary_source intentionally absent — first-seen source is kept
        },
    )

    logger.debug(
        "upsert_company: name=%r state=%r services=%r source=%r",
        normalized.name, normalized.state, normalized.services, normalized.primary_source,
    )

    await db.execute(stmt)
    await db.flush()
