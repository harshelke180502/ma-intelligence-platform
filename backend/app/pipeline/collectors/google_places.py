"""
Google Places Text Search collector.

Uses the Places Text Search API to find specialty tax firms by service
keyword + state name.  One API call per (keyword, state) pair, paginated
up to MAX_PAGES.

API reference:
  https://developers.google.com/maps/documentation/places/web-service/text-search

Raw payload shape written to raw_records:
  {
    "place":  { ...Google Places result object... },
    "_meta":  {
      "run_id":     "<uuid>",
      "query":      "cost segregation study consulting Texas",
      "state_code": "TX",
      "page":       0,
      "fetched_at": "2024-01-01T00:00:00Z"
    }
  }

The "_meta" prefix signals pipeline metadata vs source data throughout
the normalizer and enrichment layers.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.raw_record import RawRecord
from app.pipeline.collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)


# ── Domain exceptions ─────────────────────────────────────────────────────────

class PlacesRateLimitError(Exception):
    """Google Places returned OVER_QUERY_LIMIT.  Tenacity will retry."""


class PlacesAuthError(Exception):
    """API key was rejected (REQUEST_DENIED).  Fatal — do not retry."""


# ── Search vocabulary ─────────────────────────────────────────────────────────

# One search template per service key.  These are tuned to the specialty tax
# niche: general terms ("tax consulting") produce too much noise from CPA
# generalists; specific terms surface the target firms more precisely.
SERVICE_QUERIES: dict[str, str] = {
    "rd_credits":    "R&D tax credit consulting",
    "cost_seg":      "cost segregation study consulting",
    "wotc":          "work opportunity tax credit consulting",
    "sales_use_tax": "sales and use tax consulting",
}

# All 48 continental US states + DC.
# Alaska (AK) and Hawaii (HI) are excluded per thesis geography.
CONTINENTAL_STATES: dict[str, str] = {
    "AL": "Alabama",      "AZ": "Arizona",      "AR": "Arkansas",
    "CA": "California",   "CO": "Colorado",     "CT": "Connecticut",
    "DC": "Washington DC","DE": "Delaware",     "FL": "Florida",
    "GA": "Georgia",      "ID": "Idaho",        "IL": "Illinois",
    "IN": "Indiana",      "IA": "Iowa",         "KS": "Kansas",
    "KY": "Kentucky",     "LA": "Louisiana",    "ME": "Maine",
    "MD": "Maryland",     "MA": "Massachusetts","MI": "Michigan",
    "MN": "Minnesota",    "MS": "Mississippi",  "MO": "Missouri",
    "MT": "Montana",      "NE": "Nebraska",     "NV": "Nevada",
    "NH": "New Hampshire","NJ": "New Jersey",   "NM": "New Mexico",
    "NY": "New York",     "NC": "North Carolina","ND": "North Dakota",
    "OH": "Ohio",         "OK": "Oklahoma",     "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee",    "TX": "Texas",
    "UT": "Utah",         "VT": "Vermont",      "VA": "Virginia",
    "WA": "Washington",   "WV": "West Virginia","WI": "Wisconsin",
    "WY": "Wyoming",
}

# Google Places API statuses that are safe to return without retrying
_NON_RETRIABLE_STATUSES = frozenset({"OK", "ZERO_RESULTS", "INVALID_REQUEST", "NOT_FOUND"})


# ── Collector ─────────────────────────────────────────────────────────────────

class GooglePlacesCollector(BaseCollector):
    """
    Collects specialty tax firms from Google Places Text Search.

    Usage (orchestrator injects client and db):
        async with httpx.AsyncClient(timeout=settings.COLLECTOR_TIMEOUT_SECONDS) as client:
            collector = GooglePlacesCollector(
                api_key=settings.GOOGLE_PLACES_API_KEY,
                client=client,
            )
            result = await collector.collect(services, states, run_id, db)
    """

    source_name = "google_places"

    BASE_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    # Max pages per query: 3 pages × 20 results = 60 results per keyword+state.
    # Specialty tax is niche enough that the real universe is smaller than 60
    # per state, so this ceiling is unlikely to be hit in practice.
    MAX_PAGES = 3

    # Google requires a minimum 2-second delay before reusing a next_page_token.
    # Using 2.5s adds a small buffer for network latency.
    PAGE_TOKEN_DELAY = 2.5

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        """
        Args:
            api_key: Google Places API key (from settings.GOOGLE_PLACES_API_KEY).
            client:  Shared httpx.AsyncClient — injected so the orchestrator
                     controls the connection pool lifecycle.
        """
        if not api_key:
            raise ValueError(
                "GooglePlacesCollector requires a GOOGLE_PLACES_API_KEY. "
                "Set it in .env or pass it explicitly."
            )
        self.api_key = api_key
        self.client = client

    # ── Public interface ──────────────────────────────────────────────────────

    async def collect(
        self,
        services: list[str],
        states: list[str],
        run_id: UUID,
        db: AsyncSession,
    ) -> CollectorResult:
        """
        Run Text Search for every (service_keyword, state) combination.

        Each query is independent: a failure on one query is logged and the
        collector continues with remaining queries.  A PlacesAuthError (bad
        API key) is fatal and aborts all remaining queries immediately.

        Records are flushed to the DB session after each page to avoid
        accumulating a large in-memory transaction.  The orchestrator commits.
        """
        queries = self._build_queries(services, states)
        logger.info(
            "GooglePlacesCollector: %d queries for services=%s states_count=%d",
            len(queries), services, len(states),
        )

        result = CollectorResult()

        for service_key, query_str, state_code in queries:
            try:
                written = await self._collect_query(service_key, query_str, state_code, run_id, db)
                result.records_written += written
                if written:
                    logger.debug("  query=%r state=%s → %d records", query_str, state_code, written)

            except PlacesAuthError as exc:
                # Invalid API key — no point running more queries
                logger.error("GooglePlacesCollector: auth error — aborting: %s", exc)
                result.errors.append({
                    "collector": self.source_name,
                    "query": query_str,
                    "error": f"AUTH: {exc}",
                    "at": datetime.now(timezone.utc).isoformat(),
                })
                break

            except Exception as exc:
                # Per-query failure — log and continue
                logger.warning(
                    "GooglePlacesCollector: query failed (query=%r state=%s): %s",
                    query_str, state_code, exc,
                )
                result.errors.append({
                    "collector": self.source_name,
                    "query": query_str,
                    "state": state_code,
                    "error": str(exc),
                    "at": datetime.now(timezone.utc).isoformat(),
                })

        logger.info(
            "GooglePlacesCollector: finished — records_written=%d errors=%d",
            result.records_written, len(result.errors),
        )
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_queries(
    self, services: list[str], states: list[str]
) -> list[tuple[str, str, str]]:
        """
        Produce (query_string, state_code) pairs for every service × state.

        Unknown service keys are skipped with a warning (no KeyError).
        Unknown state codes are searched with the raw code as the location
        string (graceful degradation, not a crash).
        """
        pairs: list[tuple[str, str]] = []
        for svc in services:
            template = SERVICE_QUERIES.get(svc)
            if template is None:
                logger.warning("GooglePlacesCollector: no query template for service %r — skipping", svc)
                continue
            for state_code in states:
                state_name = CONTINENTAL_STATES.get(state_code, state_code)
                pairs.append((svc,f"{template} {state_name}", state_code))
        return pairs

    async def _collect_query(
        self,
        service_key: str,
        query_str: str,
        state_code: str,
        run_id: UUID,
        db: AsyncSession,
    ) -> int:
        """
        Paginate through Text Search results for a single query string.

        Writes one raw_record per Google Places result.  Flushes after
        each page so the session doesn't accumulate unbounded writes.

        Returns the total number of raw_records written for this query.
        """
        page_token: str | None = None
        page_num = 0
        written = 0

        while page_num < self.MAX_PAGES:
            # Google Places requires a pause before reusing next_page_token
            if page_token is not None:
                await asyncio.sleep(self.PAGE_TOKEN_DELAY)

            data = await self._fetch_page(query_str, page_token)
            results: list[dict] = data.get("results", [])

            for place in results:
                db.add(
                    RawRecord(
                        source_name=self.source_name,
                        raw_payload={
                            "place": place,
                            "_meta": {
                                "run_id": str(run_id),
                                "service": service_key,
                                "query": query_str,
                                "state_code": state_code,
                                "page": page_num,
                                "fetched_at": datetime.now(timezone.utc).isoformat(),
                            },
                        },
                    )
                )
                written += 1

            # Flush each page (up to 20 records) to the session.
            # Keeps the in-memory transaction small; orchestrator commits later.
            if results:
                await db.flush()

            page_token = data.get("next_page_token")
            if not page_token:
                break

            page_num += 1

        return written

    @retry(
        # Retry up to COLLECTOR_MAX_RETRIES times (default: 3)
        stop=stop_after_attempt(settings.COLLECTOR_MAX_RETRIES),
        # Exponential backoff: 2s, 4s, 8s (caps at 10s)
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Retry on transient HTTP errors, timeouts, and rate limits.
        # PlacesAuthError is NOT here — a bad key won't fix itself on retry.
        retry=retry_if_exception_type(
            (httpx.HTTPStatusError, httpx.TimeoutException, PlacesRateLimitError)
        ),
        reraise=True,  # re-raise the last exception after exhausting retries
    )
    async def _fetch_page(
        self,
        query: str,
        page_token: str | None,
    ) -> dict:
        """
        Make one GET request to the Places Text Search API.

        Raises:
            PlacesRateLimitError  — OVER_QUERY_LIMIT (tenacity will retry)
            PlacesAuthError       — REQUEST_DENIED (fatal, do not retry)
            httpx.HTTPStatusError — HTTP 4xx/5xx (tenacity will retry)
            httpx.TimeoutException — request timed out (tenacity will retry)
        """
        params: dict = {"query": query, "key": self.api_key}
        if page_token is not None:
            params["pagetoken"] = page_token

        response = await self.client.get(self.BASE_URL, params=params)
        response.raise_for_status()  # raises HTTPStatusError on 4xx/5xx

        data: dict = response.json()
        api_status: str = data.get("status", "")

        if api_status == "OVER_QUERY_LIMIT":
            raise PlacesRateLimitError(
                data.get("error_message", "Daily quota exceeded")
            )

        if api_status == "REQUEST_DENIED":
            # Fail immediately — retrying with the same key achieves nothing
            raise PlacesAuthError(
                data.get("error_message", "API key rejected by Google Places")
            )

        if api_status not in _NON_RETRIABLE_STATUSES:
            # Unexpected status — log and return empty results rather than crash
            logger.warning(
                "GooglePlacesCollector: unexpected API status %r for query %r",
                api_status, query,
            )

        return data
