import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import Evidence, EvidenceRelationship, Project, WorkItem
from ..services.fts import upsert_fts

router = APIRouter()


EVIDENCE_TYPES = {
    "MANUAL_NOTE",
    "LINK",
    "FILE_REFERENCE",
    "DOCUMENT",
    "IMAGE_REFERENCE",
    "EMAIL_REFERENCE",
    "MEETING_NOTE",
    "TEST_RESULT",
    "DEPLOYMENT",
    "CLIENT_FEEDBACK",
    "GIT_COMMIT",
    "GIT_WORKING_TREE",
    "IMPORTED_DOCUMENT",
    "OTHER",
}


class EvidenceIn(BaseModel):
    evidence_type: str = "MANUAL_NOTE"
    title: str
    summary: str = ""
    uri: str | None = None
    local_path: str | None = None
    external_ref: str | None = None
    source_system: str | None = None
    occurred_at: datetime | None = None
    confidence: str = "MANUAL"
    metadata: dict | None = None
    work_item_id: int | None = None
    project_id: int | None = None


class EvidenceUpdate(BaseModel):
    evidence_type: str | None = None
    title: str | None = None
    summary: str | None = None
    uri: str | None = None
    local_path: str | None = None
    external_ref: str | None = None
    source_system: str | None = None
    occurred_at: datetime | None = None
    confidence: str | None = None
    metadata: dict | None = None
    work_item_id: int | None = None
    project_id: int | None = None


class AttachRequest(BaseModel):
    work_item_id: int


@router.get("/evidence/types")
def evidence_types():
    return sorted(EVIDENCE_TYPES)


