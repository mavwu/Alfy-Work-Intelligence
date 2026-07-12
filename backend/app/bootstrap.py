from sqlalchemy.orm import Session

from .config import DEFAULT_IGNORE_PATTERNS, DEFAULT_USER_NAME, DEFAULT_WORKSPACE_NAME
from .models import AppSetting, ReportStyleProfile, Workspace


def ensure_defaults(db: Session) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.name == DEFAULT_WORKSPACE_NAME).first()
    if not workspace:
        workspace = Workspace(name=DEFAULT_WORKSPACE_NAME, user_name=DEFAULT_USER_NAME)
        db.add(workspace)
        db.flush()

    profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
    if not profile:
        db.add(ReportStyleProfile(workspace_id=workspace.id))

    defaults = {
        "ai_provider": "ollama",
        "selected_model": "",
        "git_ignore_patterns": "\n".join(DEFAULT_IGNORE_PATTERNS),
    }
    for key, value in defaults.items():
        if not db.get(AppSetting, key):
            db.add(AppSetting(key=key, value=value))
    db.commit()
    db.refresh(workspace)
    return workspace
