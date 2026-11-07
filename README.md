# Fund Intelligence

A Python financial document research workspace for the NeuraNX DMS chatbot assignment. Upload a PDF, inspect its performance tables, ask questions, and follow an answer back to the original page. The interface includes persistent light and dark themes, responsive navigation, a NAV chart with a clearly separated forecast region, and an evidence drawer.

[Live application](https://neuranx-fund-intelligence.vercel.app/) · [HTML presentation](https://neuranx-fund-intelligence.vercel.app/deck.html)

Vercel serves the interface and forwards API requests to an OCI server through a Cloudflare demo tunnel. Hosted uploads use private browser workspaces (4 MB, 200 pages, 10 reports per workspace); clearing browser cookies loses access. Original PDFs and extracted evidence persist on the OCI disk. The shared fictional sample is read-only. Export findings opens a formatted report with Print / Save PDF and Download HTML. See [deployment notes](deployment/README.md).

## Assignment status

Document upload, structured extraction, persisted knowledge storage, and a document-grounded chatbot interface are implemented. **The live demo does not yet fully satisfy the assignment:** embeddings/vector search and LLM generation are disabled. Provider and PostgreSQL/pgvector adapters exist in the local application but have not been verified against live services. To complete requirements 4–5, configure a provider key, enable both flags, run PostgreSQL/pgvector, and verify end-to-end retrieval and generation; deploy that database-backed pipeline if these features must work on the public URL. The hosted lightweight API currently stores JSON evidence and uses BM25, so enabling an embedding flag alone does not deploy pgvector.

## Technology

Python, FastAPI, Uvicorn, Pydantic, SQLAlchemy, SQLite; optional PostgreSQL/pgvector and OpenAI provider adapters; pdfplumber/PDFium; BM25 and Decimal arithmetic; HTML/CSS/vanilla JavaScript/SVG; Vercel, OCI, Cloudflare tunnel, systemd; pytest and Docker Compose.

The supplied **ABC Company Fund** report is fictional. Source values, derived calculations, and unresolved discrepancies are kept separate.

## Run locally

Python 3.11 or newer is required; Python 3.12 is recommended for PDF library compatibility.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [the workspace](http://127.0.0.1:8000) or [interactive API documentation](http://127.0.0.1:8000/docs).

The supplied PDF has been copied into `data/input/`, which is excluded from version control. On startup, new PDFs in that folder are ingested automatically. Alternatively, use **Add report** in the UI. No provider account or API key is needed for the offline demo.

If you clone this project elsewhere, add the PDF yourself; source files and generated extraction records are deliberately not committed. To ingest explicitly:

```sh
python -m app.ingest data/input/ABC_Company_Fund_Performance_Report_50_Pages.pdf
# Re-run the parser and validation rules against the retained original:
python -m app.ingest data/input/ABC_Company_Fund_Performance_Report_50_Pages.pdf --reprocess
```

Reprocessing replaces normalized records and resets finding review states; it preserves the uploaded PDF. Identical uploads reuse the document checksum and do not duplicate facts.

## What is implemented

- PDF signature, type, 25 MB size, encryption/readability, and 200-page limit checks.
- Background ingestion with progress, visible failure state, explicit retry, and checksum deduplication.
- Page text, original PDF, tables, individual cell coordinates, raw numeric tokens, source filenames, and extraction methods retained.
- Typed annual, quarterly, allocation, and forecast observations. The table adapters match headers instead of assuming fixed page numbers.
- Decimal arithmetic for benchmark gaps, NAV growth, CAGR, and periodic return compounding, with persisted formulas and inputs.
- Checks for NAV/return mismatch, contradictory quarterly versions, quarterly NAV continuity, annual/quarterly reconciliation, simple-sum conventions, distribution totals, unresolved currency glyphs, repeated observations, and native chart geometry.
- Structured numeric routing, page-aware BM25 narrative retrieval, explicit clarification for ambiguous quarterly questions, and unsupported-question handling.
- Optional embedding search and evidence-constrained LLM explanations behind environment flags. Default operation is deterministic and offline.
- SQLite for the local demo, or PostgreSQL through Docker Compose; normalized facts, chunks, findings, calculations, and query telemetry have separate tables.
- Source-page images, raw extraction inspection, persistent finding review states, and a complete JSON evidence export.
- Request IDs and structured request telemetry. Query logs store route, page IDs, and timing, without question text or secrets.

## Verified against the supplied PDF

The current extraction yields **50 pages, 49 tables, 346 observations, and 13 findings**. The findings comprise eight warnings and five informational notes. Each repeated observation keeps its own provenance.

- Page 9 reports the 2025 NAV of **192.9**, return of **15.6%**, and benchmark return of **13.4%**. The deterministic benchmark gap is **2.20 percentage points**.
- Page 5 reports a 2021 return of **18.0%**, while NAV moves from **100.0** on page 4 to **112.0** on page 5: an implied **12.00%** change. The report does not explain a reconciliation.
- The 2025 quarterly pages 16, 19, 22, and 25 have four different Q4 closing values: **194.7, 192.5, 194.0, and 195.5**. None equals the annual-section NAV of **192.9**. All versions are shown.
- The quarterly inputs **3.1%, 5.2%, 4.7%, 2.8%** compound to **16.7385249392%**, rounded to **16.74%**; their sum is **15.8%**. The PDF explicitly labels its full-year total as a simple sum, so this convention is reported as a note rather than a source arithmetic error.
- The forecast chart’s highest labeled tick is **360**, but its axis extends to approximately **450**. The **390.3** forecast is within the chart range. Comparing the table only to the highest tick would produce a false discrepancy.
- The currency glyph is a square in the original PDF and a dingbat `n` in extracted text. The application retains **NAV units** and **crore**, and does not guess INR or another currency.

These verified observations supersede approximate or illustrative examples in the supplied planning documents.

## Architecture and trade-offs

The browser UI and FastAPI run as one application. Uploads enter a background pipeline: extract → normalize → validate → index → persist. Numeric questions read typed source observations and use Python `Decimal`. Narrative questions retrieve bounded passages with page metadata. The answer layer attaches existing provenance and relevant warnings.

The implementation deliberately uses a custom HTML/CSS/JavaScript interface instead of the plan’s suggested Streamlit interface, to support the requested visual design and both themes. It uses pdfplumber plus PDFium for table extraction, native text/geometry inspection, and page rendering. PyMuPDF is available as an optional dependency rather than required for this report.

The default database is SQLite to make the interview demo easy to run. SQLAlchemy supplies the same repository models for PostgreSQL. Numeric values use a `NUMERIC` column and preserve their original token in a separate JSON evidence record. Full page artifacts remain available for audit and parser improvements.

The offline narrative path is **BM25 keyword retrieval**, not neural semantic search. It displays relevant source passages rather than claiming an LLM generated an answer. Optional embeddings use cosine ranking locally, and a true pgvector HNSW index with document-filtered cosine-distance search on PostgreSQL. No vector path is claimed to be tested against a live provider in this setup.

Documents and questions are treated as untrusted input. The model composer has no tools, receives bounded evidence, uses a strict response schema, and rejects citations or numeric tokens absent from the evidence. These checks constrain output but do not prove that a model paraphrase is entailed. A production deployment still needs evaluation and human review for material decisions.

## Optional provider configuration

Copy `.env.example` to `.env`, supply your own `OPENAI_API_KEY`, and enable the capabilities you want:

```dotenv
ENABLE_LLM=true
ENABLE_EMBEDDINGS=true
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

These options send selected document passages to OpenAI and may incur API costs. They remain disabled by default. Numeric lookups and arithmetic stay deterministic even when the explanation provider is enabled. Provider failures fall back to source passages with an explicit warning. Embeddings are generated lazily on the first narrative query and persisted for subsequent queries. An embedding failure falls back to BM25.

The adapter follows the official [Responses structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses) and [Embeddings API](https://developers.openai.com/api/reference/resources/embeddings/methods/create). Model access depends on your provider account. Live provider calls have not been exercised here.

## Docker and PostgreSQL

```sh
docker compose up --build
```

This starts the app and PostgreSQL with pgvector. The app binds to loopback on your computer; source files and extracted artifacts persist under `data/`. The container includes Tesseract for scanned-page fallback. The database credentials in Compose are local development defaults. Docker execution has not been verified on this machine.

## Tests and evaluation

```sh
python -m pytest -q -p no:asyncio
python -m scripts.evaluate_questions
```

The test suite covers normalization, source immutability, units and geometry, Decimal calculations, retrieval provenance, the real report’s known facts, all conflicting quarterly versions, unsupported requests, provider fallback, upload validation, new and duplicate uploads, document isolation, API behavior, source rendering, persisted review state, and evidence exports.

Real-report integration tests use the PDF under `data/input/`. They are explicitly skipped if it is missing. Core tests are self-contained. The optional `-p no:asyncio` disables an unrelated globally installed test plugin that emits Python 3.14 deprecation warnings.

The evaluation script writes a machine-readable result to `output/evaluation.json`. See [the interview walkthrough](docs/INTERVIEW_GUIDE.md) for a five-minute demo and deployment discussion.

## API

- `POST /documents/upload` — multipart PDF upload; returns a document ID and ingestion state.
- `GET /documents` — available documents.
- `GET /documents/{id}` and `/status` — document state and progress.
- `GET /documents/{id}/overview` — UI summary with underlying observations.
- `GET /documents/{id}/metrics` — facts; optional `metric`, `period`, and `classification` filters.
- `GET /documents/{id}/validation` — findings and source links.
- `PATCH /documents/{id}/validation/{issue}` — mark reviewed or reopen; never changes source values.
- `GET /documents/{id}/pages/{n}` and `/image` — raw extraction and original-page rendering.
- `GET /documents/{id}/file` and `/export` — original PDF and JSON evidence report.
- `POST /documents/{id}/retry` — retry failed extraction.
- `POST /chat/query` — `{ "document_id": "…", "question": "…" }`.
- `GET /health` — database connectivity and pipeline version.

## Current limits and production path

The local application should remain bound to `127.0.0.1`. The hosted interview demo uses cookie-based browser isolation, rather than user accounts. A customer deployment needs authentication, per-tenant authorization on every document query, encryption/retention policies, rate limits, durable jobs, and operational monitoring.

FastAPI background tasks are not a durable queue. If the app stops during ingestion, the next startup marks that job as interrupted and offers retry from the retained original. Move ingestion to a durable worker when concurrent customer workloads justify it.

Extraction adapters are validated for this report’s table layouts. Other layouts may yield narrative text without structured facts; the app does not invent the missing records. Native PDF labels and vector geometry support this report’s chart cross-check. Arbitrary raster chart understanding, numeric pie-slice measurement, and robust multi-column OCR are not claimed. On low-text pages, Tesseract is used only if installed; otherwise the page is flagged. Tesseract is not installed in the current local environment, and the supplied report does not require it.

No confidential source data is published or uploaded to a provider in the default configuration. Uploaded files, the database, and extraction artifacts are excluded from version control.

## Design credit

UI craft guidance: [Unslop](https://github.com/heydamir/unslop), created by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)), CC BY 4.0. The project follows the approved research-workspace direction with quiet neutral surfaces, one chart accent, tabular figures, evidence references, and matched themes.
