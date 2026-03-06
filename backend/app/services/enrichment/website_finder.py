"""
Website finder.

Uses Brave Search HTML to find a company's official website domain.
Brave returns static HTML with direct URLs — no JavaScript rendering,
no redirect wrapping, no API key required.

Public interface:
    async def find_company_website(company_name, state) -> Optional[str]
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse, quote_plus

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BLOCKED_KEYWORDS = (
    "linkedin",
    "facebook",
    "yelp",
    "mapquest",
    "google",
    "wikipedia",
    "yellowpages",
    "bbb.org",
    "manta.com",
    "zoominfo",
    "dnb.com",
    "crunchbase",
    "brave.com",
)

_VALID_TLDS = re.compile(r"\.(com|net|org|io|co|us|biz|info|tax|cpa)$", re.IGNORECASE)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


async def find_company_website(company_name: str, state: str) -> Optional[str]:
    """
    Return the root domain of a company's official website via Brave Search.

    Args:
        company_name: Trading name, e.g. "Acme Tax Advisors"
        state:        2-char USPS code, e.g. "TX"

    Returns:
        Root domain without scheme or www, e.g. "acmetax.com", or None.
    """
    query = quote_plus(f"{company_name} {state} official website")

    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=15,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                f"https://search.brave.com/search?q={query}",
            )

        if response.status_code != 200:
            logger.warning(
                "website_finder: Brave returned HTTP %s for %r",
                response.status_code, company_name,
            )
            return None

        soup = BeautifulSoup(response.text, "lxml")
        # Brave result links are direct URLs inside div.snippet
        links = soup.select("div.snippet a[href^='http']")
        logger.debug("website_finder: %d links for %r", len(links), company_name)

        seen: set[str] = set()
        for tag in links:
            href = tag.get("href", "")
            domain = _extract_domain(href)
            if domain and domain not in seen and _is_acceptable(domain):
                logger.info("website_finder: %r → %r", company_name, domain)
                return domain
            if domain:
                seen.add(domain)

        logger.info("website_finder: no acceptable domain found for %r", company_name)

    except Exception as exc:
        logger.warning(
            "website_finder: %s for %r: %s",
            type(exc).__name__, company_name, exc,
        )

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> Optional[str]:
    """Strip scheme, www, and path — return bare domain e.g. 'bonadio.com'."""
    if not url:
        return None
    try:
        if "://" not in url:
            url = f"https://{url}"
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or None
    except Exception:
        return None


def _is_acceptable(domain: str) -> bool:
    """Return True if the domain looks like a company's own site."""
    for keyword in _BLOCKED_KEYWORDS:
        if keyword in domain:
            return False
    return bool(_VALID_TLDS.search(domain))
