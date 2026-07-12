import hashlib
import re
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return data.decode("utf-8", errors="replace")
    if suffix == ".docx":
        doc = Document(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError("Unsupported file type. Use DOCX, PDF, Markdown, or TXT.")


def infer_document_metadata(text: str, filename: str) -> dict[str, str]:
    lower = text.lower()
    if "weekly" in lower:
        doc_type = "Weekly update"
    elif "monthly" in lower:
        doc_type = "Monthly summary"
    elif "investigation" in lower or "research" in lower:
        doc_type = "Technical investigation"
    else:
        doc_type = "Imported work document"
    period_match = re.search(r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}|\d{4}-\d{2}-\d{2}\s*(?:to|-)\s*\d{4}-\d{2}-\d{2})", text, re.I)
    return {"document_type": doc_type, "reporting_period": period_match.group(1) if period_match else ""}


def chunk_text(text: str, size: int = 2500) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    return [clean[i : i + size] for i in range(0, len(clean), size)] or [""]
