from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.event import EventOut
from app.services.event import list_events_service

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
    rows = list_events_service(
        session,
        limit=limit,
        offset=offset,
        src_ip=src_ip,
        user=user,
        action=action,
    )
    return [EventOut.model_validate(r) for r in rows]
