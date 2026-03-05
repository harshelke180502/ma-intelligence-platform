"""
Normalizer: raw_record → NormalizedCompanyInput.

Responsibilities:
  - Strip pipeline metadata (keys prefixed with "_")
  - Navigate the source-specific payload shape to extract known fields
  - Parse city and state from Google Places formatted_address
  - Reduce website URLs to root domain only
  - Return a source-agnostic NormalizedCompanyInput with services = []

Does NOT classify services, deduplicate, or write to the database.
Raises ValueError for records that are structurally unprocessable
(e.g. missing company name), so the orchestrator can log and skip them
without crashing the pipeline.
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from app.models.raw_record import RawRecord
from app.pipeline.schemas import NormalizedCompanyInput

logger = logging.getLogger(__name__)

# Country tokens that appear at the end of Google formatted_address strings
_COUNTRY_TOKENS = frozenset({"usa", "united states", "united states of america"})


def normalize_place_record(raw_record: RawRecord) -> NormalizedCompanyInput:
    """
    Normalise a Google Places raw_record into a NormalizedCompanyInput.

    Payload shape expected (written by GooglePlacesCollector):
        {
          "place": { "name": "...", "formatted_address": "...", ... },
          "_meta": { "run_id": "...", "state_code": "TX", ... }
        }

    The "_meta" block and any other "_"-prefixed keys are stripped first.
    The remaining top-level keys are inspected; if a "place" key exists
    (Google Places shape), its value is used as the data dict.

    Raises:
        ValueError — if the record has no extractable company name.
    """
    payload: dict = raw_record.raw_payload

    # ── Strip metadata keys ────────────────────────────────────────────────────
    # Keys starting with "_" are pipeline metadata, not source data.
    source_data = {k: v for k, v in payload.items() if not k.startswith("_")}

    # ── Navigate source-specific nesting ──────────────────────────────────────
    # Google Places collector nests the API result under "place".
    # Other future collectors may use a flat dict — handled by the fallback.
    if "place" in source_data and isinstance(source_data["place"], dict):
        place: dict = source_data["place"]
    else:
        place = source_data

    # ── Extract required field ─────────────────────────────────────────────────
    name: str = (place.get("name") or "").strip()
    if not name:
        raise ValueError(
            f"raw_record {raw_record.id} ({raw_record.source_name}): "
            "payload has no extractable company name — skipping"
        )

    # ── Extract optional fields ────────────────────────────────────────────────
    city, state = _parse_address(place.get("formatted_address") or "")
    website = _extract_domain(place.get("website") or "")

    return NormalizedCompanyInput(
        name=name,
        city=city,
        state=state,
        website=website,
        services=[],                        # classifier fills this next
        primary_source=raw_record.source_name,
    )


# ── Address parsing ────────────────────────────────────────────────────────────

def _parse_address(formatted_address: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract (city, state) from a Google Places formatted_address string.

    Google's format:  "STREET, CITY, STATE ZIP, COUNTRY"
    Examples:
      "123 Main St, Austin, TX 78701, USA"         → ("Austin", "TX")
      "456 Park Ave, New York, NY 10001, USA"       → ("New York", "TX")
      "Washington, DC 20001, USA"                   → ("Washington", "DC")
      "Austin, TX, USA"                             → ("Austin", "TX")

    Strategy:
      1. Split on commas, strip each part.
      2. Drop the trailing country token.
      3. The last remaining part holds "STATE [ZIP]" — extract the state code.
      4. The second-to-last remaining part is the city.
    """
    if not formatted_address:
        return None, None

    parts = [p.strip() for p in formatted_address.split(",")]

    # Drop trailing country token ("USA", "United States", etc.)
    if parts and parts[-1].strip().lower() in _COUNTRY_TOKENS:
        parts = parts[:-1]

    if not parts:
        return None, None

    state = _extract_state_code(parts[-1])
    city = parts[-2].strip() if len(parts) >= 2 else None

    return city, state


def _extract_state_code(text: str) -> Optional[str]:
    """
    Return the first 2-char uppercase USPS state code found at the start
    of a string like "TX 78701", "TX", or "NY 10001".
    """
    match = re.match(r"^([A-Z]{2})\b", text.strip())
    return match.group(1) if match else None


# ── Website normalisation ──────────────────────────────────────────────────────

def _extract_domain(url: str) -> Optional[str]:
    """
    Reduce a URL to its root domain, stripping scheme and www prefix.

    Examples:
      "https://www.acmetax.com/services/"  →  "acmetax.com"
      "http://costseg.com"                 →  "costseg.com"
      "wotcservices.net"                   →  "wotcservices.net"
    """
    if not url:
        return None
    try:
        if "://" not in url:
            url = f"https://{url}"
        netloc: str = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or None
    except Exception:
        logger.debug("_extract_domain: could not parse %r", url)
        return None
