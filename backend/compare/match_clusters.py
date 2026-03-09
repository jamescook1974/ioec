import logging
from typing import List, Dict, Any, Tuple
from backend.config import MATCH_SIMILARITY_THRESHOLD
from backend.embed.embeddings import cosine_similarity, json_to_vec

logger = logging.getLogger(__name__)


def match_clusters(
    clusters_a: List[Dict[str, Any]],
    clusters_b: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    clusters_a/b: list of cluster dicts with cluster_embedding_json, primary_category, id, representative_statement
    Returns: {
        "matched": [(cluster_a_id, cluster_b_id, similarity, category)],
        "a_only": [cluster_a_id, ...],
        "b_only": [cluster_b_id, ...]
    }
    """
    matched = []
    matched_b_ids = set()

    for ca in clusters_a:
        ca_vec = json_to_vec(ca.get("cluster_embedding_json", ""))
        best_sim = -1.0
        best_cb = None

        for cb in clusters_b:
            if cb["id"] in matched_b_ids:
                continue
            # Must be same category
            if ca.get("primary_category") != cb.get("primary_category"):
                continue
            cb_vec = json_to_vec(cb.get("cluster_embedding_json", ""))
            if ca_vec is None or cb_vec is None:
                continue
            sim = cosine_similarity(ca_vec, cb_vec)
            if sim > best_sim:
                best_sim = sim
                best_cb = cb

        if best_cb is not None and best_sim >= MATCH_SIMILARITY_THRESHOLD:
            matched.append((ca["id"], best_cb["id"], best_sim, ca.get("primary_category")))
            matched_b_ids.add(best_cb["id"])

    matched_a_ids = {m[0] for m in matched}
    a_only = [ca["id"] for ca in clusters_a if ca["id"] not in matched_a_ids]
    b_only = [cb["id"] for cb in clusters_b if cb["id"] not in matched_b_ids]

    return {"matched": matched, "a_only": a_only, "b_only": b_only}
