import logging
from typing import List, Dict, Any, Optional
from backend.config import CLUSTERING_SIMILARITY_THRESHOLD
from backend.embed.embeddings import cosine_similarity, json_to_vec, embed_text

logger = logging.getLogger(__name__)


def cluster_obligations(obligations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group obligations into clusters by embedding similarity within each category.
    obligations: list of dicts with keys: id, primary_category, normalized_statement, confidence, embedding_json
    Returns: list of cluster dicts with member_indices (indices into obligations list)
    """
    # Group by category
    by_category: Dict[str, List[int]] = {}
    for i, obs in enumerate(obligations):
        cat = obs.get("primary_category", "GOV")
        by_category.setdefault(cat, []).append(i)

    clusters = []
    for category, indices in by_category.items():
        # Sort by confidence descending
        sorted_indices = sorted(indices, key=lambda i: obligations[i].get("confidence", 0), reverse=True)

        category_clusters = []  # list of (representative_vec, member_indices)

        for idx in sorted_indices:
            obs = obligations[idx]
            vec = json_to_vec(obs.get("embedding_json", ""))
            if vec is None:
                # No embedding, create singleton cluster
                category_clusters.append((None, [idx]))
                continue

            # Try to assign to existing cluster
            assigned = False
            for c_idx, (c_vec, c_members) in enumerate(category_clusters):
                if c_vec is None:
                    continue
                sim = cosine_similarity(vec, c_vec)
                if sim >= CLUSTERING_SIMILARITY_THRESHOLD:
                    c_members.append(idx)
                    assigned = True
                    break

            if not assigned:
                category_clusters.append((vec, [idx]))

        # Build cluster records
        for c_vec, c_members in category_clusters:
            # Representative: highest confidence member
            rep_idx = max(c_members, key=lambda i: obligations[i].get("confidence", 0))
            rep_stmt = obligations[rep_idx].get("normalized_statement", "")

            # Compute cluster embedding as average
            vecs = [json_to_vec(obligations[i].get("embedding_json", "")) for i in c_members]
            valid_vecs = [v for v in vecs if v is not None]
            if valid_vecs:
                import numpy as np
                avg_vec = np.mean(valid_vecs, axis=0).tolist()
            else:
                avg_vec = None

            clusters.append({
                "primary_category": category,
                "representative_statement": rep_stmt,
                "member_indices": c_members,
                "cluster_embedding": avg_vec,
                "obligation_count": len(c_members)
            })

    return clusters
