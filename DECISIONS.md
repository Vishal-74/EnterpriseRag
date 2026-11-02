# Decisions

## D-001 Split hosting

The UI is a Next.js app intended for Vercel. The API is a long-running FastAPI process intended for Render. Document ingestion and agent runs continue after the HTTP handler returns, so the API is not a short-lived serverless function.

## D-002 Postgres and pgvector

Vectors live in the same database as users and documents. Local development uses the `pgvector/pgvector:pg16` image. A hosted deployment can use Supabase or any Postgres instance with the `vector` extension. The migration creates the extension and an HNSW cosine index.

## D-003 FastAPI, SQLAlchemy 2, Alembic

Routes are thin. Persistence uses async SQLAlchemy. Alembic uses a synchronous psycopg URL derived from `DATABASE_URL`.

## D-004 OpenAI primary, Claude fallback

Chat defaults to OpenAI. Timeout, HTTP 429, 5xx, and 401 fall back to Anthropic when that key is configured. A 401 fallback matters when the primary key is disabled. Embeddings stay on OpenAI `text-embedding-3-small` (1536 dimensions) because the vector column width is fixed.

## D-005 LangGraph agent

The agent is a LangGraph graph with plan, act, and finish nodes. Tools are `search_knowledge_base`, `analyze_documents`, `generate_report`, and `finish`. The graph stops at six steps, 45 seconds per tool, and 120 seconds overall.

## D-006 Chunking

Text chunks are 1000 characters with 150 characters of overlap. PDF chunks keep page spans. Markdown chunks keep the heading. CSV chunks cover 40 rows with 5 rows of overlap and repeat the header. Row numbers are the file's row numbers.

## D-007 Hybrid retrieval

A question is embedded and also searched with Postgres full text. The two lists are fused with reciprocal rank fusion (`k = 60`). A chunk is kept when cosine relevance is at least 0.32 or the keyword rank is at least 0.05. An optional model rerank can reorder the fused list. When nothing clears the gate, the product returns a fixed sentence and does not call the answer model.

## D-008 Memory

A conversation sends the last six messages plus a rolling summary, inside an 1800-token budget. The summary is refreshed after eight messages. Follow-up questions are rewritten into a standalone query. The first turn is not rewritten.

## D-009 Duplicate uploads

A file is identified by SHA-256 per user. A repeat upload returns HTTP 409 with the existing document id and status. A concurrent insert that loses the unique constraint returns the same existing document and does not start a second job.

## D-010 Background processing

The API process schedules ingestion and agent work with `asyncio` tasks. Tests run the same jobs inline so the next request sees the result. A document stuck in `processing` longer than 15 minutes can be reprocessed.

## D-011 Prompt injection

Retrieved text is wrapped as untrusted data. Lines that tell the model to ignore instructions, prompts, or rules are replaced before they enter the prompt. The agent planner can only emit the registered tool names. Report evidence is taken from tool observations, not from a free-form finding the model invents without those observations.

## D-012 Evaluation

`backend/eval` holds an original corpus and 28 questions. `run_eval.py` calls the real ingestion and chat services. It refuses to write `results/latest.json` when the OpenAI key is absent. Scores in this repository are not filled in by hand.

## D-013 Browser session

The Next.js server stores the API JWT in the httpOnly cookie `ei_session` (`SameSite=Lax`, `Secure` in production). The browser calls `/api/backend/...`, and that route adds the bearer token. Provider preference is `localStorage` only.

## D-014 Answer and embedding cache

Embedding cache keys are a hash of model and text. The stored row does not contain the source text. Answer cache keys include the user, prompt version, provider, rewritten query, and a fingerprint of ready documents. Entries expire after seven days.

## D-015 Rate limits

Login and chat limits use an in-process sliding window. They reset on process restart and are not shared across instances.

## D-016 Agent document scope

Document ids on an agent run come from the user request. The planner cannot widen that scope.

## D-017 Hugging Face fallback provider

A chat provider using the OpenAI-compatible SDK endpoint on Hugging Face (`HF_BASE_URL`, `HF_TOKEN`, `HF_MODEL_ID`). Registered as fallback in `LLMRouter`. Automatically falls back on 408 (timeout), 429 (rate limit), 5xx server errors, or 401 configuration errors, logging each attempt to `usage_logs`.

## D-018 Gemini Primary Provider and Dual-Provider Fallback

Per project requirements, OpenAI and Anthropic were decoupled from the active routing flow. Google Gemini (`gemini-flash-lite-latest` for chat and `gemini-embedding-001` with `outputDimensionality: 1536` for vectors) operates as the primary provider for all chat, query rewriting, reranking, verification, and agent workflows. Hugging Face serves as the registered fallback client. Exponential backoff with jitter handles transient rate limits before cascading to fallback.

## Local database

Docker Compose publishes Postgres on port 5432 with user `postgres`, password `postgres`, and database `enterprise_intel`. `docker/init.sql` also creates `enterprise_intel_test`.

## Bugs found while building

- Importing `SessionLocal` by name captured `None` before `init_engine`. Workers then failed before they could mark a document. Jobs now read the module global.
- Building `DocumentRead` with `from_attributes` lazy-loaded `updated_at` and `chunks` and raised `MissingGreenlet`. The schema now copies scalar columns.
- `expire_all()` then reading `run.id` lazy-loaded outside a greenlet. The agent service copies the ids first.
- The injection pattern required a single word between "ignore" and "instructions", so "Ignore all previous instructions" passed through. The pattern now allows a short span.
- A unit test constructed `Chunk` rows without ids. The default is applied on flush, so the rank map collided. The test assigns ids.
- Alembic's config path was relative to the process working directory. The integration fixture passes the path next to `backend/alembic.ini`.
