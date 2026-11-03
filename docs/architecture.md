# Meridian: Architecture

## 1. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Client ["Client Layer"]
        User["User Browser"]
    end

    subgraph Frontend ["Frontend Web Application (Vercel)"]
        UI["Next.js App Router (TypeScript + Tailwind)"]
        BFF["BFF API Proxy (/api/backend/*)"]
        CookieStore["httpOnly Session Cookie (ei_session)"]
    end

    subgraph Backend ["Backend Service (FastAPI on Render)"]
        AuthMiddleware["JWT Authentication & Rate Limiting"]
        Router["API Routing & Controllers"]
        
        subgraph CoreServices ["Core Domain Services"]
            DocService["Document Management Service"]
            ChatService["Chat & Conversation Service"]
            AgentService["LangGraph Agent Service"]
            MetricsService["Metrics & Activity Service"]
        end

        subgraph IngestionEngine ["Document Ingestion Engine"]
            FileParser["Parsers (PDF, MD, CSV, TXT)"]
            Chunker["Recursive & Structural Chunker"]
            Hasher["SHA-256 Duplicate Detector"]
            Worker["Async Ingestion Job Worker"]
        end

        subgraph RAGEngine ["Advanced RAG Engine"]
            Rewriter["Query Rewriter"]
            HybridRetriever["Hybrid Search (Vector + Full-Text)"]
            RRF["Reciprocal Rank Fusion (k=60)"]
            Reranker["Cross-Encoder / LLM Reranker"]
            Guard["Prompt Injection Guard"]
            Answerer["Cited Answer Generator"]
            Verifier["Two-Pass Claim Verifier"]
        end

        subgraph LLMGateway ["Resilient LLM Gateway"]
            LLMRouter["Provider Router with Fallback"]
            EmbeddingCache["Embedding & Answer Caching"]
            TokenRecorder["Token & Latency Recorder"]
        end
    end

    subgraph DatabaseLayer ["Data & Vector Store (Supabase Postgres)"]
        PGVector[("pgvector (HNSW Cosine Index)")]
        PGFTS[("Postgres Full-Text Search (tsvector)")]
        RelationalTables[("Relational Tables (users, docs, chunks, messages, agent_runs, usage_logs)")]
    end

    subgraph ExternalProviders ["AI Model Providers"]
        Gemini["Google Gemini (Primary: Flash Lite / Embedding-001)"]
        HF["Hugging Face (Fallback Client)"]
        OpenAI["OpenAI (gpt-4o-mini / text-embedding-3-small)"]
        Anthropic["Anthropic (Claude 3.5 Haiku)"]
    end

    User -->|HTTPS| UI
    UI -->|Cookie Session| BFF
    BFF -->|Authorization: Bearer JWT| AuthMiddleware

    AuthMiddleware --> Router
    Router --> DocService
    Router --> ChatService
    Router --> AgentService
    Router --> MetricsService

    DocService --> Hasher
    DocService --> Worker
    Worker --> FileParser
    FileParser --> Chunker
    Chunker --> LLMGateway
    Worker --> PGVector
    Worker --> PGFTS

    ChatService --> Rewriter
    Rewriter --> HybridRetriever
    HybridRetriever --> PGVector
    HybridRetriever --> PGFTS
    HybridRetriever --> RRF
    RRF --> Reranker
    Reranker --> Guard
    Guard --> Answerer
    Answerer --> LLMGateway
    Answerer --> Verifier
    Verifier --> LLMGateway

    AgentService --> LLMGateway
    AgentService --> RelationalTables

    MetricsService --> RelationalTables
    LLMGateway --> TokenRecorder
    TokenRecorder --> RelationalTables
    LLMGateway --> EmbeddingCache
    EmbeddingCache --> RelationalTables

    LLMRouter --> Gemini
    LLMRouter -.->|Fallback on 401/408/429/5xx| HF
    LLMRouter -.->|Fallback| OpenAI
    LLMRouter -.->|Fallback| Anthropic
