from fastapi import APIRouter
from starlette.requests import Request

from app.services.rules import reload_rules_service

router = APIRouter()

@router.post("/api/v1/rules/reload")
def reload_rules(request: Request):
    return reload_rules_service(request.app)
