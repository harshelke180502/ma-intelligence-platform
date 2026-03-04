from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContactOut(BaseModel):
    """
    Contact record returned in company detail responses.

    All fields except id and company_id are Optional — the pipeline
    captures whatever is publicly available and does not require completeness.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: Optional[str] = None
