from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import Evidence, EvidenceRelationship, Repository, WorkItem
from ..services.fts import search_fts

router = APIRouter()


@router.get("/timeline")
def timeline(
    status: str | None = None,
    area: str | None = None,
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
    if area:
        query = query.filter(WorkItem.area == area)
    if project_id is not None:
        query = query.filter(WorkItem.project_id == project_id)
    if work_status:
        query = query.filter(WorkItem.work_status == work_status)
    if work_type:
        query = query.filter(WorkItem.work_type == work_type)
    if priority:
        query = query.filter(WorkItem.priority == priority)
    items = query.order_by(WorkItem.work_date.desc()).limit(500).all()
    grouped = defaultdict(list)
    for item in items:
        month = item.work_date[:7] if item.work_date else "Undated"
        grouped[month].append(
            {
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
                "outcome": item.outcome,
                "next_step": item.next_step,
                "confidence": item.evidence_confidence,
                "project_id": item.project_id,
                "project_name": item.project.name if item.project else None,
                "evidence_count": len(item.evidence_items),
            }
        )
    return [{"month": month, "items": entries} for month, entries in grouped.items()]


@router.get("/evidence")
def evidence(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    rows = db.query(Evidence).filter(Evidence.workspace_id == workspace.id).order_by(Evidence.created_at.desc()).limit(300).all()
    return [
        {
            "id": row.id,
            "source_type": row.source_type,
            "title": row.title,
            "summary": row.summary,
            "confidence": row.confidence,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        }
        for row in rows
    ]


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


@router.get("/search")
def search(q: str, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    return search_fts(db, workspace.id, q)
