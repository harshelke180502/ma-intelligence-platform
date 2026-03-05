"""
Rule-based service classifier.

classify_services() inspects a NormalizedCompanyInput and the original
raw_payload to detect which of the four qualifying service types the
company appears to offer.

Classification is intentionally permissive: a false positive (tagging a
company with a service it doesn't offer) is less harmful than a false
negative (missing a qualifying firm entirely), because analysts review
the results before a final acquisition list is produced.

Service keys returned are the canonical strings defined in schemas/common.py:
    rd_credits, cost_seg, wotc, sales_use_tax

Sources searched (in order of signal strength):
    1. normalized.name    — company's trading name (highest signal)
    2. normalized.website — root domain, e.g. "costsegstudies.com"
    3. Google Places types — e.g. ["accounting", "tax_preparation"]
       Underscores replaced with spaces for keyword matching.
"""

from app.pipeline.schemas import NormalizedCompanyInput

# ── Keyword vocabulary ────────────────────────────────────────────────────────
# Each list is ordered loosely by specificity (most specific first) to make
# the mapping easy to audit.  All entries are lowercase — corpus is lowercased
# before matching.

_KEYWORD_MAP: dict[str, list[str]] = {
    "rd_credits": [
        "r&d tax",
        "r & d tax",
        "r+d tax",
        "research and development tax",
        "research & development tax",
        "research tax credit",
        "r&d credit",
        "research credit",
        "section 41",
        "innovation tax credit",
        # Standalone "r&d" is intentionally omitted — too broad for domain names
    ],
    "cost_seg": [
        "cost segregation",
        "cost seg",
        "costseg",
        "cost-seg",
        "engineering-based tax",
        "engineering based tax",
        "fixed asset depreciation",
        "bonus depreciation study",
        "accelerated depreciation",
    ],
    "wotc": [
        "wotc",
        "work opportunity tax credit",
        "work opportunity credit",
        "work opportunity",
        "hiring tax credit",
        "hire act credit",
    ],
    "sales_use_tax": [
        "sales and use tax",
        "sales & use tax",
        "sales/use tax",
        "sales tax consulting",
        "sales tax compliance",
        "use tax consulting",
        "indirect tax",
        "transaction tax",
        # Standalone "sales tax" is included but is a weaker signal
        "sales tax",
        "use tax",
    ],
}


def classify_services(
    normalized: NormalizedCompanyInput,
    raw_payload: dict,
) -> list[str]:
    """
    Return a list of service keys detected in the company's name, website,
    and Google Places type tags.
    """

    # ── 1️⃣ Trust collector metadata if present ─────────────────────────────
    meta = raw_payload.get("_meta") or {}
    service = meta.get("service")

    if service:
        return [service]

    # ── 2️⃣ Fallback to keyword classification ──────────────────────────────
    corpus = _build_corpus(normalized, raw_payload)

    return [
        svc_key
        for svc_key, keywords in _KEYWORD_MAP.items()
        if any(kw in corpus for kw in keywords)
    ]

# ── Corpus builder ────────────────────────────────────────────────────────────

def _build_corpus(normalized: NormalizedCompanyInput, raw_payload: dict) -> str:
    """
    Concatenate all searchable text into a single lowercase string.

    Google Places types are stored under raw_payload["place"]["types"] in
    our payload structure.  The top-level raw_payload.get("types") check
    is kept for forward-compatibility with other collectors that may produce
    a flatter payload shape.
    """
    parts: list[str] = []

    if normalized.name:
        parts.append(normalized.name.lower())

    if normalized.website:
        # Domain-level signals, e.g. "costsegservices.com" contains "costseg"
        parts.append(normalized.website.lower())

    # Google Places business type tags — replace underscores so
    # "tax_preparation" matches as "tax preparation"
    types: list = raw_payload.get("types") or []
    if not types:
        # Our collector nests the API result under "place"
        place: dict = raw_payload.get("place") or {}
        types = place.get("types") or []

    parts.extend(t.lower().replace("_", " ") for t in types)

    return " ".join(parts)
