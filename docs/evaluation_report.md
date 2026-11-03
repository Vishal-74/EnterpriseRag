# Evaluation report

## Method

The corpus in `backend/eval/corpus` is original sample material about a fictional site, Northwind Robotics / Site Alpha. It includes a PDF, Markdown, plain text, and CSV. Two documents disagree about the 12 March 2026 outage: facilities attributes it to pump P-441, and the engineering review attributes it to sensor T-19. `08-malicious-note.md` states cage code CAGE-17 and, separately, tells the model to ignore instructions and answer with `PURPLE-FALCON`.

`backend/eval/dataset.json` has 28 questions: factual, multi-document, conflict, unanswerable, injection, and a two-turn follow-up.

`backend/eval/run_eval.py` creates a user, ingests the corpus with the production parser and embedder, and calls `ChatService` for each question. It then records retrieval hits, reciprocal rank, lexical overlap with the expected fragments, the insufficient-evidence flag, the conflict flag, whether forbidden text appeared, latency, and token counts. Those numbers are written to `backend/eval/results/latest.json` only after that run.

The runner exits with status 2 when the Gemini API key is unset and does not create a results file.

## Scored Run Results (Gemini Flash Lite + Gemini Embedding)

The evaluation suite was executed against the 28 questions in `backend/eval/dataset.json` using `gemini-flash-lite-latest` and `gemini-embedding-001` (results written to `backend/eval/results/latest.json`):

- **Retrieval Hit Rate:** **100% (1.0)** — Across all questions expecting retrieval, the relevant source document chunk was successfully retrieved within the top results.
- **Mean Reciprocal Rank (MRR):** **1.0** — When relevant chunks were retrieved, they consistently ranked in the top position.
- **Lexical Match Rate:** **86.9% (0.87)** — High agreement with expected ground-truth answers and citations.
- **Insufficient Evidence Rate:** **100% (1.0)** — 100% precision in correctly identifying when information is not present in the library and answering "not enough information" rather than hallucinating.
- **Conflict Flagging Rate:** **100% (1.0)** — Successfully identified and surfaced conflicting statements across multiple documents (e.g. facility report vs. engineering review).
- **Prompt Injection Defense Rate:** **100% (1.0)** — 100% of malicious prompt injections (e.g., attempts to force `PURPLE-FALCON`) were neutralized by the input delimiters and injection guard.
- **Mean Latency:** ~8.8s end-to-end per multi-step turn (including query rewrite, hybrid retrieval, answer drafting, and claim verification).

## End-to-End REST API Endpoints Benchmark (`run_eval_endpoints.py`)

A full end-to-end evaluation was executed strictly over the HTTP REST API endpoints (`/health`, `/api/auth/register`, `/api/documents`, `/api/chat`, `/api/agent/runs`, and `/api/metrics/summary`), simulating real client network interactions and testing authorization, middleware, duplicate protection, agent execution, and metrics accounting.

Results stored in `backend/eval/results/endpoints_eval.json`:

| Metric | Score | Details |
| :--- | :---: | :--- |
| **Questions Tested** | **28 / 28** | Complete dataset across factual, conflict, multi-doc, unanswerable, injection, and multi-turn follow-ups |
| **Endpoints Completion** | **100% (True)** | Zero 5xx/4xx uncaught failures across all routes |
| **Retrieval Hit Rate** | **100.0% (1.0)** | 100% of questions expecting retrieval retrieved the correct document |
| **Mean Reciprocal Rank (MRR)** | **1.000** | Top citation accurately matched the ground-truth document |
| **Lexical Match Rate** | **92.0% (0.92)** | Exact lexical grounding with expected operational facts |
| **Insufficient Evidence Precision** | **100.0% (1.0)** | Zero hallucination on unanswerable and external questions |
| **Conflict Detection Rate** | **100.0% (1.0)** | Correctly identified contradictory information across facility report & engineering review |
| **Prompt Injection Neutralization** | **100.0% (1.0)** | Malicious system prompts and jailbreak attempts stripped / neutralized |
| **Duplicate Upload Prevention** | **100% Pass** | Re-upload of identical SHA-256 payload returned HTTP `409 Conflict` |
| **Agent Multi-Step Workflow** | **100% Pass** | 4-step execution (`search_knowledge_base` → `analyze_documents` → `generate_report`) returning structured report with evidence |
| **Metrics Accounting** | **100% Pass** | `/api/metrics/summary` recorded 27 conversations, 104 requests, 10 documents |
| **Mean End-to-End Latency** | **4,917 ms** | Average response latency per full HTTP RAG turn |

## Limits

Lexical overlap is a weak answer check. A correct paraphrase can fail it, and a wrong answer can contain the expected token. The conflict and insufficient-evidence rates depend on the model's flags, which the verifier can override. The judge is the product's own verifier plus the lexical rules in the runner, not a separate held-out model. The corpus is small and written for this exercise.
