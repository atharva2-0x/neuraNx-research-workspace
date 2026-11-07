# Five-minute interview walkthrough

## Start with the customer’s decision

“An analyst needs to answer questions about a fund report quickly, but a plausible financial answer can still be wrong. I built a workspace that keeps the reported number, the calculation, and the evidence separately inspectable. When the report contradicts itself, the system exposes the conflict.”

Before deploying for a customer, ask who makes decisions from these answers, which source is authoritative, what an unacceptable wrong answer looks like, whether documents may leave their environment, and how they want discrepancies reviewed.

## Demo 1: A simple question with inspectable evidence

On **Overview**, explain that the solid NAV line is historical and the dashed line is a forecast. Switch between light and dark themes. Open **Ask the report** and ask:

> How did the fund perform against the benchmark in 2025?

Show 15.6% versus 13.4%, the calculated 2.20 percentage-point difference, and the formula. Open its page 9 citation. Explain that the numbers came from the table and the arithmetic came from Python Decimal, independently of the optional language model.

## Demo 2: Correct arithmetic cannot repair conflicting evidence

Ask:

> Which year had the highest annual return?

The reported answer is 2021 at 18.0%, with a warning. Ask:

> Does the 2021 NAV movement agree with the reported return?

Show 100.0 → 112.0 implies 12.00%. Both the reported return and computed value remain visible. Do not claim the report is necessarily wrong: distributions, timing, or a different return methodology could explain a mismatch, but the report does not provide that explanation.

## Demo 3: The source is more complicated than the brief

Ask:

> Does the 2025 annual NAV agree with the quarterly section?

The annual value is 192.9 on page 9. Pages 16, 19, 22, and 25 have Q4 closing values 194.7, 192.5, 194.0, and 195.5. Open two citations. Explain why selecting the first page, averaging versions, or allowing a vector search result to become numeric authority would all hide the ambiguity.

Then ask:

> Compare Q2 fund and benchmark returns

The assistant asks for the year. With 2025 specified, it presents all four page-specific versions. This is a useful product behavior: asking for clarification can be more accurate than producing a confident answer.

## A useful engineering discovery

The planning notes suggested a chart-scale issue because the highest labeled tick is 360 while the 2030 NAV is 390.3. Inspect the chart on page 40: its axis extends beyond that tick, to approximately 450. Native vector geometry confirms this. The system records an informational note instead of manufacturing a warning. Explain that you validated the brief against the customer’s actual artifact.

The plan also approximated the quarterly compounded return at 16.8%. Exact Decimal arithmetic gives 16.7385249392%, displayed as 16.74%. The PDF’s 15.8% full-year value is expressly a simple sum. Methodological differences should not be mislabeled as arithmetic errors.

## Explain the architecture

The application is a modular Python service with a browser UI. Ingestion preserves raw page evidence, normalizes typed facts, runs independent validation checks, indexes narrative passages, and commits the result. The query router separates numeric lookups, narrative retrieval, and reconciliation. Calculations have their own persisted inputs, formula, result, and source fact IDs.

The local default is SQLite and BM25 retrieval. PostgreSQL and pgvector are available through the optional deployment path, and provider embeddings/LLM composition are opt-in. This makes the demo reproducible without credentials while leaving the boundaries explicit. Live provider and Docker paths have not been exercised here.

## Be candid about scope

The table parser is validated against this report, not every possible PDF. Native chart inspection works here because labels and axes are embedded in the PDF. Arbitrary chart-image OCR still needs a dedicated evaluation set. The current worker is process-local and the local app has no user authentication.

For a customer deployment, prioritize authorization and tenant isolation, a durable job queue, retention controls, a labeled question/evidence evaluation set, and monitoring for extraction failures, unsupported answers, citation quality, latency, and provider cost. Add infrastructure in response to workload and risk rather than as a substitute for validated data.
