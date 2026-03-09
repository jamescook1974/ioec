"""
LLM-based cluster representative statement generator.
"""
import json
import logging
from typing import List, Dict, Any

import anthropic

from backend.config import ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS

logger = logging.getLogger(__name__)

CLUSTER_SYSTEM_PROMPT = """You are an expert information security policy writer.
Given a set of similar security obligations, write a single unified representative statement
that captures the core requirement expressed across all of them.

The representative statement should:
- Be written in clear, formal policy language
- Use present tense, active voice
- Capture the most specific/restrictive version when obligations conflict on details
- Be concise (1-2 sentences maximum)

Return ONLY the representative statement as plain text, no JSON, no quotes."""


def generate_representative_statement(obligations: List[Dict[str, Any]], category: str) -> str:
    """
    Given a list of obligation dicts, generate a representative cluster statement.
    Falls back to the first obligation's normalized_statement if LLM unavailable.
    """
    if not obligations:
        return ""

    fallback = obligations[0].get("normalized_statement", "")

    if not ANTHROPIC_API_KEY:
        return fallback

    statements = [o.get("normalized_statement", "") for o in obligations if o.get("normalized_statement")]
    if not statements:
        return fallback

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""Category: {category}

The following security obligations have been grouped together as similar:

{chr(10).join(f"- {s}" for s in statements)}

Write a single representative statement that captures the core requirement."""

    try:
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=512,
            system=CLUSTER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        result = response.content[0].text.strip()
        return result if result else fallback
    except Exception as e:
        logger.error(f"Cluster representative generation error: {e}")
        return fallback


def cluster_obligations(obligations: List[Dict[str, Any]], category: str, similarity_threshold: float) -> List[Dict[str, Any]]:
    """
    Cluster a list of obligations by semantic similarity.
    Returns list of cluster dicts: {representative_statement, member_obligation_ids, obligation_count}

    Uses embeddings + greedy clustering.
    """
    if not obligations:
        return []

    from backend.embed.embedder import embed_texts, cosine_similarity_matrix
    import numpy as np

    texts = [o.get("normalized_statement", "") for o in obligations]
    embeddings = embed_texts(texts)

    if not embeddings or len(embeddings) != len(obligations):
        # Fallback: each obligation is its own cluster
        clusters = []
        for o in obligations:
            clusters.append({
                "representative_statement": o.get("normalized_statement", ""),
                "member_ids": [o["id"]],
                "obligation_count": 1
            })
        return clusters

    sim_matrix = cosine_similarity_matrix(embeddings, embeddings)
    n = len(obligations)
    assigned = [False] * n
    clusters = []

    for i in range(n):
        if assigned[i]:
            continue
        # Find all unassigned obligations similar to i
        members_idx = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if not assigned[j] and sim_matrix[i][j] >= similarity_threshold:
                members_idx.append(j)
                assigned[j] = True

        member_obligations = [obligations[idx] for idx in members_idx]
        member_ids = [o["id"] for o in member_obligations]

        if len(member_obligations) == 1:
            rep_statement = member_obligations[0].get("normalized_statement", "")
        else:
            rep_statement = generate_representative_statement(member_obligations, category)

        clusters.append({
            "representative_statement": rep_statement,
            "member_ids": member_ids,
            "obligation_count": len(member_ids)
        })

    return clusters
