import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import Evidence, Project, RawWorkLog, Repository, WorkItem
from ..services.extraction import extract_work_items_with_metadata
from ..services.fts import upsert_fts

router = APIRouter()


class WorkLogIn(BaseModel):
    raw_text: str
    source_label: str = "Manual work log"
    project_id: int | None = None
    title: str | None = None
    summary: str | None = None
    work_status: str | None = None
    category: str | None = None
    work_type: str | None = None
    priority: str | None = None
    work_date: str | None = None
    outcome: str | None = None
    next_step: str | None = None
    tags: list[str] | str | None = None


class WorkItemUpdate(BaseModel):
    title: str | None = None
    area: str | None = None
    work_type: str | None = None
    summary: str | None = None
    work_date: str | None = None
    status: str | None = None
    work_status: str | None = None
    category: str | None = None
    priority: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    outcome: str | None = None
    next_step: str | None = None
    tags: list[str] | str | None = None
    challenges: str | None = None
    findings: str | None = None
    fixes: str | None = None
    pending_work: str | None = None
    related_repository_id: int | None = None
    project_id: int | None = None


class ManualWorkItemIn(WorkItemUpdate):
    title: str
    summary: str
    work_date: str | None = None


WORK_REVIEW_STATUSES = {"REVIEW", "CONFIRMED", "IGNORED"}
WORK_PROGRESS_STATUSES = {"PLANNED", "IN_PROGRESS", "BLOCKED", "COMPLETED", "CANCELLED"}
PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
GENERIC_WORK_TYPES = {
    "General Work",
    "Feature / Deliverable",
    "Issue Resolution",
    "Investigation / Research",
    "Meeting",
    "Communication",
    "Administration",
    "Design",
    "Documentation",
    "Testing",
    "Deployment",
    "Support",
    "Training",
    "Field Work",
    "Other",
    "Feature Work",
    "Bug Fix",
    "Technical Investigation",
    "Work Log",
}


