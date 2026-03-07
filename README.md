# M&A Intelligence Platform

A full-stack acquisition pipeline tool for a **Specialty Tax Advisory** firm. It collects, normalises, deduplicates, and enriches company data, then scores each target against the firm's M&A thesis using a fine-tuned GPT-4o-mini model.

## Live Deployment

| Service | URL |
|---|---|
| **Frontend** | https://ma-intelligence-platform.vercel.app |
| **Backend API** | https://ma-intelligence-platform.onrender.com/api/v1/docs |
| **Database** | Neon PostgreSQL (managed cloud) |

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Data Pipeline Workflow](#data-pipeline-workflow)
3. [Enrichment Pipeline](#enrichment-pipeline)
4. [AI Thesis Scoring](#ai-thesis-scoring)
5. [Prerequisites](#prerequisites)
6. [Setup & Run](#setup--run)
7. [Environment Variables](#environment-variables)
8. [Deployment](#deployment)
9. [API Reference](#api-reference)
10. [Project Structure](#project-structure)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          M&A Intelligence Platform                          │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────┐         HTTP / JSON          ┌───────────────────┐
  │                      │ ◄──────────────────────────► │                   │
  │   React Frontend     │       (Vite proxy            │  FastAPI Backend  │
  │   (localhost:5173)   │        /api → :8000)         │  (localhost:8000) │
  │                      │                              │                   │
  │  ┌────────────────┐  │                              │  ┌─────────────┐  │
  │  │   KPI Cards    │  │                              │  │  /companies │  │
  │  │  Companies     │  │                              │  │  /kpis      │  │
  │  │  Table + Modal │  │                              │  │  /pipeline  │  │
  │  │  Charts        │  │                              │  └──────┬──────┘  │
  │  │  FineTuneCard  │  │                              │         │         │
  │  └────────────────┘  │                              │  ┌──────▼──────┐  │
  └──────────────────────┘                              │  │  Services   │  │
                                                        │  │  + Pipeline │  │
                                                        │  └──────┬──────┘  │
                                                        └─────────┼─────────┘
                                                                  │
                          ┌───────────────────────────────────────┤
                          │                                       │
              ┌───────────▼──────────┐              ┌────────────▼──────────┐
              │    PostgreSQL DB      │              │    External APIs       │
              │                      │              │                        │
              │  companies           │              │  • Google Places API   │
              │  contacts            │              │  • Brave Search        │
              │  raw_records         │              │  • OpenAI              │
              │  pipeline_runs       │              │    - GPT-4o (labeling) │
              │  thesis              │              │    - GPT-4o-mini        │
              └──────────────────────┘              │      (inference)       │
                                                    └────────────────────────┘
```

---

## Data Pipeline Workflow

```
  ┌─────────────┐
  │   TRIGGER   │  POST /api/v1/pipeline/run
  └──────┬──────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  STAGE 1 — COLLECTION                                                   │
  │                                                                         │
  │  GooglePlacesCollector                                                  │
  │  ├─ Queries "tax advisory", "R&D credits", "cost segregation" etc.      │
  │  ├─ Fetches up to 60 results per query (3 pages × 20)                  │
  │  └─ Stores raw JSON payloads → raw_records table                       │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  STAGE 2 — NORMALISATION                                                │
  │                                                                         │
  │  normalizer.py                                                          │
  │  ├─ Extracts: name, city, state, website, phone                        │
  │  ├─ Classifies services from business description text                  │
  │  │   (R&D Credits / Cost Seg / WOTC / Sales & Use Tax)                 │
  │  ├─ Sets default revenue: $3M–$10M (pipeline default)                  │
  │  └─ Sets ownership_type = 'private' (default)                          │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  STAGE 3 — DEDUPLICATION                                                │
  │                                                                         │
  │  deduplicator.py                                                        │
  │  ├─ Exact match: UNIQUE (name, state) — INSERT ON CONFLICT DO UPDATE   │
  │  └─ Fuzzy match: rapidfuzz WRatio ≥ 88 for near-duplicate detection    │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  STAGE 4 — CLASSIFICATION (Thesis Filter)                               │
  │                                                                         │
  │  classifier.py                                                          │
  │  ├─ Excludes: ERC-primary firms, property-tax-only, union shops         │
  │  └─ Marks is_excluded = TRUE with exclusion_reason                     │
  └────────────────────────────────┬────────────────────────────────────────┘
                                   │
                                   ▼
  ┌────────────────────┐
  │  companies table   │  ← Canonical deduplicated company records
  └────────────────────┘
```

---

## Enrichment Pipeline

Triggered per-company via **Enrich** button (`POST /api/v1/companies/{id}/enrich`).

```
  Company record
       │
       ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  STAGE 1 — Website Discovery                                             │
  │  Brave Search: "{name} {state} official website"                        │
  │  → Parses div.snippet links from static HTML response                   │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  │ website domain
                                  ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  STAGE 2 — Website Scraping                                              │
  │  httpx + BeautifulSoup → extracts text from p, li, h1–h3                │
  │  Max 5,000 characters of homepage content                               │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  │ scraped text
                         ┌────────┴────────┐
                         ▼                 ▼
  ┌──────────────────┐       ┌──────────────────────────┐
  │  STAGE 3         │       │  STAGE 4                 │
  │  Employee Count  │       │  Ownership Classification │
  │                  │       │                          │
  │  Regex patterns: │       │  Keyword matching:       │
  │  "over X staff"  │       │  public  → NYSE/NASDAQ   │
  │  "X+ employees"  │       │  pe_backed → "portfolio" │
  │  "team of X"     │       │  franchise → "franchise" │
  └────────┬─────────┘       └────────────┬─────────────┘
           │                              │
           ▼                              ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  STAGE 5 — Revenue from Employee Count  (highest confidence)             │
  │  Formula: $200k × employees ± 30%                                       │
  │  Example: 100 employees → $14M–$26M                                     │
  │  Only overwrites pipeline default (rev_max ≤ $10M)                      │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  │ (if no employee count)
                                  ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  STAGE 6 — Revenue from Ownership Type  (fallback)                       │
  │  pe_backed  → $15M–$150M                                                │
  │  public     → $50M–$500M                                                │
  │  franchise  → $5M–$50M                                                  │
  │  private    → stays at pipeline default ($3M–$10M)                      │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  │
                                  ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  STAGE 7 — Thesis Fit Score  (OpenAI)                                    │
  │  Input: name, state, services, ownership, revenue, scraped text          │
  │  Model: Fine-tuned GPT-4o-mini  (or zero-shot fallback)                 │
  │  Output: 0.00–1.00 acquisition fit score                                │
  └───────────────────────────────┬──────────────────────────────────────────┘
                                  │
                                  ▼
                      Persist all updates → DB
```

---

## AI Thesis Scoring

### How It Works

Every Enrich call scores the company against the M&A acquisition thesis using OpenAI.

**Scoring Factors**
| Factor | Weight | Details |
|---|---|---|
| Service portfolio | 40% | R&D Credits, Cost Seg, WOTC, Sales & Use Tax |
| Revenue range | 25% | Sweet spot: $10M–$100M |
| Ownership type | 25% | Private → PE-backed → Franchise → Public |
| Company profile | 10% | Inferred from name + scraped website text |

### Fine-Tuning Workflow

```
  ┌──────────────────────┐
  │  Click "Fine-tune    │   POST /pipeline/start-finetuning
  │  Model" in UI        │
  └──────────┬───────────┘
             │  (returns immediately; runs in background)
             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  PHASE 1 — Sampling                                                  │
  │  Query DB for 100 diverse companies:                                 │
  │   30 × (2+ services, private/PE-backed)   → expected high scores    │
  │   20 × (1 service,  private/PE-backed)    → expected medium scores  │
  │   10 × (franchise)                        → medium-low scores       │
  │   15 × (public)                           → lower scores            │
  │   25 × (0 services)                       → edge cases              │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  PHASE 2 — Labeling with GPT-4o  (~4–5 min)                         │
  │  For each company → call GPT-4o with detailed rubric                 │
  │  Concurrency: 3 simultaneous calls (30K TPM limit)                  │
  │  Retry: exponential backoff on 429 rate limits                       │
  │  Output: {"score": 0.75, "reason": "..."}  × 100 examples           │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  PHASE 3 — Upload JSONL                                              │
  │  Format 100 examples as fine-tuning JSONL:                          │
  │  {"messages": [system, user_profile, assistant_score]}              │
  │  Upload to OpenAI Files API                                          │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  PHASE 4 — OpenAI Fine-Tuning  (~15–30 min on OpenAI servers)       │
  │  Model: gpt-4o-mini-2024-07-18                                      │
  │  Job ID saved to backend/finetuning_job.json                        │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │  (frontend polls every 15s)
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  PHASE 5 — Model Saved                                               │
  │  fine_tuned_model ID written to finetuning_job.json                 │
  │  All future Enrich calls automatically use fine-tuned model         │
  │  FineTuneCard shows: "Fine-tuned GPT-4o-mini  ft:..."               │
  └──────────────────────────────────────────────────────────────────────┘
```

**Cost: ~$0.30 one-time. Per-inference cost unchanged (~$0.0002/call).**

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | ≥ 3.11 | Backend runtime |
| Node.js | ≥ 18 | Frontend build |
| PostgreSQL | ≥ 14 | Primary database |
| pip | latest | Python packages |
| npm | ≥ 9 | Frontend packages |

---

## Setup & Run

### 1. Clone the repository

```bash
git clone https://github.com/harshelke180502/ma-intelligence-platform
cd ma-intelligence-platform
```

### 2. Set up the database

```bash
# Create the PostgreSQL database
createdb ma_thesis

# Or in psql:
psql -c "CREATE DATABASE ma_thesis;"
```

### 3. Configure environment variables

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your values (see Environment Variables below)
```

### 4. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 5. Run database migrations

```bash
cd backend
alembic upgrade head
```

### 6. Start the backend server

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is now available at `http://localhost:8000`
Interactive docs: `http://localhost:8000/api/v1/docs`

### 7. Install frontend dependencies

```bash
cd frontend
npm install
```

### 8. Start the frontend dev server

```bash
cd frontend
npm run dev
```

The dashboard is now available at `http://localhost:5173`

### 9. Run your first data collection

In the dashboard, navigate to the pipeline trigger or call directly:

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{}'
```

This collects companies via Google Places, normalises, deduplicates, and classifies them. Expect 3,000–5,000 companies from a full run.

---

## Environment Variables

Create `backend/.env` with the following:

```env
# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://<user>@localhost:5432/ma_thesis

# ── Google Places (data collection) ─────────────────────────────────────────
# Get from: https://console.cloud.google.com → Places API
GOOGLE_PLACES_API_KEY=your_google_places_key

# ── OpenAI (thesis scoring + fine-tuning) ────────────────────────────────────
# Get from: https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_key

# ── Anthropic (optional, classification fallback) ────────────────────────────
ANTHROPIC_API_KEY=your_anthropic_key

# ── Application ──────────────────────────────────────────────────────────────
DEBUG=false
```

---

## Deployment

The platform is deployed for free using three managed services:

```
  ┌─────────────────────────┐     HTTPS / JSON      ┌──────────────────────────────┐
  │  Vercel (Frontend)      │ ◄───────────────────► │  Render (Backend)            │
  │                         │                       │                              │
  │  React + Vite           │                       │  FastAPI + Python 3.11       │
  │  Auto-deploys on push   │                       │  Auto-deploys on push        │
  │  to main branch         │                       │  to main branch              │
  └─────────────────────────┘                       └──────────────┬───────────────┘
                                                                   │
                                                                   │ asyncpg (TLS)
                                                                   ▼
                                                    ┌──────────────────────────────┐
                                                    │  Neon (PostgreSQL)           │
                                                    │                              │
                                                    │  Managed serverless Postgres │
                                                    │  Connection pooling enabled  │
                                                    │  Free tier: 512 MB storage   │
                                                    └──────────────────────────────┘
```

### Services Used

| Service | Plan | Purpose | URL |
|---|---|---|---|
| **Vercel** | Free | React frontend hosting + CDN | vercel.com |
| **Render** | Free | FastAPI backend (Python 3.11) | render.com |
| **Neon** | Free | Serverless PostgreSQL database | neon.tech |

### Environment Variables (Production)

Set these in the **Render** dashboard under Environment:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://<user>:<pass>@<host>/neondb?sslmode=require` |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `FRONTEND_URL` | `https://ma-intelligence-platform.vercel.app` |
| `GOOGLE_PLACES_API_KEY` | Your Google Places key |
| `ANTHROPIC_API_KEY` | Your Anthropic key |

Set this in the **Vercel** dashboard under Environment Variables:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://ma-intelligence-platform.onrender.com` |

> **Note:** The free Render plan spins down after 15 minutes of inactivity. The first request after idle may take ~30 seconds to wake up.

---

## API Reference

### Companies

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/companies` | Paginated, filterable company list |
| `GET` | `/api/v1/companies/{id}` | Full company detail with contacts |
| `PUT` | `/api/v1/companies/{id}` | Analyst correction (partial update) |
| `POST` | `/api/v1/companies/{id}/enrich` | Run 7-stage enrichment pipeline |

**Query parameters for `GET /companies`:**
- `sort` — `name`, `state`, `revenue_est_min`, `ownership_type`, `thesis_fit_score`
- `order` — `asc` / `desc`
- `page`, `limit` — pagination (max 200/page)
- `service` — filter by service key (`rd_credits`, `cost_seg`, `wotc`, `sales_use_tax`)
- `state` — filter by US state code

### KPIs

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/kpis` | All dashboard metrics in one call |

**Response includes:** total companies, ownership breakdown, top 10 states, avg revenue, enriched count, companies excluded.

### Pipeline

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/pipeline/run` | Run full data collection pipeline |
| `GET` | `/api/v1/pipeline/runs` | List all pipeline runs |
| `GET` | `/api/v1/pipeline/runs/{id}` | Status of a specific run |
| `POST` | `/api/v1/pipeline/apply-ownership-revenue` | Bulk-apply ownership-based revenue ranges |
| `POST` | `/api/v1/pipeline/start-finetuning` | Start GPT-4o-mini fine-tuning job |
| `GET` | `/api/v1/pipeline/finetuning-status` | Poll fine-tuning progress |

---

## Project Structure

```
M&A/
├── backend/
│   ├── .env                          # Environment config (not committed)
│   ├── requirements.txt              # Python dependencies
│   ├── finetuning_job.json           # Fine-tuning job state (auto-created)
│   ├── alembic/                      # Database migrations
│   │   └── versions/
│   │       └── *_initial_schema.py   # Creates all 5 tables
│   └── app/
│       ├── main.py                   # FastAPI app + router registration
│       ├── core/
│       │   ├── config.py             # Settings (pydantic-settings + .env)
│       │   └── database.py           # Async SQLAlchemy engine + session
│       ├── models/
│       │   ├── company.py            # Company ORM model (canonical record)
│       │   ├── contact.py            # Contact ORM model
│       │   ├── raw_record.py         # Raw collector payloads
│       │   ├── pipeline_run.py       # Pipeline execution tracking
│       │   └── thesis.py             # Investment thesis definition
│       ├── schemas/
│       │   ├── company.py            # CompanyList / CompanyOut / CompanyUpdate
│       │   └── kpi.py                # KPIResponse schema
│       ├── api/v1/
│       │   ├── companies.py          # CRUD + enrich endpoints
│       │   ├── kpis.py               # Aggregated dashboard metrics
│       │   └── pipeline.py           # Pipeline + fine-tuning endpoints
│       ├── pipeline/
│       │   ├── orchestrator.py       # Coordinates all pipeline stages
│       │   ├── normalizer.py         # Raw → canonical field extraction
│       │   ├── deduplicator.py       # Fuzzy + exact dedup
│       │   ├── classifier.py         # Thesis exclusion rules
│       │   └── collectors/
│       │       └── google_places.py  # Google Places API data collector
│       └── services/
│           ├── finetuning_service.py # Sample → label → upload → train
│           └── enrichment/
│               ├── enrichment_service.py    # 7-stage orchestrator
│               ├── website_finder.py        # Brave Search domain lookup
│               ├── website_scraper.py       # httpx + BeautifulSoup
│               ├── employee_estimator.py    # Regex headcount extraction
│               ├── ownership_classifier.py  # Keyword ownership detection
│               ├── revenue_estimator.py     # $200k/employee ± 30%
│               └── thesis_scorer.py         # OpenAI scoring (auto model select)
│
└── frontend/
    ├── vite.config.js                # Vite + /api proxy to :8000
    ├── package.json                  # React 18, Recharts, Axios, Tailwind
    └── src/
        ├── App.jsx                   # Root layout + KPI load + table key
        ├── api/client.js             # Axios instance + all API calls
        └── components/
            ├── KpiCards.jsx          # 4 metric cards (total, ownership, revenue, excluded)
            ├── ServicePieChart.jsx   # Recharts pie — service distribution
            ├── StateBarChart.jsx     # Recharts bar — top 10 states
            ├── CompaniesTable.jsx    # Sortable, filterable table + Enrich button
            ├── CompanyModal.jsx      # Detail drawer with thesis fit badge
            └── FineTuneCard.jsx      # Fine-tuning trigger + live progress polling
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend framework | React 18 + Vite |
| Styling | Tailwind CSS |
| Charts | Recharts |
| HTTP client | Axios |
| Backend framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 14+ |
| Migrations | Alembic |
| HTTP client (backend) | httpx |
| HTML parsing | BeautifulSoup4 + lxml |
| Fuzzy matching | rapidfuzz |
| AI — labeling | OpenAI GPT-4o |
| AI — inference | OpenAI GPT-4o-mini (fine-tuned) |
| Data collection | Google Places API |
| Web search | Brave Search (static HTML) |
