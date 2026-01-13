from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db import db
from app.rules_engine import RuleSet
from app.settings import settings

def get_db() -> Session:
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()

def require_ingest_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if settings.INGEST_API_KEY:
        if x_api_key != settings.INGEST_API_KEY:
            raise HTTPException(status_code=401, detail="invalid api key")

def get_ruleset(request: Request) -> RuleSet:
    ruleset = getattr(request.app.state, "ruleset", None)
    if ruleset is None:
        raise HTTPException(status_code=503, detail="ruleset not loaded")
    return ruleset