@router.post("/work-logs")
def create_work_log(payload: WorkLogIn, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    if not payload.raw_text.strip():
        raise HTTPException(status_code=400, detail="Work log text is required.")
    project_id = validate_project_assignment(db, workspace.id, payload.project_id)
    raw = RawWorkLog(workspace_id=workspace.id, raw_text=payload.raw_text, source_label=payload.source_label)
    db.add(raw)
    db.flush()
    upsert_fts(db, "raw_work_log", raw.id, workspace.id, payload.source_label, raw.raw_text, "USER_LOG", raw.logged_at.date().isoformat())
    extracted, analysis = extract_work_items_with_metadata(db, payload.raw_text)
    created = []
    for item_data in extracted:
        item = WorkItem(
            workspace_id=workspace.id,
            title=payload.title or item_data["title"],
            area=item_data.get("area"),
            work_type=payload.work_type or item_data.get("work_type"),
            summary=payload.summary or item_data["summary"],
            work_date=payload.work_date or item_data.get("work_date") or raw.logged_at.date().isoformat(),
            status="REVIEW",
            work_status=validate_work_status(payload.work_status or item_data.get("work_status") or "IN_PROGRESS"),
            category=clean_optional(payload.category or item_data.get("category")),
            priority=validate_priority(payload.priority or item_data.get("priority") or "NORMAL"),
            outcome=clean_optional(payload.outcome or item_data.get("outcome")),
            next_step=clean_optional(payload.next_step or item_data.get("next_step")),
            tags=serialize_tags(payload.tags if payload.tags is not None else item_data.get("tags")),
            evidence_confidence="INFERRED",
            challenges=item_data.get("challenges"),
            findings=item_data.get("findings"),
            fixes=item_data.get("fixes"),
            pending_work=item_data.get("pending_work"),
            project_id=project_id,
            extraction_confidence=item_data.get("confidence", 0.5),
        )
        db.add(item)
        db.flush()
        evidence = Evidence(
            workspace_id=workspace.id,
            work_item_id=item.id,
            project_id=project_id,
            evidence_type="MANUAL_NOTE",
            source_type="USER_LOG",
            source_id=str(raw.id),
            title=f"Work log evidence: {item.title}",
            summary=raw.raw_text,
            confidence="INFERRED",
            occurred_at=raw.logged_at,
        )
        db.add(evidence)
        db.flush()
        upsert_fts(db, "evidence", evidence.id, workspace.id, evidence.title, evidence.summary, evidence.source_type, raw.logged_at.date().isoformat())
        upsert_fts(db, "work_item", item.id, workspace.id, item.title, item.summary, item.work_type or "Work item", item.work_date)
        created.append(serialize_item(item))
    db.commit()
    return {
        "raw_log_id": raw.id,
        "analysis_mode": analysis["analysis_mode"],
        "analysis_provider": analysis.get("provider"),
        "analysis_model": analysis.get("model"),
        "analysis_fallback_reason": analysis.get("fallback_reason"),
        "extracted_items": created,
    }


@router.post("/work-items")
def create_work_item(payload: ManualWorkItemIn, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    if not payload.title.strip() or not payload.summary.strip():
        raise HTTPException(status_code=400, detail="Title and summary are required.")
    project_id = validate_project_assignment(db, workspace.id, payload.project_id)
    item = WorkItem(
        workspace_id=workspace.id,
        title=payload.title.strip()[:240],
        area=clean_optional(payload.area),
        work_type=clean_optional(payload.work_type) or "General Work",
        summary=payload.summary.strip(),
        work_date=payload.work_date or datetime.utcnow().date().isoformat(),
        status=validate_review_status(payload.status or "REVIEW"),
        work_status=validate_work_status(payload.work_status or "IN_PROGRESS"),
        category=clean_optional(payload.category),
        priority=validate_priority(payload.priority or "NORMAL"),
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        outcome=clean_optional(payload.outcome),
        next_step=clean_optional(payload.next_step),
        tags=serialize_tags(payload.tags),
        challenges=clean_optional(payload.challenges),
        findings=clean_optional(payload.findings),
        fixes=clean_optional(payload.fixes),
        pending_work=clean_optional(payload.pending_work),
        related_repository_id=payload.related_repository_id,
        project_id=project_id,
        evidence_confidence="MANUAL",
        extraction_confidence=1.0,
    )
    db.add(item)
    db.flush()
    upsert_fts(db, "work_item", item.id, item.workspace_id, searchable_title(item), searchable_body(item), item.work_type or "Work item", item.work_date)
    db.commit()
    db.refresh(item)
    return serialize_item(item)


@router.get("/work-items")
def list_work_items(
    status: str | None = None,
    project_id: int | None = None,
    work_status: str | None = None,
    work_type: str | None = None,
    priority: str | None = None,
    db: Session = Depends(get_db),
):
    workspace = ensure_defaults(db)
    query = db.query(WorkItem).filter(WorkItem.workspace_id == workspace.id)
    if status:
        query = query.filter(WorkItem.status == status)
    if project_id is not None:
        query = query.filter(WorkItem.project_id == project_id)
    if work_status:
        query = query.filter(WorkItem.work_status == validate_work_status(work_status))
    if work_type:
        query = query.filter(WorkItem.work_type == work_type)
    if priority:
        query = query.filter(WorkItem.priority == validate_priority(priority))
    items = query.order_by(WorkItem.work_date.desc(), WorkItem.created_at.desc()).limit(300).all()
    return [serialize_item(item) for item in items]


@router.get("/work-items/{item_id}")
def get_work_item(item_id: int, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    item = db.get(WorkItem, item_id)
    if not item or item.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Work item not found")
    return serialize_item(item)


@router.put("/work-items/{item_id}")
def update_work_item(item_id: int, payload: WorkItemUpdate, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    item = db.get(WorkItem, item_id)
    if not item or item.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Work item not found")
    data = payload.model_dump(exclude_unset=True)
    if "project_id" in data:
        data["project_id"] = validate_project_assignment(db, workspace.id, data["project_id"])
    if "status" in data and data["status"] is not None:
        data["status"] = validate_review_status(data["status"])
    if "work_status" in data:
        data["work_status"] = validate_work_status(data["work_status"])
    if "priority" in data:
        data["priority"] = validate_priority(data["priority"])
    if "tags" in data:
        data["tags"] = serialize_tags(data["tags"])
    if "related_repository_id" in data and data["related_repository_id"] is not None:
        repo = db.get(Repository, data["related_repository_id"])
        if not repo or repo.workspace_id != workspace.id:
            raise HTTPException(status_code=400, detail="Repository does not belong to the active workspace.")
    for field, value in data.items():
        setattr(item, field, value)
    if item.status == "CONFIRMED":
        item.evidence_confidence = "CONFIRMED"
    upsert_fts(db, "work_item", item.id, item.workspace_id, searchable_title(item), searchable_body(item), item.work_type or "Work item", item.work_date)
    db.commit()
    return serialize_item(item)


@router.post("/work-items/{item_id}/confirm")
def confirm_work_item(item_id: int, db: Session = Depends(get_db)):
    return set_status(db, item_id, "CONFIRMED")


@router.post("/work-items/{item_id}/ignore")
def ignore_work_item(item_id: int, db: Session = Depends(get_db)):
    return set_status(db, item_id, "IGNORED")


def set_status(db: Session, item_id: int, status: str):
    workspace = ensure_defaults(db)
    item = db.get(WorkItem, item_id)
    if not item or item.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Work item not found")
    item.status = status
    if status == "CONFIRMED":
        item.evidence_confidence = "CONFIRMED"
    db.commit()
    return serialize_item(item)


def serialize_item(item: WorkItem):
    project = getattr(item, "project", None)
    return {
        "id": item.id,
        "title": item.title,
        "area": item.area,
        "work_type": item.work_type,
        "summary": item.summary,
        "work_date": item.work_date,
        "status": item.status,
        "work_status": item.work_status,
        "category": item.category,
        "priority": item.priority,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "ended_at": item.ended_at.isoformat() if item.ended_at else None,
        "outcome": item.outcome,
        "next_step": item.next_step,
        "tags": parse_tags(item.tags),
        "evidence_confidence": item.evidence_confidence,
        "challenges": item.challenges,
        "findings": item.findings,
        "fixes": item.fixes,
        "pending_work": item.pending_work,
        "related_repository_id": item.related_repository_id,
        "project_id": item.project_id,
        "project_name": project.name if project else None,
        "evidence_count": len(getattr(item, "evidence_items", []) or []),
        "extraction_confidence": item.extraction_confidence,
    }


def validate_project_assignment(db: Session, workspace_id: int, project_id: int | None) -> int | None:
    if project_id is None:
        return None
    project = db.get(Project, project_id)
    if not project or project.workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="Project does not belong to the active workspace.")
    if project.status == "ARCHIVED":
        raise HTTPException(status_code=400, detail="Archived projects cannot receive new work items.")
    return project.id


def validate_review_status(value: str) -> str:
    normalized = value.upper()
    if normalized not in WORK_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid review status.")
    return normalized


def validate_work_status(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    normalized = value.upper()
    if normalized not in WORK_PROGRESS_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid work-progress status.")
    return normalized


def validate_priority(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    normalized = value.upper()
    if normalized not in PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority.")
    return normalized


def serialize_tags(value: list[str] | str | None) -> str | None:
    if value is None:
        return None
    raw_values = value if isinstance(value, list) else value.split(",")
    tags = []
    seen = set()
    for raw in raw_values:
        tag = " ".join(str(raw).strip().lower().replace("#", "").split())
        if not tag:
            continue
        tag = tag[:40]
        if tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return json.dumps(tags[:20])


def parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def searchable_title(item: WorkItem) -> str:
    return item.title or "Work item"


def searchable_body(item: WorkItem) -> str:
    return "\n".join(
        part
        for part in [
            item.summary,
            item.category,
            item.work_type,
            item.work_status,
            item.priority,
            item.outcome,
            item.next_step,
            " ".join(parse_tags(item.tags)),
            item.findings,
            item.fixes,
            item.challenges,
            item.pending_work,
        ]
        if part
    )
