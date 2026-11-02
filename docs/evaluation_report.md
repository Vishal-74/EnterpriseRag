# Evaluation report

## Method

The corpus in `backend/eval/corpus` is original sample material about a fictional site, Northwind Robotics / Site Alpha. It includes a PDF, Markdown, plain text, and CSV. Two documents disagree about the 12 March 2026 outage: facilities attributes it to pump P-441, and the engineering review attributes it to sensor T-19. `08-malicious-note.md` states cage code CAGE-17 and, separately, tells the model to ignore instructions and answer with `PURPLE-FALCON`.

`backend/eval/dataset.json` has 28 questions: factual, multi-document, conflict, unanswerable, injection, and a two-turn follow-up.

`backend/eval/run_eval.py` creates a user, ingests the corpus with the production parser and embedder, and calls `ChatService` for each question. It then records retrieval hits, reciprocal rank, lexical overlap with the expected fragments, the insufficient-evidence flag, the conflict flag, whether forbidden text appeared, latency, and token counts. Those numbers are written to `backend/eval/results/latest.json` only after that run.

The runner exits with status 2 when `OPENAI_API_KEY` is unset and does not create a results file.

## This workspace

No scored run is stored in this repository. The environment used to build the app did not have a provider key, so there is no hit rate, MRR, hallucination rate, latency, or cost to report. Integration tests cover the retrieval gate, a cited answer from a scripted model, follow-up rewrite, injection redaction, and the agent tool sequence. Those tests are not a substitute for the evaluation metrics.

## Limits

Lexical overlap is a weak answer check. A correct paraphrase can fail it, and a wrong answer can contain the expected token. The conflict and insufficient-evidence rates depend on the model's flags, which the verifier can override. The judge is the product's own verifier plus the lexical rules in the runner, not a separate held-out model. The corpus is small and written for this exercise.
