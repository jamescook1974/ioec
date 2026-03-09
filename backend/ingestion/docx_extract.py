from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def extract_docx(file_path: str) -> List[Dict[str, Any]]:
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = []
        current_heading = "Document"
        for i, para in enumerate(doc.paragraphs):
            if para.style.name.startswith("Heading"):
                current_heading = para.text.strip() or current_heading
            text = para.text.strip()
            if text:
                paragraphs.append({"section": current_heading, "text": text, "paragraph_index": i})
        return paragraphs
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return []

def extract_docx_bytes(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        f.write(file_bytes)
        tmp = f.name
    try:
        return extract_docx(tmp)
    finally:
        os.unlink(tmp)
