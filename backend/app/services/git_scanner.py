import subprocess
from datetime import date, datetime
from pathlib import Path
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import DEFAULT_IGNORE_PATTERNS
from ..models import Evidence, GitCommit, GitFileChange, GitScan, Repository, WorkItem
from .dedup import detect_promotions_for_commit
from .extraction import infer_area, infer_work_type
from .fts import upsert_fts
from .jobs import update_job

FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"


@dataclass
class GitScanError(Exception):
    stage: str
    public_message: str
    technical_detail: str

    def __str__(self):
        return f"{self.public_message} [{self.stage}] {self.technical_detail}"


def validate_git_repository(path: str) -> tuple[bool, str]:
    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        return False, "Folder does not exist."
    if not (root / ".git").exists():
        return False, "Folder is not a Git repository."
    return True, "Repository is valid."


def git(repo_path: str, args: list[str], timeout: int = 40, stage: str = "GIT_COMMAND") -> str:
    safe_path = str(Path(repo_path).resolve()).replace("\\", "/")
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={safe_path}", *args],
        cwd=repo_path,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "Git command failed"
        raise GitScanError(stage, public_git_error(detail), detail)
    return completed.stdout


def scan_repository(db: Session, repository_id: int, date_from: str | None = None, date_to: str | None = None, job_id: str | None = None) -> dict:
    stage = "VALIDATING_REPOSITORY"
    repo = db.get(Repository, repository_id)
    if not repo:
        raise ValueError("Repository not found.")
    ok, message = validate_git_repository(repo.local_path)
    if not ok:
        raise GitScanError(stage, message, message)

    scan = GitScan(repository_id=repo.id, date_from=date_from, date_to=date_to)
    db.add(scan)
    db.commit()
    update_job(job_id, 10, f"{stage}: {repo.name}") if job_id else None

    try:
        stage = "READING_COMMITS"
        args = [
            "log",
            f"--pretty=format:{RECORD_SEP}%H{FIELD_SEP}%h{FIELD_SEP}%an{FIELD_SEP}%aI{FIELD_SEP}%P{FIELD_SEP}%s{FIELD_SEP}%b",
            "--numstat",
        ]
        if date_from:
            args.append(f"--since={date_from}")
        if date_to:
            args.append(f"--until={date_to} 23:59:59")
        args.extend(["--", *pathspec_filters()])
        update_job(job_id, 18, f"{stage}: {repo.name}") if job_id else None
        output = git(repo.local_path, args, timeout=80, stage=stage)

        stage = "PARSING_COMMIT_METADATA"
        update_job(job_id, 25, stage) if job_id else None
        commits = parse_git_log(output)

        stage = "STORING_EVIDENCE"
        stored = 0
        total = max(len(commits), 1)
        for index, parsed in enumerate(commits):
            update_job(job_id, 30 + int(index / total * 45), f"{stage}: commit {index + 1} of {len(commits)}") if job_id else None
            existing = db.query(GitCommit).filter(GitCommit.repository_id == repo.id, GitCommit.commit_hash == parsed["hash"]).first()
            if existing:
                continue
            commit = GitCommit(
                repository_id=repo.id,
                scan_id=scan.id,
                commit_hash=parsed["hash"],
                short_hash=parsed["short_hash"],
                author=parsed["author"],
                commit_date=parse_iso(parsed["date"]),
                subject=parsed["subject"],
                body=parsed["body"],
                parents=parsed["parents"],
                insertions=sum(item["insertions"] for item in parsed["files"]),
                deletions=sum(item["deletions"] for item in parsed["files"]),
                diff_summary=diff_summary(repo.local_path, parsed["hash"]),
            )
            db.add(commit)
            db.flush()
            for item in parsed["files"]:
                db.add(
                    GitFileChange(
                        commit_id=commit.id,
                        file_path=item["path"],
                        change_type=item["change_type"],
                        insertions=item["insertions"],
                        deletions=item["deletions"],
                    )
                )
            db.flush()
            stage = "CREATING_WORK_SUGGESTIONS"
            work_item = create_git_work_item(db, repo, commit, parsed)
            evidence = Evidence(
                workspace_id=repo.workspace_id,
                work_item_id=work_item.id,
                project_id=work_item.project_id,
                evidence_type="GIT_COMMIT",
                source_type="GIT_COMMIT",
                source_id=str(commit.id),
                title=f"{repo.name}: {commit.subject}",
                summary=f"{commit.subject}\nFiles changed: {', '.join([f['path'] for f in parsed['files'][:10]])}",
                confidence="INFERRED",
                occurred_at=commit.commit_date,
            )
            db.add(evidence)
            db.flush()
            upsert_fts(
                db,
                "work_item",
                work_item.id,
                repo.workspace_id,
                work_item.title,
                work_item.summary,
                f"{repo.name} Git inference",
                work_item.work_date,
            )
            upsert_fts(
                db,
                "git_commit",
                commit.id,
                repo.workspace_id,
                evidence.title,
                f"{commit.subject}\n{commit.body or ''}\n{evidence.summary}",
                repo.name,
                commit.commit_date.date().isoformat() if commit.commit_date else "",
            )
            stage = "DETECTING_RELATIONSHIPS"
            detect_promotions_for_commit(db, evidence, commit, repo)
            stored += 1

        stage = "READING_WORKING_TREE"
        update_job(job_id, 82, stage) if job_id else None
        status = git(repo.local_path, ["status", "--short", "--", *pathspec_filters()], timeout=30, stage=stage)
        if status.strip():
            evidence = Evidence(
                workspace_id=repo.workspace_id,
                evidence_type="GIT_WORKING_TREE",
                source_type="GIT_WORKING_TREE",
                source_id=str(repo.id),
                title=f"{repo.name}: working tree changes",
                summary=status[:4000],
                confidence="UNVERIFIED",
                occurred_at=datetime.utcnow(),
            )
            db.add(evidence)
            db.flush()
            upsert_fts(db, "git_working_tree", evidence.id, repo.workspace_id, evidence.title, evidence.summary, repo.name, date.today().isoformat())

        scan.status = "COMPLETED"
        scan.completed_at = datetime.utcnow()
        scan.message = f"Scan completed. Stage=COMPLETED. Stored {stored} new commits."
        if not commits:
            scan.message = "Scan completed but no activity was found in the selected period."
        repo.last_scanned_at = datetime.utcnow()
        db.commit()
        return {"repository": repo.name, "new_commits": stored, "working_tree_changes": bool(status.strip()), "message": scan.message}
    except GitScanError as exc:
        db.rollback()
        scan.status = "FAILED"
        scan.completed_at = datetime.utcnow()
        scan.message = f"{exc.public_message}\nStage: {exc.stage}\nTechnical detail: {exc.technical_detail[:1200]}"
        db.add(scan)
        db.commit()
        raise
    except subprocess.TimeoutExpired as exc:
        db.rollback()
        error = GitScanError(stage, "Git command timed out.", str(exc))
        scan.status = "FAILED"
        scan.completed_at = datetime.utcnow()
        scan.message = f"{error.public_message}\nStage: {error.stage}\nTechnical detail: {error.technical_detail[:1200]}"
        db.add(scan)
        db.commit()
        raise error
    except Exception as exc:
        db.rollback()
        error = GitScanError(stage, "Git scan failed unexpectedly.", repr(exc))
        scan.status = "FAILED"
        scan.completed_at = datetime.utcnow()
        scan.message = f"{error.public_message}\nStage: {error.stage}\nTechnical detail: {error.technical_detail[:1200]}"
        db.add(scan)
        db.commit()
        raise error


