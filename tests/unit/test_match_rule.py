from __future__ import annotations

import pytest

from app.rules_engine import Rule, match_rule


@pytest.fixture
def rule_action_only() -> Rule:
    return Rule(
        id="r",
        description="",
        weight=1.0,
        action={"login_failed"},
    )


@pytest.fixture
def rule_with_object() -> Rule:
    return Rule(
        id="r",
        description="",
        weight=1.0,
        action={"command_exec"},
        object_contains_any=("/etc/shadow", ".ssh"),
    )


@pytest.fixture
def rule_no_action_constraint() -> Rule:
    return Rule(
        id="r",
        description="",
        weight=1.0,
        action=set(),
        object_contains_any=("/admin",),
    )


class TestActionMatching:
    def test_matching_action_returns_true(self, rule_action_only):
        assert match_rule("login_failed", None, rule_action_only) is True

    def test_non_matching_action_returns_false(self, rule_action_only):
        assert match_rule("login_success", None, rule_action_only) is False

    def test_action_match_is_case_sensitive(self, rule_action_only):
        assert match_rule("Login_Failed", None, rule_action_only) is False

    def test_empty_action_set_matches_any_action(self, rule_no_action_constraint):
        assert match_rule("login_success", "/admin/panel", rule_no_action_constraint) is True
        assert match_rule("command_exec", "/admin/panel", rule_no_action_constraint) is True


class TestObjectContainsAny:
    def test_substring_present_returns_true(self, rule_with_object):
        assert match_rule("command_exec", "cat /etc/shadow", rule_with_object) is True

    def test_alternative_substring_present_returns_true(self, rule_with_object):
        assert match_rule("command_exec", "ls -la ~/.ssh/", rule_with_object) is True

    def test_substring_absent_returns_false(self, rule_with_object):
        assert match_rule("command_exec", "ls /tmp", rule_with_object) is False

    def test_match_is_case_insensitive(self, rule_with_object):
        assert match_rule("command_exec", "CAT /ETC/SHADOW", rule_with_object) is True

    def test_pattern_case_insensitive_too(self):
        rule = Rule(
            id="r",
            description="",
            weight=1.0,
            action={"x"},
            object_contains_any=("ADMIN",),
        )
        assert match_rule("x", "go to /admin", rule) is True

    def test_none_object_does_not_match_object_rule(self, rule_with_object):
        assert match_rule("command_exec", None, rule_with_object) is False

    def test_empty_object_does_not_match_object_rule(self, rule_with_object):
        assert match_rule("command_exec", "", rule_with_object) is False


class TestCombinedConditions:
    def test_action_matches_but_object_not(self, rule_with_object):
        assert match_rule("command_exec", "ls /tmp", rule_with_object) is False

    def test_object_matches_but_action_not(self, rule_with_object):
        assert match_rule("login_failed", "cat /etc/shadow", rule_with_object) is False

    def test_both_conditions_satisfied(self, rule_with_object):
        assert match_rule("command_exec", "cat /etc/shadow", rule_with_object) is True

    def test_rule_without_any_constraints_matches_anything(self):
        rule = Rule(id="r", description="", weight=1.0, action=set())
        assert match_rule("anything", None, rule) is True
        assert match_rule("anything", "any object", rule) is True
