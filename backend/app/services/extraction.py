from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import AppSetting
from .semantic_extraction import (
    SemanticAnalysisRun,
    SemanticEventSchema,
    SemanticExtractionSchema,
    deterministic_semantic_analysis,
    extract_semantic_analysis,
    normalized_semantic_text,
)


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


def selected_model(db: Session) -> str:
    setting = db.get(AppSetting, "selected_model")
    return setting.value if setting else ""


def extract_work_items_with_metadata(db: Session, raw_text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    semantic_result, analysis = extract_semantic_analysis(db, raw_text)
    items = semantic_result_to_work_items(semantic_result, raw_text, analysis)
    return items, analysis.model_dump()


def extract_work_items(db: Session, raw_text: str) -> list[dict[str, Any]]:
    items, _ = extract_work_items_with_metadata(db, raw_text)
    return items


def deterministic_extract(raw_text: str) -> list[dict[str, Any]]:
    semantic_result = deterministic_semantic_analysis(raw_text)
    analysis = SemanticAnalysisRun(
        analysis_mode="EVIDENCE_ONLY",
        provider="Deterministic",
        model="",
        fallback_reason="Deterministic fallback used.",
    )
    return semantic_result_to_work_items(semantic_result, raw_text, analysis)


def semantic_result_to_work_items(
    result: SemanticExtractionSchema,
    raw_text: str,
    analysis: SemanticAnalysisRun | dict[str, Any],
) -> list[dict[str, Any]]:
    mode = analysis.analysis_mode if isinstance(analysis, SemanticAnalysisRun) else analysis.get("analysis_mode", "EVIDENCE_ONLY")
    items: list[dict[str, Any]] = []
    for event in result.events[:8]:
        item = event_to_work_item(event, raw_text, mode)
        if item["title"] and item["summary"]:
            items.append(item)
    if items:
        return items
    fallback_event = fallback_event_from_text(raw_text)
    return [event_to_work_item(fallback_event, raw_text, mode)]


def event_to_work_item(event: SemanticEventSchema, raw_text: str, analysis_mode: str) -> dict[str, Any]:
    text_parts = [event.event_subject, *event.initial_context, *event.requirement_change]
    text_parts.extend(fact.statement for fact in event.actions_performed)
    text_parts.extend(fact.statement for fact in event.findings)
    text_parts.extend(fact.statement for fact in event.open_questions)
    text_parts.extend(fact.statement for fact in event.pending_actions)
    summary = summarize_parts(text_parts, raw_text)
    title = infer_title_from_event(event, summary)
    area = infer_area(summary.lower())
    work_type = infer_work_type(summary.lower(), event)
    findings = join_unique([fact.statement for fact in event.findings])
    fixes = join_unique(
        [
            fact.statement
            for fact in event.actions_performed
            if fact.status == "COMPLETED" or any(token in fact.statement.lower() for token in ["fixed", "implemented", "resolved", "updated", "changed", "restored", "working again", "started showing"])
        ]
    )
    pending_work = join_unique([fact.statement for fact in event.open_questions + event.pending_actions])
    challenges = join_unique([fact.statement for fact in event.pending_actions] or [fact.statement for fact in event.open_questions])
    confidence = 0.72 if analysis_mode == "OLLAMA" else 0.45
    return {
        "title": title,
        "area": area,
        "work_type": work_type,
        "summary": summary,
        "work_date": date.today().isoformat(),
        "status": "REVIEW",
        "challenges": challenges,
        "findings": findings,
        "fixes": fixes,
        "pending_work": pending_work,
        "confidence": confidence,
    }


def fallback_event_from_text(raw_text: str) -> SemanticEventSchema:
    semantic_result = deterministic_semantic_analysis(raw_text)
    return semantic_result.events[0] if semantic_result.events else SemanticEventSchema(event_subject="General work")


def infer_title_from_event(event: SemanticEventSchema, summary: str) -> str:
    subject = clean_title(event.event_subject)
    if not subject:
        return infer_title(summary)
    if len(subject) <= 90:
        return subject
    return subject[:90]


def summarize_parts(parts: list[str], raw_text: str) -> str:
    chosen = [clean_summary_part(part) for part in parts if clean_summary_part(part)]
    if not chosen:
        chosen = [clean_summary_part(raw_text)]
    summary = " ".join(chosen)
    return summary[:800]


def clean_summary_part(text: str) -> str:
    return " ".join((text or "").split()).strip(" -")


def clean_title(text: str) -> str:
    cleaned = clean_summary_part(text)
    cleaned = cleaned.replace("requester", "Requester")
    return cleaned[:90]


def join_unique(parts: list[str]) -> str | None:
    values = []
    seen = set()
    for part in parts:
        normalized = normalized_semantic_text(part)
        if part and normalized not in seen:
            values.append(clean_summary_part(part))
            seen.add(normalized)
    if not values:
        return None
    return "; ".join(values)[:800]


def infer_title(chunk: str) -> str:
    words = [word for word in chunk.split() if len(word) > 2]
    if not words:
        return "Work Log Entry"
    return " ".join(words[:8]).title()[:90]


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
        "image": "Media / Assets",
        "icon": "Media / Assets",
    }
    for needle, area in areas.items():
        if needle in lower:
            return area
    return "General Work"


def infer_work_type(lower: str, event: SemanticEventSchema | None = None) -> str:
    if event and (event.pending_actions or event.open_questions):
        return "Investigation"
    if any(word in lower for word in ["bug", "fixed", "resolved", "issue", "error"]):
        return "Issue Resolution"
    if any(word in lower for word in ["implemented", "added", "built", "created", "changed", "updated"]):
        return "Deliverable Work"
    if any(word in lower for word in ["investigat", "checked", "found", "confirmed", "inspected"]):
        return "Investigation"
    return "Work Log"
