from __future__ import annotations

from app.utils.formatting import format_recent_events


class TestFormatRecentEventsEmpty:
    def test_empty_list_returns_empty_string(self):
        assert format_recent_events([]) == ""

    def test_none_safe(self):
        assert format_recent_events(list()) == ""


class TestFormatRecentEventsLayout:
    def test_single_event_one_line(self):
        out = format_recent_events(
            [{"ts": "2026-04-28T10:00:00+00:00", "source": "cowrie", "action": "login_failed", "object": None}]
        )
        assert out.count("\n") == 0
        assert "cowrie" in out
        assert "login_failed" in out
        assert "2026-04-28T10:00:00+00:00" in out

    def test_multiple_events_join_with_newlines(self):
        events = [
            {"ts": "t1", "source": "cowrie", "action": "a1", "object": "o1"},
            {"ts": "t2", "source": "ftp", "action": "a2", "object": "o2"},
        ]
        out = format_recent_events(events)
        assert out.count("\n") == 1
        lines = out.split("\n")
        assert "a1" in lines[0] and "o1" in lines[0]
        assert "a2" in lines[1] and "o2" in lines[1]

    def test_each_line_is_bullet(self):
        out = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a", "object": "o"}]
        )
        assert out.startswith("•")

    def test_ts_wrapped_in_code_tag(self):
        out = format_recent_events(
            [{"ts": "T", "source": "s", "action": "a", "object": "o"}]
        )
        assert "<code>T</code>" in out


class TestFormatRecentEventsLimit:
    def test_default_limit_is_5(self):
        events = [
            {"ts": f"t{i}", "source": "s", "action": "a", "object": f"o{i}"}
            for i in range(20)
        ]
        out = format_recent_events(events)
        assert out.count("•") == 5

        for i in range(5):
            assert f"o{i}" in out
        for i in range(5, 20):
            assert f"o{i}" not in out

    def test_max_items_can_be_overridden(self):
        events = [
            {"ts": f"t{i}", "source": "s", "action": "a", "object": f"o{i}"}
            for i in range(10)
        ]
        out = format_recent_events(events, max_items=2)
        assert out.count("•") == 2

    def test_max_items_larger_than_input_is_safe(self):
        events = [{"ts": "t", "source": "s", "action": "a", "object": "o"}]
        assert format_recent_events(events, max_items=99).count("•") == 1


class TestFormatRecentEventsHtmlEscape:
    def test_lt_gt_in_object_are_escaped(self):
        out = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a", "object": "<script>alert(1)</script>"}]
        )
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_ampersand_in_action_escaped(self):
        out = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a&b", "object": "o"}]
        )
        assert "a&amp;b" in out
        assert "&amp;amp;" not in out

    def test_quotes_in_object_escaped(self):
        out = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a", "object": 'foo"bar'}]
        )
        assert "&quot;" in out


class TestFormatRecentEventsMissingFields:
    def test_missing_object_renders_empty(self):
        out = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a"}]
        )
        assert out == "• <code>t</code> s a "

    def test_none_fields_render_dash(self):
        out = format_recent_events(
            [{"ts": None, "source": None, "action": None, "object": None}]
        )
        assert out == "• <code>-</code> - - "

    def test_none_object_renders_as_empty_not_dash(self):
        out_obj_none = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a", "object": None}]
        )
        out_obj_missing = format_recent_events(
            [{"ts": "t", "source": "s", "action": "a"}]
        )
        assert out_obj_none == out_obj_missing
        assert out_obj_none == "• <code>t</code> s a "
