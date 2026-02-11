from pathlib import Path
from typing import List, Dict
import pdfplumber

# Import chunker correctly
from src.ingestion.chunker import chunk_text
from src.embeddings.vector_store import VectorStore


def clean_text(text: str) -> str:
    """Basic text cleaning for enterprise documents."""
    text = text.replace("\n", " ")
    text = " ".join(text.split())
    return text


def load_pdf(file_path: Path) -> List[Dict]:
    """
    Load a PDF file and extract text page by page.
    """
    documents = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if not text:
                continue

            documents.append({
                "text": clean_text(text),
                "metadata": {
                    "source": file_path.name,
                    "page": page_num
                }
            })

    return documents


def load_documents_from_directory(directory: Path, pattern: str = "*.pdf") -> List[Dict]:
    """Load every matching document inside the directory."""
    all_documents: List[Dict] = []
    for file_path in sorted(directory.glob(pattern)):
        all_documents.extend(load_pdf(file_path))
    return all_documents

if __name__ == "__main__":
    docs_path = Path("data/raw_docs")
    pages = load_documents_from_directory(docs_path)
    chunks = chunk_text(pages)

    store = VectorStore()
    store.build_index(chunks)

    query = "What is the leave policy?"
    results = store.search(query)

    print("Top retrieved chunk:")
    print(results[0])
