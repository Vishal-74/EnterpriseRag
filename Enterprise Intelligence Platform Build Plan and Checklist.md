# Enterprise Intelligence Platform: Build Plan and Checklist

A complete plan for the AI Engineer assessment: local build first, then deploy. Includes the master checklist, coding standards, UI plan, testing plan and a ready-to-use DECISIONS.md.

## 0. One Important Decision Up Front: Where Things Run

You said "deploy to Vercel". Vercel is excellent for the **Next.js frontend**, but it is a poor home for a Python backend that needs background jobs (document processing), long LLM calls and agent loops. Serverless functions have timeouts and no persistent workers.

**Recommended deployment split:**

- **Frontend:** Next.js on **Vercel**
- **Backend:** FastAPI on **Render** (or Railway/Fly.io), as a normal long-running web service
- **Database + vectors:** **Supabase** (Postgres + pgvector), free tier is enough

The assessment asks for a "Frontend URL" and a separate "Backend URL", so this split matches the submission format exactly. Log this as decision D-001 in DECISIONS.md. If you insist on Vercel only, you can run FastAPI as a Vercel serverless function, but background processing (Challenge 6) and long agent runs become fragile. Not recommended.

## 1. Final Architecture

```
Browser (Next.js on Vercel)
   |  HTTPS + JWT
   v
FastAPI backend (Render)
   |-- Auth (JWT)
   |-- Document API  --> Background worker --> parse -> chunk -> embed -> store
   |-- Chat/RAG API  --> query rewrite -> hybrid search -> rerank -> LLM -> verify
   |-- Agent API     --> LangGraph agent --> tools (search, analyze, report)
   |-- LLM Gateway   --> Provider A (OpenAI) / Provider B (Claude or Gemini) + fallback
   |-- Metrics/Logs  --> usage_logs, activity_logs tables
   v
Supabase Postgres (+ pgvector, full-text search)
```

### Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui | Fast to build clean UI, deploys to Vercel natively |
| Backend | FastAPI + Pydantic v2 | Typed, async, auto-generates Swagger docs |
| DB | Postgres + pgvector (Supabase) | One database for users, metadata, vectors and keyword search |
| ORM/migrations | SQLAlchemy 2 + Alembic | Required: schema and migration files |
| Background jobs | FastAPI BackgroundTasks first, or a DB-backed job table with a worker loop | Simple, no Redis needed, still satisfies async processing |
| LLMs | OpenAI (primary) + Anthropic Claude (secondary) | Two providers plus real fallback |
| Embeddings | OpenAI text-embedding-3-small | Cheap, good quality |
| Agent | LangGraph | Explicit steps, easy to show execution visibility |
| Parsing | pypdf, python-markdown, csv module | Light and reliable |
| Evaluation | Custom framework + optional RAGAS | Full control, easier to explain in live session |
| Tests | pytest, httpx, Vitest/Playwright (light) | Backend tests matter most |
| Monitoring | Own metrics tables (+ optional Langfuse) | Dashboard needs the data anyway |

Keep every choice swappable and write the reason in DECISIONS.md. You will be asked to justify them.

## 2. Repository Structure

```
enterprise-intel/
  README.md
  CLAUDE.md
  DECISIONS.md
  DEVELOPMENT_REPORT.md
  .env.example
  docs/
    architecture.md          (diagram)
    evaluation_report.md
  backend/
    app/
      main.py
      core/        config.py, security.py, logging.py, errors.py
      api/         auth.py, documents.py, chat.py, agent.py, metrics.py
      models/      SQLAlchemy models
      schemas/     Pydantic request/response models
      services/
        ingestion/ parsers.py, chunker.py, pipeline.py, jobs.py
        retrieval/ embedder.py, vector_search.py, keyword_search.py, hybrid.py, reranker.py, rewriter.py
        rag/       prompts.py, answerer.py, verifier.py, injection_guard.py
        llm/       base.py, openai_client.py, anthropic_client.py, router.py, tokens.py
        agent/     graph.py, tools/, limits.py
        memory/    conversation.py, summarizer.py
    alembic/       migrations
    tests/         unit/, integration/
    eval/          dataset.json, run_eval.py, metrics.py, results/
    requirements.txt
  frontend/
    app/           (login, dashboard, documents, chat, agent-runs, logs)
    components/
    lib/           api client, auth helpers
    types/
```

