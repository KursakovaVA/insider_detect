from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.event import Alert
from app.schemas.event import AlertDetail, AlertOut

router = APIRouter()

@router.get("/api/v1/alerts", response_model=list[AlertOut])
def list_alerts(
    limit: int = 50,
    offset: int = 0,
    status: str = "open",
    src_ip: Optional[str] = None,
    trap_id: Optional[str] = None,
    session: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))

    stmt = select(Alert).where(Alert.status == status).order_by(desc(Alert.ts_updated)).limit(limit).offset(offset)

    if src_ip:
        stmt = stmt.where(Alert.src_ip == src_ip)
    if trap_id:
        stmt = stmt.where(Alert.trap_id == trap_id)

    rows = session.execute(stmt).scalars().all()
    return [AlertOut.model_validate(r) for r in rows]

@router.get("/api/v1/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: UUID, session: Session = Depends(get_db)):
    row = session.get(Alert, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="alert not found")
    return AlertDetail.model_validate(row)

@router.post("/api/v1/alerts/{alert_id}/close", response_model=AlertDetail)
def close_alert(alert_id: UUID, session: Session = Depends(get_db)):
    row = session.get(Alert, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="alert not found")

    row.status = "closed"
    row.ts_updated = datetime.now(timezone.utc)

    session.commit()
    session.refresh(row)

    return AlertDetail.model_validate(row)
