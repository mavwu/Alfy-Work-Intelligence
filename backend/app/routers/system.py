from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import active_workspace, ensure_defaults, set_active_workspace
from ..db import get_db
from ..models import AppSetting, ReportStyleProfile, Workspace
from ..services.ai import OllamaProvider

router = APIRouter()


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    user_name: str | None = None
    workspace_type: str | None = None
    description: str | None = None
    role_title: str | None = None
    report_audience: str | None = None
    onboarding_complete: bool | None = None


class WorkspaceCreate(BaseModel):
    name: str
    workspace_type: str | None = None
    description: str | None = None
    report_audience: str | None = None


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.get("/workspaces")
def list_workspaces(db: Session = Depends(get_db)):
    active = ensure_defaults(db)
    rows = db.query(Workspace).order_by(Workspace.name).all()
    return [serialize_workspace(row, active_id=active.id, profile=workspace_profile(db, row.id)) for row in rows]


@router.post("/workspaces")
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    ensure_defaults(db)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Workspace name is required.")
    existing = db.query(Workspace).filter(Workspace.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Workspace already exists.")
    display_name = setting_value(db, "profile_display_name", "")
    workspace = Workspace(
        name=name,
        user_name=display_name,
        workspace_type=clean_optional(payload.workspace_type),
        description=clean_optional(payload.description),
    )
    db.add(workspace)
    db.flush()
    db.add(ReportStyleProfile(workspace_id=workspace.id, audience=clean_optional(payload.report_audience) or "Stakeholder"))
    db.commit()
    db.refresh(workspace)
    return serialize_workspace(workspace, active_id=active_workspace(db).id, profile=workspace_profile(db, workspace.id))


@router.get("/workspaces/default")
def default_workspace(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    return serialize_workspace(workspace, active_id=workspace.id, profile=workspace_profile(db, workspace.id))


@router.get("/workspaces/active")
def get_active_workspace(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    return serialize_workspace(workspace, active_id=workspace.id, profile=workspace_profile(db, workspace.id))


@router.post("/workspaces/{workspace_id}/select")
def select_workspace(workspace_id: int, db: Session = Depends(get_db)):
    ensure_defaults(db)
    try:
        workspace = set_active_workspace(db, workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found.") from exc
    return serialize_workspace(workspace, active_id=workspace.id, profile=workspace_profile(db, workspace.id))


@router.put("/workspaces/default")
def update_workspace(payload: WorkspaceUpdate, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    update_workspace_fields(db, workspace, payload)
    db.refresh(workspace)
    return serialize_workspace(workspace, active_id=workspace.id, profile=workspace_profile(db, workspace.id))


@router.put("/workspaces/{workspace_id}")
def update_workspace_by_id(workspace_id: int, payload: WorkspaceUpdate, db: Session = Depends(get_db)):
    ensure_defaults(db)
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    update_workspace_fields(db, workspace, payload)
    active = active_workspace(db)
    db.refresh(workspace)
    return serialize_workspace(workspace, active_id=active.id, profile=workspace_profile(db, workspace.id))


def update_workspace_fields(db: Session, workspace: Workspace, payload: WorkspaceUpdate):
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Workspace name is required.")
        duplicate = db.query(Workspace).filter(Workspace.name == name, Workspace.id != workspace.id).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Workspace already exists.")
        workspace.name = name
    if payload.user_name is not None:
        workspace.user_name = payload.user_name.strip() or workspace.user_name
    if payload.workspace_type is not None:
        workspace.workspace_type = clean_optional(payload.workspace_type)
    if payload.description is not None:
        workspace.description = clean_optional(payload.description)
    if payload.role_title is not None:
        upsert_setting(db, "profile_role_title", payload.role_title.strip())
    if payload.report_audience is not None:
        profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
        if not profile:
            profile = ReportStyleProfile(workspace_id=workspace.id)
            db.add(profile)
        profile.audience = payload.report_audience.strip() or profile.audience
    if payload.onboarding_complete is not None:
        workspace.onboarding_complete = payload.onboarding_complete
    workspace.updated_at = datetime.utcnow()
    db.commit()


@router.get("/ai/status")
def ai_status(db: Session = Depends(get_db)):
    provider = OllamaProvider()
    status = provider.health_check()
    setting = db.get(AppSetting, "selected_model")
    selected_model = setting.value if setting else ""
    status["provider"] = "Ollama"
    status["selected_model"] = selected_model
    return status


@router.post("/ai/test")
def test_ai(payload: dict, db: Session = Depends(get_db)):
    provider = OllamaProvider()
    status = provider.health_check()
    setting = db.get(AppSetting, "selected_model")
    model = (payload.get("model") or (setting.value if setting else "")).strip()
    status["provider"] = "Ollama"
    status["selected_model"] = model
    if not status.get("available"):
        return status
    try:
        if not model:
            return {"available": False, "message": "No Ollama model is selected.", "models": status.get("models", []), "selected_model": ""}
        text = provider.generate_text(model, "Reply with one short sentence confirming you are ready to help summarize local work evidence.")
        return {"available": True, "message": text, "models": status.get("models", []), "selected_model": model}
    except Exception as exc:
        return {"available": False, "message": str(exc), "models": status.get("models", []), "selected_model": model}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    settings = {row.key: row.value for row in db.query(AppSetting).all()}
    profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
    if profile:
        settings.setdefault("default_report_audience", profile.audience)
    return {
        "settings": settings,
        "style_profile": serialize_style_profile(profile) if profile else None,
    }


@router.put("/settings")
def update_setting(payload: SettingUpdate, db: Session = Depends(get_db)):
    setting = upsert_setting(db, payload.key, payload.value)
    if payload.key == "default_report_audience":
        workspace = ensure_defaults(db)
        profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
        if not profile:
            profile = ReportStyleProfile(workspace_id=workspace.id)
            db.add(profile)
        profile.audience = payload.value.strip() or profile.audience
    db.commit()
    return {"ok": True}


def serialize_workspace(workspace: Workspace, active_id: int | None = None, profile: ReportStyleProfile | None = None):
    return {
        "id": workspace.id,
        "name": workspace.name,
        "user_name": workspace.user_name,
        "workspace_type": workspace.workspace_type,
        "description": workspace.description,
        "report_audience": profile.audience if profile else None,
        "onboarding_complete": workspace.onboarding_complete,
        "is_active": workspace.id == active_id if active_id is not None else False,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None,
    }


def serialize_style_profile(profile: ReportStyleProfile):
    return {
        "id": profile.id,
        "workspace_id": profile.workspace_id,
        "audience": profile.audience,
        "tone": profile.tone,
        "technical_depth": profile.technical_depth,
        "notes": profile.notes,
        "updated_at": profile.updated_at.isoformat(),
    }


def upsert_setting(db: Session, key: str, value: str) -> AppSetting:
    setting = db.get(AppSetting, key)
    if not setting:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    return setting


def setting_value(db: Session, key: str, default: str) -> str:
    setting = db.get(AppSetting, key)
    return setting.value if setting and setting.value else default


def workspace_profile(db: Session, workspace_id: int) -> ReportStyleProfile | None:
    return db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace_id).first()


def clean_optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None
