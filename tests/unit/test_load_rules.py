from __future__ import annotations

import pytest

from app.rules_engine import RuleSet, load_rules


class TestLoadRulesParsing:
    def test_returns_ruleset_instance(self, write_rules_yaml, minimal_yaml_data):
        path = write_rules_yaml(minimal_yaml_data)
        rs = load_rules(str(path))

        assert isinstance(rs, RuleSet)

    def test_parses_thresholds(self, write_rules_yaml, minimal_yaml_data):
        path = write_rules_yaml(minimal_yaml_data)
        rs = load_rules(str(path))

        assert rs.alert_threshold == pytest.approx(10.0)
        assert rs.severity_medium == pytest.approx(6.0)
        assert rs.severity_high == pytest.approx(12.0)
        assert rs.severity_critical == pytest.approx(20.0)

    def test_parses_context(self, write_rules_yaml, minimal_yaml_data):
        path = write_rules_yaml(minimal_yaml_data)
        rs = load_rules(str(path))

        assert rs.tz == "Europe/Moscow"
        assert rs.work_start == "09:00"
        assert rs.work_end == "18:00"
        assert rs.work_weekdays == (1, 2, 3, 4, 5)
        assert rs.off_hours_multiplier == pytest.approx(2.0)
        assert rs.off_hours_actions == ("login_failed", "login_success")

    def test_parses_single_rule(self, write_rules_yaml, minimal_yaml_data):
        path = write_rules_yaml(minimal_yaml_data)
        rs = load_rules(str(path))

        assert len(rs.rules) == 1
        rule = rs.rules[0]
        assert rule.id == "test_rule"
        assert rule.description == "тестовое правило"
        assert rule.weight == pytest.approx(1.5)
        assert rule.action == {"login_failed"}
        assert rule.object_contains_any == ()

    def test_parses_multiple_rules_preserving_order(self, write_rules_yaml):
        data = {
            "rules": [
                {"id": "r1", "weight": 1.0, "match": {"action": ["a1"]}},
                {"id": "r2", "weight": 2.0, "match": {"action": ["a2"]}},
                {"id": "r3", "weight": 3.0, "match": {"action": ["a3"]}},
            ]
        }
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert tuple(r.id for r in rs.rules) == ("r1", "r2", "r3")

    def test_parses_object_contains_any_as_tuple(self, write_rules_yaml):
        data = {
            "rules": [
                {
                    "id": "r",
                    "weight": 1.0,
                    "match": {"action": ["x"], "object_contains_any": ["a", "b", "c"]},
                }
            ]
        }
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.rules[0].object_contains_any == ("a", "b", "c")

    def test_action_is_loaded_as_set(self, write_rules_yaml):
        data = {
            "rules": [
                {"id": "r", "weight": 1.0, "match": {"action": ["x", "y", "x"]}}
            ]
        }
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.rules[0].action == {"x", "y"}


class TestLoadRulesDefaults:
    def test_empty_yaml_returns_defaults(self, write_rules_yaml):
        path = write_rules_yaml({})
        rs = load_rules(str(path))

        assert rs.tz == "Europe/Moscow"
        assert rs.work_start == "09:00"
        assert rs.work_end == "19:00"
        assert rs.work_weekdays == (1, 2, 3, 4, 5)
        assert rs.off_hours_multiplier == pytest.approx(1.0)
        assert rs.off_hours_actions == ("login_failed", "login_success")
        assert rs.alert_threshold == pytest.approx(10.0)
        assert rs.severity_medium == pytest.approx(6.0)
        assert rs.severity_high == pytest.approx(12.0)
        assert rs.severity_critical == pytest.approx(20.0)
        assert rs.rules == ()

    def test_missing_thresholds_uses_defaults(self, write_rules_yaml):
        path = write_rules_yaml({"rules": []})
        rs = load_rules(str(path))

        assert rs.alert_threshold == pytest.approx(10.0)

    def test_partial_severity_uses_defaults(self, write_rules_yaml):
        path = write_rules_yaml({"thresholds": {"severity": {"medium": 4.0}}})
        rs = load_rules(str(path))

        assert rs.severity_medium == pytest.approx(4.0)
        assert rs.severity_high == pytest.approx(12.0)
        assert rs.severity_critical == pytest.approx(20.0)

    def test_off_hours_multiplier_one_when_missing(self, write_rules_yaml):
        path = write_rules_yaml({"context": {}})
        rs = load_rules(str(path))

        assert rs.off_hours_multiplier == pytest.approx(1.0)


class TestLoadRulesEdgeCases:
    def test_rule_without_match_section(self, write_rules_yaml):
        data = {"rules": [{"id": "no_match", "weight": 1.0}]}
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.rules[0].action == set()
        assert rs.rules[0].object_contains_any == ()

    def test_rule_without_description(self, write_rules_yaml):
        data = {"rules": [{"id": "r", "weight": 1.0, "match": {"action": ["x"]}}]}
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.rules[0].description == ""

    def test_rule_without_weight_defaults_to_zero(self, write_rules_yaml):
        data = {"rules": [{"id": "zero", "match": {"action": ["x"]}}]}
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.rules[0].weight == pytest.approx(0.0)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_rules(str(tmp_path / "does_not_exist.yaml"))

    def test_weekdays_preserved_as_given(self, write_rules_yaml):
        data = {
            "context": {
                "work_hours": {"start": "10:00", "end": "20:00", "weekdays": [1, 3, 5]}
            }
        }
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.work_weekdays == (1, 3, 5)


class TestLoadRulesNegativeCases:
    def test_broken_yaml_raises_yaml_error(self, tmp_path):
        from yaml import YAMLError

        path = tmp_path / "broken.yaml"
        path.write_text(
            "rules:\n  - id: r1\n  weight: 1.0\n   bad indent\n",
            encoding="utf-8",
        )

        with pytest.raises(YAMLError):
            load_rules(str(path))

    def test_rule_without_id_raises_key_error(self, write_rules_yaml):
        data = {"rules": [{"weight": 1.0, "match": {"action": ["x"]}}]}
        path = write_rules_yaml(data)

        with pytest.raises(KeyError):
            load_rules(str(path))

    def test_non_numeric_weight_raises_value_error(self, write_rules_yaml):
        data = {"rules": [{"id": "r", "weight": "не-число", "match": {"action": ["x"]}}]}
        path = write_rules_yaml(data)

        with pytest.raises(ValueError):
            load_rules(str(path))

    def test_numeric_string_weight_is_coerced(self, write_rules_yaml):
        data = {"rules": [{"id": "r", "weight": "1.5", "match": {"action": ["x"]}}]}
        path = write_rules_yaml(data)
        rs = load_rules(str(path))

        assert rs.rules[0].weight == pytest.approx(1.5)

    def test_rules_null_treated_as_empty_list(self, tmp_path):
        path = tmp_path / "null_rules.yaml"
        path.write_text("rules:\n", encoding="utf-8")

        rs = load_rules(str(path))
        assert rs.rules == ()

    def test_empty_yaml_file_treated_as_defaults(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")

        rs = load_rules(str(path))
        assert rs.rules == ()
        assert rs.alert_threshold == pytest.approx(10.0)
