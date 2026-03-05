"""
Pipeline orchestrator.

run_pipeline() is the single entry point for a full data collection run.
It drives every stage in sequence:

  1. Create PipelineRun (status="running")
  2. Run collectors concurrently via asyncio.gather()
       → raw_records flushed to DB (processed=False)
  3. Load all unprocessed raw_records
  4. For each record: normalize → classify → upsert → mark processed
  5. Compute metrics (companies_added, duplicates_found)
  6. Finalise PipelineRun (status="completed" or "failed")
  7. Single db.commit()

Error isolation:
  - A collector failure is logged and added to PipelineRun.errors;
    remaining collectors continue (return_exceptions=True in gather).
  - A per-record processing failure is logged and added to errors;
    remaining records continue (try/except inside the loop).
  - An unrecoverable exception in the orchestration logic itself marks
    the run as "failed" but still commits the PipelineRun record so the
    failure is visible in GET /pipeline/runs.

Session ownership:
  - The db session is passed in from the route handler (via get_db()).
  - Only this function calls db.commit() — collectors and deduplicator
    only flush().
  - NOTE: AsyncSession is not safe for concurrent access.  With a single
    collector the gather is effectively sequential.  When additional
    collectors are introduced, each must receive its own AsyncSession.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.company import Company
from app.models.pipeline_run import PipelineRun
from app.models.raw_record import RawRecord
from app.pipeline.classifier import classify_services
from app.pipeline.collectors.base import CollectorResult
from app.pipeline.collectors.google_places import CONTINENTAL_STATES, GooglePlacesCollector
from app.pipeline.deduplicator import upsert_company
from app.pipeline.normalizer import normalize_place_record

logger = logging.getLogger(__name__)

# ── Default thesis parameters ─────────────────────────────────────────────────
# Hardcoded for V1 — a future increment will read these from the Thesis model
# when a thesis_id is passed to run_pipeline().
_DEFAULT_SERVICES: list[str] = ["rd_credits", "cost_seg", "wotc", "sales_use_tax"]
_DEFAULT_STATES: list[str] = list(CONTINENTAL_STATES.keys())  # 49 states + DC


def _ts() -> str:
    """ISO-8601 UTC timestamp string for error log entries."""
    return datetime.now(timezone.utc).isoformat()


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_pipeline(db: AsyncSession) -> PipelineRun:
    """
    Execute a full pipeline run and return the finalised PipelineRun record.

    The caller is responsible for providing a valid AsyncSession.
    This function commits the session exactly once, at the end.
    """

    # ── 1. Create PipelineRun ─────────────────────────────────────────────────
    run = PipelineRun(status="running")
    db.add(run)
    await db.flush()   # populate run.id without committing
    logger.info("Pipeline started  run_id=%s", run.id)

    errors: list[dict] = []

    try:
        # ── 2. Run collectors ─────────────────────────────────────────────────
        errors = await _run_collectors(run, db)

        # ── 3. Load unprocessed raw_records ───────────────────────────────────
        raw_records = (
            await db.execute(
                select(RawRecord).where(RawRecord.processed.is_(False))
            )
        ).scalars().all()

        logger.info("Normalization phase: %d raw records to process", len(raw_records))

        # Snapshot company count before upserts to compute companies_added
        before_count: int = (
            await db.scalar(select(func.count()).select_from(Company))
        ) or 0

        # ── 4. Normalize → classify → upsert each record ──────────────────────
        successful_upserts = 0

        for raw_record in raw_records:
            try:
                normalized = normalize_place_record(raw_record)
                normalized.services = classify_services(
                    normalized, raw_record.raw_payload
                )
                await upsert_company(db, normalized)
                raw_record.processed = True
                successful_upserts += 1

            except Exception as exc:
                logger.warning(
                    "Skipping raw_record %s (%s): %s",
                    raw_record.id, raw_record.source_name, exc,
                )
                errors.append({
                    "stage": "normalization",
                    "raw_record_id": str(raw_record.id),
                    "source": raw_record.source_name,
                    "error": str(exc),
                    "at": _ts(),
                })

        await db.flush()

        # ── 5. Compute metrics ────────────────────────────────────────────────
        after_count: int = (
            await db.scalar(select(func.count()).select_from(Company))
        ) or 0

        companies_added = after_count - before_count
        # Upserts that hit ON CONFLICT are duplicates (merged, not inserted)
        duplicates_found = max(0, successful_upserts - companies_added)

        # ── 6. Mark run complete ──────────────────────────────────────────────
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.companies_added = companies_added
        run.duplicates_found = duplicates_found
        run.errors = errors

        logger.info(
            "Pipeline complete  run_id=%s  companies_added=%d  "
            "duplicates=%d  errors=%d",
            run.id, companies_added, duplicates_found, len(errors),
        )

    except Exception as exc:
        # Unrecoverable orchestration failure — mark run failed so the
        # error is visible in GET /pipeline/runs without crashing the process.
        logger.error("Pipeline fatal error  run_id=%s: %s", run.id, exc, exc_info=True)
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.errors = errors + [{"stage": "orchestrator", "error": str(exc), "at": _ts()}]

    # ── 7. Single commit ──────────────────────────────────────────────────────
    await db.commit()
    await db.refresh(run)
    return run


# ── Collector phase ───────────────────────────────────────────────────────────

async def _run_collectors(run: PipelineRun, db: AsyncSession) -> list[dict]:
    """
    Instantiate collectors and run them via asyncio.gather().

    Returns a flat list of error dicts from all collector results.
    Collector-level exceptions are caught (return_exceptions=True) and
    recorded without aborting other collectors.
    """
    errors: list[dict] = []

    async with httpx.AsyncClient(
        timeout=float(settings.COLLECTOR_TIMEOUT_SECONDS)
    ) as client:
        collector = GooglePlacesCollector(
            api_key=settings.GOOGLE_PLACES_API_KEY or "",
            client=client,
        )

        outputs = await asyncio.gather(
            collector.collect(
                services=_DEFAULT_SERVICES,
                states=_DEFAULT_STATES,
                run_id=run.id,
                db=db,
            ),
            return_exceptions=True,
        )

    total_written = 0
    for output in outputs:
        if isinstance(output, Exception):
            logger.error("Collector raised an exception: %s", output)
            errors.append({
                "stage": "collection",
                "collector": "google_places",
                "error": str(output),
                "at": _ts(),
            })
        elif isinstance(output, CollectorResult):
            total_written += output.records_written
            errors.extend(output.errors)

    logger.info("Collection phase complete: %d raw records written", total_written)
    return errors
