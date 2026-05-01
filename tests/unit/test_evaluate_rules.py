from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.rules_engine import Rule, RuleSet, evaluate_rules


MSK = ZoneInfo("Europe/Moscow")

class TestNoMatch:
    def test_no_match_returns_default_weight(self, synthetic_ruleset):
        delta, hits = evaluate_rules("unknown_action", None, synthetic_ruleset)

        assert delta == pytest.approx(0.5)

    def test_no_match_hits_contain_default_marker(self, synthetic_ruleset):
        _, hits = evaluate_rules("unknown_action", None, synthetic_ruleset)

        assert len(hits) == 1
        assert hits[0]["rule_id"] == "default"
        assert hits[0]["weight"] == pytest.approx(0.5)


class TestSingleMatch:
    def test_action_only_rule_match(self, synthetic_ruleset):
        delta, hits = evaluate_rules("login_failed", None, synthetic_ruleset)

        assert delta == pytest.approx(2.0)
        assert [h["rule_id"] for h in hits] == ["rule_action_only"]

    def test_action_with_object_rule_match(self, synthetic_ruleset):
        delta, hits = evaluate_rules("command_exec", "cat /etc/shadow", synthetic_ruleset)

        assert delta == pytest.approx(5.0)
        assert [h["rule_id"] for h in hits] == ["rule_with_object"]

    def test_no_action_constraint_rule_match(self, synthetic_ruleset):
        delta, hits = evaluate_rules("any_action", "/admin/login", synthetic_ruleset)

        assert delta == pytest.approx(0.3)
        assert [h["rule_id"] for h in hits] == ["rule_match_any_action"]


class TestMultipleMatches:
    def test_object_substring_in_two_patterns(self, synthetic_ruleset):
        delta, hits = evaluate_rules(
            "command_exec", "cat ~/.ssh/authorized_keys && open /admin", synthetic_ruleset
        )

        assert delta == pytest.approx(5.0 + 0.3)
        assert {h["rule_id"] for h in hits} == {"rule_with_object", "rule_match_any_action"}


class TestHitsStructure:
    def test_hits_contain_rule_metadata(self, synthetic_ruleset):
        _, hits = evaluate_rules("login_failed", None, synthetic_ruleset)

        hit = hits[0]
        assert set(hit.keys()) >= {"rule_id", "weight", "description"}
        assert hit["rule_id"] == "rule_action_only"
        assert hit["weight"] == pytest.approx(2.0)
        assert hit["description"] == "срабатывает только по action"


class TestOffHoursMultiplier:
    def test_off_hours_multiplier_applied_for_relevant_action(
        self, synthetic_ruleset, dt_workday_evening
    ):
        delta, hits = evaluate_rules(
            "login_failed", None, synthetic_ruleset, ts=dt_workday_evening
        )

        assert delta == pytest.approx(2.0 * 2.0)
        assert any(h["rule_id"] == "off_hours" for h in hits)

    def test_off_hours_multiplier_not_applied_during_work_hours(
        self, synthetic_ruleset, dt_workday_office
    ):
        delta, hits = evaluate_rules(
            "login_failed", None, synthetic_ruleset, ts=dt_workday_office
        )

        assert delta == pytest.approx(2.0)
        assert all(h["rule_id"] != "off_hours" for h in hits)

    def test_off_hours_multiplier_not_applied_for_irrelevant_action(
        self, synthetic_ruleset, dt_workday_evening
    ):
        delta, hits = evaluate_rules(
            "command_exec", "cat /etc/shadow", synthetic_ruleset, ts=dt_workday_evening,
        )

        assert delta == pytest.approx(5.0)
        assert all(h["rule_id"] != "off_hours" for h in hits)

    def test_no_ts_means_no_multiplier(self, synthetic_ruleset):
        delta, hits = evaluate_rules("login_failed", None, synthetic_ruleset, ts=None)

        assert delta == pytest.approx(2.0)
        assert all(h["rule_id"] != "off_hours" for h in hits)

    def test_off_hours_applied_on_weekend(self, synthetic_ruleset, dt_saturday_noon):
        delta, _ = evaluate_rules(
            "login_failed", None, synthetic_ruleset, ts=dt_saturday_noon
        )

        assert delta == pytest.approx(2.0 * 2.0)

    def test_off_hours_multiplier_one_means_no_change(self, synthetic_ruleset, dt_workday_evening):
        rs_no_mult = replace(synthetic_ruleset, off_hours_multiplier=1.0)
        delta, hits = evaluate_rules(
            "login_failed", None, rs_no_mult, ts=dt_workday_evening,
        )

        assert delta == pytest.approx(2.0)
        assert all(h["rule_id"] != "off_hours" for h in hits)

    def test_off_hours_hit_weight_equals_delta_increment(
        self, synthetic_ruleset, dt_workday_evening
    ):
        delta, hits = evaluate_rules(
            "login_failed", None, synthetic_ruleset, ts=dt_workday_evening
        )

        off_hit = next(h for h in hits if h["rule_id"] == "off_hours")
        assert off_hit["weight"] == pytest.approx(delta - 2.0)


class TestZeroWeightAndDefault:
    @pytest.fixture
    def ruleset_with_zero_weight_rule(self, synthetic_ruleset) -> RuleSet:
        return replace(
            synthetic_ruleset,
            rules=(
                Rule(
                    id="zero_weight_marker",
                    description="ярлык без вклада в risk",
                    weight=0.0,
                    action={"login_success"},
                ),
            ),
            off_hours_multiplier=1.0,
        )

    def test_zero_weight_rule_match_still_triggers_default(
        self, ruleset_with_zero_weight_rule
    ):
        delta, hits = evaluate_rules(
            "login_success", None, ruleset_with_zero_weight_rule
        )

        assert delta == pytest.approx(0.5)
        rule_ids = {h["rule_id"] for h in hits}
        assert rule_ids == {"zero_weight_marker", "default"}

    def test_zero_weight_rule_with_no_match_only_default(
        self, ruleset_with_zero_weight_rule
    ):
        delta, hits = evaluate_rules(
            "login_failed", None, ruleset_with_zero_weight_rule
        )
        assert delta == pytest.approx(0.5)
        assert {h["rule_id"] for h in hits} == {"default"}
