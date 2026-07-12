from sqlalchemy import text
from sqlalchemy.orm import Session


def upsert_fts(db: Session, content_type: str, content_id: int | str, workspace_id: int, title: str, body: str, source: str, event_date: str = ""):
    db.execute(
        text("DELETE FROM fts_index WHERE content_type = :content_type AND content_id = :content_id"),
        {"content_type": content_type, "content_id": str(content_id)},
    )
    db.execute(
        text(
            """
            INSERT INTO fts_index(content_type, content_id, workspace_id, title, body, source, event_date)
            VALUES(:content_type, :content_id, :workspace_id, :title, :body, :source, :event_date)
            """
        ),
        {
            "content_type": content_type,
            "content_id": str(content_id),
            "workspace_id": workspace_id,
            "title": title or "",
            "body": body or "",
            "source": source or "",
            "event_date": event_date or "",
        },
    )


def search_fts(db: Session, workspace_id: int, query: str, limit: int = 12):
    safe_query = " ".join(part.strip().replace('"', "") for part in query.split() if part.strip())
    if not safe_query:
        return []
    try:
        rows = db.execute(
            text(
                """
                SELECT content_type, content_id, title, body, source, event_date, rank
                FROM fts_index
                WHERE workspace_id = :workspace_id AND fts_index MATCH :query
                ORDER BY rank
                LIMIT :limit
                """
            ),
            {"workspace_id": workspace_id, "query": safe_query, "limit": limit},
        ).mappings()
        return [dict(row) for row in rows]
    except Exception:
        like = f"%{query}%"
        rows = db.execute(
            text(
                """
                SELECT content_type, content_id, title, body, source, event_date, 0 as rank
                FROM fts_index
                WHERE workspace_id = :workspace_id AND (title LIKE :like OR body LIKE :like)
                LIMIT :limit
                """
            ),
            {"workspace_id": workspace_id, "like": like, "limit": limit},
        ).mappings()
        return [dict(row) for row in rows]
