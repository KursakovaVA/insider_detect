from __future__ import annotations

from typing import Any, Optional

from app.rules_engine import RuleSet, load_rules
from app.settings import settings


def reload_rules_service(app: Any, rules_path: Optional[str] = None) -> dict:
    path = rules_path or getattr(settings, "RULES_PATH", None) or "rules/rules.yaml"
    app.state.ruleset = load_rules(path)
    rs: RuleSet = app.state.ruleset
    return {"status": "ok", "rules": len(rs.rules), "alert_threshold": rs.alert_threshold}
