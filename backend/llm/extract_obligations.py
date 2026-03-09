import logging
import json
from typing import List, Dict, Any
from backend.config import EXTRACTION_CONFIDENCE_MIN, QUOTE_SNIPPET_MAX_LEN
from backend.llm.client import call_llm_json
from backend.llm.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_TEMPLATE

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"GOV", "IAM", "LOG", "VULN", "SDLC", "IR", "DATA", "TPRM", "BCDR", "PHYS", "CUST", "PROD"}
VALID_MODALITIES = {"must", "should", "may", "implicit"}


def validate_obligation(obs: dict) -> bool:
    if not obs.get("normalized_statement"):
        return False
    if obs.get("primary_category") not in VALID_CATEGORIES:
        return False
    if obs.get("modality") not in VALID_MODALITIES:
        obs["modality"] = "implicit"
    conf = obs.get("confidence", 0.0)
    if not isinstance(conf, (int, float)) or conf < EXTRACTION_CONFIDENCE_MIN:
        return False
    # Truncate quote_snippet
    qs = obs.get("quote_snippet", "")
    if len(qs) > QUOTE_SNIPPET_MAX_LEN:
        obs["quote_snippet"] = qs[:QUOTE_SNIPPET_MAX_LEN]
    # Cap secondary categories
    sc = obs.get("secondary_categories", [])
    if not isinstance(sc, list):
        sc = []
    obs["secondary_categories"] = [c for c in sc if c in VALID_CATEGORIES][:2]
    return True


def extract_from_chunks(chunks: List[Dict[str, Any]], source_name: str) -> List[Dict[str, Any]]:
    """Extract obligations from all chunks. Returns list of obligation dicts."""
    all_obligations = []
    for chunk in chunks:
        chunk_text = chunk["text"]
        if len(chunk_text.strip()) < 50:
            continue
        user_prompt = EXTRACTION_USER_TEMPLATE.format(
            source_name=source_name,
            chunk_index=chunk["chunk_index"],
            chunk_text=chunk_text[:8000]  # Safety limit
        )
        try:
            result = call_llm_json(EXTRACTION_SYSTEM_PROMPT, user_prompt)
            obligations = result.get("obligations", [])
            for obs in obligations:
                if validate_obligation(obs):
                    # Merge locator from chunk
                    chunk_locator = chunk.get("locator", {})
                    if obs.get("source_locator"):
                        for k, v in chunk_locator.items():
                            if obs["source_locator"].get(k) is None:
                                obs["source_locator"][k] = v
                    else:
                        obs["source_locator"] = chunk_locator
                    all_obligations.append(obs)
        except Exception as e:
            logger.error(f"Extraction failed for chunk {chunk.get('chunk_index')}: {e}")
    return all_obligations
