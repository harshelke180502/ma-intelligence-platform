"""
Enrichment service orchestrator.

enrich_company() drives the full per-company enrichment pipeline:

  Stage 1 — Website discovery        (Brave search, only if website is null)
  Stage 2 — Website scraping         (fetches homepage text via httpx + BS4)
  Stage 3 — Employee estimation      (regex extraction from scraped text)
  Stage 4 — Ownership classification (keyword matching from scraped text)
  Stage 5 — Revenue from employees   ($200k/employee ±30%, highest confidence)
  Stage 6 — Revenue from ownership   (ownership-tier ranges, fallback when no
                                       employee count is available)
  Stage 7 — Thesis fit score         (GPT-4o-mini, 0.0–1.0 acquisition fit)

Revenue confidence tiers (highest → lowest):
  1. Employee-derived  — $200k × headcount ± 30%
  2. Ownership-derived — broad tier ranges per ownership type
  3. Pipeline default  — $3M–$10M set by normalizer on ingestion

The ownership-derived ranges reflect typical deal sizes for this thesis:
  pe_backed → $15M–$150M   (PE acquires mid-market companies)
  public    → $50M–$500M
  franchise → $5M–$50M
  private   → stays at pipeline default ($3M–$10M); too broad to improve
               without headcount data

Guarding principles:
  - Employee-derived revenue ALWAYS wins over ownership-derived.
  - Ownership-derived revenue replaces the pipeline default (≤$10M min)
    but never overwrites a previously enriched value.
  - Analyst corrections (any value > pipeline default) are never touched.
  - Each stage is individually guarded with try/except.
  - One commit at the end.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.services.enrichment.employee_estimator import estimate_employees
from app.services.enrichment.ownership_classifier import classify_ownership
from app.services.enrichment.revenue_estimator import estimate_revenue
from app.services.enrichment.thesis_scorer import score_thesis_fit
from app.services.enrichment.website_finder import find_company_website
from app.services.enrichment.website_scraper import scrape_website_text

logger = logging.getLogger(__name__)

# Ownership-based revenue ranges (thousands USD) used when no employee count
# is available.  Midpoints reflect typical acquisition target sizes.
_OWNERSHIP_REVENUE: dict[str, tuple[int, int]] = {
    "pe_backed": (15_000, 150_000),   # $15M – $150M
    "public":    (50_000, 500_000),   # $50M – $500M
    "franchise": (5_000,  50_000),    # $5M  – $50M
    # "private" intentionally omitted — pipeline default ($3M–$10M) is fine
}

# Revenue values at or below this threshold are treated as the pipeline
# default and are eligible to be replaced by enrichment estimates.
_PIPELINE_DEFAULT_MAX = 10_000   # $10M (the normalizer sets rev_max = 10_000)


async def enrich_company(company: Company, db: AsyncSession) -> None:
    """
    Run the full enrichment pipeline for a single company and persist.

    Args:
        company: ORM instance already bound to `db`.  Modified in-place.
        db:      AsyncSession — commit is called once at the end of this
                 function.  The caller should NOT commit afterwards.
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

    # ── Stage 5: Revenue from employee count (highest confidence) ────────────
    # Uses $200k/employee ±30%.  Overwrites pipeline default and any prior
    # ownership-derived estimate because headcount is more precise.
    effective_employees = employees or company.employee_count
    if effective_employees is not None:
        try:
            rev_min, rev_max = estimate_revenue(effective_employees)
            if rev_min is not None and _is_pipeline_default(company):
                company.revenue_est_min = rev_min
                company.revenue_est_max = rev_max
                logger.info(
                    "revenue from employees → $%sK–$%sK  (%d employees)",
                    rev_min, rev_max, effective_employees,
                )
        except Exception as exc:
            logger.warning(
                "enrich_company: revenue_estimator failed for %s: %s", company.id, exc
            )

    # ── Stage 6: Revenue from ownership type (fallback) ───────────────────────
    # Applies only when employee-based revenue was not set AND the company
    # still holds the pipeline default.  Gives a much better range for
    # PE-backed, public, and franchise companies without scrape data.
    if _is_pipeline_default(company) and company.ownership_type in _OWNERSHIP_REVENUE:
        rev_min, rev_max = _OWNERSHIP_REVENUE[company.ownership_type]
        company.revenue_est_min = rev_min
        company.revenue_est_max = rev_max
        logger.info(
            "revenue from ownership (%s) → $%sK–$%sK",
            company.ownership_type, rev_min, rev_max,
        )

    # ── Stage 7: Thesis fit score (GPT-4o-mini) ───────────────────────────────
    try:
        score = await score_thesis_fit(
            name=company.name,
            state=company.state,
            services=company.services or [],
            ownership_type=company.ownership_type,
            revenue_est_min=company.revenue_est_min,
            revenue_est_max=company.revenue_est_max,
            employee_count=company.employee_count,
            website_text=text,
        )
        if score is not None:
            company.thesis_fit_score = score
            logger.info("thesis_fit_score → %.2f", score)
    except Exception as exc:
        logger.warning(
            "enrich_company: thesis_scorer failed for %s: %s", company.id, exc
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_pipeline_default(company: Company) -> bool:
    """
    Return True if the company's revenue is still at the pipeline-ingestion
    default (rev_max ≤ $10M) or is unset — i.e., no enrichment has improved
    it yet.  Analyst corrections above $10M are never overwritten.
    """
    if company.revenue_est_min is None:
        return True
    return (company.revenue_est_max or 0) <= _PIPELINE_DEFAULT_MAX
