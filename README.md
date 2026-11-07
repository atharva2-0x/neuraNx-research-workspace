# NeuraNx DMS — RAG-Powered Document Management Chatbot

A Python financial document research workspace for the NeuraNx DMS assignment. Upload reports, inspect extracted facts and validation findings, ask questions with source citations, and export findings. The sample ABC Company Fund report is fictional.

## Cloud hosted application

The public UI is served by Vercel at [neuranx-fund-intelligence.vercel.app](https://neuranx-fund-intelligence.vercel.app/). Its API proxy forwards document and question requests over HTTPS to the persistent OCI service at `92-4-81-209.sslip.io`, with Caddy providing TLS. Uvicorn and PostgreSQL remain private on the VM. Uploads and extracted evidence persist on OCI; Vercel's serverless filesystem is not used for durable data.

Hosted uploads are limited to 4 MB, 200 pages, and 10 reports per browser workspace. The workspace is identified by a secure browser cookie, so clearing cookies removes access to those private reports. The fictional sample is shared and read-only. OCI changes must be deployed and the `neuranx-api` service restarted separately; pushing to `main` deploys the Vercel UI and proxy, not the OCI backend. See [deployment operations](deployment/README.md) and the [configuration and recovery handbook](docs/CONFIGURATION_HANDBOOK.md).

The OCI service can enable local BGE-small embeddings with PostgreSQL/pgvector using `HOSTED_VECTORS=true`; its live status is available from `/health`. LLM composition requires a supported provider and a server-side API key. Hosted and local environment variables are independent. Do not put secrets in frontend code or commit them.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web UI (Vanilla JS)                      │
│  Upload PDF  │  Browse Documents  │  Chat / Ask Questions       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI Backend (Python)                      │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  PDF Upload  │  │  Extraction  │  │   RAG Pipeline         │ │
│  │  & Ingestion │→ │  pdfplumber  │→ │  BM25 + Vector Search  │ │
│  └─────────────┘  │  + Tesseract │  │  + LLM (Claude / GPT)  │ │
│                    └──────────────┘  └────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Embeddings (choose one):                                 │  │
│  │   • local: BAAI/bge-small-en-v1.5, 384-dim, CPU, no key  │  │
│  │   • openai: text-embedding-3-small, 1536-dim, API key     │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│         PostgreSQL 16 + pgvector (Docker container)             │
│  • Documents, facts, chunks, validation findings                │
│  • HNSW vector index for cosine similarity search               │
└─────────────────────────────────────────────────────────────────┘
```

## Features

| Requirement | Implementation |
|---|---|
| **Document Upload** | PDF upload via web UI or API; validates format, size (≤25 MB), page count (≤200) |
| **Document Extraction & Structuring** | pdfplumber extracts text, tables, geometry; Tesseract OCR for scanned pages; structured facts with source provenance |
| **Knowledge Base Creation** | Facts, chunks, and validation findings stored in PostgreSQL with full audit trail |
| **Embedding Model + Vector DB** | Local BGE-small (384-dim) or OpenAI (1536-dim) + PostgreSQL pgvector with HNSW index |
| **RAG with LLM** | Hybrid retrieval (BM25 keyword + vector cosine) → Anthropic Claude or OpenAI GPT for evidence-grounded answers |
| **Chatbot Interface** | Web UI with chat panel, suggested prompts, source citations, and evidence drawer |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x
- **LLM**: Anthropic Claude (default) *or* OpenAI GPT — switchable via `LLM_PROVIDER`
- **Embeddings**: Local BGE-small via fastembed (default) *or* OpenAI — switchable via `EMBEDDING_PROVIDER`
- **Vector DB**: PostgreSQL 16 + pgvector (HNSW index, cosine similarity)
- **PDF Processing**: pdfplumber + Tesseract OCR (optional)
- **Frontend**: Vanilla HTML/CSS/JS with responsive design, dark mode

---

## Run locally

### Prerequisites

- Python 3.11 or newer (Python 3.12 recommended)
- Optional: Docker and Docker Compose v2 for PostgreSQL/pgvector

### 1. Create a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,fast-pdf]'
```

SQLite at `data/fund.db` is the default, so basic local use needs no database server or provider key. Start the app bound to your own machine:

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). To use the sample locally, place its PDF in `data/input/` (that folder is not included in a fresh clone); PDFs there are ingested at startup. Or upload one using **Add report**. Local uploads use the full app's default 25 MB limit and a 200-page maximum.

For optional configuration, copy `.env.example` to `.env`. `DATABASE_URL` and `DATA_DIR` choose the local database and storage path. LLM composition requires `ENABLE_LLM=true`, a supported `LLM_PROVIDER`, and its API key. OpenAI embeddings require `ENABLE_EMBEDDINGS=true` and `OPENAI_API_KEY`; these differ from OCI's BGE/pgvector configuration. Restart the app after changing `.env`.

