from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import GeneratedReport, ReportRevision
from ..services.reports import REPORT_TYPES, create_report_revision, evidence_for_period, export_docx, export_pptx, generate_report, restore_report_revision

router = APIRouter()


class ReportRequest(BaseModel):
    report_type: str
    date_from: str
    date_to: str
    include_inferred_ids: list[int] = []


class ApproveRequest(BaseModel):
    draft_markdown: str | None = None
    use_as_style_reference: bool = False


class RefineRequest(BaseModel):
    instruction: str


@router.get("/reports/types")
def report_types():
    return REPORT_TYPES


@router.post("/reports/preview")
def preview(payload: ReportRequest, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    confirmed, inferred = evidence_for_period(db, workspace.id, payload.date_from, payload.date_to)
    return {
        "confirmed": [serialize_item(item) for item in confirmed],
        "inferred_needs_review": [serialize_item(item) for item in inferred],
    }


@router.post("/reports")
def create_report(payload: ReportRequest, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    if payload.report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown report type.")
    report = generate_report(db, workspace.id, payload.report_type, payload.date_from, payload.date_to, payload.include_inferred_ids)
    return serialize_report(report)


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    reports = db.query(GeneratedReport).filter(GeneratedReport.workspace_id == workspace.id).order_by(GeneratedReport.created_at.desc()).all()
    return [serialize_report(report) for report in reports]


@router.put("/reports/{report_id}/approve")
def approve_report(report_id: int, payload: ApproveRequest, db: Session = Depends(get_db)):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if payload.draft_markdown is not None:
        report.draft_markdown = payload.draft_markdown
    report.status = "APPROVED"
    report.approved_at = datetime.utcnow()
    report.use_as_style_reference = payload.use_as_style_reference
    db.commit()
    return serialize_report(report)


@router.get("/reports/{report_id}/revisions")
def list_revisions(report_id: int, db: Session = Depends(get_db)):
    revisions = db.query(ReportRevision).filter(ReportRevision.report_id == report_id).order_by(ReportRevision.revision_number).all()
    return [serialize_revision(revision) for revision in revisions]


@router.post("/reports/{report_id}/refine")
def refine_report(report_id: int, payload: RefineRequest, db: Session = Depends(get_db)):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not payload.instruction.strip():
        raise HTTPException(status_code=400, detail="Refinement instruction is required.")
    revision = create_report_revision(db, report, payload.instruction)
    db.refresh(report)
    return {"report": serialize_report(report), "revision": serialize_revision(revision)}


@router.post("/reports/{report_id}/revisions/{revision_id}/restore")
def restore_revision(report_id: int, revision_id: int, db: Session = Depends(get_db)):
    report = db.get(GeneratedReport, report_id)
    revision = db.get(ReportRevision, revision_id)
    if not report or not revision or revision.report_id != report_id:
        raise HTTPException(status_code=404, detail="Report revision not found")
    restore_report_revision(db, report, revision)
    return serialize_report(report)


@router.get("/reports/{report_id}/export/docx")
def download_docx(report_id: int, db: Session = Depends(get_db)):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    path = export_docx(report)
    return FileResponse(path, filename=path.name)


@router.get("/reports/{report_id}/export/pptx")
def download_pptx(report_id: int, db: Session = Depends(get_db)):
    report = db.get(GeneratedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    path = export_pptx(report)
    return FileResponse(path, filename=path.name)


def serialize_item(item):
    return {"id": item.id, "title": item.title, "summary": item.summary, "work_date": item.work_date, "status": item.status, "area": item.area, "work_type": item.work_type}


def serialize_report(report: GeneratedReport):
    return {
        "id": report.id,
        "report_type": report.report_type,
        "title": report.title,
        "date_from": report.date_from,
        "date_to": report.date_to,
        "draft_markdown": report.draft_markdown,
        "status": report.status,
        "use_as_style_reference": report.use_as_style_reference,
        "created_at": report.created_at.isoformat(),
        "approved_at": report.approved_at.isoformat() if report.approved_at else None,
    }


def serialize_revision(revision: ReportRevision):
    return {
        "id": revision.id,
        "report_id": revision.report_id,
        "revision_number": revision.revision_number,
        "reason": revision.reason,
        "draft_markdown": revision.draft_markdown,
        "validation_notes": revision.validation_notes,
        "created_at": revision.created_at.isoformat(),
    }
