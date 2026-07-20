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


class WorkItemUpdate(BaseModel):
    title: str | None = None
    area: str | None = None
    work_type: str | None = None
    summary: str | None = None
    work_date: str | None = None
    status: str | None = None
    challenges: str | None = None
    findings: str | None = None
    fixes: str | None = None
    pending_work: str | None = None
    related_repository_id: int | None = None
    project_id: int | None = None


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
            title=item_data["title"],
            area=item_data.get("area"),
            work_type=item_data.get("work_type"),
            summary=item_data["summary"],
            work_date=item_data.get("work_date") or raw.logged_at.date().isoformat(),
            status="REVIEW",
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
            source_type="USER_LOG",
            source_id=str(raw.id),
            title=f"Work log evidence: {item.title}",
            summary=raw.raw_text,
            confidence="INFERRED",
            occurred_at=raw.logged_at,
        )
        db.add(evidence)
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


@router.get("/work-items")
def list_work_items(status: str | None = None, project_id: int | None = None, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    query = db.query(WorkItem).filter(WorkItem.workspace_id == workspace.id)
    if status:
        query = query.filter(WorkItem.status == status)
    if project_id is not None:
        query = query.filter(WorkItem.project_id == project_id)
    items = query.order_by(WorkItem.work_date.desc(), WorkItem.created_at.desc()).limit(300).all()
    return [serialize_item(item) for item in items]


@router.put("/work-items/{item_id}")
def update_work_item(item_id: int, payload: WorkItemUpdate, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    item = db.get(WorkItem, item_id)
    if not item or item.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Work item not found")
    data = payload.model_dump(exclude_unset=True)
    if "project_id" in data:
        data["project_id"] = validate_project_assignment(db, workspace.id, data["project_id"])
    if "related_repository_id" in data and data["related_repository_id"] is not None:
        repo = db.get(Repository, data["related_repository_id"])
        if not repo or repo.workspace_id != workspace.id:
            raise HTTPException(status_code=400, detail="Repository does not belong to the active workspace.")
    for field, value in data.items():
        setattr(item, field, value)
    if item.status == "CONFIRMED":
        item.evidence_confidence = "CONFIRMED"
    upsert_fts(db, "work_item", item.id, item.workspace_id, item.title, item.summary, item.work_type or "Work item", item.work_date)
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
        "evidence_confidence": item.evidence_confidence,
        "challenges": item.challenges,
        "findings": item.findings,
        "fixes": item.fixes,
        "pending_work": item.pending_work,
        "related_repository_id": item.related_repository_id,
        "project_id": item.project_id,
        "project_name": project.name if project else None,
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
