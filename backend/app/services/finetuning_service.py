"""
Fine-tuning service for the thesis fit scorer.

Workflow
────────
  Phase 1 — sampling   : Query the DB for ~100 diverse companies (varied by
                          ownership type, service count, revenue range).
  Phase 2 — labeling   : Call GPT-4o (stronger model) with a detailed rubric
                          to produce high-quality score labels.  This is
                          "knowledge distillation" — the larger model teaches
                          the smaller one.
  Phase 3 — uploading  : Write a JSONL file and upload it to the OpenAI
                          Files API.
  Phase 4 — training   : Create a fine-tuning job on gpt-4o-mini-2024-07-18.
  Phase 5 — monitoring : The GET /finetuning-status endpoint polls OpenAI for
                          job completion and saves the model ID on success.

Status is persisted to backend/finetuning_job.json so it survives server
restarts.  thesis_scorer.py reads this file at call time and uses the
fine-tuned model when available.
"""

import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.company import Company

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Fine-tunable version of gpt-4o-mini (OpenAI requirement)
_BASE_MODEL = "gpt-4o-mini-2024-07-18"

# Persistent status file — survives server restarts
STATUS_FILE = Path(__file__).resolve().parent.parent.parent / "finetuning_job.json"

# Max concurrent GPT-4o label calls (stay within 30K TPM free-tier limit)
# Each call uses ~480 tokens; 3 concurrent = ~1,440 tokens/request-burst,
# well under the 30,000 TPM cap.  A 2 s inter-batch pause provides headroom.
_LABEL_CONCURRENCY = 3
_LABEL_BATCH_PAUSE_S = 2.0   # seconds between batches


# ── Status helpers ────────────────────────────────────────────────────────────

def read_status() -> dict:
    """Read current fine-tuning status from disk."""
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except Exception:
            pass
    return {
        "phase": "idle",
        "job_id": None,
        "model_id": None,
        "examples_labeled": 0,
        "examples_total": 100,
        "message": "No fine-tuning job has been run yet.",
        "started_at": None,
        "completed_at": None,
    }


def _write_status(update: dict) -> None:
    current = read_status()
    current.update(update)
    STATUS_FILE.write_text(json.dumps(current, indent=2, default=str))


# ── Company sampling ──────────────────────────────────────────────────────────

async def _sample_companies(db: AsyncSession, target: int = 100) -> list[Company]:
    """
    Return a diverse sample of companies for fine-tuning.

    Sampling strategy (5 buckets):
      30  — 2+ services, private/PE-backed  → expected high scores
      20  — 1 service,   private/PE-backed  → expected medium scores
      10  — franchise, any service count    → medium-low scores
      15  — public, any service count       → lower scores (deal-unfriendly)
      25  — 0 services detected             → edge cases
    """
    seen_ids: set = set()
    results: list[Company] = []

    async def _bucket(stmt, n: int) -> None:
        rows = (await db.execute(stmt.limit(n))).scalars().all()
        for r in rows:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                results.append(r)

    base = select(Company).where(Company.is_excluded.is_(False))

    await _bucket(
        base.where(
            Company.ownership_type.in_(["private", "pe_backed"]),
            func.jsonb_array_length(Company.services) >= 2,
        ).order_by(func.random()),
        30,
    )
    await _bucket(
        base.where(
            Company.ownership_type.in_(["private", "pe_backed"]),
            func.jsonb_array_length(Company.services) == 1,
        ).order_by(func.random()),
        20,
    )
    await _bucket(
        base.where(Company.ownership_type == "franchise").order_by(func.random()),
        10,
    )
    await _bucket(
        base.where(Company.ownership_type == "public").order_by(func.random()),
        15,
    )
    await _bucket(
        base.where(func.jsonb_array_length(Company.services) == 0).order_by(func.random()),
        25,
    )
    # Fill any gap to reach target
    if len(results) < target:
        await _bucket(base.order_by(func.random()), target - len(results))

    logger.info("sampled %d companies for fine-tuning", len(results))
    return results[:target]


# ── GPT-4o labeling ───────────────────────────────────────────────────────────

