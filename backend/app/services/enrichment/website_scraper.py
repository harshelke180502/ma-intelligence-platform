"""
Website scraper.

Fetches a company homepage and extracts visible text for downstream analysis.

Public interface:
    async def scrape_website_text(url: str) -> Optional[str]
"""

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    ),
}

_TEXT_TAGS = ["p", "li", "h1", "h2", "h3"]
_MAX_CHARS = 5_000


async def scrape_website_text(url: str) -> Optional[str]:
    """
    Fetch the homepage of `url` and return up to 5 000 chars of visible text.

    Args:
        url: Root domain or full URL, e.g. "bonadio.com" or "https://bonadio.com".

    Returns:
        Concatenated visible text, or None on failure.
    """
    if not url:
        return None

    if "://" not in url:
        url = f"https://{url}"

    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=10,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("website_scraper: request failed for %r: %s", url, exc)
        return None

    try:
        soup = BeautifulSoup(response.text, "lxml")
        parts = [tag.get_text(" ", strip=True) for tag in soup.find_all(_TEXT_TAGS)]
        text = " ".join(parts)[:_MAX_CHARS]
        return text or None
    except Exception as exc:
        logger.warning("website_scraper: parse failed for %r: %s", url, exc)
        return None
