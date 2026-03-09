"""
Embedding utilities using sentence-transformers.
Falls back to a simple TF-IDF style approximation if sentence-transformers is unavailable.
"""
import logging
from typing import List, Optional
import numpy as np

from backend.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.warning(f"Could not load sentence-transformers model: {e}. Using fallback.")
            _model = "fallback"
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts, returning list of float vectors."""
    if not texts:
        return []
    model = _get_model()
    if model == "fallback":
        return _fallback_embed(texts)
    try:
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return embeddings.tolist()
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return _fallback_embed(texts)


def embed_text(text: str) -> List[float]:
    """Embed a single text string."""
    results = embed_texts([text])
    return results[0] if results else []


def cosine_similarity_matrix(embeddings_a: List[List[float]], embeddings_b: List[List[float]]) -> np.ndarray:
    """Compute cosine similarity matrix between two sets of embeddings."""
    if not embeddings_a or not embeddings_b:
        return np.array([])
    a = np.array(embeddings_a)
    b = np.array(embeddings_b)
    # Normalize
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return np.dot(a_norm, b_norm.T)


def _fallback_embed(texts: List[str]) -> List[List[float]]:
    """Simple character n-gram based fallback embedding (dim=128)."""
    dim = 128
    result = []
    for text in texts:
        vec = np.zeros(dim)
        text_lower = text.lower()
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i+3]
            idx = hash(trigram) % dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        result.append(vec.tolist())
    return result
