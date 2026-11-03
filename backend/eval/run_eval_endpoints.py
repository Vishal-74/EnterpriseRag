"""Evaluate the platform strictly via its HTTP REST API endpoints.

Tests user registration, document upload & processing status, chat retrieval &
citations, conflict detection, prompt injection defense, conversational memory,
agent execution, and metrics logging through HTTP requests.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import mimetypes
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.main import create_app

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus"
DATASET_FILE = ROOT / "dataset.json"
RESULTS_FILE = ROOT / "results" / "endpoints_eval.json"


@dataclass
class EndpointScoreRow:
    id: str
    type: str
    question: str
    status_code: int
    hit: bool
    reciprocal_rank: float
    lexical_match: bool
    lexical_applicable: bool
    forbidden_text_present: bool
    insufficient_evidence: bool
    expected_insufficient: bool
    conflict: bool
    expected_conflict: bool
    ungrounded: bool
    latency_ms: int
    total_tokens: int
    answer_origin: str
    citation_docs: list[str]
    expects_retrieval: bool
    error: str | None


async def run_evaluation(base_url: str | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    gemini_key = settings.gemini_api_key or settings.gemini
    if not gemini_key:
        print("ERROR: GEMINI API key is not configured in environment or .env.")
        return 2

    if not DATASET_FILE.is_file():
        print(f"ERROR: Dataset file not found at {DATASET_FILE}")
        return 1

    dataset = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    questions = dataset.get("questions", [])
    print(f"\n========================================================")
    print(f"  Meridian Endpoint Evaluation Suite")
    print(f"  Dataset: {dataset.get('name')} (v{dataset.get('version')})")
    print(f"  Total Questions: {len(questions)}")
    print(f"========================================================\n")

    transport = None
    app = None
    if not base_url:
        print("[1/5] Using in-process ASGI FastAPI transport with inline jobs...")
        app = create_app(inline_jobs=True)
        transport = httpx.ASGITransport(app=app)
        client_base_url = "http://testserver"
    else:
        print(f"[1/5] Testing against external HTTP server: {base_url}")
        client_base_url = base_url.rstrip("/")

    from contextlib import nullcontext
    lifespan_mgr = app.router.lifespan_context(app) if app is not None else nullcontext()

    async with lifespan_mgr, httpx.AsyncClient(
        transport=transport,
        base_url=client_base_url,
        timeout=httpx.Timeout(120.0, connect=10.0),
    ) as client:
        # Step 1: Health check
        health_resp = await client.get("/health")
        if health_resp.status_code != 200:
            print(f"FAIL: Health check failed: {health_resp.status_code} - {health_resp.text}")
            return 1
        print("  -> /health endpoint: OK (200)")

        # Step 2: Register test user
        test_email = f"eval-endpoint-{uuid4().hex[:8]}@example.com"
        test_password = f"Pass-{uuid4().hex[:12]}!"
        reg_resp = await client.post(
            "/api/auth/register",
            json={"email": test_email, "password": test_password},
        )
        if reg_resp.status_code != 201:
            print(f"FAIL: /api/auth/register returned {reg_resp.status_code}: {reg_resp.text}")
            return 1
        token = reg_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  -> /api/auth/register: User created ({test_email}), JWT acquired")

        # Step 3: Ingest evaluation corpus via /api/documents
        print("\n[2/5] Ingesting evaluation corpus documents via /api/documents...")
        uploaded_docs: dict[str, str] = {}
        corpus_files = sorted(f for f in CORPUS_DIR.iterdir() if f.is_file() and not f.name.startswith("."))

        for file_path in corpus_files:
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            with open(file_path, "rb") as f:
                content = f.read()

            upload_resp = await client.post(
                "/api/documents",
                headers=headers,
                files={"file": (file_path.name, io.BytesIO(content), mime)},
            )
            if upload_resp.status_code not in {200, 201, 202}:
                print(f"  [X] Upload failed for {file_path.name}: {upload_resp.status_code} {upload_resp.text}")
                return 1

            doc_data = upload_resp.json()
            doc_id = doc_data["id"]

            # Poll until ready if status is still processing/pending
            status = doc_data.get("status")
            attempts = 0
            while status in {"pending", "processing"} and attempts < 30:
                await asyncio.sleep(1)
                attempts += 1
                poll_resp = await client.get(f"/api/documents/{doc_id}", headers=headers)
                if poll_resp.status_code == 200:
                    status = poll_resp.json().get("status")
                    doc_data = poll_resp.json()

            if status != "ready":
                print(f"  [X] Document {file_path.name} failed with status: {status} ({doc_data.get('error_message')})")
                return 1

            uploaded_docs[file_path.name] = doc_id
            print(f"  [✓] {file_path.name:<28} -> Ready ({doc_data.get('chunk_count', 0)} chunks)")

        # Verify duplicate file rejection (Challenge requirement)
        first_file = corpus_files[0]
        mime = mimetypes.guess_type(first_file.name)[0] or "application/octet-stream"
        with open(first_file, "rb") as f:
            dup_content = f.read()
        dup_resp = await client.post(
            "/api/documents",
            headers=headers,
            files={"file": (first_file.name, io.BytesIO(dup_content), mime)},
        )
        if dup_resp.status_code == 409:
            print("  [✓] Duplicate upload test: Rejected with 409 Conflict as required.")
        else:
            print(f"  [!] Duplicate upload returned unexpected code: {dup_resp.status_code}")

        # Step 4: Run evaluation questions through /api/chat
        print(f"\n[3/5] Testing {len(questions)} evaluation questions via POST /api/chat...")
        rows: list[EndpointScoreRow] = []
        conversations: dict[str, str] = {}

        for i, q in enumerate(questions, start=1):
            qid = q["id"]
            qtype = q["type"]
            qtext = q["question"]
            conv_key = q.get("conversation") or ""
            conv_id = conversations.get(conv_key)

            payload = {"message": qtext}
            if conv_id:
                payload["conversation_id"] = conv_id

            t0 = time.perf_counter()
            chat_resp = await client.post("/api/chat", headers=headers, json=payload)
            if chat_resp.status_code in {429, 502}:
                # Pacing retry for free tier quota recovery
                await asyncio.sleep(6.0)
                chat_resp = await client.post("/api/chat", headers=headers, json=payload)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            if chat_resp.status_code != 200:
                print(f"  [{qid}] FAILED HTTP {chat_resp.status_code}: {chat_resp.text}")
                rows.append(
                    EndpointScoreRow(
                        id=qid,
                        type=qtype,
                        question=qtext,
                        status_code=chat_resp.status_code,
                        hit=False,
                        reciprocal_rank=0.0,
                        lexical_match=False,
                        lexical_applicable=bool(q.get("expected_contains")),
                        forbidden_text_present=False,
                        insufficient_evidence=False,
                        expected_insufficient=bool(q.get("insufficient_evidence")),
                        conflict=False,
                        expected_conflict=bool(q.get("conflict")),
                        ungrounded=False,
                        latency_ms=elapsed_ms,
                        total_tokens=0,
                        answer_origin="error",
                        citation_docs=[],
                        expects_retrieval=bool(q.get("expected_files")),
                        error=chat_resp.text[:200],
                    )
                )
                continue

            resp_data = chat_resp.json()
            if conv_key and "conversation_id" in resp_data:
                conversations[conv_key] = resp_data["conversation_id"]

            answer = resp_data.get("answer", "")
            citations = resp_data.get("citations", [])
            citation_docs = [c.get("document_name", "") for c in citations]
            expected_files = q.get("expected_files", [])
            expected_set = set(expected_files)

            # Hit rate & MRR
            rank = next((idx for idx, name in enumerate(citation_docs, start=1) if name in expected_set), None)
            hit = not expected_set or bool(expected_set.intersection(citation_docs))
            reciprocal_rank = 0.0 if rank is None else 1.0 / rank

            # Lexical checks
            lowered = answer.lower()
            fragments = [f.lower() for f in q.get("expected_contains", [])]
            lexical_match = all(f in lowered for f in fragments)
            must_not = [f.lower() for f in q.get("must_not_contain", [])]
            forbidden_present = any(f in lowered for f in must_not)

            is_insufficient = bool(resp_data.get("insufficient_evidence"))
            is_conflict = bool(resp_data.get("conflict"))
            is_ungrounded = bool(resp_data.get("ungrounded"))

            score_row = EndpointScoreRow(
                id=qid,
                type=qtype,
                question=qtext,
                status_code=chat_resp.status_code,
                hit=hit,
                reciprocal_rank=reciprocal_rank,
                lexical_match=lexical_match,
                lexical_applicable=bool(fragments),
                forbidden_text_present=forbidden_present,
                insufficient_evidence=is_insufficient,
                expected_insufficient=bool(q.get("insufficient_evidence")),
                conflict=is_conflict,
                expected_conflict=bool(q.get("conflict")),
                ungrounded=is_ungrounded,
                latency_ms=resp_data.get("latency_ms", elapsed_ms),
                total_tokens=resp_data.get("total_tokens", 0),
                answer_origin=resp_data.get("answer_origin", "unknown"),
                citation_docs=citation_docs,
                expects_retrieval=bool(expected_set),
                error=None,
            )
            rows.append(score_row)

            # Status pill
            status_tag = "✓ PASS"
            if not hit and expected_set:
                status_tag = "! MISS"
            elif forbidden_present:
                status_tag = "X INJECT"
            elif fragments and not lexical_match:
                status_tag = "~ LEXICAL"

            print(f"  [{qid}] {status_tag:<9} | {qtype:<11} | MRR: {reciprocal_rank:.2f} | Latency: {elapsed_ms}ms | Q: {qtext[:50]}...")
            await asyncio.sleep(2.0)

        # Step 5: Test Agent endpoint (/api/agent/runs)
        print("\n[4/5] Testing Agent execution via POST /api/agent/runs...")
        await asyncio.sleep(3.0)
        agent_resp = await client.post(
            "/api/agent/runs",
            headers=headers,
            json={"task": "Find common failure causes and generate an operational report"},
        )
        if agent_resp.status_code in {200, 202}:
            agent_data = agent_resp.json()
            steps = agent_data.get("steps", [])
            print(f"  [✓] Agent run succeeded with {len(steps)} steps.")
            for step in steps:
                print(f"      - Step {step.get('step_index')}: {step.get('tool_name')} ({step.get('status')})")
        else:
            print(f"  [!] Agent run returned status {agent_resp.status_code}: {agent_resp.text}")

        # Step 6: Test Metrics endpoint (/api/metrics/summary)
        print("\n[5/5] Testing Metrics endpoints...")
        metrics_resp = await client.get("/api/metrics/summary", headers=headers)
        if metrics_resp.status_code == 200:
            m = metrics_resp.json()
            print(f"  [✓] Metrics Summary: {m.get('conversations', 0)} conversations, {m.get('requests', 0)} requests, {m.get('documents', 0)} documents, avg latency {m.get('avg_latency_ms', 0):.0f}ms")
        else:
            print(f"  [!] Metrics summary returned status {metrics_resp.status_code}")

        # Compute summary
        summary = compute_summary(rows)
        print("\n========================================================")
        print("  Evaluation Results Summary (HTTP REST API Endpoints)")
        print("========================================================")
        print(f"  Total Questions Tested:       {summary['questions']}")
        print(f"  All Endpoints Completed:      {summary['complete']}")
        print(f"  Retrieval Hit Rate:           {summary['retrieval_hit_rate'] * 100:.1f}%")
        print(f"  Mean Reciprocal Rank (MRR):   {summary['mrr']:.3f}")
        print(f"  Lexical Grounding Match Rate: {summary['lexical_match_rate'] * 100:.1f}%")
        print(f"  Insufficient Evidence Rate:   {summary['insufficient_evidence_rate'] * 100:.1f}%")
        print(f"  Conflict Detection Rate:      {summary['conflict_flag_rate'] * 100:.1f}%")
        print(f"  Prompt Injection Block Rate:  {summary['injection_block_rate'] * 100:.1f}%")
        print(f"  Mean Latency:                 {summary['mean_latency_ms']:.0f} ms")
        print("========================================================\n")

        # Save to results JSON
        RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        out_payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "transport": "asgi_fastapi" if not base_url else f"http_remote_{base_url}",
            "summary": summary,
            "rows": [asdict(r) for r in rows],
        }
        RESULTS_FILE.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
        print(f"Results saved to: {RESULTS_FILE}\n")

        return 0 if summary["complete"] and summary["retrieval_hit_rate"] >= 0.8 else 1


def compute_summary(rows: list[EndpointScoreRow]) -> dict[str, object]:
    expected_retrieval = [r for r in rows if r.expects_retrieval and r.error is None]
    lexical_rows = [r for r in rows if r.lexical_applicable and r.error is None]
    withheld_rows = [r for r in rows if r.expected_insufficient and r.error is None]
    conflict_rows = [r for r in rows if r.expected_conflict and r.error is None]
    injection_rows = [r for r in rows if r.type == "injection" and r.error is None]

    return {
        "questions": len(rows),
        "complete": all(r.error is None for r in rows),
        "retrieval_hit_rate": _mean(1 if r.hit else 0 for r in expected_retrieval),
        "mrr": _mean(r.reciprocal_rank for r in expected_retrieval),
        "lexical_match_rate": _mean(1 if r.lexical_match else 0 for r in lexical_rows),
        "insufficient_evidence_rate": _mean(1 if r.insufficient_evidence else 0 for r in withheld_rows),
        "conflict_flag_rate": _mean(1 if r.conflict else 0 for r in conflict_rows),
        "injection_block_rate": _mean(0 if r.forbidden_text_present else 1 for r in injection_rows),
        "mean_latency_ms": _mean(r.latency_ms for r in rows if r.error is None),
    }


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Meridian REST API Endpoints Evaluation Runner")
    parser.add_argument("--base-url", default=None, help="Base URL of running server (e.g. http://localhost:8000)")
    args = parser.parse_args()
    code = asyncio.run(run_evaluation(args.base_url))
    sys.exit(code)


if __name__ == "__main__":
    main()
