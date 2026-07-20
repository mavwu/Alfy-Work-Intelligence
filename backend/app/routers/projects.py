from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import Project, Workspace

router = APIRouter()

PROJECT_STATUSES = {"ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"}


class ProjectIn(BaseModel):
    name: str
    workspace_id: int | None = None
    description: str | None = None
    status: str = "ACTIVE"
    category: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    category: str | None = None
    start_date: str | None = None
    end_date: str | None = None


@router.get("/projects")
def list_projects(workspace_id: int | None = None, include_archived: bool = False, db: Session = Depends(get_db)):
    workspace = workspace_for_request(db, workspace_id)
    query = db.query(Project).filter(Project.workspace_id == workspace.id)
    if not include_archived:
        query = query.filter(Project.status != "ARCHIVED")
    projects = query.order_by(Project.name).all()
    return [serialize_project(project) for project in projects]


@router.post("/projects")
def create_project(payload: ProjectIn, db: Session = Depends(get_db)):
    workspace = workspace_for_request(db, payload.workspace_id)
    name = clean_name(payload.name)
    status = validate_status(payload.status)
    if existing_project(db, workspace.id, name):
        raise HTTPException(status_code=400, detail="Project already exists in this workspace.")
    project = Project(
        workspace_id=workspace.id,
        name=name,
        description=clean_optional(payload.description),
        status=status,
        category=clean_optional(payload.category),
        start_date=clean_optional(payload.start_date),
        end_date=clean_optional(payload.end_date),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return serialize_project(project)


@router.get("/projects/{project_id}")
def read_project(project_id: int, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    project = project_in_workspace(db, project_id, workspace.id)
    return serialize_project(project)


@router.put("/projects/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    project = project_in_workspace(db, project_id, workspace.id)
    if payload.name is not None:
        name = clean_name(payload.name)
        duplicate = existing_project(db, workspace.id, name, exclude_id=project.id)
        if duplicate:
            raise HTTPException(status_code=400, detail="Project already exists in this workspace.")
        project.name = name
    if payload.status is not None:
        project.status = validate_status(payload.status)
    if payload.description is not None:
        project.description = clean_optional(payload.description)
    if payload.category is not None:
        project.category = clean_optional(payload.category)
    if payload.start_date is not None:
        project.start_date = clean_optional(payload.start_date)
    if payload.end_date is not None:
        project.end_date = clean_optional(payload.end_date)
    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)
    return serialize_project(project)


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: int, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    project = project_in_workspace(db, project_id, workspace.id)
    project.status = "ARCHIVED"
    project.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(project)
    return serialize_project(project)


def workspace_for_request(db: Session, workspace_id: int | None) -> Workspace:
    if workspace_id is None:
        return ensure_defaults(db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def project_in_workspace(db: Session, project_id: int, workspace_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project or project.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def existing_project(db: Session, workspace_id: int, name: str, exclude_id: int | None = None) -> Project | None:
    query = db.query(Project).filter(Project.workspace_id == workspace_id, Project.name == name)
    if exclude_id:
        query = query.filter(Project.id != exclude_id)
    return query.first()


def validate_status(value: str) -> str:
    status = (value or "").strip().upper()
    if status not in PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid project status.")
    return status


def clean_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")
    return name


def clean_optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def serialize_project(project: Project):
    return {
        "id": project.id,
        "workspace_id": project.workspace_id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "category": project.category,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