```

## 2. Advanced Hybrid RAG & Verification Pipeline

```mermaid
flowchart TD
    UserQuery["User Query / Follow-up Turn"] --> RewriterNode["Query Rewriter (LLM)<br/>Resolves conversational coreference"]
    
    subgraph ParallelRetrieval ["Dual-Channel Retrieval"]
        VectorBranch["pgvector Cosine Search<br/>Top 20 Semantic Candidates"]
        KeywordBranch["Postgres Full-Text Search<br/>Top 20 Lexical Candidates (ts_rank)"]
    end
    
    RewriterNode --> VectorBranch
    RewriterNode --> KeywordBranch
    
    VectorBranch --> RRFNode["Reciprocal Rank Fusion (k=60)<br/>Combines ranked lists"]
    KeywordBranch --> RRFNode
    
    RRFNode --> RelevanceGate{"Relevance Gate<br/>Cosine >= 0.32 OR Lexical >= 0.05?"}
    RelevanceGate -- No --> InsufficientAns["Return: Not enough information found in documents.<br/>(Zero Hallucination / Zero LLM Call)"]
    
    RelevanceGate -- Yes --> RerankerNode["LLM / Cross-Encoder Reranker<br/>Selects top K most relevant chunks"]
    RerankerNode --> InjectionGuard["Prompt Injection Guard<br/>Sanitizes instruction-override patterns & wraps untrusted text"]
    
    InjectionGuard --> AnswerDraft["Answer Generator (LLM)<br/>Drafts response with numbered citations [1], [2]"]
    
    AnswerDraft --> ClaimVerifier["Two-Pass Claim Verifier<br/>Checks factual statements against source snippets"]
    ClaimVerifier --> GroundedCheck{"Unsupported Claims Detected?"}
    
    GroundedCheck -- Yes --> ConflictFlag["Append Warning: Conflicting or partially grounded sources"]
    GroundedCheck -- No --> OutputAnswer["Output Verified Answer with Interactive Source Chips"]
    ConflictFlag --> OutputAnswer
```

## 3. LangGraph Autonomous Agent State Loop

```mermaid
stateDiagram-v2
    [*] --> Plan

    state Plan {
        description: Evaluates user goal and history to choose tool or finish
    }

    Plan --> ValidateTool: Tool selected

    state ValidateTool {
        description: Validates tool name and Pydantic arguments
    }

    ValidateTool --> Act: Validation Passed
    ValidateTool --> Plan: Validation Error (Feedback to LLM)

    state Act {
        state ToolFork <<choice>>
        ToolFork --> SearchKB: search_knowledge_base
        ToolFork --> AnalyzeDoc: analyze_documents
        ToolFork --> GenReport: generate_report
    }

    SearchKB --> Observe: Query RAG hybrid index
    AnalyzeDoc --> Observe: Extract themes / failure modes across docs
    GenReport --> Observe: Synthesize structured Markdown report

    state Observe {
        description: Persist step to agent_steps table (inputs, output, latency)
    }

    Observe --> CheckLimits: Evaluate Step & Time Limits

    state CheckLimits <<choice>>
    CheckLimits --> Plan: Steps < 6 AND Time < 120s
    CheckLimits --> Finish: Max steps reached OR Timeout

    Plan --> Finish: Agent emits finish tool
    Finish --> [*]: Return structured final report with evidence
```

## 4. End-to-End Request Lifecycles

1. **Upload & Ingestion**:
   - `POST /api/documents/upload` calculates SHA-256 hash. If duplicate, returns `HTTP 409`.
   - Inserts document row (`pending`), responds `HTTP 202 Accepted`, and enqueues background worker.
   - Worker invokes parsers (PDF, TXT, MD, CSV) $\to$ semantic chunker $\to$ batch embedding generation $\to$ stores chunks in `chunks` table with pgvector cosine embeddings $\to$ status transitions to `ready`.
2. **Chat & Hybrid RAG**:
   - Query rewriter resolves contextual follow-ups.
   - Parallel query against `pgvector` (cosine distance) and Postgres FTS (`tsvector`), combined using Reciprocal Rank Fusion ($k=60$).
   - Relevance gate blocks ungrounded queries early; reranker refines chunk ordering.
   - Prompt injection guard filters prompt override attempts and wraps untrusted chunks in XML tags.
   - Answer generator cites source chunks; two-pass verifier audits claims against cited snippets.
3. **Autonomous Agent**:
   - LangGraph cyclical graph: Plan $\to$ Tool Validation $\to$ Act (`search_knowledge_base`, `analyze_documents`, `generate_report`) $\to$ Observe $\to$ Step & Timeout Guards (max 6 steps, 45s/tool, 120s total).
   - Generates structured analytical Markdown report with direct empirical citations.
4. **Security & Session**:
   - Browser never handles API JWTs directly; Next.js BFF sets `ei_session` as an httpOnly, Secure cookie and forwards `Bearer` tokens to FastAPI.
   - Multi-tenant data segregation: all SQL queries enforce explicit `user_id` ownership filtering.

