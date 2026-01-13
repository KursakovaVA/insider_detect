from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.event import Event
from app.schemas.event import EventOut

router = APIRouter()

@router.get("/api/v1/events", response_model=list[EventOut])
def list_events(
    limit: int = 50,
    offset: int = 0,
    src_ip: Optional[str] = None,
    user: Optional[str] = None,
    action: Optional[str] = None,
    session: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))

    stmt = select(Event).order_by(desc(Event.ts)).limit(limit).offset(offset)

    if src_ip:
        stmt = stmt.where(Event.src_ip == src_ip)
    if user:
        stmt = stmt.where(Event.user == user)
    if action:
        stmt = stmt.where(Event.action == action)

    rows = session.execute(stmt).scalars().all()
    return [EventOut.model_validate(r) for r in rows]
