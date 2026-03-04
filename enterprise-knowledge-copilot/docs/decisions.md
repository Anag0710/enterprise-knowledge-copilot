# Key Design Decisions

1. **Rule-based policy before LLM calls**
   - Guarantees retrieval-before-generation and keeps reasoning explainable.
2. **Tool abstraction instead of direct function calls**
   - Retrieval, answer generation, and clarification are discrete tools with logs, mimicking enterprise agent platforms.
3. **Confidence derived from FAISS distances**
   - L2 distance is converted to a bounded [0,1] score so safety thresholds remain implementation-agnostic.
4. **LLM client is a protocol**
   - Allows plugging OpenAI, Azure OpenAI, Anthropic, or internal models without touching agent logic. Fallback template keeps the app runnable without credentials.
5. **Evaluation configured through JSON**
   - Keeps regression tests data-driven and easy to extend without touching code.
6. **Persist FAISS artifacts as JSONL + binary index**
   - Keeps reload times low without introducing heavyweight databases; artifacts live under `data/processed_chunks/vector_store/`.
7. **Production OpenAI client with retry + redaction**
   - `OpenAIChatClient` centralizes rate-limit handling, exponential backoff, and sensitive text scrubbing before prompts leave the network.
8. **Audit every run to JSONL**
   - `AgentRunLogger` creates a tamper-evident record of questions, steps, and retrieved chunks so SOC and compliance reviews have source data.
9. **Checksum-based cache invalidation**
   - Before loading cached embeddings, we hash each raw PDF and compare against the manifest so stale caches rebuild automatically.
10. **CLI clarification loop**
   - Keeps the user inside one session, allowing clarification prompts and retries without restarting the app.
11. **Dedicated evaluation runner**
   - `evaluation/run_eval.py` gives CI and developers a single entry point that exits non-zero on failure, mirroring unit-test ergonomics.
12. **Prometheus metrics for observability**
   - Centralized `AgentMetrics` class tracks request durations, confidence distributions, decision counts, cache performance, and LLM calls.
13. **Semantic vagueness detection**
   - Policy uses embedding similarity (cosine distance) to detect vaguely phrased questions beyond simple keyword matching.
14. **FastAPI REST API**
   - Production-ready HTTP interface with async support, automatic OpenAPI docs, health checks, and Prometheus integration.
15. **Standalone web UI**
   - Single-file HTML/JS interface demonstrates the API without requiring framework dependencies; chat UI with real-time status indicators.
16. **Multilingual normalization before retrieval**
   - Questions/history are auto-detected and translated into English so the same policy/routing logic works globally; answers/refusals are localized back to the detected language.
17. **Pluggable experiment harness**
   - `evaluation/experiments.json` describes variants that are instantiated on-demand, letting us test retrieval/policy tweaks without branching deployments.
18. **Async log shipper**
   - Audit logs stream to an HTTP endpoint via a bounded buffer + retries so SOC teams ingest data in near real time without blocking the request path.
