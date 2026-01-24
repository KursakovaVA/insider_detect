from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.profile import ProfileOut
from app.services.profiles import list_profiles_service

router = APIRouter()

@router.get("/api/v1/profiles", response_model=list[ProfileOut])
def list_profiles(limit: int = 50, session: Session = Depends(get_db)):
    rows = list_profiles_service(session, limit=limit)
    return [ProfileOut.model_validate(r) for r in rows]
