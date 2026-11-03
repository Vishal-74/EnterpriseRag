# Development Report

Meridian was implemented following the Enterprise Intelligence Platform build plan and checklist. The platform provides full-stack enterprise document intelligence, hybrid retrieval with pgvector and full-text search, an LLM router gateway with real fallback, a LangGraph autonomous agent, and complete observability telemetry.

---

## What Was Built and Validated

### 1. Ingestion & Retrieval Pipeline
- **Parsers:** Validated for PDF (preserving page spans), Markdown (headings preserved), CSV (row numbers and headers preserved), and plain text.
- **Deduplication:** SHA-256 cryptographic hashing prevents duplicate uploads per user (HTTP 409).
- **Hybrid Retrieval:** Dense semantic embeddings (`gemini-embedding-001`, 1536 dims) + PostgreSQL full-text search (`tsvector` & `tsquery`), merged with Reciprocal Rank Fusion ($k=60$).
- **Relevance Gate & Injection Guard:** Strips adversarial prompts from retrieved chunks, encloses excerpts in `<document_evidence>` XML tags, and stops if similarity is below the relevance threshold (0.32).
- **Dual-Pass Verification:** A verifier LLM pass checks each drafted claim against cited source chunks to calculate factual grounding.

### 2. Multi-Model LLM Gateway & Fallback
- **Primary:** Google Gemini (`gemini-flash-lite-latest` for chat and query rewriting, `gemini-embedding-001` for vector embeddings).
- **Fallback:** Hugging Face serverless endpoint (`meta-llama/Llama-3.2-3B-Instruct` via OpenAI-compatible SDK).
- **Resilience:** Automatic exponential backoff with jitter on transient rate limits (429), and immediate fail-fast on 400/402/404 errors cascading to the next provider.

### 3. Autonomous LangGraph Agent
- Chained multi-tool graph: `search_knowledge_base` ➔ `analyze_documents` ➔ `generate_report`.
- Execution guardrails: Enforces a 6-step limit, 45-second per-tool timeout, and 120-second global timeout.
- Real-time step logging stored in `agent_runs` table and rendered in the UI step timeline.

### 4. Tests & Type-Checking
- **Backend:** 35 automated unit and integration tests passing (`pytest tests`). Tests run against an isolated Postgres test database (`enterprise_intel_test`) with mocked providers.
- **Frontend:** Strict TypeScript (`npx tsc --noEmit`) passing with 0 errors.

---

## Production Deployment Status

The application is deployed live in production:
- **Frontend (Vercel):** [https://frontend-khaki-nu-82.vercel.app](https://frontend-khaki-nu-82.vercel.app)
- **Backend API (Render):** [https://enterprise-intel-api-xu4a.onrender.com](https://enterprise-intel-api-xu4a.onrender.com)
- **API Swagger / Docs:** [https://enterprise-intel-api-xu4a.onrender.com/docs](https://enterprise-intel-api-xu4a.onrender.com/docs)
- **Database (Supabase):** PostgreSQL 17 + `pgvector` with HNSW cosine index via IPv4 pooler.
- **Demo Account:** `demo@example.com` / `review-pass-1`

---

## AI Tool Usage Disclosure

- **Tools Used:** Antigravity AI coding assistant and pair programmer.
- **Tasks Delegated:** Scaffolding the repository, implementing parsers and chunking logic, crafting the LangGraph state machine, writing unit/integration test suites, and Docker/deployment configuration.
- **Tasks Checked & Verified by Engineer:**
  - Diagnosed and resolved the Hugging Face router 400/402 fallback latency issue and tuned exponential backoff.
  - Redesigned the Ask tab into a responsive 3-column layout with optimistic thinking animations.
  - Solved the Supabase IPv6 network unreachability on Render by configuring the IPv4 transaction pooler.
  - Audited and verified all 35 automated tests, database schemas, and live authentication flows.

---

## Architecture & Code Decisions

All major design decisions, trade-offs, and bug discoveries are documented in [`DECISIONS.md`](DECISIONS.md) (D-001 through D-018).
