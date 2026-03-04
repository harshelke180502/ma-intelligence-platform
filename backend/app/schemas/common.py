"""
Shared enums and vocabulary used across schemas, models, and pipeline logic.

These string-enum values are the single source of truth for service keys.
The same strings appear in:
  - Thesis.services / Thesis.exclusions  (JSONB arrays)
  - Company.services                      (JSONB array)
  - API filter query params
  - Classifier output
  - Dashboard filter labels
"""

from enum import Enum


class ServiceType(str, Enum):
    """Qualifying service types from the M&A thesis."""

    rd_credits = "rd_credits"       # R&D Tax Credits
    cost_seg = "cost_seg"           # Cost Segregation
    wotc = "wotc"                   # Work Opportunity Tax Credits
    sales_use_tax = "sales_use_tax" # Sales & Use Tax consulting

    # Exclusion markers — present in Thesis.exclusions, not in qualifying services
    erc = "erc"                     # Employee Retention Credit (excluded)
    property_tax = "property_tax"   # Property Tax consulting (excluded)


class OwnershipType(str, Enum):
    """Ownership classification for a company."""

    private = "private"
    pe_backed = "pe_backed"
    public = "public"
    franchise = "franchise"
    unknown = "unknown"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class PipelineStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
