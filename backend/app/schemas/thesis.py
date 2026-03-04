from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import ServiceType


class ThesisCreate(BaseModel):
    """
    Payload for POST /thesis.

    Enables the bonus feature: running the pipeline against a custom thesis
    (different industry, geography, size range) without code changes.
    """

    name: str

    # Service keys that qualify a company, e.g. ["rd_credits", "cost_seg"]
    services: list[str]

    # Size thresholds — None means no minimum enforced
    revenue_min: Optional[int] = None   # thousands USD
    employee_min: Optional[int] = None

    # 2-char state codes — None means all continental US states
    states: Optional[list[str]] = None

    # Service keys that disqualify a company (primary service is one of these)
    exclusions: list[str] = []

    # Ownership types that qualify — None means any non-public ownership
    ownership: Optional[list[str]] = None

    @field_validator("services", "exclusions")
    @classmethod
    def validate_service_keys(cls, v: list[str]) -> list[str]:
        valid = {e.value for e in ServiceType}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(
                f"Unknown service keys: {invalid}. Valid: {valid}"
            )
        return v

    @field_validator("states")
    @classmethod
    def validate_states(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for s in v:
            if len(s) != 2 or not s.isalpha():
                raise ValueError(
                    f"State codes must be 2-letter USPS codes, got: {s!r}"
                )
        return [s.upper() for s in v]


class ThesisOut(ThesisCreate):
    """Thesis record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