### 2. Optional: Docker with PostgreSQL/pgvector

```bash
docker compose up --build
```

This starts the FastAPI app and PostgreSQL with pgvector. The app is reachable only from your computer at http://127.0.0.1:8000. App files persist under `data/`; PostgreSQL data persists in a Docker volume. `docker compose down` preserves that volume; `docker compose down -v` deletes it.

Compose uses local development database credentials. Provider keys are optional and needed only for provider-generated explanations.

### 3. Upload a document and chat

1. Click **"Add report"** in the UI
2. Upload any PDF document (up to 25 MB, up to 200 pages)
3. Wait for extraction to complete (progress bar shown)
4. Navigate to **"Ask the report"** tab
5. Type questions or use suggested prompts
6. Answers come with source citations you can click to verify

---

## Local Development (without Docker)

`requirements.txt` is intentionally limited to the Vercel serverless API dependencies. For local development, `pip install -e ".[local,dev]"` installs the full extraction, database, and embedding stack declared in `pyproject.toml`.

### Prerequisites

- Python 3.11+
- PostgreSQL 16 with pgvector extension (or use the Docker DB)

### Option A: Use Docker only for PostgreSQL

```bash
# Start just the database
docker compose up db -d

# Install Python dependencies
pip install -e ".[local,dev]"

# Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Option B: Full local setup

```bash
# 1. Install PostgreSQL 16 with pgvector extension
# macOS: brew install postgresql@16 && brew install pgvector
# Ubuntu: sudo apt install postgresql-16-pgvector

# 2. Create database
createdb fund
psql fund -c "CREATE EXTENSION vector;"

# 3. Set DATABASE_URL in .env
# DATABASE_URL=postgresql+psycopg://youruser:yourpass@localhost:5432/fund

# 4. Install dependencies
pip install -e ".[local,dev]"

# 5. Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### SQLite fallback (no PostgreSQL needed)

For quick testing without PostgreSQL (vector search uses in-memory cosine):

```bash
# In .env, set:
DATABASE_URL=sqlite:///data/fund.db

pip install -e ".[local]"
uvicorn app.main:app --reload
```

---

## Provider Configuration

### LLM Provider

| Setting | `LLM_PROVIDER=anthropic` (default) | `LLM_PROVIDER=openai` |
|---|---|---|
| API Key env var | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` |
| Model env var | `ANTHROPIC_MODEL` | `OPENAI_MODEL` |
| Default model | `claude-sonnet-4-20250514` | `gpt-4.1-mini` |

### Embedding Provider

| Setting | `EMBEDDING_PROVIDER=local` (default) | `EMBEDDING_PROVIDER=openai` |
|---|---|---|
| Model | BAAI/bge-small-en-v1.5 (fastembed) | text-embedding-3-small |
| Dimensions | 384 | 1536 |
| API Key needed | No (runs on CPU) | Yes (`OPENAI_API_KEY`) |

> **Note:** If you switch embedding providers after documents have been indexed, drop the `semantic_vectors` table and re-upload documents so vectors are regenerated with the new dimensions.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check (DB connectivity) |
| `GET` | `/documents` | List all uploaded documents |
| `POST` | `/documents/upload` | Upload a PDF document |
| `GET` | `/documents/{id}` | Get document metadata |
| `GET` | `/documents/{id}/overview` | Full document overview with facts |
| `GET` | `/documents/{id}/metrics` | Query extracted metrics/facts |
| `GET` | `/documents/{id}/validation` | Data quality findings |
| `GET` | `/documents/{id}/pages/{n}` | Get page-level extraction data |
| `GET` | `/documents/{id}/pages/{n}/image` | Render page as PNG |
| `GET` | `/documents/{id}/file` | Download original PDF |
| `POST` | `/chat/query` | **Ask a question about a document** |
| `POST` | `/documents/{id}/retry` | Retry failed extraction |

### Chat API Example

```bash
curl -X POST http://localhost:8000/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "your-document-id",
    "question": "What are the key findings in this document?"
  }'
```

Response includes:
- `answer` — evidence-grounded response
- `sources` — page references with excerpts
- `calculations` — any deterministic calculations performed
- `warnings` — data quality caveats
- `query_type` — routing method (structured/semantic/hybrid)

---

## How the RAG Pipeline Works

### 1. Document Ingestion
```
PDF Upload → Page Extraction (pdfplumber) → Table Normalization
           → Fact Structuring → Validation Checks → Chunk Indexing
           → Vector Embedding (local or OpenAI) → pgvector Storage
```

### 2. Query Processing
```
User Question → Intent Classification (regex-based routing)
             → Structured Lookup (for numeric/metric queries)
             → BM25 Keyword Retrieval (for semantic queries)
             → Vector Similarity Search (pgvector cosine)
             → Passage Fusion (hybrid ranking)
             → LLM Composition (Claude or GPT, evidence-constrained)
             → Citation Validation → Response
