# Architecture Overview

## Layers
1. **Ingestion**
   - `src/ingestion/loader.py` loads PDFs page-by-page, normalizes whitespace, preserves metadata.
   - `src/ingestion/chunker.py` slices pages into overlapping chunks with source/page/chunk identifiers.
2. **Embedding + Storage**
   - `src/embeddings/vector_store.py` encodes every chunk with SentenceTransformers, adds them to a FAISS index, and persists both the index (`index.faiss`) and metadata (`documents.jsonl`) under `data/processed_chunks/vector_store/` for fast restarts.
3. **Retrieval**
   - `src/retrieval/engine.py` converts FAISS hits into typed `RetrievedChunk` objects and computes aggregate confidence.
4. **Agent**
   - `src/agent/policy.py` decides whether to clarify, retrieve, answer, or refuse. Now includes semantic vagueness detection using embedding similarity.
   - `src/agent/tools.py` contains retrieval, answer-generation, and clarification tools with logging hooks.
   - `src/agent/llm_client.py` provides the production OpenAI client with retry, backoff, and redaction.
   - `src/agent/controller.py` orchestrates steps, logs tool calls, enforces safety gates, and returns formatted responses.
   - `src/agent/metrics.py` collects Prometheus metrics for observability (request durations, confidence scores, decision counts).
5. **Observability**
   - `src/agent/logger.py` appends every run (question, steps, citations, retrieved chunks) to `data/logs/agent_runs.jsonl` for auditing.
   - `src/agent/metrics.py` exposes Prometheus-compatible metrics for dashboards and alerting.
6. **API Layer**
   - `src/api.py` provides FastAPI REST endpoints: `/ask` for questions, `/health` for status, `/metrics` for Prometheus scraping.
   - `ui/index.html` is a standalone web interface for interactive chat with the agent.
7. **Evaluation**
   - `src/evaluation/suite.py` loads JSON cases, runs the agent, and checks behavior, faithfulness, hallucination handling, and retrieval targeting.
   - `evaluation/eval_questions.json` now has 12+ diverse test cases covering answer/clarify/refuse scenarios.

## Data flow
1. PDFs → loader → cleaned page objects with metadata.
2. Pages → chunker → overlapping chunks (id: `source_page_chunk`).
3. Chunks → vector store → FAISS index + metadata cache (persisted for reuse).
4. Query → retrieval engine → ranked chunks + confidence.
5. Agent policy routes between clarification (semantic vagueness detection), refusal, or answering with citations. Answering uses the OpenAI client when configured, otherwise deterministic fallback.
6. CLI loop keeps requesting clarifications until enough context exists.
7. Agent logger writes the full interaction trace for observability.
8. Metrics collector tracks performance for Prometheus.
9. REST API exposes `/ask`, `/health`, `/metrics` endpoints.
10. Evaluation suite replays questions to detect regressions; `evaluation/run_eval.py` is the entry point for CI.

## Safety + Explainability
- Confidence thresholds enforced before generation; refusal message includes rationale.
- Every agent step captures `AgentStep` and `ToolCallLog` for observability.
- Citations are deduplicated by `(source, page)` and verified against retrieved chunks.
- Clarification heuristics guard against pronoun-heavy, short, or ambiguous prompts.
- Audit logs provide after-the-fact explainability without relying on console history.
