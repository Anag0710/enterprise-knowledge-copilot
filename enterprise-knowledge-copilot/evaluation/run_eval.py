"""CLI entry point for running the evaluation suite locally or in CI."""

import argparse
import json
import logging
from pathlib import Path

from src.agent import (
    AnswerGenerationTool,
    ClarificationTool,
    EnterpriseKnowledgeAgent,
    RetrievalTool,
)
from src.embeddings.vector_store import VectorStore
from src.ingestion.chunker import chunk_text
from src.ingestion.loader import load_documents_from_directory
from src.retrieval.engine import RetrievalEngine
from src.evaluation.suite import EvaluationSuite


logger = logging.getLogger(__name__)


def build_agent(raw_docs_dir: Path, vector_cache_dir: Path) -> EnterpriseKnowledgeAgent:
    from src.main import initialize_agent  # reuse existing wiring

    return initialize_agent(raw_docs_dir=raw_docs_dir, vector_cache_dir=vector_cache_dir)


def main():
    parser = argparse.ArgumentParser(description="Run Enterprise Knowledge Copilot evaluations")
    parser.add_argument("--questions", default="evaluation/eval_questions.json", help="Path to evaluation JSON")
    parser.add_argument("--raw-docs", default="data/raw_docs", help="Directory containing raw PDFs")
    parser.add_argument("--vector-cache", default="data/processed_chunks/vector_store", help="Cache directory for FAISS artifacts")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    questions_path = Path(args.questions)
    raw_docs_dir = Path(args.raw_docs)
    vector_cache_dir = Path(args.vector_cache)

    agent = build_agent(raw_docs_dir, vector_cache_dir)
    suite = EvaluationSuite(agent, questions_path)
    metrics = suite.run()

    print(json.dumps(metrics.__dict__, indent=2))

    if metrics.failed > 0:
        print("Failures:")
        for detail in metrics.details:
            print("-", detail)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
