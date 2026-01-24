from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.alert import Alert


def list_alerts_service(
    session: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str = "open",
    src_ip: Optional[str] = None,
    trap_id: Optional[str] = None,
) -> list[Alert]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    stmt = (
        select(Alert)
        .where(Alert.status == status)
        .order_by(desc(Alert.ts_updated))
        .limit(limit)
        .offset(offset)
    )

    if src_ip:
        stmt = stmt.where(Alert.src_ip == src_ip)
    if trap_id:
        stmt = stmt.where(Alert.trap_id == trap_id)

    return session.execute(stmt).scalars().all()


def get_alert_service(session: Session, alert_id: UUID) -> Optional[Alert]:
    return session.get(Alert, alert_id)


def close_alert_service(session: Session, alert_id: UUID) -> Optional[Alert]:
    row = session.get(Alert, alert_id)
    if not row:
        return None

    row.status = "closed"
    row.ts_updated = datetime.now(timezone.utc)

    session.commit()
    session.refresh(row)
    return row