```

### 3. Answer Safety
- The LLM is instructed to answer **only** from supplied passages
- Citation pages are validated against actual source pages
- New numeric values not present in evidence are rejected
- Forecasts and synthetic data are disclosed with warnings

---

## All Configuration Variables

| Environment Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/fund.db` | Database connection string |
| `LLM_PROVIDER` | `anthropic` | LLM provider: `anthropic` or `openai` |
| `EMBEDDING_PROVIDER` | `local` | Embedding provider: `local` or `openai` |
| `ANTHROPIC_API_KEY` | *(required for Anthropic)* | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model |
| `OPENAI_API_KEY` | *(required for OpenAI)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4.1-mini` | GPT model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `OPENAI_EMBEDDING_DIM` | `1536` | OpenAI embedding dimensions |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model name |
| `EMBEDDING_DIM` | `384` | Local embedding dimensions |
| `ENABLE_LLM` | `true` | Enable LLM answer composition |
| `ENABLE_EMBEDDINGS` | `true` | Enable vector search |
| `MAX_UPLOAD_MB` | `25` | Maximum PDF upload size |
| `DATA_DIR` | `data` | Directory for PDFs and processed output |

---

## Project Structure

```
neuraNx-research-workspace/
├── app/
│   ├── main.py           # FastAPI application, routes, lifespan
│   ├── provider.py        # Multi-provider LLM + embedding abstraction
│   ├── vector.py          # pgvector semantic search (384 or 1536-dim)
│   ├── hosted_vector.py   # Hosted pgvector with fastembed (legacy)
│   ├── retrieval.py       # BM25 keyword retrieval + cosine utils
│   ├── answering.py       # Query routing and answer composition
│   ├── extraction.py      # PDF text/table extraction (pdfplumber)
│   ├── pipeline.py        # Ingestion pipeline orchestration
│   ├── db.py              # SQLAlchemy models and database setup
│   ├── models.py          # Pydantic schemas (Fact, Source, Query)
│   ├── validation.py      # Data quality checks
│   ├── calculations.py    # Decimal-safe arithmetic
│   └── ingest.py          # CLI ingestion entry point
├── ui/
│   ├── index.html         # Single-page application shell
│   ├── app.js             # Client-side rendering and state
│   └── style.css          # Responsive design with dark mode
├── tests/
│   ├── conftest.py
│   ├── test_core.py
│   └── test_api.py
├── docker-compose.yml     # PostgreSQL (pgvector) + App
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── .env                   # Configuration (add your API key here)
└── README.md
```

---

## Running Tests

```bash
pip install -e ".[local,dev]"
pytest -v
```

---

## License

This project was developed as a technical assessment for NeuraNx.ai.

## Chat quality checks

Chat responses support safe Markdown headings, lists and comparison tables. Quarterly
answers retain each conflicting source version in its own row, with arithmetic in
an expandable section. **New chat** clears the active document’s conversation.
Relative requests such as “last two years” use the latest historical dates in the
uploaded report, rather than today’s date or forecast years. Semantic paraphrases
can reach the configured model without requiring literal keyword overlap.

Run the source-labelled financial regression suite after ingesting the supplied
ABC Company Fund sample into the database used by the command:

```bash
python -m scripts.evaluate_questions
```

The command disables paid model and embedding calls by default. It writes
`output/evaluation.json` with per-case results and these separate metrics:

- Citation precision and recall against manually verified relevant pages.
- Answer accuracy as coverage of expected source-verified claims.
- Raw BM25 page precision and recall at up to four retrieved chunks, measured
  before structured routing and final citation selection.

The BM25 metric is a baseline across the labelled questions, including questions
answered by structured lookup; it is not the hybrid pipeline’s overall precision.
Expected-claim coverage does not measure every possible unsupported statement.
Use `python -m scripts.evaluate_questions --live` to explicitly evaluate the
configured providers (may incur provider charges). Run `pytest -q` for isolated
regressions, including relative dates, quarterly versions and paraphrased retrieval.

### Dashboard motion and conversation history

The first overview visit for each report in a page session reveals the NAV series,
animates the allocation bars, and rolls the headline numbers into their reported
values. Reduced-motion preferences show the final values immediately.

The chat workspace keeps conversations in a right-hand history pane (a horizontal
history list on phones). New chat preserves previous conversations. History is
saved in this browser’s local storage, separated by document; it is not synced
between devices. Fast responses have a one-second minimum presentation time, with
one API request per question and no artificial delay added to slower responses.
Source notes remain available in an expandable section below each answer.

Run the browser-state checks without a browser installation or paid requests:

```bash
node --test tests/ui.test.cjs
```
