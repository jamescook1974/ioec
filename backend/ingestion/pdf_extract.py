from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def extract_pdf(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from PDF, returning list of {page, text} dicts."""
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append({"page": i, "text": text})
        return pages
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return []

def extract_pdf_bytes(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(file_bytes)
        tmp = f.name
    try:
        return extract_pdf(tmp)
    finally:
        os.unlink(tmp)
