from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import AppSetting, ReportStyleProfile, Workspace
from ..services.ai import OllamaProvider

router = APIRouter()


class WorkspaceUpdate(BaseModel):
    name: str
    user_name: str = "Alfy"
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
    workspace.name = payload.name.strip() or workspace.name
    workspace.user_name = payload.user_name.strip() or workspace.user_name
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
    return {"settings": settings, "style_profile": profile.__dict__ if profile else None}


@router.put("/settings")
def update_setting(payload: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.get(AppSetting, payload.key)
    if not setting:
        setting = AppSetting(key=payload.key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
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
