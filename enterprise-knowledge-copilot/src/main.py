import logging
import os
from pathlib import Path
from typing import Optional

from src.agent import (
    AnswerGenerationTool,
    AgentMetrics,
    AgentRunLogger,
    ClarificationTool,
    EnterpriseKnowledgeAgent,
    OpenAIChatClient,
    RetrievalTool,
)
from src.embeddings.vector_store import VectorStore
from src.ingestion.chunker import chunk_text
from src.ingestion.loader import load_documents_from_directory
from src.retrieval.engine import RetrievalEngine


logger = logging.getLogger(__name__)


def build_vector_store(raw_docs_dir: Path, cache_dir: Path) -> VectorStore:
    store = VectorStore()
    manifest = _build_manifest(raw_docs_dir)

    if cache_dir and store.try_load(cache_dir):
        cached_manifest = getattr(store, "manifest", {})
        if cached_manifest.get("documents") == manifest.get("documents"):
            logger.info("Vector store loaded from cache at %s", cache_dir)
            return store
        logger.info("Vector cache stale; rebuilding index")

    documents = load_documents_from_directory(raw_docs_dir)
    if not documents:
        raise FileNotFoundError(
            f"No PDF documents found in {raw_docs_dir}. Add docs before running the agent."
        )

    chunks = chunk_text(documents)
    store.build_index(chunks)

    if cache_dir:
        manifest["built_at"] = _now_iso()
        store.save(cache_dir, manifest)

    return store


def initialize_agent(
    raw_docs_dir: Path = Path("data/raw_docs"),
    llm_client: Optional[object] = None,
    vector_cache_dir: Path = Path("data/processed_chunks/vector_store"),
    log_path: Optional[Path] = Path("data/logs/agent_runs.jsonl"),
    enable_metrics: bool = False,
) -> EnterpriseKnowledgeAgent:
    store = build_vector_store(raw_docs_dir, vector_cache_dir)
    retrieval_engine = RetrievalEngine(store)
    retrieval_tool = RetrievalTool(retrieval_engine)
    llm_client = llm_client or _maybe_initialize_llm_client()
    answer_tool = AnswerGenerationTool(llm_client=llm_client)
    clarification_tool = ClarificationTool()
    run_logger = AgentRunLogger(log_path) if log_path else None
    metrics = AgentMetrics() if enable_metrics else None

    # Create policy with semantic similarity support
    from src.agent.policy import AgentPolicy
    policy = AgentPolicy(embedding_model=store.model)

    if metrics:
        metrics.set_vector_store_size(len(store.documents))

    return EnterpriseKnowledgeAgent(
        retrieval_tool=retrieval_tool,
        answer_tool=answer_tool,
        clarification_tool=clarification_tool,
        policy=policy,
        run_logger=run_logger,
        metrics=metrics,
    )


def _format_sources(sources):
    if not sources:
        return "-"
    return ", ".join(
        f"{source.get('source')} (p{source.get('page')})" for source in sources
    )


def _maybe_initialize_llm_client() -> Optional[OpenAIChatClient]:
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not found; falling back to deterministic summarizer")
        return None

    try:
        return OpenAIChatClient()
    except ValueError as exc:
        logger.error("Failed to initialize OpenAI client | reason=%s", exc)
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.exception("Unexpected error while creating OpenAI client: %s", exc)
    return None


def _build_manifest(raw_docs_dir: Path) -> dict:
    manifest = {"documents": []}
    for pdf_path in sorted(raw_docs_dir.glob("*.pdf")):
        fingerprint = VectorStore.fingerprint_file(pdf_path)
        manifest["documents"].append({
            "path": str(pdf_path.name),
            "fingerprint": fingerprint,
        })
    return manifest


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def run_cli():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    try:
        agent = initialize_agent()
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return

    logger.info("Enterprise Knowledge Copilot ready")

    conversation: list[str] = []

    while True:
        try:
            question = input("\nEnter your question (or 'exit'): ").strip()
        except KeyboardInterrupt:
            print("\nSession cancelled.")
            break

        if not question:
            print("Question cannot be empty.")
            continue

        if question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        response = agent.run(question, conversation_history=conversation)
        conversation.append(question)
        if response.status == "clarification_needed":
            print("\nNeed clarification:\n", response.answer)
            continue

        print("\nAnswer:\n", response.answer)
        print("\nSources:", _format_sources(response.sources))
        print(f"Confidence: {response.confidence:.2f}")
        if response.status == "no_context":
            print("(No sufficient context retrieved; please rephrase or supply more detail.)")

if __name__ == "__main__":
    run_cli()
