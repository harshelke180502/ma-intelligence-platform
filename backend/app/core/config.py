from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ma_thesis"
    )

    # ── Application ───────────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "M&A Thesis Research Platform"
    DEBUG: bool = False

    # CORS — frontend dev servers (Vite default: 5173, CRA default: 3000)
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ── External API keys ─────────────────────────────────────────────────────
    # Optional: pipeline runs in keyword-rules-only mode when absent
    GOOGLE_PLACES_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # ── Pipeline tuning ───────────────────────────────────────────────────────
    # Per-collector HTTP timeout in seconds
    COLLECTOR_TIMEOUT_SECONDS: int = 30
    # Retry attempts before a collector marks a source as failed
    COLLECTOR_MAX_RETRIES: int = 3
    # rapidfuzz WRatio threshold for fuzzy company-name matching (0–100)
    FUZZY_MATCH_THRESHOLD: int = 88

    # ── Export ────────────────────────────────────────────────────────────────
    MAX_EXPORT_ROWS: int = 10_000


# Single shared instance — import this everywhere
settings = Settings()
