from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping=True — issues a lightweight SELECT 1 before handing out a
# connection, so stale connections are detected and replaced automatically.
# pool_size / max_overflow — sized for a single-server deployment; tune up
# when horizontal scaling is introduced.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,  # logs SQL statements in DEBUG mode
)

# ── Session factory ───────────────────────────────────────────────────────────
# expire_on_commit=False — keeps model attributes accessible after commit
# without issuing a lazy-load query.  Required for async code where lazy
# loading is not supported.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────
# Usage in route handlers:
#
#   @router.get("/companies")
#   async def list_companies(db: AsyncSession = Depends(get_db)):
#       ...
#
# The try/except/rollback pattern ensures that any unhandled exception inside
# a request handler rolls back the transaction before the session closes.
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ── Dev / test helpers ────────────────────────────────────────────────────────
# Use these in scripts and test fixtures, not in production request handlers.
# Production schema changes are managed exclusively through Alembic migrations.
async def create_all_tables() -> None:
    """Create all tables from current ORM metadata.  Development use only."""
    # Import models here (not at module level) to avoid a circular import
    # between database.py and models/__init__.py at startup.
    import app.models  # noqa: F401 — registers all mappers with Base.metadata
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables() -> None:
    """Drop all tables.  Use only in test teardown — irreversible."""
    import app.models  # noqa: F401
    from app.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
