from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import database_url


class Base(DeclarativeBase):
    pass


engine = create_engine(database_url(), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        ensure_column(conn, "workspaces", "workspace_type", "VARCHAR(60)")
        ensure_column(conn, "workspaces", "description", "TEXT")
        ensure_column(conn, "workspaces", "updated_at", "DATETIME")
        ensure_column(conn, "work_items", "project_id", "INTEGER")
        ensure_column(conn, "generated_reports", "project_id", "INTEGER")
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
                    content_type,
                    content_id UNINDEXED,
                    workspace_id UNINDEXED,
                    title,
                    body,
                    source,
                    event_date UNINDEXED
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_evidence_type ON evidence(source_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_work_items_date ON work_items(work_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_work_items_project_id ON work_items(project_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_generated_reports_project_id ON generated_reports(project_id)"))


def ensure_column(conn, table_name: str, column_name: str, ddl: str):
    columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table_name})"))}
    if column_name not in columns:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