## 3. Coding Standards

**Backend (Python)**

- [ ] Type hints everywhere; run `mypy` or `pyright` on the app folder
- [ ] Format and lint with `ruff` (and `black` style); pre-commit hook
- [ ] Layering: routes call services, services call repositories/clients. No business logic in route handlers
- [ ] All input/output through Pydantic schemas; never return raw ORM objects
- [ ] One config module reading env vars (pydantic-settings); no `os.getenv` scattered around
- [ ] Custom exception classes and one global error handler returning consistent JSON errors
- [ ] Structured logging (JSON) with a request ID on every log line
- [ ] Never log API keys, passwords or full document text
- [ ] Async I/O for network calls; timeouts on every external call
- [ ] Small functions, docstrings on public functions, no dead code

**Frontend (TypeScript)**

- [ ] Strict TypeScript, no `any` without a comment
- [ ] One typed API client; components never call `fetch` directly
- [ ] Loading, empty and error states on every screen
- [ ] ESLint + Prettier
- [ ] Tokens stored safely (httpOnly cookie preferred; if localStorage, note the tradeoff in DECISIONS.md)

**Git**

- [ ] Meaningful commit history: small commits like `feat(ingestion): add PDF parser`, `test(rag): add conflict case`
- [ ] Conventional commit messages, feature branches merged to main
- [ ] `.gitignore` covers `.env`, `node_modules`, venvs, uploads
- [ ] Never commit secrets; keep `.env.example` sanitized

## 4. Phased Plan (24 Hours)

Adjust the hours to your pace. The order matters more than exact times: **get a thin end-to-end slice working early, then deepen it.**

### Phase 0: Setup and Design (Hours 0 to 1.5)

- [ ] Create repo, folder structure, `.gitignore`, `.env.example`
- [ ] Write `CLAUDE.md` (project rules for the AI coding agent: stack, standards, commands, "don't fake anything")
- [ ] Create `DECISIONS.md` and log D-001 onward (template in section 11)
- [ ] Create Supabase project, enable pgvector, get connection string
- [ ] Get OpenAI and Anthropic keys; put in local `.env`
- [ ] Draw first architecture diagram
- [ ] Pick your 3+ challenges (suggested in section 6)

### Phase 1: Backend Foundation (Hours 1.5 to 4)

- [ ] FastAPI app, config, logging, error handler, health endpoint
- [ ] SQLAlchemy models + first Alembic migration (users, documents, chunks, conversations, messages, usage\_logs, activity\_logs, agent\_runs)
- [ ] Auth: register, login, JWT, password hashing, `get_current_user` dependency
- [ ] Authorization: every query filtered by `user_id`
- [ ] Tests: auth works, protected route rejects no token

### Phase 2: Document Intelligence, Module A (Hours 4 to 8)

- [ ] Upload endpoint: validate type, size, extension and content sniffing
- [ ] Parsers for PDF, TXT, MD, CSV (keep page numbers for PDF, row ranges for CSV)
- [ ] Chunker: recursive splitting with overlap; store page/section metadata
- [ ] Embedding generation in batches, with retries
- [ ] Store vectors + metadata in pgvector; create vector index (HNSW)
- [ ] Status tracking: `pending -> processing -> ready / failed`, with error message
- [ ] Duplicate detection via SHA-256 file hash per user
- [ ] Background processing so upload returns immediately (Challenge 6)
- [ ] Endpoints: list, get, delete, reprocess documents
- [ ] Tests: each parser, chunker edge cases, duplicate upload, corrupt PDF

### Phase 3: LLM Layer, Module C (Hours 8 to 10.5)

