from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bootstrap import ensure_defaults
from ..db import get_db
from ..services.chat import answer_work_question

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    workspace = ensure_defaults(db)
    return answer_work_question(db, workspace.id, payload.message, payload.conversation_id)