@router.get("/evidence")
def list_evidence(
    work_item_id: int | None = None,
    project_id: int | None = None,
    evidence_type: str | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    workspace = ensure_defaults(db)
    if work_item_id is not None:
        validate_work_item(db, workspace.id, work_item_id)
    if project_id is not None:
        validate_project(db, workspace.id, project_id)
    query = db.query(Evidence).filter(Evidence.workspace_id == workspace.id)
    if not include_archived:
        query = query.filter(Evidence.archived_at.is_(None))
    if work_item_id is not None:
        query = query.filter(Evidence.work_item_id == work_item_id)
    if project_id is not None:
        query = query.filter(Evidence.project_id == project_id)
    if evidence_type:
        query = query.filter(Evidence.evidence_type == normalize_evidence_type(evidence_type))
    rows = query.order_by(Evidence.occurred_at.desc().nullslast(), Evidence.created_at.desc()).limit(300).all()
    return [serialize_evidence(row) for row in rows]


@router.post("/evidence")
def create_evidence(payload: EvidenceIn, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Evidence title is required.")
    work_item = validate_work_item(db, workspace.id, payload.work_item_id) if payload.work_item_id is not None else None
    project = validate_project(db, workspace.id, payload.project_id) if payload.project_id is not None else None
    if work_item and project and work_item.project_id and work_item.project_id != project.id:
        raise HTTPException(status_code=400, detail="Evidence project does not match the work item's project.")
    if work_item and not project and work_item.project_id:
        project = db.get(Project, work_item.project_id)
    evidence = Evidence(
        workspace_id=workspace.id,
        project_id=project.id if project else None,
        work_item_id=work_item.id if work_item else None,
        evidence_type=normalize_evidence_type(payload.evidence_type),
        source_type=normalize_evidence_type(payload.evidence_type),
        source_id=None,
        title=payload.title.strip()[:240],
        summary=payload.summary.strip(),
        uri=clean_optional(payload.uri),
        local_path=clean_optional(payload.local_path),
        external_ref=clean_optional(payload.external_ref),
        source_system=clean_optional(payload.source_system) or "Manual",
        confidence=payload.confidence or "MANUAL",
        occurred_at=payload.occurred_at,
        metadata_json=json.dumps(payload.metadata or {}),
        is_manual=True,
    )
    db.add(evidence)
    db.flush()
    index_evidence(db, evidence)
    db.commit()
    db.refresh(evidence)
    return serialize_evidence(evidence)


@router.put("/evidence/{evidence_id}")
def update_evidence(evidence_id: int, payload: EvidenceUpdate, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    evidence = get_workspace_evidence(db, workspace.id, evidence_id)
    if not evidence.is_manual:
        raise HTTPException(status_code=400, detail="Automatically generated evidence cannot be edited here.")
    data = payload.model_dump(exclude_unset=True)
    if "work_item_id" in data:
        data["work_item_id"] = validate_work_item(db, workspace.id, data["work_item_id"]).id if data["work_item_id"] is not None else None
    if "project_id" in data:
        data["project_id"] = validate_project(db, workspace.id, data["project_id"]).id if data["project_id"] is not None else None
    if data.get("work_item_id") and data.get("project_id"):
        item = db.get(WorkItem, data["work_item_id"])
        if item and item.project_id and item.project_id != data["project_id"]:
            raise HTTPException(status_code=400, detail="Evidence project does not match the work item's project.")
    if "evidence_type" in data and data["evidence_type"] is not None:
        data["evidence_type"] = normalize_evidence_type(data["evidence_type"])
        data["source_type"] = data["evidence_type"]
    if "metadata" in data:
        data["metadata_json"] = json.dumps(data.pop("metadata") or {})
    for field, value in data.items():
        if hasattr(evidence, field):
            setattr(evidence, field, value)
    index_evidence(db, evidence)
    db.commit()
    return serialize_evidence(evidence)


@router.delete("/evidence/{evidence_id}")
def archive_evidence(evidence_id: int, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    evidence = get_workspace_evidence(db, workspace.id, evidence_id)
    if not evidence.is_manual:
        raise HTTPException(status_code=400, detail="Automatically generated evidence cannot be archived here.")
    evidence.archived_at = datetime.utcnow()
    evidence.work_item_id = None
    db.commit()
    return serialize_evidence(evidence)


@router.post("/evidence/{evidence_id}/attach")
def attach_evidence(evidence_id: int, payload: AttachRequest, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    evidence = get_workspace_evidence(db, workspace.id, evidence_id)
    item = validate_work_item(db, workspace.id, payload.work_item_id)
    if evidence.project_id and item.project_id and evidence.project_id != item.project_id:
        raise HTTPException(status_code=400, detail="Evidence project does not match the work item's project.")
    evidence.work_item_id = item.id
    if item.project_id and not evidence.project_id:
        evidence.project_id = item.project_id
    db.commit()
    return serialize_evidence(evidence)


@router.post("/evidence/{evidence_id}/detach")
def detach_evidence(evidence_id: int, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    evidence = get_workspace_evidence(db, workspace.id, evidence_id)
    evidence.work_item_id = None
    db.commit()
    return serialize_evidence(evidence)


@router.get("/evidence/relationships")
def relationships(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    evidence_ids = [row_id for (row_id,) in db.query(Evidence.id).filter(Evidence.workspace_id == workspace.id).all()]
    if not evidence_ids:
        return []
    rows = (
        db.query(EvidenceRelationship)
        .filter(EvidenceRelationship.from_evidence_id.in_(evidence_ids), EvidenceRelationship.to_evidence_id.in_(evidence_ids))
        .order_by(EvidenceRelationship.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": row.id,
            "from_evidence_id": row.from_evidence_id,
            "to_evidence_id": row.to_evidence_id,
            "relationship_type": row.relationship_type,
            "confidence_score": row.confidence_score,
            "explanation": row.explanation,
        }
        for row in rows
    ]


def get_workspace_evidence(db: Session, workspace_id: int, evidence_id: int) -> Evidence:
    evidence = db.get(Evidence, evidence_id)
    if not evidence or evidence.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence


def validate_work_item(db: Session, workspace_id: int, work_item_id: int | None) -> WorkItem:
    item = db.get(WorkItem, work_item_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="Work item does not belong to the active workspace.")
    return item


def validate_project(db: Session, workspace_id: int, project_id: int | None) -> Project:
    project = db.get(Project, project_id)
    if not project or project.workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="Project does not belong to the active workspace.")
    return project


def normalize_evidence_type(value: str) -> str:
    normalized = (value or "OTHER").upper().replace(" ", "_").replace("-", "_")
    if normalized not in EVIDENCE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid evidence type.")
    return normalized


def serialize_evidence(row: Evidence):
    metadata = {}
    if row.metadata_json:
        try:
            metadata = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            metadata = {"raw": row.metadata_json}
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "project_name": row.project.name if getattr(row, "project", None) else None,
        "work_item_id": row.work_item_id,
        "work_item_title": row.work_item.title if getattr(row, "work_item", None) else None,
        "evidence_type": row.evidence_type or row.source_type,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "title": row.title,
        "summary": row.summary,
        "uri": row.uri,
        "local_path": row.local_path,
        "external_ref": row.external_ref,
        "source_system": row.source_system,
        "confidence": row.confidence,
        "metadata": metadata,
        "is_manual": bool(row.is_manual),
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "created_at": row.created_at.isoformat(),
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
    }


def index_evidence(db: Session, evidence: Evidence):
    body = "\n".join(
        part
        for part in [evidence.summary, evidence.uri, evidence.local_path, evidence.external_ref, evidence.source_system, evidence.evidence_type]
        if part
    )
    event_date = evidence.occurred_at.date().isoformat() if evidence.occurred_at else ""
    upsert_fts(db, "evidence", evidence.id, evidence.workspace_id, evidence.title, body, evidence.evidence_type or evidence.source_type, event_date)


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