- [ ] Common `LLMClient` interface; OpenAI and Anthropic adapters
- [ ] Prompt templates in one place, versioned
- [ ] Structured output with Pydantic validation (retry once on invalid JSON)
- [ ] Router: primary model, fallback on timeout, 5xx or 429 (Challenge 1)
- [ ] Retry with exponential backoff and jitter; respect `Retry-After`
- [ ] Token counting per call (prompt, completion, total) and cost estimate
- [ ] Write every call to `usage_logs` (model, latency, tokens, status, error)
- [ ] Tests: simulated provider failure triggers fallback; invalid output rejected

### Phase 4: Advanced RAG, Module B (Hours 10.5 to 14)

- [ ] Retrieval: embed query, vector search top-k
- [ ] Improvement 1: **hybrid search** (pgvector + Postgres full-text) merged with Reciprocal Rank Fusion
- [ ] Improvement 2: **query rewriting** (turn follow-ups into standalone queries) and optional reranking
- [ ] Answer generation with numbered citations (doc name, page/section, chunk ID, snippet)
- [ ] Insufficient evidence: relevance threshold, and the model must answer "not enough information" instead of guessing
- [ ] Conflict handling: detect contradicting chunks from different documents and present both sides with sources
- [ ] Prompt injection guard (Challenge 2): wrap retrieved text in delimiters, tell the model it is untrusted data, strip or flag instruction-like patterns, never let document text trigger tools
- [ ] Response verification (Challenge 4): second pass checks each claim against cited chunks, flags unsupported claims
- [ ] Write the "why this retrieval strategy" paragraph in DECISIONS.md
- [ ] Tests: irrelevant question returns "not found"; conflicting docs; malicious document

### Phase 5: Memory, Module E (Hours 14 to 15.5)

- [ ] Conversations and messages tables, per-user
- [ ] Context builder: last N turns + rolling summary of older turns + only the documents referenced
- [ ] Follow-up resolution through query rewriting ("what about the second document?")
- [ ] Token budget for history; log how many tokens history used
- [ ] Tests: a follow-up question refers correctly to a document from earlier

### Phase 6: Agent, Module D (Hours 15.5 to 18)

- [ ] Tool 1: Knowledge Base Search (wraps the RAG retriever)
- [ ] Tool 2: Document Analysis (summarise, extract themes, or find failure causes across selected documents)
- [ ] Tool 3: Structured Report Generation (takes outputs of tools 1 and 2, returns a Pydantic report: summary, findings with evidence, recommendations, gaps)
- [ ] LangGraph graph: plan, choose tool, validate parameters, execute, observe, repeat or finish
- [ ] Agent reliability (Challenge 7): max steps, per-tool timeout, total timeout, parameter validation, retry once then recover gracefully
- [ ] Store each step in `agent_runs` (tool, input, output, latency, status) for UI visibility
- [ ] Demo workflow: "Find the most common system failure causes and give a report" runs search, then analysis, then report
- [ ] Tests: invalid params rejected; tool failure handled; step limit enforced

### Phase 7: Metrics and Evaluation, Modules F (backend) and G (Hours 18 to 20)

- [ ] Metrics endpoints: totals, tokens by day and model, latency percentiles, error rate, activity log
- [ ] Create sample corpus (6 to 10 documents, mix of PDF/TXT/MD/CSV, include one conflicting pair and one malicious file)
- [ ] Eval dataset: **25+ questions** with expected answer, expected source document, and a type tag (factual, multi-doc, conflict, unanswerable, injection)
- [ ] Metrics: retrieval hit rate / MRR, answer correctness (LLM-as-judge with rubric), grounding (verifier score), hallucination rate on unanswerable questions, latency, tokens
- [ ] Run it, save real results, write `evaluation_report.md` with methodology and honest limitations (small dataset, LLM judge bias, same-model judging, etc.)

### Phase 8: Frontend (build alongside, finish Hours 8 to 22)

Build the frontend in slices right after each backend phase so you always have something demoable:

