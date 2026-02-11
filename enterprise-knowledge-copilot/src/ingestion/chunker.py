from typing import List, Dict


def chunk_text(
    documents: List[Dict],
    chunk_size: int = 500,
    overlap: int = 100
) -> List[Dict]:
    """
    Split documents into overlapping chunks.
    """
    chunks = []

    for doc in documents:
        words = doc["text"].split()
        start = 0
        chunk_id = 0

        while start < len(words):
            end = start + chunk_size
            chunk_words = words[start:end]

            chunks.append({
                "id": f'{doc["metadata"]["source"]}_p{doc["metadata"]["page"]}_c{chunk_id}',
                "text": " ".join(chunk_words),
                "metadata": {
                    **doc["metadata"],
                    "chunk": chunk_id
                }
            })

            start = end - overlap
            chunk_id += 1

    return chunks
