import time
import anthropic
import logging
from backend.config import ANTHROPIC_API_KEY, LLM_MODEL, LLM_MAX_TOKENS

logger = logging.getLogger(__name__)

def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def call_llm(system: str, user: str, max_tokens: int = LLM_MAX_TOKENS) -> str:
    """Call Claude and return text response. Retries with backoff on rate limits."""
    client = get_client()
    for attempt in range(5):
        try:
            with client.messages.stream(
                model=LLM_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}]
            ) as stream:
                return stream.get_final_message().content[-1].text
        except anthropic.RateLimitError as e:
            wait = 2 ** (attempt + 2)  # 4s, 8s, 16s, 32s, 64s
            logger.warning(f"Rate limit hit (attempt {attempt+1}), waiting {wait}s: {e}")
            time.sleep(wait)
    raise RuntimeError("Rate limit: exhausted retries")

def call_llm_json(system: str, user: str, max_retries: int = 2) -> dict:
    """Call Claude expecting JSON response. Retries on parse failure."""
    import json
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            text = call_llm(system, user)
            # Strip markdown code fences if present
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            return json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            last_err = e
            logger.warning(f"LLM JSON parse attempt {attempt+1} failed: {e}")
    raise ValueError(f"LLM failed to return valid JSON after {max_retries+1} attempts: {last_err}")
