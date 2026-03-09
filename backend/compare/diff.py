import json
import logging
from typing import Dict, Any, Optional
from backend.llm.client import call_llm_json
from backend.llm.prompts import DIFF_SYSTEM_PROMPT, DIFF_USER_TEMPLATE

logger = logging.getLogger(__name__)

COMPARABLE_FIELDS = ["modality", "frequency_timing", "retention_duration", "scope_system", "owner_role"]


def compute_diff(
    cluster_a: Dict[str, Any],
    cluster_b: Dict[str, Any],
    analysis_a_name: str,
    analysis_b_name: str,
    obligations_a: list,
    obligations_b: list
) -> Dict[str, Any]:
    """
    Compute diff between two matched clusters using LLM.
    Returns diff_json and conflict_level.
    """
    # Aggregate key attributes from member obligations
    def aggregate_attrs(obligations):
        attrs = {}
        for field in COMPARABLE_FIELDS:
            vals = list(set(str(o.get(field, "")) for o in obligations if o.get(field)))
            if vals:
                attrs[field] = vals[0] if len(vals) == 1 else vals
        return attrs

    attrs_a = aggregate_attrs(obligations_a)
    attrs_b = aggregate_attrs(obligations_b)

    user_prompt = DIFF_USER_TEMPLATE.format(
        analysis_a_name=analysis_a_name,
        cluster_a_statement=cluster_a.get("representative_statement", ""),
        attrs_a=json.dumps(attrs_a),
        analysis_b_name=analysis_b_name,
        cluster_b_statement=cluster_b.get("representative_statement", ""),
        attrs_b=json.dumps(attrs_b)
    )

    try:
        result = call_llm_json(DIFF_SYSTEM_PROMPT, user_prompt, max_retries=1)
        return {
            "diff_json": json.dumps(result.get("differences", [])),
            "conflict_level": result.get("conflict_level", "low"),
            "summary": result.get("summary", "")
        }
    except Exception as e:
        logger.error(f"Diff computation failed: {e}")
        return {"diff_json": "[]", "conflict_level": "low", "summary": str(e)}
