from fastapi import APIRouter
from starlette.requests import Request

from app.rules_engine import RuleSet, load_rules
from app.settings import settings

router = APIRouter()

@router.post("/api/v1/rules/reload")
def reload_rules(request: Request):
    rules_path = getattr(settings, "RULES_PATH", None) or "rules/rules.yaml"
    request.app.state.ruleset = load_rules(rules_path)
    rs: RuleSet = request.app.state.ruleset
    return {"status": "ok", "rules": len(rs.rules), "alert_threshold": rs.alert_threshold}
