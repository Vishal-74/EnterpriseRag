# Development report

Meridian was implemented in Cursor from the enterprise intelligence build plan. The work covered the API, the Next.js UI, the sample corpus, and the evaluation runner.

## What was validated

- `ruff`, `mypy`, and `pytest` pass. Integration tests run against local Postgres with pgvector and scripted provider doubles. 29 tests passed.
- The Next.js app lints and builds. In the browser, registration reaches a dashboard of zeros, documents show an empty state, a question returns “The embedding provider is unavailable.”, an agent run is stored as failed when no provider key is set, the activity log shows those provider errors, settings shows the account email, logout returns to sign-in, and `/dashboard` then redirects to `/login`.
- HTTP checks covered a bad password, a missing token, duplicate upload (409), a corrupt PDF marked failed, a text upload marked failed with the missing-key message, cross-user document access (404), and the cookie proxy.
- `backend/eval/run_eval.py` was not given a provider key, so `docs/evaluation_report.md` contains no score table.

## What was not done

- The app was not deployed to Vercel, Render, or Supabase. `render.yaml` and `backend/Dockerfile` are the deployment definitions.
- No demo video was recorded.
- No evaluation JSON was written by hand.

## Product behavior without keys

Registration, login, document listing, and the dashboard work. An upload is stored, the worker calls the embedder, and the document becomes `failed` with a message that names the missing OpenAI key. Reprocess retries that job. Chat returns a provider error instead of a fabricated answer.

## Review notes

- Services stay separate: ingestion, retrieval, RAG, memory, chat, agent, metrics, and the LLM router.
- The rate limiter and the job dispatcher are in-process. More than one API instance would not share them.
- The chat document fingerprint lists at most 500 ready documents.
- Answer caching is exact on the rewritten query and corpus fingerprint.
