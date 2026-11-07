# Configuration and interview handbook

## Project in one minute

A Python DMS research workspace: upload a PDF, extract page text and tables, normalize financial facts, persist evidence, retrieve relevant passages, and attach page citations. Financial arithmetic uses Decimal. The custom browser UI supports light and dark themes.

## Request journey

Browser → same-origin Vercel Python proxy → HTTPS Caddy on OCI → FastAPI → report JSON/PDF and PostgreSQL pgvector. The proxy sets a Secure, HttpOnly, SameSite=Lax browser workspace cookie. It forwards the capability through X-Workspace. OCI hashes it into a private storage namespace; vector queries also filter by that namespace and document ID.

## Deployment inventory

GitHub: atharva2-0x/neuraNx-research-workspace, branch main. Vercel: team atharva2ox-gmailcoms-projects, project neuranx-fund-intelligence. Public URL: https://neuranx-fund-intelligence.vercel.app/. OCI: Mumbai, instance neuranx-fund-api, Oracle Linux 9, VM.Standard.E2.1.Micro, 1 GB RAM. Public IPv4: 92.4.81.209. Backend hostname: 92-4-81-209.sslip.io. Always Free availability and service continuity are not guaranteed.

## Why the outage happened

The Cloudflare quick tunnel used a temporary hostname that stopped resolving. It changes across restarts. The VM also logged an out-of-memory kill of dnf-makecache. Only the default ~498 MB swap was active after restart; the added swap had not been persisted in fstab. A shell loading successfully with Request failed (500) therefore indicated a backend connection failure.

## Reliability changes

Use stable IP-based DNS and automatic HTTPS in Caddy, rather than a temporary quick tunnel. Persist 2 GB extra swap through /etc/fstab. Disable the automatic dnf-makecache timer that exhausted memory; run security updates deliberately during maintenance. Persist the journal across reboot. systemd starts services at boot and restarts them after failures. A single small VM remains a single point of failure; production needs monitoring, backups, redundant capacity and a domain under your control.

## Ports and services

OCI subnet security list allows TCP 22, 80, 443. The OS firewall also permits HTTP/HTTPS. Caddy listens publicly on 80/443 and forwards to 127.0.0.1:8000. Uvicorn stays on loopback. PostgreSQL should accept only local connections, never public port 5432. Services: neuranx-api.service, caddy.service, postgresql.service. The old neuranx-tunnel.service can be disabled after stable HTTPS is verified.

## Files and secrets

Runtime directory: /opt/neuranx. Shared fictional evidence: evidence.json and sample-report.pdf. Private reports: private-data/<SHA256 workspace capability>/<document checksum prefix>.pdf and .json. Page images cache beside the PDF. Python packages: /opt/neuranx/.venv/lib/python3.9/site-packages. SSH user: opc. Local private SSH key: deployment/.secrets/neuranx-oci; never commit or share its contents. Provider keys belong in protected server environment files, never browser JavaScript or GitHub.

## Code map

ui/app.js handles navigation, upload, chat, citations and printable HTML export. app/extraction.py extracts and normalizes evidence. app/validation.py produces discrepancy findings. app/answering.py routes questions, calculates numeric results and selects cited passages. app/hosted_vector.py creates local neural embeddings and queries pgvector for hosted reports. deployment/private_api.py isolates browser workspaces and provides the hosted API. deployment/vercel_api.py forwards Vercel requests to OCI. scripts/build_frontend.py prepares public assets for Git deployment.

## Embeddings and pgvector

BGE-small-en-v1.5 generates 384-dimensional embeddings locally through FastEmbed/ONNX. Text chunks and vectors are persisted in PostgreSQL report_vectors. The primary key contains workspace, document_id, chunk_id. HNSW uses vector_cosine_ops; queries order by <=> cosine distance and filter workspace plus document. Chunk metadata retains source page and section. BM25 supplements vector retrieval. Numeric answers still use typed facts rather than embedding similarity. First model load/indexing is slower; cache and pre-index the sample before demo.

## What to say about RAG

Retrieval finds evidence; generation writes an answer from that evidence. Embeddings and a vector database satisfy requirement 4 only when active and verified. The optional OpenAI composer is disabled without a key, so requirement 5 is still pending until enabled and tested. Never present deterministic templates as LLM generation. An API key, ENABLE_LLM=true and an accessible model are needed. Provider calls send bounded passages externally and incur usage charges.

## Deploy and rollback

Push a commit to main to trigger the connected Vercel project. The root vercel.json builds scripts/build_frontend.py and serves public assets plus api/index.py. Changes to backend Python code must also be deployed to OCI; a frontend deployment does not automatically update that machine. Copy reviewed backend files to /opt/neuranx, restore SELinux labels, then restart neuranx-api. Use the Vercel deployment menu to promote a previous good deployment; retain a backend release backup before updating.

## Recovery checklist

1. Open /health on Vercel and directly on the backend. 2. SSH to opc@92.4.81.209. 3. Check systemctl status neuranx-api caddy postgresql. 4. Read journalctl -u neuranx-api -n 80 and journalctl -u caddy -n 80. 5. Check free -m, swapon --show, df -h, and journalctl -k for OOM messages. 6. Check curl http://127.0.0.1:8000/health. 7. If loopback works but HTTPS fails, inspect Caddy certificate logs and both firewall layers. 8. If direct HTTPS works but Vercel fails, inspect BACKEND_ORIGIN/backend.json and Vercel function logs. Avoid force reboot unless the OS is unresponsive.

## Interview questions

Why separate numeric and narrative routes? Decimal calculations are reproducible; narrative retrieval finds context. Why pgvector? It combines relational document authorization, metadata and vector search. Why HNSW? It accelerates approximate nearest-neighbor search, trading recall for latency and memory. Why not run everything on Vercel? Durable PDFs, model caches and background work need persistent storage/processes. What would you change for production? Authenticated accounts, durable queues, object storage, managed Postgres, backups, monitoring, rate limits and retrieval evaluation.

## Submission boundaries

The sample PDF is fictional: 50 pages, 49 tables, 346 observations, 13 findings. Arbitrary PDF table layouts and scanned images need broader parser/OCR evaluation. Private browser workspaces are capability-based isolation, not user accounts. Clearing cookies loses access. Do not promise zero downtime, universal document understanding, or tested LLM generation until those claims are verified.