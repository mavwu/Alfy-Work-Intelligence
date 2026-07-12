import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import AppSetting, Conversation, ConversationMessage, WorkItem
from .ai import AIUnavailable, OllamaProvider
from .fts import search_fts


def answer_work_question(db: Session, workspace_id: int, question: str, conversation_id: int | None = None) -> dict:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
    else:
        conversation = Conversation(workspace_id=workspace_id, title=question[:80] or "Work chat")
        db.add(conversation)
        db.flush()
    db.add(ConversationMessage(conversation_id=conversation.id, role="user", content=question))
    retrieved = search_fts(db, workspace_id, question, limit=10)
    retrieved = merge_retrieved(retrieved, intent_evidence_rows(db, workspace_id, question))
    answer = ai_answer(db, question, retrieved) or deterministic_answer(db, workspace_id, question, retrieved)
    summary = summarize_evidence(retrieved)
    db.add(ConversationMessage(conversation_id=conversation.id, role="assistant", content=answer, evidence_summary=summary))
    db.commit()
    return {"conversation_id": conversation.id, "answer": answer, "evidence": retrieved, "evidence_summary": summary}


def ai_answer(db: Session, question: str, retrieved: list[dict]) -> str | None:
    setting = db.get(AppSetting, "selected_model")
    model = setting.value if setting else ""
    if not model:
        return None
    provider = OllamaProvider()
    if not provider.health_check().get("available"):
        return None
    context = "\n".join(f"- [{row['content_type']}] {row['title']}: {row['body'][:600]}" for row in retrieved)
    prompt = f"""
Answer this question about Alfy's Ride Yanga work.
Use only the retrieved local evidence. If evidence is weak, say so.

Question: {question}

Evidence:
{context or 'No matching evidence was retrieved.'}
"""
    try:
        return provider.generate_text(model, prompt, system="You are a grounded local work-memory assistant. Do not invent work history.")
    except AIUnavailable:
        return None


def deterministic_answer(db: Session, workspace_id: int, question: str, retrieved: list[dict]) -> str:
    lower = question.lower()
    if "this week" in lower or "week" in lower:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        items = (
            db.query(WorkItem)
            .filter(WorkItem.workspace_id == workspace_id, WorkItem.status == "CONFIRMED")
            .filter(WorkItem.work_date >= week_start.isoformat(), WorkItem.work_date <= today.isoformat())
            .order_by(WorkItem.work_date.desc())
            .limit(20)
            .all()
        )
        if items:
            bullets = "\n".join(f"- {item.work_date}: {item.title} - {item.summary}" for item in items)
            return f"Based on confirmed work items currently stored, your recent work includes:\n\n{bullets}"
        return "I do not have confirmed work items for this week yet. Review and confirm inferred work, or add a work log for this week."
    since = since_month_date(lower)
    if since:
        items = (
            db.query(WorkItem)
            .filter(WorkItem.workspace_id == workspace_id, WorkItem.status == "CONFIRMED")
            .filter(WorkItem.work_date >= since.isoformat())
            .order_by(WorkItem.work_date)
            .limit(80)
            .all()
        )
        if items:
            by_area: dict[str, int] = {}
            for item in items:
                by_area[item.area or "General Engineering"] = by_area.get(item.area or "General Engineering", 0) + 1
            area_line = ", ".join(f"{area} ({count})" for area, count in sorted(by_area.items()))
            bullets = "\n".join(f"- {item.work_date}: {item.title}" for item in items[:12])
            return f"Based on confirmed evidence since {since.isoformat()}, I found {len(items)} work item(s). Main areas: {area_line}.\n\n{bullets}"
        return f"I do not have confirmed evidence since {since.isoformat()} yet."
    if not retrieved:
        return "I do not have enough local evidence to answer that confidently yet. Add work logs, import reports, or scan repositories first."
    bullets = "\n".join(f"- {row['title']} ({row['source']})" for row in retrieved[:6])
    return f"I found related local evidence, but AI rewriting is unavailable until Ollama is connected and a model is selected.\n\n{bullets}"


def intent_evidence_rows(db: Session, workspace_id: int, question: str) -> list[dict]:
    lower = question.lower()
    today = date.today()
    date_from = None
    date_to = today
    if "this week" in lower or "week" in lower:
        date_from = today - timedelta(days=today.weekday())
    else:
        date_from = since_month_date(lower)
    if not date_from:
        return []
    items = (
        db.query(WorkItem)
        .filter(WorkItem.workspace_id == workspace_id, WorkItem.status == "CONFIRMED")
        .filter(WorkItem.work_date >= date_from.isoformat(), WorkItem.work_date <= date_to.isoformat())
        .order_by(WorkItem.work_date.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "content_type": "work_item",
            "content_id": str(item.id),
            "title": item.title,
            "body": item.summary,
            "source": item.evidence_confidence,
            "event_date": item.work_date,
            "rank": 0,
        }
        for item in items
    ]


def merge_retrieved(primary: list[dict], secondary: list[dict]) -> list[dict]:
    seen = {(row["content_type"], str(row["content_id"])) for row in primary}
    merged = list(primary)
    for row in secondary:
        key = (row["content_type"], str(row["content_id"]))
        if key not in seen:
            merged.append(row)
            seen.add(key)
    return merged


def since_month_date(lower_question: str) -> date | None:
    if "since" not in lower_question:
        return None
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    for name, number in months.items():
        if re.search(rf"\bsince\s+{name}\b", lower_question):
            return date(date.today().year, number, 1)
    return None


def summarize_evidence(rows: list[dict]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["content_type"]] = counts.get(row["content_type"], 0) + 1
    if not counts:
        return "Based on: no retrieved evidence."
    return "Based on: " + ", ".join(f"{count} {kind.replace('_', ' ')}" for kind, count in counts.items()) + "."
