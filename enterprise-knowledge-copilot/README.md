# Enterprise Knowledge Copilot (RAG + Agentic AI)

Enterprise-grade retrieval-augmented generation (RAG) assistant that constrains answers to internal documents and explains every decision it makes. The goal is to be interview-ready code that a real company would ship.

## Why this project exists
- Protects against hallucinations by forcing retrieval before generation and refusing when context is weak.
- Encapsulates agent reasoning so decisions are logged, auditable, and easy to explain to stakeholders.
- Keeps tooling minimal (pdfplumber, FAISS, sentence-transformers) for reliability and portability.

## Architecture at a glance
1. **Ingestion**: [`ingestion/loader.py`](src/ingestion/loader.py) parses PDFs with pdfplumber, [`ingestion/chunker.py`](src/ingestion/chunker.py) creates overlapping context windows.
2. **Vector store**: [`embeddings/vector_store.py`](src/embeddings/vector_store.py) embeds chunks with SentenceTransformers, indexes them in FAISS, and persists both the index and metadata under `data/processed_chunks/vector_store/`.
3. **Retrieval**: [`retrieval/engine.py`](src/retrieval/engine.py) normalizes FAISS hits into typed results with confidence metrics.
4. **Agent**: [`agent/controller.py`](src/agent/controller.py) orchestrates policy, tools, safety gates, and logging. Tools live in [`agent/tools.py`](src/agent/tools.py); guardrails in [`agent/policy.py`](src/agent/policy.py); production LLM integration is handled by [`agent/llm_client.py`](src/agent/llm_client.py).
5. **Observation + audit**: [`agent/logger.py`](src/agent/logger.py) streams every run to `data/logs/agent_runs.jsonl` for compliance-grade tracing.
6. **Evaluation**: [`evaluation/suite.py`](src/evaluation/suite.py) runs behavior, faithfulness, and retrieval-quality checks driven by `evaluation/eval_questions.json`.

## Core safety rules (enforced in code)
- Retrieval occurs before any generation. No context → no answer.
- If confidence < threshold, the agent says "I don't know" and cites why.
- Citations preserve source + page metadata, verified during evaluation.
- Clarification tool triggers when the question is underspecified or relies on pronouns/ambiguous keywords with no history.
- **Semantic vagueness detection** uses embedding similarity to catch vague questions like "tell me more" or "explain that" even when phrased differently.
- Every interaction is written to a JSONL audit log so investigations never rely on transient console output.
- **Prometheus metrics** track confidence, retrieval quality, decision paths, and LLM performance for production monitoring.

## Getting started

### CLI Usage
1. Drop PDFs into `data/raw_docs/`.
2. Install dependencies: `pip install -r requirements.txt`.
3. (Optional but recommended) Export `OPENAI_API_KEY` (and `OPENAI_ORG` if using Azure OpenAI) so the production LLM client can replace the deterministic fallback.
4. Run the agent: `python -m src.main`. The CLI loads the cached vector index from `data/processed_chunks/vector_store/` (building it once if absent) and stays in a loop so clarification prompts/feed-back conversations happen in one session. Type `exit` to quit.
5. Inspect audit trails in `data/logs/agent_runs.jsonl` or wire them into your existing log pipeline.
6. Run evaluations locally or in CI with `python evaluation/run_eval.py --questions evaluation/eval_questions.json`.

### REST API Usage
1. Start the API server: `python -m uvicorn src.api:app --reload`
2. Access interactive docs at `http://localhost:8000/docs`
3. Key endpoints:
   - `POST /ask` - Submit questions and get answers
   - `GET /health` - Check system status
   - `GET /metrics` - Prometheus metrics endpoint

### Web UI
1. Start the API server (see above)
2. Open `ui/index.html` in your browser
3. Beautiful chat interface with real-time status indicators

### Monitoring
- Prometheus metrics exposed at `/metrics` endpoint
- Track request durations, confidence scores, decision types, cache hits/misses
- Visualize with Grafana or any Prometheus-compatible tool

## Evaluation workflow
- Expanded test suite with 12+ cases covering:
  - Direct answers with source verification
  - Clarification triggers (vague/pronoun-heavy questions)
  - Refusal cases (out-of-domain queries)
  - Multi-document synthesis scenarios
- Run `python evaluation/run_eval.py --questions evaluation/eval_questions.json` to get pass/fail metrics plus failure details (non-zero exit code on failure so CI can gate releases).
- Treat evaluation output like unit tests: wire it into CI before deployment to catch regressions.

## Next steps
- Configure Grafana dashboards to visualize Prometheus metrics (request latency, confidence distributions, cache performance)
- Integrate with enterprise SSO/authentication for multi-user deployments
- Add document versioning to track when knowledge base content changes
- Scale horizontally by deploying multiple API instances behind a load balancer