- [ ] After Phase 1: login/register, protected layout
- [ ] After Phase 2: documents page with upload, status badges, delete
- [ ] After Phase 4: chat page with citations
- [ ] After Phase 6: agent run view
- [ ] After Phase 7: dashboard and logs

Full screen list is in section 7.

### Phase 9: Local Verification (Hours 20 to 21.5)

- [ ] Run the full local test pass (section 8)
- [ ] Fix bugs, remove dead code, run linters

### Phase 10: Deployment (Hours 21.5 to 23.5)

- [ ] Section 9 steps

### Phase 11: Docs, Report, Demo (Hours 23.5 to 24+)

- [ ] README, architecture diagram, development report, 5 to 10 minute demo video

Tip: if you run short on time, cut polish, never cut the deploy step. A local-only app is rejected.

## 5. Master Checklist by Module

**Module A: Document Intelligence**

- [ ] PDF, TXT, MD, CSV upload
- [ ] File validation (type, size, empty, corrupt)
- [ ] Text extraction and preprocessing
- [ ] Chunking with overlap and metadata
- [ ] Embeddings generated and stored
- [ ] Vectors + metadata in DB
- [ ] Document-level retrieval (search inside selected documents)
- [ ] Processing status tracking
- [ ] Duplicate upload handling
- [ ] Failed processing handling and reprocess option

**Module B: Advanced RAG**

- [ ] Question embedding and chunk retrieval
- [ ] Context-aware answer with citations
- [ ] Insufficient information handled
- [ ] Conflicting information handled
- [ ] At least one retrieval improvement (plan: hybrid + query rewriting)
- [ ] Written explanation of why it fits

**Module C: LLM Integration**

- [ ] Two providers working
- [ ] Structured output
- [ ] Prompt templates
- [ ] Model selection
- [ ] Token tracking
- [ ] Error handling
- [ ] Rate-limit handling
- [ ] Fallback
- [ ] Response validation

**Module D: Agent**

- [ ] Knowledge Base Search tool
- [ ] Document Analysis tool
- [ ] Report Generation tool
- [ ] Tool selection
- [ ] Parameter validation
- [ ] Multi-step execution
- [ ] Tool output processing
- [ ] Failure handling
- [ ] Demonstrated chained workflow

**Module E: Memory**

- [ ] Multiple conversations
- [ ] User-specific history
- [ ] Follow-up context retained
- [ ] Context trimming/summarising
- [ ] Follow-up demo about earlier documents

**Module F: Dashboard**

- [ ] Authentication
- [ ] Protected routes
- [ ] Dashboard + usage stats
- [ ] Document management
- [ ] Chat interface
- [ ] Source references
- [ ] Conversation history
- [ ] Agent execution visibility
- [ ] Token usage, latency, errors, activity logs

**Module G: Evaluation**

- [ ] 20+ question dataset
- [ ] Retrieval relevance
- [ ] Answer correctness
- [ ] Source grounding
- [ ] Hallucination handling
- [ ] Latency and tokens
- [ ] Framework chosen
- [ ] Methodology and limitations written

## 6. Advanced Challenges: Recommended Picks

The brief requires at least three. Since they overlap with the core work, aim for five:

- [ ] **1. Intelligent Model Fallback** (Phase 3)
- [ ] **2. Prompt Injection Protection** (Phase 4)
- [ ] **3. Retrieval Optimization** (Phase 4)
- [ ] **4. AI Response Verification** (Phase 4)
- [ ] **6. Asynchronous Document Processing** (Phase 2)
- [ ] **7. Agent Reliability** (Phase 6), bonus
- [ ] **5. Cost Optimization**, bonus: cache embeddings by chunk hash and cache identical question answers

These also line up with the live verification tasks (fallback, conflicts, new tool, duplicate jobs, irrelevant retrieval, security fix), so they double as practice.

## 7. UI Plan (Screens That Support Everything)

