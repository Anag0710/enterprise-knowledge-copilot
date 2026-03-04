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
from src.agent.config import AgentRuntimeConfig
from src.embeddings.vector_store import VectorStore
from src.ingestion.chunker import chunk_text
from src.ingestion.loader import load_documents_from_directory
from src.retrieval.engine import RetrievalEngine


logger = logging.getLogger(__name__)


def build_vector_store(raw_docs_dir: Path, cache_dir: Path, language_detector=None) -> VectorStore:
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
    if language_detector:
        for chunk in chunks:
            chunk_language = language_detector.normalize(language_detector.detect(chunk["text"]))
            chunk["metadata"]["language"] = chunk_language
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
    enable_advanced_retrieval: bool = True,
    *,
    store: Optional[VectorStore] = None,
    agent_config: Optional[AgentRuntimeConfig] = None,
    run_logger: Optional[AgentRunLogger] = None,
    metrics: Optional[AgentMetrics] = None,
) -> EnterpriseKnowledgeAgent:
    config = agent_config or AgentRuntimeConfig(
        enable_advanced_retrieval=enable_advanced_retrieval
    )

    env_multilingual = os.getenv("EKC_MULTILINGUAL")
    if env_multilingual:
        config.multilingual.enabled = env_multilingual.lower() not in {"0", "false", "no"}

    runtime_language_detector = None
    translator = None
    ingestion_language_detector = None

    if config.multilingual.enabled:
        try:
            from src.multilingual.language_detector import LanguageDetector
            from src.multilingual.translator import Translator

            runtime_language_detector = LanguageDetector(config.multilingual.default_language)
            translator = Translator(
                default_target=config.multilingual.default_language,
                provider=config.multilingual.translation_provider
            )
            ingestion_language_detector = runtime_language_detector
        except ImportError as exc:
            logger.warning("Multilingual mode disabled (missing dependency): %s", exc)
            config.multilingual.enabled = False

    if store is None:
        store = build_vector_store(
            raw_docs_dir,
            vector_cache_dir,
            language_detector=ingestion_language_detector
        )
    
    # Create retrieval engine with advanced features
    retrieval_engine = RetrievalEngine(
        store,
        enable_reranking=config.enable_advanced_retrieval,
        enable_hybrid_search=config.enable_advanced_retrieval,
        enable_query_reformulation=config.enable_advanced_retrieval
    )
    
    # Build BM25 index for hybrid search if enabled
    if config.enable_advanced_retrieval and retrieval_engine.hybrid_search:
        try:
            retrieval_engine.index_for_hybrid_search(store.documents)
            logger.info("BM25 index built for hybrid search")
        except Exception as e:
            logger.warning(f"Failed to build BM25 index: {e}")
    
    retrieval_tool = RetrievalTool(retrieval_engine)
    llm_client = llm_client or _maybe_initialize_llm_client()
    answer_tool = AnswerGenerationTool(llm_client=llm_client)
    clarification_tool = ClarificationTool()
    run_logger = run_logger or (AgentRunLogger(log_path) if log_path else None)
    metrics = metrics or (AgentMetrics() if enable_metrics else None)

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
        enable_specialized_tools=config.enable_specialized_tools,
        retrieval_confidence_threshold=config.retrieval_confidence_threshold,
        language_detector=runtime_language_detector,
        translator=translator,
        default_language=config.multilingual.default_language,
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
    """Build manifest for all supported document formats."""
    manifest = {"documents": []}
    supported_extensions = ['*.pdf', '*.docx', '*.xlsx', '*.txt', '*.md', '*.html']
    
    for pattern in supported_extensions:
        for doc_path in sorted(raw_docs_dir.glob(pattern)):
            fingerprint = VectorStore.fingerprint_file(doc_path)
            manifest["documents"].append({
                "path": str(doc_path.name),
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
