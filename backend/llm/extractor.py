"""
LLM-based obligation extractor using Anthropic Claude.
"""
import json
import logging
from typing import List, Dict, Any

import anthropic

from backend.config import ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS, EXTRACTION_CONFIDENCE_MIN

logger = logging.getLogger(__name__)

TAXONOMY_IDS = ["GOV", "IAM", "LOG", "VULN", "SDLC", "IR", "DATA", "TPRM", "BCDR", "PHYS", "CUST", "PROD"]

EXTRACTION_SYSTEM_PROMPT = """You are an expert information security compliance analyst.
Your task is to extract information security obligations from the provided text chunk.

An obligation is any statement that:
- Requires, mandates, or expects a specific security control or behavior
- Uses language like "must", "shall", "is required", "will", "should", "may" in a normative sense
- Describes a recurring security practice with a clear subject and action

For each obligation found, output a JSON object with these fields:
- primary_category: One of GOV, IAM, LOG, VULN, SDLC, IR, DATA, TPRM, BCDR, PHYS, CUST, PROD
- secondary_categories: Array of 0-2 additional category IDs (different from primary)
- normalized_statement: A clean, normalized restatement of the obligation in present tense, active voice
- modality: One of "must", "should", "may", "implicit"
- action: The verb/action being required (e.g., "encrypt", "review", "notify")
- object_field: What the action is applied to (e.g., "customer data", "access logs")
- scope_system: What systems/people this applies to (e.g., "all production systems", "privileged users")
- frequency_timing: Any timing or frequency mentioned (e.g., "annually", "within 24 hours", null)
- retention_duration: Any data retention period mentioned (e.g., "12 months", null)
- owner_role: Who is responsible (e.g., "Security team", "System administrators", null)
- evidence_hint: What evidence would demonstrate compliance (e.g., "audit log", "policy document", null)
- quote_snippet: The exact verbatim quote from the source text (max 240 chars)
- confidence: Float 0.0-1.0 indicating extraction confidence

Output ONLY a JSON array of obligation objects. If no obligations are found, output [].
Do not include any explanatory text outside the JSON array."""


def extract_obligations_from_chunk(chunk_text: str, document_id: str, locator: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract obligations from a single text chunk.
    Returns list of obligation dicts ready for DB insertion.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY set. Skipping extraction.")
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""Extract all information security obligations from the following text chunk:

<text>
{chunk_text}
</text>

Source locator: {json.dumps(locator)}

Return a JSON array of obligation objects as specified."""

    try:
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

        obligations_raw = json.loads(raw)
        if not isinstance(obligations_raw, list):
            logger.error("LLM returned non-list response")
            return []

        # Filter and enrich
        obligations = []
        for obs in obligations_raw:
            confidence = float(obs.get("confidence", 0.0))
            if confidence < EXTRACTION_CONFIDENCE_MIN:
                continue
            if obs.get("primary_category") not in TAXONOMY_IDS:
                continue

            secondary = obs.get("secondary_categories", [])
            if not isinstance(secondary, list):
                secondary = []
            secondary = [c for c in secondary if c in TAXONOMY_IDS and c != obs["primary_category"]][:2]

            obligations.append({
                "document_id": document_id,
                "primary_category": obs["primary_category"],
                "secondary_categories": json.dumps(secondary),
                "normalized_statement": str(obs.get("normalized_statement", "")).strip(),
                "modality": obs.get("modality", "implicit"),
                "action": obs.get("action"),
                "object_field": obs.get("object_field"),
                "scope_system": obs.get("scope_system"),
                "frequency_timing": obs.get("frequency_timing"),
                "retention_duration": obs.get("retention_duration"),
                "owner_role": obs.get("owner_role"),
                "evidence_hint": obs.get("evidence_hint"),
                "quote_snippet": str(obs.get("quote_snippet", ""))[:240],
                "source_locator": json.dumps(locator),
                "confidence": confidence,
            })

        return obligations

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from LLM: {e}")
        return []
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        return []
