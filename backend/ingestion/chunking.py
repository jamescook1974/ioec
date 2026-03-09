from typing import List, Dict, Any
from backend.config import CHUNK_TARGET_TOKENS, CHUNK_OVERLAP_RATIO

def estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)

def chunk_pages(pages: List[Dict[str, Any]], document_id: str) -> List[Dict[str, Any]]:
    """
    pages: list of dicts with 'text' and optionally 'page', 'section', 'paragraph_index'
    Returns list of chunk dicts with: document_id, chunk_index, text, locator
    """
    chunks = []
    chunk_index = 0
    all_texts = []

    for p in pages:
        text = p.get("text", "")
        if not text.strip():
            continue
        words = text.split()
        all_texts.append((words, p))

    # Flatten all words with source metadata
    flat_words = []
    flat_meta = []
    for words, meta in all_texts:
        for w in words:
            flat_words.append(w)
            flat_meta.append(meta)

    if not flat_words:
        return []

    target_words = int(CHUNK_TARGET_TOKENS / 1.3)
    overlap_words = int(target_words * CHUNK_OVERLAP_RATIO)

    start = 0
    while start < len(flat_words):
        end = min(start + target_words, len(flat_words))
        chunk_words = flat_words[start:end]
        chunk_text = " ".join(chunk_words)

        # Build locator from first and last meta
        first_meta = flat_meta[start] if start < len(flat_meta) else {}
        locator = {
            "page": first_meta.get("page"),
            "section": first_meta.get("section"),
            "paragraph": first_meta.get("paragraph_index")
        }

        chunks.append({
            "document_id": document_id,
            "chunk_index": chunk_index,
            "text": chunk_text,
            "locator": locator
        })
        chunk_index += 1

        if end >= len(flat_words):
            break
        start = end - overlap_words

    return chunks

def chunk_text_direct(text: str, document_id: str) -> List[Dict[str, Any]]:
    """Chunk plain text directly."""
    pages = [{"text": text, "page": None, "section": None, "paragraph_index": 0}]
    return chunk_pages(pages, document_id)