# Detailed rubric used by GPT-4o to produce high-quality labels.
# Explicit point ranges reduce scoring variance across different companies.
_LABELING_SYSTEM = """\
You are an expert M&A analyst scoring companies for acquisition fit for a
specialty tax advisory firm.

The firm acquires accounting and tax service companies that offer:
  - R&D Tax Credits consulting
  - Cost Segregation Studies
  - WOTC (Work Opportunity Tax Credit) consulting
  - Sales & Use Tax compliance

SCORING RUBRIC (four components that sum to 0.0–1.0):

Service portfolio (40% weight):
  - 4 qualifying services → +0.40
  - 3 services            → +0.32
  - 2 services            → +0.24
  - 1 service             → +0.14
  - 0 services            → +0.00  (unless company text clearly shows advisory)

Revenue (25% weight):
  - $10M–$100M            → +0.25  (sweet spot)
  - $5M–$10M or $100M–$200M → +0.18
  - $200M–$500M           → +0.10
  - >$500M or <$1M        → +0.03
  - Unknown               → +0.12

Ownership (25% weight):
  - private               → +0.25
  - pe_backed             → +0.22
  - franchise             → +0.15
  - public                → +0.05
  - unknown               → +0.12

Company profile (10% weight):
  - Name clearly indicates specialty tax / accounting advisory → +0.10
  - Name suggests unrelated industry (trust, investment, insurance) → +0.00
  - Unclear                → +0.05

Apply the rubric, sum the four components.

Respond ONLY with valid JSON:
{"reasoning": "<2-3 sentence rubric-based analysis>", "score": <float 0.0-1.0>, "reason": "<one concise sentence>"}
""".strip()


def _build_profile(company: Company) -> str:
    """Build a human-readable company profile (mirrors thesis_scorer.py format)."""
    rev_str = "unknown"
    if company.revenue_est_min is not None and company.revenue_est_max is not None:
        rev_str = (
            f"${company.revenue_est_min / 1000:.1f}M"
            f" – ${company.revenue_est_max / 1000:.1f}M"
        )
    services_str = ", ".join(company.services) if company.services else "none detected"
    return (
        f"Company: {company.name} ({company.state or 'state unknown'})\n"
        f"Services: {services_str}\n"
        f"Ownership: {company.ownership_type or 'unknown'}\n"
        f"Revenue estimate: {rev_str}\n"
        f"Employees: {company.employee_count if company.employee_count is not None else 'unknown'}"
    )


async def _label_one(client: AsyncOpenAI, company: Company) -> tuple[float, str]:
    """
    Call GPT-4o to score one company with exponential-backoff retry on 429.
    Returns (score, reason).
    """
    from openai import RateLimitError

    backoff = 2.0   # initial wait in seconds; doubles each retry up to 4 attempts
    for attempt in range(4):
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _LABELING_SYSTEM},
                    {"role": "user", "content": _build_profile(company)},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=250,
            )
            data = json.loads(response.choices[0].message.content or "{}")
            score = max(0.0, min(1.0, float(data["score"])))
            reason = data.get("reason", "")
            logger.debug("labeled %r → %.2f", company.name, score)
            return round(score, 2), reason
        except RateLimitError:
            if attempt == 3:
                break
            wait = backoff * (2 ** attempt)
            logger.info("rate limited labeling %r — retrying in %.0fs", company.name, wait)
            await asyncio.sleep(wait)
        except Exception as exc:
            logger.warning("label_one failed for %r: %s", company.name, exc)
            break

    return 0.5, "Labeling error — neutral default"


async def _label_all(
    client: AsyncOpenAI,
    companies: list[Company],
) -> list[dict]:
    """
    Label every company concurrently in batches, returning fine-tuning JSONL
    records (each a dict with a 'messages' key).
    """
    # Import the exact system prompt used at inference time so training
    # and inference conditions are identical.
    from app.services.enrichment.thesis_scorer import _SYSTEM_PROMPT as _INFERENCE_SYSTEM

    training_examples: list[dict] = []
    sem = asyncio.Semaphore(_LABEL_CONCURRENCY)

    async def _guarded(c: Company) -> tuple[float, str]:
        async with sem:
            return await _label_one(client, c)

    for i in range(0, len(companies), _LABEL_CONCURRENCY):
        batch = companies[i : i + _LABEL_CONCURRENCY]
        scored = await asyncio.gather(*[_guarded(c) for c in batch])

        for company, (score, reason) in zip(batch, scored):
            training_examples.append(
                {
                    "messages": [
                        {"role": "system", "content": _INFERENCE_SYSTEM},
                        {"role": "user", "content": _build_profile(company)},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {"score": score, "reason": reason}
                            ),
                        },
                    ]
                }
            )

        done = len(training_examples)
        total = len(companies)
        _write_status(
            {
                "examples_labeled": done,
                "message": f"Labeled {done}/{total} companies with GPT-4o...",
            }
        )
        logger.info("labeling progress: %d/%d", done, total)

        # Pause between batches to respect the 30K TPM rate limit
        if i + _LABEL_CONCURRENCY < len(companies):
            await asyncio.sleep(_LABEL_BATCH_PAUSE_S)

    return training_examples


