from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.event import Profile
from app.schemas.event import ProfileOut

router = APIRouter()

@router.get("/api/v1/profiles", response_model=list[ProfileOut])
def list_profiles(limit: int = 50, session: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    stmt = select(Profile).order_by(Profile.risk_score.desc()).limit(limit)
    rows = session.execute(stmt).scalars().all()
    return [ProfileOut.model_validate(r) for r in rows]
