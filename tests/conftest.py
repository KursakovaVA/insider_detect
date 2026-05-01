from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pytest
import yaml

from app.rules_engine import Rule, RuleSet, load_rules


MSK = ZoneInfo("Europe/Moscow")


@pytest.fixture
def write_rules_yaml(tmp_path: Path) -> Callable[[dict[str, Any]], Path]:
    def _write(data: dict[str, Any], filename: str = "rules.yaml") -> Path:
        path = tmp_path / filename
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def minimal_yaml_data() -> dict[str, Any]:
    return {
        "context": {
            "timezone": "Europe/Moscow",
            "work_hours": {"start": "09:00", "end": "18:00", "weekdays": [1, 2, 3, 4, 5]},
            "off_hours": {"multiplier": 2.0, "actions": ["login_failed", "login_success"]},
        },
        "thresholds": {
            "alert": 10.0,
            "severity": {"medium": 6.0, "high": 12.0, "critical": 20.0},
        },
        "rules": [
            {
                "id": "test_rule",
                "description": "тестовое правило",
                "weight": 1.5,
                "match": {"action": ["login_failed"]},
            }
        ],
    }


@pytest.fixture
def synthetic_ruleset() -> RuleSet:
    return RuleSet(
        rules=(
            Rule(
                id="rule_action_only",
                description="срабатывает только по action",
                weight=2.0,
                action={"login_failed"},
            ),
            Rule(
                id="rule_with_object",
                description="срабатывает по action + подстроке в object",
                weight=5.0,
                action={"command_exec"},
                object_contains_any=("/etc/shadow", ".ssh"),
            ),
            Rule(
                id="rule_match_any_action",
                description="без ограничения по action",
                weight=0.3,
                action=set(),
                object_contains_any=("/admin",),
            ),
        ),
        alert_threshold=10.0,
        severity_medium=6.0,
        severity_high=12.0,
        severity_critical=20.0,
        tz="Europe/Moscow",
        work_start="09:00",
        work_end="18:00",
        work_weekdays=(1, 2, 3, 4, 5),
        off_hours_multiplier=2.0,
        off_hours_actions=("login_failed", "login_success"),
    )


@pytest.fixture
def project_ruleset() -> RuleSet:
    project_root = Path(__file__).resolve().parent.parent
    return load_rules(str(project_root / "rules" / "rules.yaml"))


@pytest.fixture
def dt_workday_office() -> datetime:
    return datetime(2026, 4, 28, 14, 0, 0, tzinfo=MSK)


@pytest.fixture
def dt_workday_evening() -> datetime:
    return datetime(2026, 4, 28, 22, 0, 0, tzinfo=MSK)


@pytest.fixture
def dt_workday_morning_before_work() -> datetime:
    return datetime(2026, 4, 28, 7, 30, 0, tzinfo=MSK)


@pytest.fixture
def dt_saturday_noon() -> datetime:
    return datetime(2026, 5, 2, 12, 0, 0, tzinfo=MSK)


@pytest.fixture
def dt_sunday_noon() -> datetime:
    return datetime(2026, 5, 3, 12, 0, 0, tzinfo=MSK)
