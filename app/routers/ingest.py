from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_ruleset, require_ingest_key
from app.rules_engine import RuleSet
from app.schemas.event import EventIn
from app.services.ingest_service import ingest_event

router = APIRouter()

@router.post("/api/v1/ingest")
def ingest(
    event: EventIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    _: None = Depends(require_ingest_key),
    ruleset: RuleSet = Depends(get_ruleset),
):
    return ingest_event(event, background_tasks, session, ruleset)
