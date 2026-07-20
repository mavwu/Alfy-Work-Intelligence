from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import DEFAULT_REPORT_AUDIENCE, DEFAULT_USER_NAME, DEFAULT_WORKSPACE_NAME
from .db import Base


def now_utc():
    return datetime.utcnow()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default=DEFAULT_WORKSPACE_NAME, unique=True)
    user_name: Mapped[str] = mapped_column(String(120), default=DEFAULT_USER_NAME)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    local_path: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40), default="OTHER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    promotes_to_repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    promotes_to: Mapped["Repository | None"] = relationship(remote_side=[id])


class GitScan(Base):
    __tablename__ = "git_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    message: Mapped[str | None] = mapped_column(Text)
    date_from: Mapped[str | None] = mapped_column(String(20))
    date_to: Mapped[str | None] = mapped_column(String(20))


class GitCommit(Base):
    __tablename__ = "git_commits"
    __table_args__ = (UniqueConstraint("repository_id", "commit_hash", name="uq_repo_commit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("git_scans.id"), nullable=True)
    commit_hash: Mapped[str] = mapped_column(String(80))
    short_hash: Mapped[str] = mapped_column(String(16))
    author: Mapped[str | None] = mapped_column(String(180))
    commit_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    parents: Mapped[str | None] = mapped_column(Text)
    insertions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    diff_summary: Mapped[str | None] = mapped_column(Text)


class GitFileChange(Base):
    __tablename__ = "git_file_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    commit_id: Mapped[int] = mapped_column(ForeignKey("git_commits.id"), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    change_type: Mapped[str | None] = mapped_column(String(20))
    insertions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)


class RawWorkLog(Base):
    __tablename__ = "raw_work_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    source_label: Mapped[str] = mapped_column(String(80), default="Manual work log")


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    area: Mapped[str | None] = mapped_column(String(160))
    work_type: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    work_date: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(40), default="REVIEW")
    evidence_confidence: Mapped[str] = mapped_column(String(30), default="INFERRED")
    challenges: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[str | None] = mapped_column(Text)
    fixes: Mapped[str | None] = mapped_column(Text)
    pending_work: Mapped[str | None] = mapped_column(Text)
    related_repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), nullable=True)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(30), default="INFERRED")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class EvidenceRelationship(Base):
    __tablename__ = "evidence_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    to_evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40))
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ImportedDocument(Base):
    __tablename__ = "imported_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    filename: Mapped[str] = mapped_column(String(260))
    original_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(80), unique=True)
    document_type: Mapped[str | None] = mapped_column(String(80))
    reporting_period: Mapped[str | None] = mapped_column(String(120))
    extracted_text: Mapped[str] = mapped_column(Text)
    use_as_style_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("imported_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class ReportStyleProfile(Base):
    __tablename__ = "report_style_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), unique=True)
    audience: Mapped[str] = mapped_column(String(160), default=DEFAULT_REPORT_AUDIENCE)
    tone: Mapped[str] = mapped_column(String(120), default="Professional")
    technical_depth: Mapped[str] = mapped_column(String(120), default="Moderate")
    notes: Mapped[str] = mapped_column(Text, default="Explain technical context clearly before conclusions. Prefer concrete findings and practical recommendations. Avoid exaggerated achievements.")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(240))
    date_from: Mapped[str] = mapped_column(String(20))
    date_to: Mapped[str] = mapped_column(String(20))
    draft_markdown: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    use_as_style_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReportRevision(Base):
    __tablename__ = "report_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("generated_reports.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(260), default="Initial generation")
    draft_markdown: Mapped[str] = mapped_column(Text)
    validation_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(180), default="Work chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
