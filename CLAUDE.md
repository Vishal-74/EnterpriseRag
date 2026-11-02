# Engineering notes

Meridian is a document-intelligence product. Answers, retrieval, and metrics must come from the running system.

## Boundaries

- Routes validate input and call a service. Services own transactions and jobs. Repositories own SQL.
- Read configuration from `app.core.config.Settings`. Do not call `os.getenv` in feature code.
- Raise `AppError` subclasses. Clients receive `{ "error": { "code", "message", "request_id" } }`.
- Log JSON with a request id. Do not log document text, prompts, passwords, or API keys.
- Production embeddings and chat go through `OpenAIEmbedder` and `LLMRouter`. Fakes belong in `backend/tests`.
- Do not write evaluation numbers that were not produced by `backend/eval/run_eval.py`.

## Data access

- Every document, conversation, message, usage row, and agent run is filtered by `user_id`.
- After `init_engine`, use `app.db.session.SessionLocal` through the module (`from app.db import session as db_session`). A name imported earlier stays `None`.
- Do not read ORM relationships from a Pydantic `from_attributes` model on an async session. Copy columns, as `DocumentRead.from_document` does.
- Capture ids before `session.expire_all()`. Expired attributes lazy-load and fail outside a greenlet.

## Jobs and providers

- Upload commits the pending document, then the dispatcher runs ingestion. Tests use `InlineJobDispatcher`.
- The router retries the same provider for timeout, 429, and 5xx. It falls back to the other provider on those errors and on 401.
- Retrieved document text is untrusted. The injection guard redacts instruction-like lines before the text is placed in a prompt. Agent tool names come from the planner enum, not from document text.

## Frontend

- Components call `frontend/lib/api.ts`. They do not call the backend origin directly.
- The session cookie is httpOnly and is set only by the Next.js auth routes.
- Every workspace page shows loading, empty, and error states. Empty metrics are zeros from the API.
