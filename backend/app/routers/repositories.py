from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db, SessionLocal
from ..models import Repository
from ..services.git_scanner import GitScanError, scan_repository, validate_git_repository
from ..services.jobs import create_job, get_job

router = APIRouter()


class RepositoryIn(BaseModel):
    name: str
    local_path: str
    role: str = "OTHER"
    is_active: bool = True
    promotes_to_repository_id: int | None = None


class ScanRequest(BaseModel):
    repository_id: int
    date_from: str | None = None
    date_to: str | None = None


@router.get("/repositories")
def list_repositories(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    repos = db.query(Repository).filter(Repository.workspace_id == workspace.id).order_by(Repository.name).all()
    return [serialize_repo(repo) for repo in repos]


@router.post("/repositories")
def create_repository(payload: RepositoryIn, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    ok, message = validate_git_repository(payload.local_path)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    if payload.promotes_to_repository_id is not None:
        target = db.get(Repository, payload.promotes_to_repository_id)
        if not target or target.workspace_id != workspace.id:
            raise HTTPException(status_code=400, detail="Canonical repository must belong to the active workspace.")
    repo = Repository(
        workspace_id=workspace.id,
        name=payload.name.strip() or Path(payload.local_path).name,
        local_path=str(Path(payload.local_path).expanduser()),
        role=payload.role,
        is_active=payload.is_active,
        promotes_to_repository_id=payload.promotes_to_repository_id,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return serialize_repo(repo)


@router.put("/repositories/{repository_id}")
def update_repository(repository_id: int, payload: RepositoryIn, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    repo = db.get(Repository, repository_id)
    if not repo or repo.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Repository not found")
    ok, message = validate_git_repository(payload.local_path)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    repo.name = payload.name
    repo.local_path = str(Path(payload.local_path).expanduser())
    repo.role = payload.role
    repo.is_active = payload.is_active
    repo.promotes_to_repository_id = payload.promotes_to_repository_id
    db.commit()
    return serialize_repo(repo)


@router.post("/git/scan")
def start_scan(payload: ScanRequest, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    repo = db.get(Repository, payload.repository_id)
    if not repo or repo.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Repository not found")

    def run(job_id: str):
        db = SessionLocal()
        try:
            return scan_repository(db, payload.repository_id, payload.date_from, payload.date_to, job_id=job_id)
        except GitScanError as exc:
            raise RuntimeError(f"{exc.public_message} Stage: {exc.stage}. Detail: {exc.technical_detail[:600]}") from exc
        finally:
            db.close()

    job_id = create_job("Git scan", run)
    return {"job_id": job_id}


@router.post("/git/scan-now/{repository_id}")
def scan_now(repository_id: int, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    repo = db.get(Repository, repository_id)
    if not repo or repo.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Repository not found")
    try:
        return scan_repository(db, repository_id)
    except GitScanError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": exc.public_message,
                "stage": exc.stage,
                "technical_detail": exc.technical_detail,
            },
        ) from exc


@router.get("/jobs/{job_id}")
def read_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def serialize_repo(repo: Repository):
    return {
        "id": repo.id,
        "name": repo.name,
        "local_path": repo.local_path,
        "role": repo.role,
        "is_active": repo.is_active,
        "promotes_to_repository_id": repo.promotes_to_repository_id,
        "last_scanned_at": repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
    }
    if payload.promotes_to_repository_id is not None:
        target = db.get(Repository, payload.promotes_to_repository_id)
        if not target or target.workspace_id != workspace.id:
            raise HTTPException(status_code=400, detail="Canonical repository must belong to the active workspace.")
