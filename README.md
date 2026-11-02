# Meridian

Local-first enterprise document intelligence. Upload PDF, TXT, Markdown, and CSV files, ask questions with citations, and run a tool-using agent that writes a structured report.

The browser talks to a Next.js app. That app stores the session in an httpOnly cookie and forwards API calls to FastAPI. FastAPI stores users, documents, chunks, conversations, usage, and agent steps in Postgres with pgvector.

## Layout

- `backend/app` — FastAPI application. Routes call services. Services call repositories.
- `backend/alembic` — schema migrations, including the `vector` extension.
- `backend/tests` — unit tests and Postgres integration tests. Test doubles live only under `tests/`.
- `backend/eval` — sample corpus, question set, and the evaluation runner.
- `frontend` — Next.js App Router UI.
- `docs` — architecture and the evaluation write-up.

## Local setup

Requirements: Docker, Python 3.10 or newer, Node 22.

```bash
docker compose up -d db
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp .env.example .env
# Set JWT_SECRET to at least 32 random characters.
cd backend && .venv/bin/alembic upgrade head
cd frontend && npm install
```

`make db`, `make install`, and `make migrate` do the same steps.

Start the API and the UI in two terminals:

```bash
make api
make web
```

Open http://localhost:3000 and register an account. Without `OPENAI_API_KEY`, uploads are accepted and then marked failed with a message to set the key and reprocess. Chat and the agent return a provider error. The dashboard stays at zero until a real model call is logged.

Optional demo account, after both keys you want are in `.env`:

```bash
cd backend && .venv/bin/python scripts/seed_demo.py
```

The script reads `DEMO_USER_EMAIL` and `DEMO_USER_PASSWORD`. It embeds the sample corpus only when `OPENAI_API_KEY` is set.

## Checks

```bash
make lint
make test
```

Integration tests use the `enterprise_intel_test` database and refuse to truncate any other database name. They use `FakeEmbedder` and `FakeRouter`, which are not wired into the application runtime.

## Evaluation

```bash
cd backend && .venv/bin/python eval/run_eval.py
```

If `OPENAI_API_KEY` is empty the command exits with status 2 and does not write a score file. A completed run writes `backend/eval/results/latest.json`. See `docs/evaluation_report.md`.

## Deploy

`backend/Dockerfile` runs the migration and uvicorn. `render.yaml` describes the API service. The frontend is a standard Next.js app: set `API_URL` to the public API origin. Set `DATABASE_URL`, `JWT_SECRET`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `CORS_ORIGINS` on the API host. This repository does not contain a live deployment.
