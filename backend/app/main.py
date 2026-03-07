from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    debug=settings.DEBUG,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for development).
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "project": settings.PROJECT_NAME}


# ── API routers ───────────────────────────────────────────────────────────────
from app.api.v1 import companies, kpis, pipeline

app.include_router(companies.router, prefix=settings.API_V1_PREFIX)
app.include_router(kpis.router,      prefix=settings.API_V1_PREFIX)
app.include_router(pipeline.router,  prefix=settings.API_V1_PREFIX)

# Registered as implemented:
# from app.api.v1 import export, thesis
# app.include_router(export.router,  prefix=settings.API_V1_PREFIX)
# app.include_router(thesis.router,  prefix=settings.API_V1_PREFIX)
