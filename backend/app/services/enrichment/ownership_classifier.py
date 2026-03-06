"""
Ownership classifier.

Classifies a company's ownership type from website text using keyword matching.

Ownership types (must match the DB constraint):
    private   — independent, family-owned, or founder-led (default)
    pe_backed — owned or backed by private equity / venture capital
    public    — listed on a stock exchange
    franchise — franchise model

Public interface:
    def classify_ownership(text: str) -> str
"""

import re

_PE_KEYWORDS = [
    r"\bprivate equity\b",
    r"\bpe[- ]backed\b",
    r"\bventure capital\b",
    r"\bvc[- ]backed\b",
    r"\bportfolio company\b",
    r"\bequity[- ]backed\b",
    r"\binvestment firm\b",
    r"\bacquired by\b",
    r"\brecapitalization\b",
    r"\bgrowth equity\b",
]

_PUBLIC_KEYWORDS = [
    r"\bnyse[:\s]",
    r"\bnasdaq[:\s]",
    r"\bstock exchange\b",
    r"\bpublicly traded\b",
    r"\bpublic company\b",
    r"\bshareholders\b",
    r"\bsec filing",
    r"\b10-k\b",
    r"\bannual report\b",
]

_FRANCHISE_KEYWORDS = [
    r"\bfranchise\b",
    r"\bfranchisee\b",
    r"\bfranchising\b",
    r"\bmaster franchise\b",
    r"\bfranchise owner\b",
    r"\bfranchise network\b",
]

_PE_RE = [re.compile(p, re.IGNORECASE) for p in _PE_KEYWORDS]
_PUBLIC_RE = [re.compile(p, re.IGNORECASE) for p in _PUBLIC_KEYWORDS]
_FRANCHISE_RE = [re.compile(p, re.IGNORECASE) for p in _FRANCHISE_KEYWORDS]


def classify_ownership(text: str) -> str:
    """
    Return the most likely ownership type for the company described in `text`.

    Evaluation order: public → pe_backed → franchise → private (default).
    Public is checked first because a PE firm can take a company public,
    and "public" is the stronger signal in that case.
    """
    if not text:
        return "private"

    if any(p.search(text) for p in _PUBLIC_RE):
        return "public"

    if any(p.search(text) for p in _PE_RE):
        return "pe_backed"

    if any(p.search(text) for p in _FRANCHISE_RE):
        return "franchise"

    return "private"
