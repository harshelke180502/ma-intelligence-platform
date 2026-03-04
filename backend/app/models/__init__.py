# Import every model here so that:
#   1. Alembic's env.py can discover all tables via Base.metadata
#   2. SQLAlchemy's relationship() references resolve at startup

from app.models.base import Base  # noqa: F401
from app.models.thesis import Thesis  # noqa: F401
from app.models.company import Company  # noqa: F401
from app.models.contact import Contact  # noqa: F401
from app.models.raw_record import RawRecord  # noqa: F401
from app.models.pipeline_run import PipelineRun  # noqa: F401

__all__ = [
    "Base",
    "Thesis",
    "Company",
    "Contact",
    "RawRecord",
    "PipelineRun",
]
