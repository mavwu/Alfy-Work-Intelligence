from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Evidence, EvidenceRelationship, GitCommit, GitFileChange, Repository


def normalize_subject(text: str) -> set[str]:
    words = "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    return {w for w in words if len(w) > 3 and w not in {"update", "fixed", "added", "changes", "work"}}


def file_set(db: Session, commit_id: int) -> set[str]:
    rows = db.query(GitFileChange).filter(GitFileChange.commit_id == commit_id).all()
    return {row.file_path.lower().replace("\\", "/") for row in rows}


def overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left | right), 1)


def detect_promotions_for_commit(db: Session, evidence: Evidence, commit: GitCommit, repository: Repository):
    if not repository.promotes_to_repository_id:
        detect_canonical_commit_against_sandboxes(db, evidence, commit, repository)
        return
    canonical_commits = (
        db.query(GitCommit)
        .filter(GitCommit.repository_id == repository.promotes_to_repository_id)
        .filter(GitCommit.commit_date >= (commit.commit_date or datetime.utcnow()) - timedelta(days=14))
        .filter(GitCommit.commit_date <= (commit.commit_date or datetime.utcnow()) + timedelta(days=14))
        .all()
    )
    source_words = normalize_subject(commit.subject)
    source_files = file_set(db, commit.id)
    for candidate in canonical_commits:
        words = normalize_subject(candidate.subject)
        word_score = len(source_words & words) / max(len(source_words | words), 1)
        files_score = overlap_score(source_files, file_set(db, candidate.id))
        score = (word_score * 0.55) + (files_score * 0.45)
        if score >= 0.35:
            target = db.query(Evidence).filter(Evidence.source_type == "GIT_COMMIT", Evidence.source_id == str(candidate.id)).first()
            add_relationship(db, evidence, target, score)


def detect_canonical_commit_against_sandboxes(db: Session, canonical_evidence: Evidence, canonical_commit: GitCommit, canonical_repository: Repository):
    sandbox_repositories = db.query(Repository).filter(Repository.promotes_to_repository_id == canonical_repository.id).all()
    if not sandbox_repositories:
        return
    canonical_words = normalize_subject(canonical_commit.subject)
    canonical_files = file_set(db, canonical_commit.id)
    for sandbox_repo in sandbox_repositories:
        sandbox_commits = (
            db.query(GitCommit)
            .filter(GitCommit.repository_id == sandbox_repo.id)
            .filter(GitCommit.commit_date >= (canonical_commit.commit_date or datetime.utcnow()) - timedelta(days=14))
            .filter(GitCommit.commit_date <= (canonical_commit.commit_date or datetime.utcnow()) + timedelta(days=14))
            .all()
        )
        for sandbox_commit in sandbox_commits:
            word_score = len(canonical_words & normalize_subject(sandbox_commit.subject)) / max(
                len(canonical_words | normalize_subject(sandbox_commit.subject)),
                1,
            )
            files_score = overlap_score(canonical_files, file_set(db, sandbox_commit.id))
            score = (word_score * 0.55) + (files_score * 0.45)
            if score >= 0.35:
                sandbox_evidence = db.query(Evidence).filter(Evidence.source_type == "GIT_COMMIT", Evidence.source_id == str(sandbox_commit.id)).first()
                add_relationship(db, sandbox_evidence, canonical_evidence, score)


def add_relationship(db: Session, source: Evidence | None, target: Evidence | None, score: float):
    if not source or not target or source.id == target.id:
        return
    if existing_relationship(db, source.id, target.id):
        return
    relationship_type = "PROMOTED_TO" if score >= 0.58 else "POSSIBLE_DUPLICATE"
    db.add(
        EvidenceRelationship(
            from_evidence_id=source.id,
            to_evidence_id=target.id,
            relationship_type=relationship_type,
            confidence_score=round(score, 2),
            explanation="Detected from sandbox-to-canonical repository link, similar commit wording, overlapping files, and close dates.",
        )
    )


def existing_relationship(db: Session, left_id: int, right_id: int) -> bool:
    return (
        db.query(EvidenceRelationship)
        .filter(EvidenceRelationship.from_evidence_id == left_id, EvidenceRelationship.to_evidence_id == right_id)
        .first()
        is not None
    )
