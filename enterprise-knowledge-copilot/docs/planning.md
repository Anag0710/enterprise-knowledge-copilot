# Planning Notes

## Near-term backlog
- Build admin dashboard for experiment summaries (variant win rates, traffic splits, guardrail metrics).
- Surface multilingual usage stats (per-language volumes, refusal rates) in Prometheus/Grafana.
- Add configurable PII redaction modes to `/export` so compliance can pick mask/hash/remove per channel.

## Agent reasoning flow
1. **Question intake**: `AgentPolicy.entrypoint_decision()` checks length, pronouns, and ambiguous keywords; may dispatch clarification immediately.
2. **Retrieval-first**: `RetrievalTool` executes before any generation; FAISS distance is converted into a [0,1] confidence score.
3. **Safety gate**: confidence is compared to the threshold; if low, `AgentPolicy.should_refuse()` returns the refusal template.
4. **Answer orchestration**: when confidence passes, `AnswerGenerationTool` builds a grounded prompt (or deterministic fallback) and records citations.
5. **Response packaging**: `EnterpriseKnowledgeAgent` emits `AgentResponse` with status (`answered`, `clarification_needed`, `no_context`) plus `AgentStep` logs for every tool call.

## Risks
- Cached embeddings can become stale if documents change without an invalidation strategy.
- Clarification heuristics are rule-based; subtle ambiguity or multilingual prompts may still slip through without semantic checks.
- OpenAI integration introduces external dependency risk (latency, rate limits, compliance) that needs monitoring hooks.

## Known limitations
- Cache invalidation currently hashes only PDF contents; it does not detect partial-page updates inside PDFs (would require ingestion-level diffing).
- Clarification logic is still heuristic; it does not leverage semantic similarity to prior turns.
- When no `OPENAI_API_KEY` is present the system falls back to a deterministic summary, which is unsuitable for production answers.
- Evaluation suite depends on manually curated JSON and reports pass/fail only (no answer quality scoring yet).
