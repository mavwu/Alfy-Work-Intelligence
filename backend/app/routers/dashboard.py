from datetime import date, datetime, timedelta
from sqlalchemy import func

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import AppSetting, GitCommit, Repository, WorkItem

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_start_s = week_start.isoformat()
    today_s = today.isoformat()
    items = (
        db.query(WorkItem)
        .filter(WorkItem.workspace_id == workspace.id)
        .filter(WorkItem.work_date >= week_start_s, WorkItem.work_date <= today_s)
        .all()
    )
    repos = db.query(Repository).filter(Repository.workspace_id == workspace.id).all()
    repo_ids = [repo.id for repo in repos]
    commits = 0
    if repo_ids:
        commits = db.query(GitCommit).filter(GitCommit.repository_id.in_(repo_ids), GitCommit.commit_date >= datetime.combine(week_start, datetime.min.time())).count()
    areas = sorted({item.area for item in items if item.area})
    types = {
        "issues": sum(1 for item in items if legacy_or_generic_type(item.work_type, ["bug", "issue"])),
        "investigations": sum(1 for item in items if legacy_or_generic_type(item.work_type, ["technical", "investigation", "research"])),
        "deliverables": sum(1 for item in items if legacy_or_generic_type(item.work_type, ["feature", "deliverable"])),
    }
    return {
        "greeting_name": profile_display_name(db) or workspace.user_name,
        "this_week": {
            "work_days_logged": len({item.work_date for item in items}),
            "git_commits": commits,
            "areas_worked_on": areas,
            "confirmed_work_items": sum(1 for item in items if item.status == "CONFIRMED"),
            "bugs_resolved": types["issues"],
            "investigations": types["investigations"],
            "features_worked_on": types["deliverables"],
            "pending_items": sum(1 for item in items if item.pending_work or item.next_step or item.work_status in {"BLOCKED", "IN_PROGRESS"}),
        },
        "recent_work": [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.summary,
                "work_date": item.work_date,
                "status": item.status,
                "work_status": item.work_status,
                "category": item.category,
                "priority": item.priority,
                "outcome": item.outcome,
            }
            for item in sorted(items, key=lambda item: item.work_date, reverse=True)[:8]
        ],
        "repository_health": [
            {
                "id": repo.id,
                "name": repo.name,
                "role": repo.role,
                "last_scanned_at": repo.last_scanned_at.isoformat() if repo.last_scanned_at else None,
            }
            for repo in repos
        ],
        "ai_insight": make_insight(items),
        "weekly_report_generated": False,
    }


def make_insight(items: list[WorkItem]) -> str | None:
    areas = {}
    for item in items:
        if item.area:
            areas[item.area] = areas.get(item.area, 0) + 1
    if not areas:
        return None
    top = sorted(areas.items(), key=lambda pair: pair[1], reverse=True)[0]
    if top[1] < 2:
        return None
    return f"Most recorded activity this week is concentrated around {top[0]}."


def legacy_or_generic_type(value: str | None, needles: list[str]) -> bool:
    lower = (value or "").lower()
    return any(needle in lower for needle in needles)


def profile_display_name(db: Session) -> str:
    setting = db.get(AppSetting, "profile_display_name")
    return setting.value.strip() if setting and setting.value else ""
