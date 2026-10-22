from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from stylelens.chat.service import ChatRequest, run_chat
from stylelens.db.models import Conversation, Feedback, Message
from stylelens.db.session import get_session

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    guide_id: str
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    comparison_id: str | None = None


@router.post("/chat")
async def chat(body: ChatIn):
    """Streams Server-Sent Events: status, sources, token…, citations, followups, done (or error)."""
    req = ChatRequest(guide_id=body.guide_id, message=body.message.strip(),
                      conversation_id=body.conversation_id, comparison_id=body.comparison_id)
    return EventSourceResponse(run_chat(req), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict]
    meta: dict
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    guide_id: str
    comparison_id: str | None
    title: str | None
    created_at: datetime


@router.get("/conversations", response_model=list[ConversationOut])
async def conversations(guide_id: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Conversation).order_by(Conversation.created_at.desc()).limit(50)
    if guide_id:
        stmt = stmt.where(Conversation.guide_id == guide_id)
    return [ConversationOut.model_validate(c, from_attributes=True) for c in await session.scalars(stmt)]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def conversation_messages(conversation_id: str, session: AsyncSession = Depends(get_session)):
    rows = await session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at))
    return [MessageOut.model_validate(m, from_attributes=True) for m in rows]


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=2000)


@router.post("/messages/{message_id}/feedback", status_code=204)
async def feedback(message_id: str, body: FeedbackIn, session: AsyncSession = Depends(get_session)):
    msg = await session.get(Message, message_id)
    if msg is None or msg.role != "assistant":
        raise HTTPException(404, "Message not found")
    existing = await session.scalar(select(Feedback).where(Feedback.message_id == message_id))
    if existing:
        existing.rating, existing.comment = body.rating, body.comment
    else:
        session.add(Feedback(message_id=message_id, rating=body.rating, comment=body.comment))
    await session.commit()