| Screen | What it shows |
| --- | --- |
| Login / Register | Forms, validation, error messages |
| Dashboard | Cards: documents, conversations, total tokens, avg latency, error rate. Charts: tokens per day, latency over time, requests by model |
| Documents | Drag-and-drop upload, table with status badge (processing/ready/failed), size, chunk count, delete, reprocess, duplicate warning |
| Chat | Conversation sidebar, message thread, model selector, document scope filter, citations as clickable chips that open a source panel with snippet and page, "not enough information" and "conflict found" banners, token/latency per answer |
| Agent | Task input, live step timeline (tool, input, output, time, status), final structured report with evidence |
| Logs | Filterable table of LLM calls and activity events (time, user, action, model, tokens, latency, status, error) |
| Settings (optional) | Default model, logout |

UI rules:

- [ ] Every page has loading, empty and error states
- [ ] Protected routes redirect to login
- [ ] Responsive layout, works on laptop widths at minimum
- [ ] Show the real data only; no mock numbers in charts

## 8. Local Testing Plan (Before Any Deployment)

**Automated**

- [ ] Backend unit tests: parsers, chunker, hashing, token counter, router fallback, validators
- [ ] Backend integration tests: auth, upload, retrieval, chat, agent, with the LLM mocked **only in tests**
- [ ] Target around 70% coverage on services
- [ ] Lint and type-check pass
- [ ] Frontend build passes (`next build`) and lint passes

**Manual end-to-end script (run it exactly)**

- [ ] Register and log in; confirm protected routes block anonymous access
- [ ] Upload one file of each type; watch statuses update
- [ ] Upload the same file again; duplicate is handled
- [ ] Upload a corrupt PDF; status is failed with a clear message
- [ ] Ask a normal question; answer has correct citations
- [ ] Ask something not in the documents; app says it does not know
- [ ] Ask about the conflicting pair; both sources shown
- [ ] Ask a follow-up ("what about the second document?"); it works
- [ ] Upload the malicious document; instructions inside are ignored
- [ ] Disable the primary API key; fallback model answers
- [ ] Run the agent task; see three tools chained in the timeline
- [ ] Check dashboard numbers match the logs
- [ ] Run the eval script; results file is generated

## 9. Deployment Plan (After Local Passes)

**Database**

- [ ] Supabase project live, pgvector enabled
- [ ] Run Alembic migrations against it

**Backend on Render**

- [ ] Dockerfile or build command + start command (`uvicorn app.main:app --host 0.0.0.0 --port $PORT`)
- [ ] Set env vars in the dashboard (DB URL, API keys, JWT secret, allowed origins)
- [ ] Health check endpoint configured
- [ ] CORS limited to your Vercel domain
- [ ] Swagger available at `/docs`
- [ ] Note: free Render instances sleep; wake it before the demo and the live session

**Frontend on Vercel**

- [ ] Import GitHub repo, set root directory to `frontend`
- [ ] Set `NEXT_PUBLIC_API_URL` to the Render URL
- [ ] Deploy and test login from the live URL

**Post-deploy**

- [ ] Run the full manual script against the live URLs
- [ ] Confirm no secrets in the repo or in client-side bundles
- [ ] Seed a demo account and sample documents for reviewers
- [ ] Put credentials for the demo account in the README

## 10. Security Checklist

