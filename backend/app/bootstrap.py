from sqlalchemy.orm import Session

from .config import (
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_PROFILE_ROLE_TITLE,
    DEFAULT_PROFILE_TIMEZONE,
    DEFAULT_REPORT_AUDIENCE,
    DEFAULT_REPORT_SIGNATURE,
    DEFAULT_USER_NAME,
    DEFAULT_WORKSPACE_NAME,
    RIDE_YANGA_REPORT_AUDIENCE,
)
from .models import AppSetting, ReportStyleProfile, Workspace


def ensure_defaults(db: Session) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.name == DEFAULT_WORKSPACE_NAME).first()
    if not workspace:
        workspace = db.query(Workspace).order_by(Workspace.id).first()
    if not workspace:
        workspace = Workspace(name=DEFAULT_WORKSPACE_NAME, user_name=DEFAULT_USER_NAME)
        db.add(workspace)
        db.flush()

    profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
    if not profile:
        audience = RIDE_YANGA_REPORT_AUDIENCE if workspace.name == DEFAULT_WORKSPACE_NAME else DEFAULT_REPORT_AUDIENCE
        db.add(ReportStyleProfile(workspace_id=workspace.id, audience=audience))

    defaults = {
        "ai_provider": "ollama",
        "selected_model": "",
        "git_ignore_patterns": "\n".join(DEFAULT_IGNORE_PATTERNS),
        "profile_display_name": workspace.user_name or DEFAULT_USER_NAME,
        "profile_role_title": DEFAULT_PROFILE_ROLE_TITLE,
        "profile_timezone": DEFAULT_PROFILE_TIMEZONE,
        "profile_report_signature": DEFAULT_REPORT_SIGNATURE,
    }
    for key, value in defaults.items():
        if not db.get(AppSetting, key):
            db.add(AppSetting(key=key, value=value))
    db.commit()
    db.refresh(workspace)
    return workspace
