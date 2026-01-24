from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.alert import AlertDetail, AlertOut
from app.services.alerts import list_alerts_service, get_alert_service, close_alert_service

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
    rows = list_alerts_service(
        session,
        limit=limit,
        offset=offset,
        status=status,
        src_ip=src_ip,
        trap_id=trap_id,
    )
    return [AlertOut.model_validate(r) for r in rows]

@router.get("/api/v1/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: UUID, session: Session = Depends(get_db)):
    row = get_alert_service(session, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="alert not found")
    return AlertDetail.model_validate(row)

@router.post("/api/v1/alerts/{alert_id}/close", response_model=AlertDetail)
def close_alert(alert_id: UUID, session: Session = Depends(get_db)):
    row = close_alert_service(session, alert_id)
    if not row:
        raise HTTPException(status_code=404, detail="alert not found")
    return AlertDetail.model_validate(row)
