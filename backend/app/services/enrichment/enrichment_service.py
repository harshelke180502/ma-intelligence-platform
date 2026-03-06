"""
Enrichment service orchestrator.

enrich_company() drives the full per-company enrichment pipeline:

  Stage 1 — Website discovery   (DuckDuckGo search, only if company.website is null)
  Stage 2 — Website scraping    (fetches homepage text via httpx + BeautifulSoup)
  Stage 3 — Employee estimation (regex extraction from scraped text)
  Stage 4 — Ownership classification (keyword matching from scraped text)
  Stage 5 — Revenue estimation  (derived from employee count, $200k/employee ±30%)

Guarding principles:
  - Existing non-null values are NEVER overwritten.  Analyst corrections
    and collector data take precedence over inferred values.
  - ownership_type is only updated when still at the pipeline default
    ("private") — so a PE-backed company already classified is not reset.
  - Each stage is individually guarded with try/except so one failure
    does not abort the remaining stages.
  - The session is committed once at the end.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.services.enrichment.employee_estimator import estimate_employees
from app.services.enrichment.ownership_classifier import classify_ownership
from app.services.enrichment.revenue_estimator import estimate_revenue
from app.services.enrichment.website_finder import find_company_website
from app.services.enrichment.website_scraper import scrape_website_text

logger = logging.getLogger(__name__)


async def enrich_company(company: Company, db: AsyncSession) -> None:
    """
    Run the full enrichment pipeline for a single company and persist.

    Args:
        company: ORM instance already bound to `db`.  Modified in-place.
        db:      AsyncSession — commit is called once at the end of this
                 function.  The caller should NOT commit afterwards.

    Post-condition:
        company fields are updated where enrichment found new data.
        All changes are committed and the instance is refreshed.
    """
    logger.info("enrich_company: start  id=%s  name=%r", company.id, company.name)

    # ── Stage 1: Website discovery ────────────────────────────────────────────
    if not company.website:
        try:
            found = await find_company_website(
                company_name=company.name,
                state=company.state or "",
            )
            if found:
                company.website = found
                logger.info("website found → %s", found)
        except Exception as exc:
            logger.warning(
                "enrich_company: website_finder failed for %s: %s", company.id, exc
            )

    # ── Stage 2: Website scraping ─────────────────────────────────────────────
    text: str | None = None
    if company.website:
        try:
            text = await scrape_website_text(company.website)
            logger.info("scraped text length → %s", len(text) if text else 0)
        except Exception as exc:
            logger.warning(
                "enrich_company: scraper failed for %s (%s): %s",
                company.id, company.website, exc,
            )

    # ── Stage 3: Employee estimation ──────────────────────────────────────────
    employees: int | None = None
    if text and company.employee_count is None:
        try:
            employees = estimate_employees(text)
            if employees is not None:
                company.employee_count = employees
                logger.info("employees detected → %s", employees)
        except Exception as exc:
            logger.warning(
                "enrich_company: employee_estimator failed for %s: %s", company.id, exc
            )

    # ── Stage 4: Ownership classification ────────────────────────────────────
    if text and company.ownership_type in (None, "private"):
        try:
            ownership = classify_ownership(text)
            if ownership != "private":
                company.ownership_type = ownership
                logger.info("ownership detected → %s", ownership)
        except Exception as exc:
            logger.warning(
                "enrich_company: ownership_classifier failed for %s: %s", company.id, exc
            )

    # ── Stage 5: Revenue estimation ───────────────────────────────────────────
    effective_employees = employees or company.employee_count
    if effective_employees is not None:
        try:
            rev_min, rev_max = estimate_revenue(effective_employees)
            if rev_min is not None and (
                company.revenue_est_min is None
                or company.revenue_est_min < 5000
            ):
                company.revenue_est_min = rev_min
                company.revenue_est_max = rev_max
                logger.info("revenue estimate → %s-%s", rev_min, rev_max)
        except Exception as exc:
            logger.warning(
                "enrich_company: revenue_estimator failed for %s: %s", company.id, exc
            )

    # ── Persist ───────────────────────────────────────────────────────────────
    await db.commit()
    await db.refresh(company)

    logger.info(
        "enrich_company: done  id=%s  website=%s  employees=%s  ownership=%s  "
        "rev_min=%s  rev_max=%s",
        company.id,
        company.website,
        company.employee_count,
        company.ownership_type,
        company.revenue_est_min,
        company.revenue_est_max,
    )
