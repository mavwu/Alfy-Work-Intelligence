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
