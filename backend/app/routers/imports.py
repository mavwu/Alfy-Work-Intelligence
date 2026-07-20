from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import DocumentChunk, Evidence, ImportedDocument, WorkItem
from ..services.documents import chunk_text, content_hash, extract_text, infer_document_metadata
from ..services.extraction import extract_work_items_with_metadata
from ..services.fts import upsert_fts

router = APIRouter()


@router.post("/imports")
async def import_documents(files: list[UploadFile] = File(...), use_as_style_reference: bool = False, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    results = []
    for file in files:
        data = await file.read()
        digest = content_hash(data)
        existing = db.query(ImportedDocument).filter(ImportedDocument.workspace_id == workspace.id, ImportedDocument.content_hash == digest).first()
        if existing:
            results.append({"filename": file.filename, "duplicate": True, "document_id": existing.id})
            continue
        try:
            text = extract_text(file.filename or "", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metadata = infer_document_metadata(text, file.filename or "")
        doc = ImportedDocument(
            workspace_id=workspace.id,
            filename=file.filename or "imported-document",
            content_hash=digest,
            document_type=metadata["document_type"],
            reporting_period=metadata["reporting_period"],
            extracted_text=text,
            use_as_style_reference=use_as_style_reference,
        )
        db.add(doc)
        db.flush()
        for index, chunk in enumerate(chunk_text(text)):
            db.add(DocumentChunk(document_id=doc.id, chunk_index=index, text=chunk))
            upsert_fts(db, "document_chunk", f"{doc.id}-{index}", workspace.id, doc.filename, chunk, "IMPORTED_DOCUMENT", "")
        extracted = []
        extracted_items, analysis = extract_work_items_with_metadata(db, text[:12000])
        for item_data in extracted_items:
            item = WorkItem(
                workspace_id=workspace.id,
                title=item_data["title"],
                area=item_data.get("area"),
                work_type=item_data.get("work_type"),
                summary=item_data["summary"],
                work_date=item_data.get("work_date"),
                status="REVIEW",
                evidence_confidence="INFERRED",
                challenges=item_data.get("challenges"),
                findings=item_data.get("findings"),
                fixes=item_data.get("fixes"),
                pending_work=item_data.get("pending_work"),
                extraction_confidence=item_data.get("confidence", 0.5),
            )
            db.add(item)
            db.flush()
            db.add(
                Evidence(
                    workspace_id=workspace.id,
                    work_item_id=item.id,
                    source_type="IMPORTED_DOCUMENT",
                    source_id=str(doc.id),
                    title=f"{doc.filename}: {item.title}",
                    summary=item.summary,
                    confidence="INFERRED",
                )
            )
            upsert_fts(db, "work_item", item.id, workspace.id, item.title, item.summary, item.work_type or "Imported work", item.work_date)
            extracted.append({"id": item.id, "title": item.title, "summary": item.summary})
        db.commit()
        results.append(
            {
                "filename": doc.filename,
                "duplicate": False,
                "document_id": doc.id,
                "document_type": doc.document_type,
                "reporting_period": doc.reporting_period,
                "analysis_mode": analysis["analysis_mode"],
                "analysis_provider": analysis.get("provider"),
                "analysis_model": analysis.get("model"),
                "extracted_items": extracted,
            }
        )
    return results


@router.get("/imports")
def list_imports(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    docs = db.query(ImportedDocument).filter(ImportedDocument.workspace_id == workspace.id).order_by(ImportedDocument.created_at.desc()).all()
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "document_type": doc.document_type,
            "reporting_period": doc.reporting_period,
            "use_as_style_reference": doc.use_as_style_reference,
            "created_at": doc.created_at.isoformat(),
        }
        for doc in docs
    ]