- [ ] Password hashing (bcrypt/argon2), JWT expiry
- [ ] Authorization check on every document, conversation and run (no accessing another user's data by ID)
- [ ] Upload limits, file type verification, safe filenames
- [ ] Rate limiting on login and chat endpoints
- [ ] Parameterized queries only
- [ ] Retrieved text treated as untrusted; tools cannot be triggered by document content
- [ ] CORS locked down, secrets only in env vars
- [ ] Error messages do not leak internals

## 11. DECISIONS.md (Template + Starter Entries)

Create `DECISIONS.md` in the repo root in Phase 0 and **add an entry at the moment you make each decision**, not at the end. Reviewers read this, and it also prepares you for the live questions.

**Entry format:**

```
## D-XXX: Short title
- Date/Time:
- Phase / Module:
- Context: what problem or choice came up
- Options considered: A, B, C
- Decision: what you chose
- Reason: why (performance, cost, simplicity, time limit)
- Tradeoffs / risks: what you give up
- Made by: me / AI suggested, I changed it / AI suggested, I accepted after checking
- Validation: how you verified it works
- Status: active / replaced by D-YYY
```

**Starter entries to write on day one:**

- D-001: Frontend on Vercel, backend on Render (serverless limits for background jobs)
- D-002: Supabase Postgres + pgvector instead of Pinecone (one DB for everything)
- D-003: FastAPI over Rails (Python AI ecosystem, typed schemas, automatic OpenAPI)
- D-004: OpenAI primary, Claude secondary, fallback rules
- D-005: LangGraph vs custom agent loop
- D-006: Chunk size and overlap values (update after eval)
- D-007: Hybrid search + RRF, and why
- D-008: Memory strategy (last N turns + summary)
- D-009: Duplicate detection by file hash
- D-010: Background job approach
- D-011: Prompt injection defense approach
- D-012: Evaluation framework (custom) and judge model
- D-013: Token storage on the client

Also keep a short **Bugs and AI Mistakes Log** at the bottom: every time an AI tool gave wrong or risky code, write what it was and how you caught it. This feeds the Development Report directly.

## 12. AI Tool Usage Disclosure (Development Report Notes)

Track this as you go in `DEVELOPMENT_REPORT.md`:

- [ ] Which tools you used (Claude Code, ChatGPT, Cursor, etc.)
- [ ] Which tasks you delegated
- [ ] Which decisions you made yourself
- [ ] Errors the AI generated and how you found them
- [ ] How you validated the code (tests, manual checks, reading every module)

## 13. Prepare for the Live 60-Minute Session (No AI Allowed)

Practice these on your own codebase before the session:

- [ ] Add a third LLM provider and wire the fallback
- [ ] Make the RAG answer handle two conflicting documents differently
- [ ] Add a fourth agent tool
- [ ] Block duplicate processing jobs (what if the same doc is uploaded twice at the same time?)
- [ ] Fix unsupported answers when retrieval returns irrelevant chunks (threshold + verifier)
- [ ] Find a planted security bug (missing ownership check, SQL string, unvalidated upload)
- [ ] Be able to explain: chunking, embeddings, RRF, prompt templates, token counting, agent graph, migrations, deployment config
- [ ] Know how to run tests and read logs quickly

**Rule of thumb:** do not keep any file you cannot explain line by line.

## 14. Final Submission Checklist

- [ ] GitHub repo with meaningful commit history
- [ ] Frontend URL (Vercel)
- [ ] Backend URL (Render) with `/docs`
- [ ] Architecture diagram
- [ ] Database schema and migration files
- [ ] API documentation (OpenAPI)
- [ ] Working RAG demo
- [ ] Working agent demo
- [ ] Evaluation dataset (20+ questions)
- [ ] Evaluation report (results, methodology, limitations)
- [ ] README (setup, env vars, how to run tests, how to deploy)
- [ ] CLAUDE.md
- [ ] DECISIONS.md
- [ ] Development report
- [ ] `.env.example` with no real keys
- [ ] 5 to 10 minute demo recording covering: login, upload, status, chat with citations, conflict case, follow-up, agent workflow, dashboard, fallback, evaluation

## 15. Honesty Rules (Disqualifiers)

- No hardcoded answers passed off as LLM output
- No mock retrieval; no fake tool calls
- Evaluation numbers must come from a real run
- Screenshots are not proof of deployment; the URLs must work
- Mocks are fine **inside tests only**, and should be labelled as such

## Suggested Next Step

Start with Phase 0 today: create the repo, write CLAUDE.md and the first DECISIONS.md entries, and get the Supabase and API keys ready. I can write the CLAUDE.md, the database schema, or the starter DECISIONS.md file next, whichever you want first.
