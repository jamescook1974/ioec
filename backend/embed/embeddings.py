import json
import logging
import numpy as np
from typing import List, Optional
from backend.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)
_model = None


def get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    return _model


def embed_text(text: str) -> List[float]:
    model = get_model()
    vec = model.encode([text])[0]
    return vec.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_model()
    vecs = model.encode(texts)
    return [v.tolist() for v in vecs]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    a_arr = np.array(a, dtype=float)
    b_arr = np.array(b, dtype=float)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


def vec_to_json(vec: List[float]) -> str:
    return json.dumps(vec)


def json_to_vec(s: str) -> Optional[List[float]]:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None
