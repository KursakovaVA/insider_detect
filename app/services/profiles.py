from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import Profile


def list_profiles_service(session: Session, *, limit: int = 50) -> list[Profile]:
    limit = max(1, min(limit, 500))
    stmt = select(Profile).order_by(Profile.risk_score.desc()).limit(limit)
    return session.execute(stmt).scalars().all()
