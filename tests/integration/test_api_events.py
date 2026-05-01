from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.integration.conftest import BAIT_FILE_PATH


class TestEventsList:
    def test_returns_empty_list_when_no_events(self, client):
        resp = client.get("/api/v1/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_ingested_events(self, client, ingest):
        ingest(action="login_success")
        ingest(action="login_failed")

        resp = client.get("/api/v1/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2

    def test_events_ordered_by_ts_desc(self, client, ingest):
        now = datetime.now(timezone.utc)
        for i, action in enumerate(["a1", "a2", "a3"]):
            ingest(action=action, ts=(now - timedelta(seconds=10 - i)).isoformat())

        resp = client.get("/api/v1/events")
        events = resp.json()
        timestamps = [e["ts"] for e in events]
        assert timestamps == sorted(timestamps, reverse=True)


class TestEventsFiltering:
    def test_filter_by_src_ip(self, client, ingest):
        ingest(src_ip="10.0.0.1")
        ingest(src_ip="10.0.0.2")

        resp = client.get("/api/v1/events", params={"src_ip": "10.0.0.1"})
        events = resp.json()
        assert len(events) == 1
        assert events[0]["src_ip"] == "10.0.0.1"

    def test_filter_by_user(self, client, ingest):
        ingest(user="alice")
        ingest(user="bob")

        resp = client.get("/api/v1/events", params={"user": "alice"})
        events = resp.json()
        assert len(events) == 1
        assert events[0]["user"] == "alice"

    def test_filter_by_action(self, client, ingest):
        ingest(action="login_success")
        ingest(action="login_failed")
        ingest(action="login_failed")

        resp = client.get("/api/v1/events", params={"action": "login_failed"})
        events = resp.json()
        assert len(events) == 2
        assert all(e["action"] == "login_failed" for e in events)

    def test_filter_combined(self, client, ingest):
        ingest(src_ip="10.0.0.1", user="alice")
        ingest(src_ip="10.0.0.1", user="bob")
        ingest(src_ip="10.0.0.2", user="alice")

        resp = client.get(
            "/api/v1/events",
            params={"src_ip": "10.0.0.1", "user": "alice"},
        )
        events = resp.json()
        assert len(events) == 1


class TestEventsPagination:
    def test_limit_caps_response_size(self, client, ingest):
        for _ in range(5):
            ingest()

        resp = client.get("/api/v1/events", params={"limit": 2})
        assert len(resp.json()) == 2

    def test_offset_skips_first_n(self, client, ingest):
        now = datetime.now(timezone.utc)
        for i in range(4):
            ingest(action=f"a{i}", ts=(now - timedelta(seconds=10 - i)).isoformat())

        all_resp = client.get("/api/v1/events").json()
        offset_resp = client.get(
            "/api/v1/events", params={"limit": 2, "offset": 2}
        ).json()

        assert offset_resp == all_resp[2:4]

    def test_negative_offset_is_clamped_to_zero(self, client, ingest):
        ingest()
        resp = client.get("/api/v1/events", params={"offset": -5})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_oversize_limit_clamped_to_500(self, client, ingest):
        ingest()
        resp = client.get("/api/v1/events", params={"limit": 99_999})
        assert resp.status_code == 200
        assert len(resp.json()) <= 500


class TestEventsResponseSchema:
    def test_response_includes_rule_eval_in_raw(self, client, ingest):
        ingest(action="file_download", object=BAIT_FILE_PATH)

        events = client.get("/api/v1/events").json()
        rule_eval = events[0]["raw"]["rule_eval"]

        assert rule_eval["delta"] == 10.0
        rule_ids = {r["rule_id"] for r in rule_eval["matched_rules"]}
        assert "bait_file_download" in rule_ids
        assert "file_download_any" in rule_ids

    def test_response_includes_trap_id(self, client, ingest):
        ingest(trap_id="sensor_a")

        events = client.get("/api/v1/events").json()
        assert events[0].get("trap_id") == "sensor_a"
