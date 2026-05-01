from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.rules_engine import RuleSet
from app.services.rules import reload_rules_service


@pytest.fixture
def fake_app():
    return SimpleNamespace(state=SimpleNamespace())


class TestReloadRulesService:
    def test_loads_rules_from_explicit_path(
        self, fake_app, write_rules_yaml, minimal_yaml_data
    ):
        path = write_rules_yaml(minimal_yaml_data)

        out = reload_rules_service(fake_app, str(path))

        assert isinstance(fake_app.state.ruleset, RuleSet)
        assert out["status"] == "ok"
        assert out["rules"] == 1
        assert out["alert_threshold"] == pytest.approx(10.0)

    def test_explicit_path_takes_priority_over_settings(
        self,
        fake_app,
        write_rules_yaml,
        minimal_yaml_data,
        monkeypatch,
    ):
        from app.services import rules as rules_module

        wrong_path = write_rules_yaml(
            {"rules": [{"id": "wrong", "weight": 1.0}]},
            filename="wrong.yaml",
        )
        monkeypatch.setattr(
            rules_module.settings, "RULES_PATH", str(wrong_path)
        )

        right_path = write_rules_yaml(minimal_yaml_data, filename="right.yaml")
        out = reload_rules_service(fake_app, str(right_path))

        assert out["rules"] == 1
        assert fake_app.state.ruleset.rules[0].id == "test_rule"

    def test_fallback_to_settings_path_when_arg_is_none(
        self,
        fake_app,
        write_rules_yaml,
        minimal_yaml_data,
        monkeypatch,
    ):
        from app.services import rules as rules_module

        path = write_rules_yaml(minimal_yaml_data)
        monkeypatch.setattr(rules_module.settings, "RULES_PATH", str(path))

        out = reload_rules_service(fake_app, None)

        assert out["status"] == "ok"
        assert fake_app.state.ruleset.rules[0].id == "test_rule"

    def test_returns_actual_rule_count_for_multi_rule_yaml(
        self, fake_app, write_rules_yaml
    ):
        path = write_rules_yaml(
            {
                "thresholds": {"alert": 7.5},
                "rules": [
                    {"id": "r1", "weight": 1.0, "match": {"action": ["a"]}},
                    {"id": "r2", "weight": 2.0, "match": {"action": ["b"]}},
                    {"id": "r3", "weight": 3.0, "match": {"action": ["c"]}},
                ],
            }
        )

        out = reload_rules_service(fake_app, str(path))

        assert out["rules"] == 3
        assert out["alert_threshold"] == pytest.approx(7.5)
        assert len(fake_app.state.ruleset.rules) == 3

    def test_overwrites_existing_ruleset(
        self, fake_app, write_rules_yaml, minimal_yaml_data
    ):
        fake_app.state.ruleset = "stale"
        path = write_rules_yaml(minimal_yaml_data)

        reload_rules_service(fake_app, str(path))

        assert isinstance(fake_app.state.ruleset, RuleSet)
        assert fake_app.state.ruleset != "stale"
