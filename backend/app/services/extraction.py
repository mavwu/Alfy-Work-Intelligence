import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import AppSetting
from .ai import AIUnavailable, OllamaProvider


class ExtractedWorkItem(BaseModel):
    title: str
    area: str | None = None
    work_type: str | None = "Work Log"
    summary: str
    work_date: str = Field(default_factory=lambda: date.today().isoformat())
    status: str | None = "REVIEW"
    challenges: str | None = None
    findings: str | None = None
    fixes: str | None = None
    pending_work: str | None = None
    confidence: float = 0.55


class WorkExtraction(BaseModel):
    items: list[ExtractedWorkItem] = Field(default_factory=list)


SYSTEM_WORK_LOG = """You extract conservative engineering work items from messy local notes.
Preserve uncertainty. Do not invent accomplishments. Split long summaries into multiple work items only when the evidence clearly describes distinct tasks."""


def selected_model(db: Session) -> str:
    setting = db.get(AppSetting, "selected_model")
    return setting.value if setting else ""


def extract_work_items(db: Session, raw_text: str) -> list[dict[str, Any]]:
    model = selected_model(db)
    provider = OllamaProvider()
    if model and provider.health_check().get("available"):
        prompt = f"""
Extract work items from this Ride Yanga work evidence.

Rules:
- Original text may contain one or many tasks.
- Use REVIEW status and INFERRED confidence unless the user explicitly confirmed completion.
- Keep titles factual and modest.
- Use ISO dates when dates are visible; otherwise use today's date.

Evidence:
{raw_text[:12000]}
"""
        try:
            result = provider.generate_structured(model, prompt, WorkExtraction, system=SYSTEM_WORK_LOG)
            return [item.model_dump() for item in result.items if item.title and item.summary]
        except (AIUnavailable, Exception):
            pass
    return deterministic_extract(raw_text)


def deterministic_extract(raw_text: str) -> list[dict[str, Any]]:
    text = raw_text.strip()
    if not text:
        return []
    chunks = split_possible_tasks(text)
    items = []
    for chunk in chunks[:8]:
        lower = chunk.lower()
        title = infer_title(chunk)
        area = infer_area(lower)
        work_type = infer_work_type(lower)
        items.append(
            {
                "title": title,
                "area": area,
                "work_type": work_type,
                "summary": summarize_chunk(chunk),
                "work_date": date.today().isoformat(),
                "status": "REVIEW",
                "challenges": extract_after(lower, chunk, ["issue", "problem", "challenge", "blocked"]),
                "findings": extract_after(lower, chunk, ["found", "noticed", "confirmed", "identified"]),
                "fixes": extract_after(lower, chunk, ["fixed", "resolved", "implemented", "updated"]),
                "pending_work": extract_after(lower, chunk, ["pending", "next", "todo", "still"]),
                "confidence": 0.45,
            }
        )
    return items


def split_possible_tasks(text: str) -> list[str]:
    bullet_parts = [p.strip(" -\t") for p in re.split(r"\n\s*(?:[-*]|\d+[.)])\s+", text) if p.strip()]
    if len(bullet_parts) > 1:
        return bullet_parts
    sentence_parts = re.split(r"(?<=[.!?])\s+(?=(?:also|then|next|after|fixed|implemented|investigated|checked)\b)", text, flags=re.I)
    return [p.strip() for p in sentence_parts if p.strip()] or [text]


def infer_title(chunk: str) -> str:
    words = re.findall(r"[A-Za-z0-9/+-]+", chunk)
    important = [w for w in words if len(w) > 3][:7]
    if not important:
        return "Work Log Entry"
    title = " ".join(important).title()
    return title[:90]


def infer_area(lower: str) -> str:
    areas = {
        "notification": "Notifications",
        "booking": "Booking Workflow",
        "boat": "Boat Cruise",
        "payment": "Payments",
        "dashboard": "Dashboard / API",
        "api": "Dashboard / API",
        "driver": "Driver App",
        "user app": "User App",
        "wordpress": "Website",
        "permalink": "Website",
    }
    for needle, area in areas.items():
        if needle in lower:
            return area
    return "General Engineering"


def infer_work_type(lower: str) -> str:
    if any(word in lower for word in ["investigat", "checked", "found", "research"]):
        return "Technical Investigation"
    if any(word in lower for word in ["bug", "fixed", "resolved", "issue"]):
        return "Bug Fix"
    if any(word in lower for word in ["implemented", "added", "built", "created"]):
        return "Feature Work"
    return "Work Log"


def summarize_chunk(chunk: str) -> str:
    compact = re.sub(r"\s+", " ", chunk).strip()
    return compact[:700]


def extract_after(lower: str, original: str, markers: list[str]) -> str | None:
    for marker in markers:
        index = lower.find(marker)
        if index >= 0:
            return original[index : index + 260].strip()
    return None
