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


def _process_chunk(chunk: Dict[str, Any], source_name: str) -> List[Dict[str, Any]]:
    """Extract obligations from a single chunk."""
    chunk_text = chunk["text"]
    if len(chunk_text.strip()) < 50:
        return []
    user_prompt = EXTRACTION_USER_TEMPLATE.format(
        source_name=source_name,
        chunk_index=chunk["chunk_index"],
        chunk_text=chunk_text[:8000]
    )
    try:
        result = call_llm_json(EXTRACTION_SYSTEM_PROMPT, user_prompt)
        obligations = result.get("obligations", [])
        valid = []
        for obs in obligations:
            if validate_obligation(obs):
                chunk_locator = chunk.get("locator", {})
                if obs.get("source_locator"):
                    for k, v in chunk_locator.items():
                        if obs["source_locator"].get(k) is None:
                            obs["source_locator"][k] = v
                else:
                    obs["source_locator"] = chunk_locator
                valid.append(obs)
        return valid
    except Exception as e:
        logger.error(f"Extraction failed for chunk {chunk.get('chunk_index')}: {e}")
        return []


def extract_from_chunks(chunks: List[Dict[str, Any]], source_name: str, chunk_callback=None) -> List[Dict[str, Any]]:
    """Extract obligations from all chunks in parallel. Returns list of obligation dicts."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_obligations = []
    max_workers = min(8, len(chunks))
    if max_workers == 0:
        return []
    futures = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for chunk in chunks:
            f = executor.submit(_process_chunk, chunk, source_name)
            futures[f] = chunk
        for f in as_completed(futures):
            all_obligations.extend(f.result())
            if chunk_callback:
                chunk_callback()
    return all_obligations
