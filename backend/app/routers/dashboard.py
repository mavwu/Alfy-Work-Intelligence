from datetime import date, datetime, timedelta
from sqlalchemy import func

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..models import GitCommit, Repository, WorkItem

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
    types = {kind: sum(1 for item in items if (item.work_type or "").lower().startswith(kind.lower())) for kind in ["Bug", "Technical", "Feature"]}
    return {
        "greeting_name": workspace.user_name,
        "this_week": {
            "work_days_logged": len({item.work_date for item in items}),
            "git_commits": commits,
            "areas_worked_on": areas,
            "confirmed_work_items": sum(1 for item in items if item.status == "CONFIRMED"),
            "bugs_resolved": types["Bug"],
            "investigations": types["Technical"],
            "features_worked_on": types["Feature"],
            "pending_items": sum(1 for item in items if item.pending_work),
        },
        "recent_work": [
            {"id": item.id, "title": item.title, "summary": item.summary, "work_date": item.work_date, "status": item.status}
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
