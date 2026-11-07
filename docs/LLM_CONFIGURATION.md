# LLM configuration and verification

Both localhost and Vercel support the same two connection modes:

1. Server configuration: set `ENABLE_LLM=true`, `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and optionally `ANTHROPIC_MODEL` (default `claude-haiku-4-5`). OpenAI uses `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` instead. Never put a provider key in public/static assets, Git, or a deployment archive.
2. Request configuration: use Connect AI to unlock a browser-encrypted key. Paired `provider` and `api_key` fields override the server provider for that request only. Refreshing locks the browser key. The local, Vercel sample, and OCI endpoints support this mode.

Local `.env` is loaded by `app.main`. Vercel does not inherit it: add the variables to the existing project's **Production** environment and redeploy. The production endpoint currently serves `deployment.vercel_api`; its health response reports whether OCI is connected. Configuring OCI alone does not configure the Vercel sample API.

`GET /health` reports a non-secret `llm` configuration object. `enabled` and `configured` describe settings, not provider connectivity. A successful `POST /chat/query` must return `composer: "llm"` and `llm.used: true` to prove a model composed that answer. The response also names the configured provider and model. `llm.state: "failed"` means a provider call or output validation failed; the answer then uses source evidence and the UI labels the fallback explicitly.

All supported answers with citations can use model composition, including structured lookups and assumptions. Calculations remain deterministic and their results are supplied as evidence. Unsupported requests, necessary clarification, and pure user-input calculations without document citations do not require a provider call. A missing key or provider failure preserves source-only answers.

## Verification on 8 November 2026

- Before changes: localhost successfully called Claude for a narrative question; structured queries bypassed it. Vercel returned deterministic responses without supplied credentials.
- A separate live Vercel diagnostic with the existing Claude key supplied for that request returned HTTP 200 and `composer: "llm"`. Its provider integration works; default requests lack an active provider connection. The key was not saved by this diagnostic.
- After changes: all ten golden-bank questions on localhost returned `composer: "llm"`, `llm.used: true`, and the expected answers. Raw responses are in `output/localhost-llm-verification.json`.
- Hosted production verification must be repeated after the Vercel production environment and deployment are updated. The local result is not proof of hosted activation.

To rerun the live checks, use `python3 scripts/check_live_llm.py BASE_URL --output output/llm-live-check.json` with the golden-bank JSON created by the evaluation task. This sends ten provider-backed queries when the target is configured and uses that provider's normal API billing.