def create_git_work_item(db: Session, repo: Repository, commit: GitCommit, parsed: dict) -> WorkItem:
    file_list = [item["path"] for item in parsed["files"][:12]]
    evidence_text = " ".join([commit.subject or "", commit.body or "", " ".join(file_list)])
    work_date = commit.commit_date.date().isoformat() if commit.commit_date else date.today().isoformat()
    summary = f"Git activity in {repo.name}."
    if file_list:
        summary += f". Changed files include: {', '.join(file_list)}."
    item = WorkItem(
        workspace_id=repo.workspace_id,
        title=commit.subject[:220] or f"Git activity {commit.short_hash}",
        area=infer_area(evidence_text.lower()),
        work_type=infer_work_type(evidence_text.lower()),
        summary=summary[:1200],
        work_date=work_date,
        status="REVIEW",
        work_status="IN_PROGRESS",
        priority="NORMAL",
        evidence_confidence="INFERRED",
        related_repository_id=repo.id,
        extraction_confidence=0.55,
    )
    db.add(item)
    db.flush()
    return item


def pathspec_excludes() -> list[str]:
    return [f":(exclude){pattern}" for pattern in DEFAULT_IGNORE_PATTERNS]


def pathspec_filters() -> list[str]:
    return [".", *pathspec_excludes()]


def parse_git_log(output: str) -> list[dict]:
    commits = []
    for record in output.split(RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        lines = record.splitlines()
        meta = lines[0].split(FIELD_SEP)
        if len(meta) < 7:
            continue
        files = []
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) >= 3:
                ins = int(parts[0]) if parts[0].isdigit() else 0
                dels = int(parts[1]) if parts[1].isdigit() else 0
                path = parts[-1]
                if not is_ignored(path):
                    files.append({"insertions": ins, "deletions": dels, "path": path, "change_type": "MODIFIED"})
        commits.append(
            {
                "hash": meta[0],
                "short_hash": meta[1],
                "author": meta[2],
                "date": meta[3],
                "parents": meta[4],
                "subject": meta[5],
                "body": meta[6],
                "files": files,
            }
        )
    return commits


def is_ignored(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(part in normalized for part in DEFAULT_IGNORE_PATTERNS)


def parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def diff_summary(repo_path: str, commit_hash: str) -> str:
    try:
        summary = git(repo_path, ["show", "--stat", "--oneline", "--find-renames", commit_hash, "--", *pathspec_filters()], timeout=30, stage="READING_FILE_CHANGES")
    except Exception:
        return ""
    return summary[:6000]


def public_git_error(detail: str) -> str:
    lower = detail.lower()
    if "dubious ownership" in lower:
        return "Git could not read this repository because Windows reports a different repository owner."
    if "not a git repository" in lower:
        return "Git could not read this repository."
    if "does not exist" in lower or "no such file" in lower:
        return "Repository path no longer exists."
    if "timed out" in lower:
        return "Git command timed out."
    return "Git could not read this repository."
