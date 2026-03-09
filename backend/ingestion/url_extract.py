from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def extract_url(url: str) -> List[Dict[str, Any]]:
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        sections = []
        current_heading = "Content"
        buffer = []
        for elem in soup.find_all(["h1","h2","h3","h4","p","li","td","th"]):
            if elem.name in ["h1","h2","h3","h4"]:
                if buffer:
                    sections.append({"section": current_heading, "text": " ".join(buffer), "paragraph_index": len(sections)})
                    buffer = []
                current_heading = elem.get_text(strip=True) or current_heading
            else:
                text = elem.get_text(strip=True)
                if text:
                    buffer.append(text)
        if buffer:
            sections.append({"section": current_heading, "text": " ".join(buffer), "paragraph_index": len(sections)})
        return sections
    except Exception as e:
        logger.error(f"URL extraction error for {url}: {e}")
        return []
