from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.ingest import is_within_cooldown, make_dedup_key


class TestMakeDedupKey:
    def test_format_is_trap_ip_severity(self):
        assert make_dedup_key("ssh-1", "10.0.0.5", "high") == "ssh-1:10.0.0.5:high"

    def test_different_severity_gives_different_keys(self):
        k_med = make_dedup_key("t", "ip", "medium")
        k_hi = make_dedup_key("t", "ip", "high")
        k_cr = make_dedup_key("t", "ip", "critical")

        assert k_med != k_hi != k_cr
        assert len({k_med, k_hi, k_cr}) == 3

    def test_different_src_ip_not_aggregated(self):
        k1 = make_dedup_key("trap", "10.0.0.1", "high")
        k2 = make_dedup_key("trap", "10.0.0.2", "high")
        assert k1 != k2

    def test_different_trap_not_aggregated(self):
        k1 = make_dedup_key("ssh", "10.0.0.5", "high")
        k2 = make_dedup_key("ftp", "10.0.0.5", "high")
        assert k1 != k2

    def test_key_is_deterministic(self):
        for _ in range(5):
            assert make_dedup_key("t", "1.2.3.4", "low") == "t:1.2.3.4:low"

    def test_key_is_string(self):
        assert isinstance(make_dedup_key("t", "ip", "low"), str)


class TestIsWithinCooldown:
    @pytest.fixture
    def now(self) -> datetime:
        return datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)

    def test_just_now_is_within_window(self, now):
        assert is_within_cooldown(now, now, minutes=10) is True

    def test_one_second_old_is_within_window(self, now):
        last = now - timedelta(seconds=1)
        assert is_within_cooldown(now, last, minutes=10) is True

    def test_inside_window_is_true(self, now):
        last = now - timedelta(minutes=5)
        assert is_within_cooldown(now, last, minutes=10) is True

    def test_at_window_boundary_is_inclusive(self, now):
        last = now - timedelta(minutes=10)
        assert is_within_cooldown(now, last, minutes=10) is True

    def test_one_second_past_window_is_false(self, now):
        last = now - timedelta(minutes=10, seconds=1)
        assert is_within_cooldown(now, last, minutes=10) is False

    def test_far_in_the_past_is_false(self, now):
        last = now - timedelta(days=7)
        assert is_within_cooldown(now, last, minutes=10) is False

    def test_future_last_updated_is_not_within(self, now):
        last = now + timedelta(seconds=1)
        assert is_within_cooldown(now, last, minutes=10) is False

    def test_zero_minutes_disables_cooldown(self, now):
        last = now - timedelta(seconds=1)
        assert is_within_cooldown(now, last, minutes=0) is False

    def test_negative_minutes_treated_as_disabled(self, now):
        last = now - timedelta(seconds=1)
        assert is_within_cooldown(now, last, minutes=-5) is False

