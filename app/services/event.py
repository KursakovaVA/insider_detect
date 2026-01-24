from __future__ import annotations
from typing import Optional
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.event import Event

def list_events_service(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    src_ip: Optional[str] = None,
    user: Optional[str] = None,
    action: Optional[str] = None,
) -> list[Event]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    stmt = select(Event).order_by(desc(Event.ts)).limit(limit).offset(offset)

    if src_ip:
        stmt = stmt.where(Event.src_ip == src_ip)
    if user:
        stmt = stmt.where(Event.user == user)
    if action:
        stmt = stmt.where(Event.action == action)

    return session.execute(stmt).scalars().all()

