"""
Employee estimator.

Extracts an employee headcount from free-form website text using regex patterns.
Returns the largest plausible number found — longer-established firms tend to
mention their total headcount in their "about" section alongside smaller
team-size references.

Public interface:
    def estimate_employees(text: str) -> Optional[int]
"""

import re
from typing import Optional

# Patterns ordered loosely by specificity.
# Each captures a numeric group (possibly with commas).
_PATTERNS = [
    # "over 200 employees", "more than 1,500 professionals"
    r"(?:over|more than|nearly|approximately|about)\s+([\d,]+)\s+"
    r"(?:employees?|staff|professionals?|team members?|associates?|people)",

    # "200+ employees", "1,500+ professionals"
    r"([\d,]+)\+\s*(?:employees?|staff|professionals?|team members?|associates?|people)",

    # "team of 200", "staff of 1,500"
    r"(?:team|staff)\s+of\s+([\d,]+)",

    # "200 employees", "1,500 professionals"
    r"([\d,]+)\s+(?:employees?|staff|professionals?|team members?|associates?|people)",

    # "200-person team", "50-person firm"
    r"([\d,]+)[‐\-–]\s*person\s+(?:team|firm|company|office|group)",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def estimate_employees(text: str) -> Optional[int]:
    """
    Return the largest employee count found in `text`, or None.

    Taking the largest value avoids returning incidental small numbers
    (e.g. "our 5-person leadership team") when the page also mentions
    the full headcount.
    """
    if not text:
        return None

    candidates: list[int] = []

    for pattern in _COMPILED:
        for match in pattern.finditer(text):
            raw = match.group(1).replace(",", "")
            try:
                value = int(raw)
                if 2 <= value <= 500_000:  # sanity bounds
                    candidates.append(value)
            except ValueError:
                continue

    return max(candidates) if candidates else None
