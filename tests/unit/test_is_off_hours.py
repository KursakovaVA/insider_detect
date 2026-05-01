from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.rules_engine import is_off_hours


MSK = ZoneInfo("Europe/Moscow")


class TestRegularSchedule:
    def test_business_hours_is_in_office(self, synthetic_ruleset, dt_workday_office):
        assert is_off_hours(dt_workday_office, synthetic_ruleset) is False

    def test_evening_is_off_hours(self, synthetic_ruleset, dt_workday_evening):
        assert is_off_hours(dt_workday_evening, synthetic_ruleset) is True

    def test_morning_before_work_is_off_hours(
        self, synthetic_ruleset, dt_workday_morning_before_work
    ):
        assert is_off_hours(dt_workday_morning_before_work, synthetic_ruleset) is True

    def test_saturday_is_off_hours(self, synthetic_ruleset, dt_saturday_noon):
        assert is_off_hours(dt_saturday_noon, synthetic_ruleset) is True

    def test_sunday_is_off_hours(self, synthetic_ruleset, dt_sunday_noon):
        assert is_off_hours(dt_sunday_noon, synthetic_ruleset) is True


class TestBoundaryTimes:
    def test_work_start_boundary_is_in_office(self, synthetic_ruleset):
        ts = datetime(2026, 4, 28, 9, 0, 0, tzinfo=MSK)
        assert is_off_hours(ts, synthetic_ruleset) is False

    def test_one_second_before_work_start_is_off(self, synthetic_ruleset):
        ts = datetime(2026, 4, 28, 8, 59, 59, tzinfo=MSK)
        assert is_off_hours(ts, synthetic_ruleset) is True

    def test_work_end_boundary_is_off_hours(self, synthetic_ruleset):
        ts = datetime(2026, 4, 28, 18, 0, 0, tzinfo=MSK)
        assert is_off_hours(ts, synthetic_ruleset) is True

    def test_one_second_before_work_end_is_in_office(self, synthetic_ruleset):
        ts = datetime(2026, 4, 28, 17, 59, 59, tzinfo=MSK)
        assert is_off_hours(ts, synthetic_ruleset) is False


class TestTimezoneHandling:
    def test_naive_datetime_is_treated_as_utc(self, synthetic_ruleset):
        ts_naive = datetime(2026, 4, 28, 14, 0, 0)
        assert is_off_hours(ts_naive, synthetic_ruleset) is False

    def test_naive_datetime_late_utc_becomes_off_hours_in_msk(self, synthetic_ruleset):
        ts_naive = datetime(2026, 4, 28, 16, 0, 0)
        assert is_off_hours(ts_naive, synthetic_ruleset) is True

    def test_aware_utc_datetime_converted_to_local(self, synthetic_ruleset):
        ts = datetime(2026, 4, 28, 5, 0, 0, tzinfo=timezone.utc)
        assert is_off_hours(ts, synthetic_ruleset) is True


class TestNonStandardSchedule:
    def test_overnight_shift_includes_midnight(self, synthetic_ruleset):
        rs_night = replace(synthetic_ruleset, work_start="22:00", work_end="06:00")

        ts_night = datetime(2026, 4, 28, 23, 0, 0, tzinfo=MSK)
        ts_early = datetime(2026, 4, 29, 3, 0, 0, tzinfo=MSK)
        ts_day = datetime(2026, 4, 28, 12, 0, 0, tzinfo=MSK)

        assert is_off_hours(ts_night, rs_night) is False
        assert is_off_hours(ts_early, rs_night) is False
        assert is_off_hours(ts_day, rs_night) is True

    def test_custom_weekdays_only(self, synthetic_ruleset):
        rs_mwf = replace(synthetic_ruleset, work_weekdays=(1, 3, 5))
        tuesday_noon = datetime(2026, 4, 28, 12, 0, 0, tzinfo=MSK)

        assert is_off_hours(tuesday_noon, rs_mwf) is True