# ── Upload and submit fine-tuning job ─────────────────────────────────────────

async def _upload_and_submit(client: AsyncOpenAI, examples: list[dict]) -> str:
    """Write JSONL, upload to OpenAI, create fine-tuning job. Returns job_id."""
    # Write JSONL to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
        tmp_path = f.name

    _write_status(
        {"phase": "uploading", "message": "Uploading training data to OpenAI..."}
    )

    with open(tmp_path, "rb") as f:
        file_obj = await client.files.create(file=f, purpose="fine-tune")

    logger.info("training file uploaded: %s", file_obj.id)

    _write_status(
        {"phase": "training", "message": "Submitting fine-tuning job to OpenAI..."}
    )

    job = await client.fine_tuning.jobs.create(
        training_file=file_obj.id,
        model=_BASE_MODEL,
    )

    logger.info("fine-tuning job created: %s", job.id)
    return job.id


# ── Main pipeline (runs as a FastAPI BackgroundTask) ──────────────────────────

async def run_finetuning_pipeline() -> None:
    """
    Full fine-tuning workflow.  Invoked as a FastAPI background task so the
    HTTP response is returned immediately while this runs asynchronously.
    """
    if not settings.OPENAI_API_KEY:
        _write_status(
            {"phase": "failed", "message": "OPENAI_API_KEY is not set in .env"}
        )
        return

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        # ── Phase 1: Sample ──────────────────────────────────────────────────
        _write_status(
            {
                "phase": "sampling",
                "job_id": None,
                "model_id": None,
                "examples_labeled": 0,
                "examples_total": 100,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": None,
                "message": "Sampling diverse companies from database...",
            }
        )
        async with AsyncSessionLocal() as db:
            companies = await _sample_companies(db)

        _write_status(
            {
                "examples_total": len(companies),
                "message": f"Sampled {len(companies)} companies. Labeling with GPT-4o...",
            }
        )

        # ── Phase 2: Label ───────────────────────────────────────────────────
        _write_status({"phase": "labeling"})
        examples = await _label_all(client, companies)

        if len(examples) < 10:
            raise ValueError(
                f"Only {len(examples)} training examples generated; OpenAI requires ≥10."
            )

        logger.info("generated %d fine-tuning examples", len(examples))

        # ── Phase 3 + 4: Upload + submit ─────────────────────────────────────
        job_id = await _upload_and_submit(client, examples)
        _write_status(
            {
                "job_id": job_id,
                "message": (
                    f"Fine-tuning job {job_id} submitted. "
                    "Training typically takes 15–30 minutes."
                ),
            }
        )

    except Exception as exc:
        logger.error("finetuning pipeline error: %s", exc, exc_info=True)
        _write_status({"phase": "failed", "message": str(exc)})


# ── Status polling (called by the GET endpoint) ───────────────────────────────

async def poll_job_status() -> dict:
    """
    Fetch the latest job status from OpenAI if a job is in progress.
    Saves the fine-tuned model ID on success.
    Returns the updated status dict.
    """
    status = read_status()
    phase = status.get("phase")
    job_id = status.get("job_id")

    # Only poll when a job is actively running
    if not job_id or phase not in ("training", "uploading"):
        return status

    if not settings.OPENAI_API_KEY:
        return status

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        job = await client.fine_tuning.jobs.retrieve(job_id)

        if job.status == "succeeded":
            model_id = job.fine_tuned_model
            _write_status(
                {
                    "phase": "succeeded",
                    "model_id": model_id,
                    "completed_at": datetime.utcnow().isoformat(),
                    "message": f"Fine-tuning complete. Model: {model_id}",
                }
            )
            logger.info("fine-tuning succeeded, model: %s", model_id)

        elif job.status in ("failed", "cancelled"):
            err = getattr(job, "error", None)
            _write_status(
                {
                    "phase": "failed",
                    "message": f"OpenAI job {job.status}: {err}",
                }
            )

        else:
            # Still running — surface token progress if available
            trained = getattr(job, "trained_tokens", None) or 0
            msg = f"Training in progress (job: {job_id})"
            if trained:
                msg += f" — {trained:,} tokens processed"
            _write_status({"message": msg})

    except Exception as exc:
        logger.warning("poll_job_status error: %s", exc)

    return read_status()
