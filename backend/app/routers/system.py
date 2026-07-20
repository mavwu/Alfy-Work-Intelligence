from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import AppSetting, ReportStyleProfile, Workspace
from ..services.ai import OllamaProvider

router = APIRouter()


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    user_name: str | None = None
    role_title: str | None = None
    report_audience: str | None = None
    onboarding_complete: bool | None = None


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.get("/workspaces/default")
def default_workspace(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    return serialize_workspace(workspace)


@router.put("/workspaces/default")
def update_workspace(payload: WorkspaceUpdate, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    if payload.name is not None:
        workspace.name = payload.name.strip() or workspace.name
    if payload.user_name is not None:
        workspace.user_name = payload.user_name.strip() or workspace.user_name
        upsert_setting(db, "profile_display_name", workspace.user_name)
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
    db.commit()
    db.refresh(workspace)
    return serialize_workspace(workspace)


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
    if payload.key == "profile_display_name":
        workspace = ensure_defaults(db)
        workspace.user_name = payload.value.strip() or workspace.user_name
    elif payload.key == "default_report_audience":
        workspace = ensure_defaults(db)
        profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
        if not profile:
            profile = ReportStyleProfile(workspace_id=workspace.id)
            db.add(profile)
        profile.audience = payload.value.strip() or profile.audience
    db.commit()
    return {"ok": True}


def serialize_workspace(workspace: Workspace):
    return {
        "id": workspace.id,
        "name": workspace.name,
        "user_name": workspace.user_name,
        "onboarding_complete": workspace.onboarding_complete,
        "created_at": workspace.created_at.isoformat(),
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
