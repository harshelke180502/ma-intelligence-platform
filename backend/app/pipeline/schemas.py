"""
Internal data transfer type for the pipeline transformation layer.

NormalizedCompanyInput is the intermediate representation that flows
through the three pipeline stages:

  raw_records
      │
      ▼  normalizer.normalize_place_record()
  NormalizedCompanyInput  (services = [])
      │
      ▼  classifier.classify_services()
  NormalizedCompanyInput  (services = [...detected keys...])
      │
      ▼  deduplicator.upsert_company()
  companies table

Using a dataclass (not a Pydantic model) because this is a pure
in-process type with no serialization or HTTP boundary concerns.
Mutable so the orchestrator can assign services after classification.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalizedCompanyInput:
    """
    Cleansed, source-agnostic company representation.

    Produced by the normalizer from a single raw_record.
    The services field starts empty; the classifier populates it
    before the deduplicator persists the record.
    """

    # Required — insert is rejected if blank (enforced in normalizer)
    name: str

    # All geographic / contact fields are Optional — partial data is valid
    city: Optional[str]
    state: Optional[str]       # 2-char USPS code, e.g. "TX"
    website: Optional[str]     # root domain only, e.g. "acmetax.com"

    # Populated by classifier.classify_services() before upsert
    services: list[str] = field(default_factory=list)

    # Carries through from raw_record.source_name for provenance
    primary_source: str = ""

    # Thesis defaults applied by normalizer when source data is absent.
    # Revenue stored in thousands USD (3000 = $3M, 10000 = $10M).
    ownership_type: str = "private"
    revenue_est_min: Optional[int] = 3000
    revenue_est_max: Optional[int] = 10000
