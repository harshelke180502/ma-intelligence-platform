"""
Thesis fit scorer.

Generates a 0.00–1.00 score representing how well a company fits the
specialty tax advisory M&A acquisition thesis.

Model selection (automatic):
  - If a fine-tuned model ID is stored in finetuning_job.json (written by
    finetuning_service.py after a successful fine-tuning job), that model is
    used for all subsequent Enrich calls.
  - Otherwise falls back to zero-shot gpt-4o-mini.

The fine-tuned model was trained on GPT-4o-labeled examples drawn from the
actual company database using a detailed scoring rubric, so it produces more
calibrated and consistent scores than zero-shot prompting.
"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None

_SYSTEM_PROMPT = """\
You are an M&A analyst at a specialty tax advisory firm evaluating potential
acquisition targets. The firm acquires accounting and tax service companies
that provide one or more of:
  - R&D Tax Credits (R&D consulting, innovation credits)
  - Cost Segregation Studies (real estate tax strategy)
  - Work Opportunity Tax Credit (WOTC) consulting
  - Sales & Use Tax compliance and consulting

Ideal acquisition profile:
  - Offers one or more of the qualifying services above (the more the better)
  - Revenue between $5M and $200M (sweet spot: $10M–$100M)
  - Privately held or PE-backed (easier deal structure; avoid pure public cos)
  - Regional or national client base of mid-market businesses
  - Recurring or repeat-engagement revenue model

Score the company from 0.0 to 1.0:
  0.0 — Wrong fit entirely (e.g., solo CPA, pure bookkeeping, payroll-only,
          revenue >$500M, or purely unrelated industry)
  0.3 — Weak fit (adjacent services but not qualifying, or very small/large)
  0.5 — Moderate fit (some qualifying services, size or ownership is off)
  0.7 — Good fit (qualifying services, right size, decent ownership type)
  1.0 — Perfect target (all qualifying services, sweet-spot revenue, private/PE)

Respond ONLY with valid JSON: {"score": <float 0.0-1.0>, "reason": "<one concise sentence>"}
""".strip()


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set in .env")
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _active_model() -> str:
    """
    Return the model ID to use for scoring.

    Prefers the fine-tuned model stored in finetuning_job.json (written by
    finetuning_service.py on job success).  Falls back to gpt-4o-mini if no
    fine-tuned model is available yet.
    """
    try:
        from app.services.finetuning_service import STATUS_FILE, read_status
        if STATUS_FILE.exists():
            model_id = read_status().get("model_id")
            if model_id:
                return model_id
    except Exception:
        pass
    return "gpt-4o-mini"


async def score_thesis_fit(
    name: str,
    state: Optional[str],
    services: list[str],
    ownership_type: Optional[str],
    revenue_est_min: Optional[int],
    revenue_est_max: Optional[int],
    employee_count: Optional[int],
    website_text: Optional[str],
) -> Optional[float]:
    """
    Call GPT-4o-mini to score the company's M&A thesis fit.

    Returns a float in [0.0, 1.0] rounded to 2 dp, or None if the call fails.

    Revenue values are in thousands USD (3000 = $3M, 10000 = $10M).
    """
    # Build human-readable revenue string
    rev_str = "unknown"
    if revenue_est_min is not None and revenue_est_max is not None:
        rev_str = f"${revenue_est_min / 1000:.1f}M – ${revenue_est_max / 1000:.1f}M"
    elif revenue_est_min is not None:
        rev_str = f"${revenue_est_min / 1000:.1f}M+"

    services_str = ", ".join(services) if services else "none detected"

    profile = (
        f"Company: {name} ({state or 'state unknown'})\n"
        f"Services: {services_str}\n"
        f"Ownership: {ownership_type or 'unknown'}\n"
        f"Revenue estimate: {rev_str}\n"
        f"Employees: {employee_count if employee_count is not None else 'unknown'}"
    )

    if website_text:
        # Limit website excerpt to keep token cost low (~$0.0002 per call at mini rates)
        profile += f"\n\nWebsite excerpt:\n{website_text[:1200]}"

    try:
        model = _active_model()
        client = _get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": profile},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=120,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        score = float(data["score"])
        score = max(0.0, min(1.0, score))   # clamp to valid range
        reason = data.get("reason", "")
        logger.info(
            "thesis_scorer: %r → %.2f  model=%s  reason=%r", name, score, model, reason
        )
        return round(score, 2)
    except Exception as exc:
        logger.warning("thesis_scorer: failed for %r: %s", name, exc)
        return None
