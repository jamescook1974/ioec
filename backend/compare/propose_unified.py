import logging
from typing import Dict, Any
from backend.llm.client import call_llm_json
from backend.llm.prompts import UNIFIED_SYSTEM_PROMPT, UNIFIED_USER_TEMPLATE

logger = logging.getLogger(__name__)


def propose_unified(
    statement_a: str,
    statement_b: str,
    conflict_summary: str,
    analysis_a_name: str,
    analysis_b_name: str
) -> Dict[str, str]:
    """
    Propose unified obligation statements for a conflicting pair.
    Returns dict with strictest_merge, align_to_a, align_to_b.
    """
    user_prompt = UNIFIED_USER_TEMPLATE.format(
        analysis_a_name=analysis_a_name,
        statement_a=statement_a,
        analysis_b_name=analysis_b_name,
        statement_b=statement_b,
        conflict_summary=conflict_summary
    )
    try:
        result = call_llm_json(UNIFIED_SYSTEM_PROMPT, user_prompt, max_retries=1)
        return result.get("proposals", {
            "strictest_merge": statement_a,
            "align_to_a": statement_a,
            "align_to_b": statement_b
        })
    except Exception as e:
        logger.error(f"Unified proposal failed: {e}")
        return {
            "strictest_merge": statement_a,
            "align_to_a": statement_a,
            "align_to_b": statement_b
        }
