from typing import List, Dict, Any
import hashlib
import json
import logging
from pathlib import Path
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)


class VectorStore:
    """Lightweight FAISS wrapper with scoring helpers and persistence."""

    INDEX_FILENAME = "index.faiss"
    DOCS_FILENAME = "documents.jsonl"
    METADATA_FILENAME = "manifest.json"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.documents: List[Dict[str, Any]] = []

    def build_index(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            raise ValueError("Cannot build vector index without chunks")

        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.model.encode(texts, show_progress_bar=True)

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dim)
        self.index.add(np.array(embeddings).astype("float32"))

        self.documents = chunks
        logger.info("Vector index built with %d chunks", len(chunks))

    def save(self, directory: Path, manifest: Dict[str, Any]):
        if not self.is_ready():
            raise RuntimeError("Vector index must be built before saving")

        directory.mkdir(parents=True, exist_ok=True)
        index_path = directory / self.INDEX_FILENAME
        docs_path = directory / self.DOCS_FILENAME
        manifest_path = directory / self.METADATA_FILENAME

        faiss.write_index(self.index, str(index_path))
        with docs_path.open("w", encoding="utf-8") as handle:
            for document in self.documents:
                handle.write(json.dumps(document) + "\n")
        manifest_payload = {
            "built_at": manifest.get("built_at"),
            "documents": manifest.get("documents", []),
        }
        manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        logger.info("Vector index persisted to %s", directory)

    def load(self, directory: Path):
        index_path = directory / self.INDEX_FILENAME
        docs_path = directory / self.DOCS_FILENAME
        manifest_path = directory / self.METADATA_FILENAME

        if not index_path.exists() or not docs_path.exists():
            raise FileNotFoundError(f"Vector artifacts missing under {directory}")
        if not manifest_path.exists():
            raise FileNotFoundError(f"Vector manifest missing under {directory}")

        self.index = faiss.read_index(str(index_path))
        documents: List[Dict[str, Any]] = []
        with docs_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                documents.append(json.loads(line))

        if not documents:
            raise ValueError("Vector documents payload is empty")

        self.documents = documents
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        logger.info("Vector index loaded from %s", directory)

    def try_load(self, directory: Path) -> bool:
        try:
            self.load(directory)
            return True
        except (FileNotFoundError, ValueError) as exc:
            logger.info("Vector cache unavailable | path=%s | reason=%s", directory, exc)
            return False

    @staticmethod
    def fingerprint_file(path: Path) -> str:
        hash_obj = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    def is_ready(self) -> bool:
        return self.index is not None and bool(self.documents)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.is_ready():
            raise RuntimeError("Vector index has not been initialized")

        query_embedding = self.model.encode([query])
        distances, indices = self.index.search(
            np.array(query_embedding).astype("float32"),
            top_k
        )

        results: List[Dict[str, Any]] = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            document = self.documents[idx]
            score = self._distance_to_score(distance)
            enriched = {
                "text": document["text"],
                "metadata": document.get("metadata", {}),
                "score": score,
                "distance": float(distance)
            }
            results.append(enriched)

        logger.debug(
            "Vector search completed | query=%s | results=%d",
            query,
            len(results)
        )

        return results

    @staticmethod
    def _distance_to_score(distance: float) -> float:
        # Convert L2 distance to a bounded similarity score.
        return float(1 / (1 + distance))
