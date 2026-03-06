"""
Revenue estimator.

Derives a revenue range from employee count using a flat $200 000 per-employee
heuristic.  Returns values in thousands of USD to match the DB schema.

  $200k × employees → midpoint
  range = midpoint ± 30 %

Public interface:
    def estimate_revenue(employee_count: int) -> tuple[int, int]
"""

from typing import Optional

_REVENUE_PER_EMPLOYEE = 200  # thousands USD per employee ($200k)
_RANGE_FACTOR = 0.30         # ±30 % around the midpoint


def estimate_revenue(employee_count: int) -> tuple[Optional[int], Optional[int]]:
    """
    Return (rev_min, rev_max) in thousands USD, or (None, None) if input invalid.

    Example:
        estimate_revenue(100) → (14000, 26000)   # $14M – $26M
    """
    if not employee_count or employee_count <= 0:
        return None, None

    midpoint = employee_count * _REVENUE_PER_EMPLOYEE
    margin = int(midpoint * _RANGE_FACTOR)

    rev_min = max(midpoint - margin, 1)
    rev_max = midpoint + margin

    return rev_min, rev_max
