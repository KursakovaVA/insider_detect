from __future__ import annotations

from dataclasses import replace

import pytest

from app.rules_engine import severity_from_risk


@pytest.mark.parametrize(
    "risk, expected",
    [
        (0.0, "low"),
        (5.99, "low"),
        (6.0, "medium"),
        (6.0001, "medium"),
        (11.99, "medium"),
        (12.0, "high"),
        (12.0001, "high"),
        (19.99, "high"),
        (20.0, "critical"),
        (20.0001, "critical"),
        (1000.0, "critical"),
    ],
)
def test_severity_thresholds(synthetic_ruleset, risk, expected):
    assert severity_from_risk(risk, synthetic_ruleset) == expected


def test_severity_uses_ruleset_thresholds(synthetic_ruleset):
    custom = replace(
        synthetic_ruleset,
        severity_medium=1.0,
        severity_high=2.0,
        severity_critical=3.0,
    )

    assert severity_from_risk(0.5, custom) == "low"
    assert severity_from_risk(1.0, custom) == "medium"
    assert severity_from_risk(2.0, custom) == "high"
    assert severity_from_risk(3.0, custom) == "critical"
