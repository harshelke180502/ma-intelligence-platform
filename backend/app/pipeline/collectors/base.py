"""
Base class and result type for all data collectors.

Every collector follows the same contract:
  - Accepts a list of service keys and state codes scoped by the active thesis
  - Writes raw payloads directly to raw_records (no normalization here)
  - Returns a CollectorResult summarising what was written and what failed
  - Is independently testable — the DB session and HTTP client are injected

The orchestrator calls collect() on each collector via asyncio.gather(),
then commits the session after all collectors have flushed their records.
Collectors must only flush(), never commit() — transaction ownership stays
with the orchestrator.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class CollectorResult:
    """
    Summary returned by every collector after a run.

    records_written — raw_records rows flushed to the session
    errors          — per-query failure dicts: {collector, query, error, at}
                      Non-fatal: a query can fail while the collector continues.
    """

    records_written: int = 0
    errors: list[dict] = field(default_factory=list)

    def merge(self, other: "CollectorResult") -> "CollectorResult":
        """Combine two results — used by the orchestrator to aggregate totals."""
        return CollectorResult(
            records_written=self.records_written + other.records_written,
            errors=self.errors + other.errors,
        )


class BaseCollector(ABC):
    """
    Abstract base for all data source collectors.

    Subclasses must:
      1. Set the class-level `source_name` constant — written into every
         raw_record.source_name so the normalizer knows the payload shape.
      2. Implement `collect()` according to the contract above.
    """

    # Must be overridden: identifies the collector in raw_records and error logs
    source_name: str

    @abstractmethod
    async def collect(
        self,
        services: list[str],
        states: list[str],
        run_id: UUID,
        db: AsyncSession,
    ) -> CollectorResult:
        """
        Fetch companies matching the given services and states.

        Writes raw payloads to raw_records via db.add() + db.flush().
        Does NOT normalise, classify, or deduplicate.
        Does NOT call db.commit() — that is the orchestrator's responsibility.

        Args:
            services: List of service keys from the active thesis,
                      e.g. ["rd_credits", "cost_seg"]
            states:   List of 2-char state codes to search within,
                      e.g. ["TX", "FL", "CA"]
            run_id:   UUID of the active PipelineRun — embedded in every
                      raw_payload._meta for provenance tracking.
            db:       AsyncSession owned by the orchestrator.

        Returns:
            CollectorResult with records_written count and any query errors.
        """
        ...
