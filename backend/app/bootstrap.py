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

ACTIVE_WORKSPACE_SETTING = "active_workspace_id"


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
    active_setting = db.get(AppSetting, ACTIVE_WORKSPACE_SETTING)
    if not active_setting:
        db.add(AppSetting(key=ACTIVE_WORKSPACE_SETTING, value=str(workspace.id)))
    db.commit()
    db.refresh(workspace)
    return active_workspace(db)


def active_workspace(db: Session) -> Workspace:
    workspace = configured_active_workspace(db)
    if workspace:
        ensure_workspace_profile(db, workspace)
        db.commit()
        db.refresh(workspace)
        return workspace
    fallback = db.query(Workspace).order_by(Workspace.id).first()
    if not fallback:
        fallback = Workspace(name=DEFAULT_WORKSPACE_NAME, user_name=DEFAULT_USER_NAME)
        db.add(fallback)
        db.flush()
    set_active_workspace(db, fallback.id, commit=False)
    ensure_workspace_profile(db, fallback)
    db.commit()
    db.refresh(fallback)
    return fallback


def configured_active_workspace(db: Session) -> Workspace | None:
    setting = db.get(AppSetting, ACTIVE_WORKSPACE_SETTING)
    if not setting or not setting.value:
        return None
    try:
        workspace_id = int(setting.value)
    except ValueError:
        return None
    return db.get(Workspace, workspace_id)


def set_active_workspace(db: Session, workspace_id: int, commit: bool = True) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise ValueError("Workspace not found")
    setting = db.get(AppSetting, ACTIVE_WORKSPACE_SETTING)
    if not setting:
        db.add(AppSetting(key=ACTIVE_WORKSPACE_SETTING, value=str(workspace.id)))
    else:
        setting.value = str(workspace.id)
    ensure_workspace_profile(db, workspace)
    if commit:
        db.commit()
        db.refresh(workspace)
    return workspace


def ensure_workspace_profile(db: Session, workspace: Workspace):
    profile = db.query(ReportStyleProfile).filter(ReportStyleProfile.workspace_id == workspace.id).first()
    if not profile:
        audience = RIDE_YANGA_REPORT_AUDIENCE if workspace.name == DEFAULT_WORKSPACE_NAME else DEFAULT_REPORT_AUDIENCE
        db.add(ReportStyleProfile(workspace_id=workspace.id, audience=audience))
